#!/bin/sh
# ============================================================
# pack.sh —— 从仓库打部署包
#
# 用法（仓库根目录）：
#   sh scripts/pack.sh                 # 用 CHANGELOG 里的当前版本号
#   sh scripts/pack.sh 4.6.0-11        # 指定版本号
#   sh scripts/pack.sh --check xxx.tar.gz   # 只验一个已有包，不打包
#
# 产物：/workspace/audiobook-deploy-<版本>.tar.gz（或在当前目录）
#
# ------------------------------------------------------------
# 为什么不能简单地 tar -czf 一下
#
# 1. 不能用 --transform 改顶层目录名。
#    tar 的 --transform 会连带作用于**符号链接的目标内容**：
#      s,^\.,audiobook,  会把链接里的 "../../../../node_modules/x"
#      改写成 "audiobook./../../../node_modules/x"，127 个链接全废。
#    正确做法是 cd 到父目录、对目录名打包（见下）。
#
# 2. myreader-dist 必须完整。它 2732 条、92M、127 个符号链接，
#    链接目标指向它自己的 node_modules/.pnpm（相对路径）。
#    少一条 .pnpm 里的文件，链接就全断，阅读器启动即 502。
#    打包后必须实际数一遍有效链接（本脚本第 4 步）。
#
# 3. app/node_modules 要带上。Dockerfile 里 `COPY app/ /build/` 依赖它，
#    且 NAS 上 npm ci 极易因网络抖动失败。
# ============================================================
set -eu

SELF_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$SELF_DIR/.." && pwd)
cd "$ROOT"

# ---------- 只验包模式 ----------
if [ "${1:-}" = "--check" ]; then
    PKG="${2:-}"
    [ -n "$PKG" ] && [ -f "$PKG" ] || { echo "用法: sh scripts/pack.sh --check <包路径>"; exit 2; }
    verify() {
        T=$(mktemp -d)
        trap 'rm -rf "$T"' EXIT
        tar -xzf "$PKG" -C "$T" || { echo "!! 解压失败"; exit 1; }
        D="$T/audiobook"
        [ -d "$D" ] || D="$T"      # 允许把已解开的目录打包后再验
        [ -d "$D" ] || { echo "!! 包内没有 audiobook/ 或包根不是目录"; exit 1; }

        fail=0
        # 该有的东西：少一样就起不来或没法升级
        for f in Dockerfile docker-compose.yml myreader-dist/app/server.js \
                 conf/supervisor/mybooks.conf conf/nginx/mybooks.conf \
                 scripts/upgrade.sh scripts/deploy.sh scripts/check-reader.sh \
                 scripts/pack.sh scripts/hotfix.sh tools/category_backfill.py; do
            [ -e "$D/$f" ] || { echo "  !! 缺 $f"; fail=1; }
        done

        # 不该有的东西：归档、开发侧杂物
        # 注意：app/node_modules 是要的 —— Dockerfile 里 COPY app/ /build/ 靠它走「已有产物」快路，
        # 少了它镜像里没有 next，阅读器起不来。别当成杂物排掉。
        for junk in scripts/archive docs/archive docs/settings-redesign audiobook-src .git skills .claude tests; do
            [ -e "$D/$junk" ] && { echo "  !! 部署包里混入不该下发的内容: $junk"; fail=1; }
        done

        # __pycache__ / .pytest_cache：允许零星几个（比如解压后又跑过脚本），但不该整片带进来
        npc=$(find "$D" -name '__pycache__' -type d 2>/dev/null | wc -l)
        if [ "$npc" -gt 5 ]; then
            echo "  !! 包里有 $npc 个 __pycache__ 目录（应为 0）—— 打包时漏了清理"
            fail=1
        fi
        pc=$(find "$D" -name '.pytest_cache' -type d 2>/dev/null | wc -l)
        if [ "$pc" -gt 0 ]; then
            echo "  !! 包里有 $pc 个 .pytest_cache 目录（应为 0）"
            find "$D" -name '.pytest_cache' -type d 2>/dev/null | head -5 | sed 's/^/     /'
            fail=1
        fi

        # myreader-dist 必须完整：符号链接是相对路径，打包方式一变就全断
        valid=0; broken=0
        for l in $(find "$D/myreader-dist" -type l 2>/dev/null); do
            if [ -e "$l" ]; then valid=$((valid + 1)); else broken=$((broken + 1)); fi
        done
        n=$(find "$D/myreader-dist" \( -type f -o -type l \) 2>/dev/null | wc -l)
        echo "  myreader-dist: $n 条, 有效链接 $valid, 断链 $broken"

        if [ "$valid" -lt 100 ]; then
            echo "  !! 有效链接只有 $valid 个（应 ≥100）—— 多半被 --transform 改坏了，或解压压扁了"
            fail=1
        fi
        # §断链必须为 0§ 4.6.0-16 起拒收任何断链。
        # 以前容忍 8 条「历史残留」（sharp / turso-database / styled-jsx 的悬空 pnpm 链接），
        # 那些目标目录早在构建时就不存在了，留着只会让"到底有没有坏"永远说不清。
        # 现在一条都不许有：多出来就说明包被改坏了（--transform、解压压扁、符号链接丢失）。
        if [ "$broken" -gt 0 ]; then
            echo "  !! 断链 $broken 个（必须为 0）—— 检查打包方式，或清掉 myreader-dist 里的悬空链接"
            find "$D/myreader-dist" -type l ! -exec test -e {} \; -print 2>/dev/null | head -10 | sed 's/^/     /'
            fail=1
        fi

        # 数据目录：空的允许（可能是空壳），有文件就是误打包
        for d in books book data audios library upload imports sync cache logs; do
            [ -e "$D/$d" ] || continue
            if [ -z "$(find "$D/$d" -type f 2>/dev/null | head -1)" ]; then
                echo "  - $d/ 是空目录"
            else
                echo "  !! 混入带数据的目录 $d（$(du -sh "$D/$d" | cut -f1)）"; fail=1
            fi
        done

        # 脚本与文档清单：包里只剩长期脚本，不能出现 8 个散脚本那套
        # 注意 *.py 也要列 —— watch-upstream.py 是日常运维要用的，别漏看
        echo "  脚本: $(cd "$D/scripts" 2>/dev/null && ls *.sh *.py 2>/dev/null | tr '\n' ' ')"
        echo "  文档: $(cd "$D/docs" 2>/dev/null && ls *.md 2>/dev/null | tr '\n' ' ')"

        # 盯上游的工具必须能在部署机上跑（只用标准库，不需要装依赖）
        [ -e "$D/scripts/watch-upstream.py" ] || {
            echo "  !! 缺 scripts/watch-upstream.py（盯上游的工具不完整）"; fail=1; }

        # 基线文件是**运行状态**（记录上次盯到哪个提交），首次 `--baseline` 时
        # 自动生成。不能当打包硬性要求 —— 否则清一次状态文件就出不了包。
        if [ -e "$D/docs/upstream-baseline.json" ]; then
            echo "  基线: docs/upstream-baseline.json（$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('date','?'))" "$D/docs/upstream-baseline.json" 2>/dev/null || echo '?')）"
        else
            echo "  基线: 无（首次跑 watch-upstream.py --baseline 时自动生成，不影响使用）"
        fi

        # srt-tool 只该留运行必需的 4 个文件 —— 打包脚本漏排会立刻在这里暴露
        # 注意：不能用 `var=$(...)` 收集，set -e 下 ls 找不到文件会让整个脚本静默退出
        st_junk=""
        for f in build.bat build.py make_srt.spec; do
            if [ -e "$D/srt-tool/$f" ]; then st_junk="$st_junk $f"; fi
        done
        if [ -d "$D/srt-tool/tests" ]; then st_junk="$st_junk tests"; fi
        if [ -n "$st_junk" ]; then
            echo "  !! srt-tool 混入开发侧文件:$st_junk"
            echo "     （包内只该留 README.md / make_srt.py / srt_core.py / make_srt_gui.py）"
            fail=1
        fi

        # tools/ 同理只该留运维脚本 —— 抓取/开发工具混进来说明裁剪没生效
        tk_junk=""
        for f in $(ls "$D/tools" 2>/dev/null); do
            case " category_backfill.py fix_broken_fonts.py migrate_from_upstream.sh upgrade-from-upstream-manual.sh hotfix-from-src.sh " in
                *" $f "*) ;;
                *) tk_junk="$tk_junk $f" ;;
            esac
        done
        if [ -n "$tk_junk" ]; then
            echo "  !! tools/ 混入部署机用不到的开发工具:$tk_junk"
            echo "     （包内只该留 5 个运维脚本，见 docs/部署包说明.md）"
            fail=1
        fi

        # 版本锁：运行期版本 4.6.0-20 不得被回退（写回 4.8.x）、写成裸 4.6.0、
        # 或被交付标签/构建参数覆盖（防反弹保护；失败信息由脚本自己打印，说明补救方法）
        if [ -f "$D/scripts/check-version-lock.py" ]; then
            if command -v python3 >/dev/null 2>&1; then
                python3 "$D/scripts/check-version-lock.py" --root "$D" || fail=1
            else
                echo "  !! 没有 python3，跳过版本锁检查（请在构建机或服务器上补跑）"
            fi
        else
            echo "  !! 缺 scripts/check-version-lock.py（版本锁检查不完整）"; fail=1
        fi

        [ "$fail" = "0" ] && echo "  ✅ 校验通过" || { echo "  ❌ 校验失败"; exit 1; }
    }

    echo "==> 校验 $PKG"
    verify
    exit 0
fi

# ---------- 确定版本号 ----------
VER="${1:-}"
if [ -z "$VER" ]; then
    VER=$(grep -m1 -oE '^## [0-9]+\.[0-9]+\.[0-9]+-[0-9]+' CHANGELOG.md | sed 's/^## //')
    [ -n "$VER" ] || { echo "!! 无法从 CHANGELOG.md 取版本号，请手动指定"; exit 2; }
    echo "==> 版本号（取自 CHANGELOG）: $VER"
else
    echo "==> 版本号（手动指定）: $VER"
fi

# 可复现基准时间：取最后一个提交的作者时间，而不是「现在」。
# 这样同一份源码不管哪天重出，包内时间戳和 md5 都一样；
# 源码一变，基准时间跟着走，md5 自然变。
REPRO_MTIME=$(git log -1 --format=%ct 2>/dev/null)
[ -n "$REPRO_MTIME" ] || REPRO_MTIME=1700000000   # 不在 git 仓库里时的兜底

NAME="audiobook-deploy-$VER"
OUTDIR="${OUTDIR:-/workspace}"
OUT="$OUTDIR/$NAME.tar.gz"

# ---------- 打包前自检 ----------
echo "==> [1/4] 源码目录自检"
# 数据目录必须不存在。注意：sync/ cache/ logs/ 可能只是空壳残留
# （开发时跑过服务留下的），只要没有实际数据就不算污染——打包时会被排除。
for d in books book data audios library upload imports sync cache logs; do
    [ -e "$d" ] || continue
    if [ -z "$(find "$d" -type f 2>/dev/null | head -1)" ]; then
        echo "  - $d/ 是空目录，打包时排除（无实际数据）"
    else
        echo "  !! 仓库里出现带数据的目录 $d（$(du -sh "$d" | cut -f1)），先清掉再打包"; exit 1
    fi
done
echo "  OK：无数据污染"

echo "==> [2/4] MyReader 产物自检"
[ -d myreader-dist/node_modules ] || { echo "  !! 缺 myreader-dist/node_modules（产物不完整，见 .gitignore 例外区）"; exit 1; }
mr_total=$(find myreader-dist \( -type f -o -type l \) | wc -l)
mr_valid=0
for l in $(find myreader-dist -type l); do [ -e "$l" ] && mr_valid=$((mr_valid + 1)); done
echo "  $mr_total 条，有效链接 $mr_valid"
[ "$mr_valid" -ge 100 ] || { echo "  !! 有效链接只有 $mr_valid（应 ≥100），产物坏了"; exit 1; }

# ---------- 打包 ----------
echo "==> [3/4] 打包（cd 到父目录对目录名打包，不用 --transform）"

# 同一份源码要能出同一个 md5，否则「包没传坏吧」这个问题永远说不清。
# 变数有两个，都钉死：
#   1. gzip 会把压缩时间戳写进文件头 → -n 去掉
#   2. tar 按文件名排序时，同一批命令产生的 mtime 精度不同 → --mtime + --sort=name
# gzip -n 而不是 export GZIP：新版 gzip 会对该变量告警，且它不是给 tar 用的接口
TAR_OPTS="--sort=name --mtime=@$REPRO_MTIME --owner=0 --group=0 --numeric-owner"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
# 用硬链接镜像出一份叫 audiobook 的树，避免复制 92M 产物
mkdir -p "$STAGE/audiobook"
for item in $(ls -A); do
    case "$item" in
        # 版本库与开发侧杂物
        .git|.claude|node_modules|cache|sync|books|data|__pycache__|logs) continue ;;
        # skills/ 是给 AI 客户端（clawdbot / openclaw）加载的 skill 包，走 HTTP API
        # 操作书库，不是服务端依赖。NAS 上用不到，要用的在 PC 上装。
        skills) continue ;;
        # pytest 缓存在仓库根也会生成（在 srt-tool/ 里跑测试时 rootdir 会往上找到仓库根）
        .pytest_cache) continue ;;
        # 误提交的嵌套仓库条目（历史上 clone 自己的残留），空目录，无内容
        audiobook-src) continue ;;
    esac
    cp -al "$item" "$STAGE/audiobook/$item" 2>/dev/null || cp -a "$item" "$STAGE/audiobook/$item"
done

# 归档目录不进部署包：它们是历史记录（v9 那趟的一次性脚本、旧版操作手册、
# 设计稿截图），NAS 上用不到，只会让包变大、让人分不清哪个脚本该跑。
# 仓库里保留，随时可查。
# tests/ 同理：根 tests/ 是 pytest 夹具（calibre 库结构 + epub 样本，5.6M / 263 条），
# 只有本地跑测试才有用。webserver/epub_to_audio/tests/ 是子目录，不受影响。
for junk in scripts/archive docs/archive docs/settings-redesign tests; do
    [ -e "$STAGE/audiobook/$junk" ] && rm -rf "$STAGE/audiobook/$junk"
done

# srt-tool 是 PC 上的辅助工具，NAS 上既跑不了也不该跑。包内只留能直接运行的
# 4 个文件（README / make_srt.py / srt_core.py / make_srt_gui.py）：
#   - build.bat / build.py / make_srt.spec：在 Windows 上建 venv + PyInstaller 打 exe 用
#   - tests/：pytest 用例，部署环境没有 pytest
# 要完整的去 gitee 仓库或 srt-tool-v1.2.0.zip 取。
for f in build.bat build.py make_srt.spec; do
    rm -f "$STAGE/audiobook/srt-tool/$f"
done
rm -rf "$STAGE/audiobook/srt-tool/tests"

# tools/ 是上游带的一整套书源抓取与开发工具（豆瓣/kgbook 爬虫、OPDS、DjVu 元数据、
# EPUB 解析、网盘下载、推荐引擎合成基准…），NAS 上既不跑也用不到，spider 还会往外发请求。
# 只留部署机上真会执行的 5 个：
#   category_backfill.py           读者组 #category 分类回填（deploy.sh 校验 + 部署后手动跑）
#   fix_broken_fonts.py            坏字体批量清扫（webserver/services/epub_font_fix.py 指向它）
#   migrate_from_upstream.sh       上游三方合并迁移
#   upgrade-from-upstream-manual.sh / hotfix-from-src.sh   手动升级与源码侧热更
# 要完整的去 gitee 仓库取，仓库里一个没删。
KEEP_TOOLS=" category_backfill.py fix_broken_fonts.py migrate_from_upstream.sh upgrade-from-upstream-manual.sh hotfix-from-src.sh "
for f in "$STAGE/audiobook/tools"/* "$STAGE/audiobook/tools"/.[!.]*; do
    [ -e "$f" ] || continue
    case "$KEEP_TOOLS" in
        *" $(basename "$f") "*) continue ;;
    esac
    rm -rf "$f"
done
echo "  tools/ 只留运维脚本: $(ls "$STAGE/audiobook/tools" | tr '\n' ' ')"

# __pycache__ 同理：开发时跑过脚本就会留下，5MB 左右，NAS 上纯占地方。
# 镜像构建本来就从 .dockerignore 排掉它，部署包里更不该有。
# 注意 .gitignore 里也有 __pycache__/，所以这些文件不在版本库里，
# 清掉不影响任何东西（下次跑脚本会自己重建）。
find "$STAGE/audiobook" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null
# .pytest_cache 会在任意跑过 pytest 的目录里冒出来（仓库根、srt-tool/、webserver/epub_to_audio/），
# 只排顶层不够，必须全局扫
find "$STAGE/audiobook" -name '.pytest_cache' -type d -prune -exec rm -rf {} + 2>/dev/null
find "$STAGE/audiobook" \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null
echo "  已清掉 __pycache__ / .pytest_cache / *.pyc（开发残留）"

mkdir -p "$OUTDIR"
( cd "$STAGE" && tar $TAR_OPTS -cf - audiobook | gzip -n > "$OUT" )
echo "  产物: $OUT"

# ---------- 验包 ----------
echo "==> [4/4] 验包"
sh "$SELF_DIR/pack.sh" --check "$OUT"

ls -lh "$OUT"
echo "md5: $(md5sum "$OUT" | cut -d' ' -f1)"
