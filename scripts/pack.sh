#!/usr/bin/env bash
# ============================================================
# pack.sh —— 从仓库打部署包
#
# 用法（仓库根目录）：
#   bash scripts/pack.sh 4.6.0-build.27-r27  # 推荐：显式传完整修订号（含 -rN）
#   bash scripts/pack.sh --src 4.6.0-build.27-r27
#                                        # 打源码整包 audiobook-src-<版本>-full.tar.gz
#                                        # （与部署包同一套暂存/门禁，仅顶层结构与裁剪不同）
#   bash scripts/pack.sh --full 4.6.0-build.27-r27
#                                        # 完整包：保留 app/node_modules（构建期依赖），
#                                        # 产物名带 -full 后缀，不会覆盖同名正式包。
#                                        # 只在「改了前端却没重新出 dist、需要现场
#                                        # npm ci + generate」的开发场景才用得到。
#                                        # 默认已排除这一层；--slim 保留为兼容别名
#                                        # （等价于默认，不再产生 -slim 后缀）。
#   bash scripts/pack.sh                 # 不传参时版本号取自 CHANGELOG 首条，只有基础版本
#                                        # （形如 4.6.0-build.27，缺 -rN，会被清单断言拒绝）
#   bash scripts/pack.sh --check xxx.tar.gz   # 只验一个已有包，不打包（自动识别部署包/源码包）
#
# 产物：$OUTDIR/audiobook-deploy-<版本>.tar.gz（默认 /workspace 可写则用它，否则 ~/audiobook-out；可用 OUTDIR=... 指定）
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
# 3. app/node_modules 是构建期依赖，运行时不读。Dockerfile v3 只要 app/dist 齐全
#    就走「跳过 npm ci / generate」快路，生产镜像里的 app/ 来自 /app-static（只含
#    dist 与几个配置文件），从来不含 node_modules；.dockerignore 也本来就排除它。
#    所以默认排除，包体 215MB → 153MB（实测），NAS 传输与构建上下文都更轻。
#    真机证据：r29（TraeCode CN 出的包）就没带这一层，热更到 r30 后站点一直正常；
#    r33 又在沙箱用 docker build --target builder 复验，日志明确打印
#    「检测到预构建 dist，跳过 npm ci 与 generate」，768 个 dist 文件全部带上。
#    只有 --full 才保留（供「改了前端却没重新出 dist」的开发场景）。
#    注意：myreader-dist 下三层 node_modules 是 Next standalone 的运行期产物、
#    不是可重装的依赖，任何模式都不动，由第 4 步断链门禁（断链必须为 0）保证。
# ============================================================
set -euo pipefail

SELF_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$SELF_DIR/.." && pwd)
cd "$ROOT"

# ---------- 只验包模式 ----------
if [ "${1:-}" = "--check" ]; then
    PKG="${2:-}"
    [ -n "$PKG" ] && [ -f "$PKG" ] || { echo "用法: sh scripts/pack.sh --check <包路径>"; exit 2; }
    verify() {
        T=$(mktemp -d -p "$(pwd)" 2>/dev/null || mktemp -d)
        trap 'rm -rf "$T"' EXIT
        tar -xzf "$PKG" -C "$T" || { echo "!! 解压失败"; exit 1; }
        # 包类型自动识别：带 audiobook/ 顶层前缀的是部署包；仓库根即包根的是源码整包。
        # 两者共用大部分检查，只有「不该有什么」和开发侧裁剪的断言不同。
        IS_SRC=0
        [ -d "$T/audiobook" ] || IS_SRC=1
        D="$T/audiobook"
        [ -d "$D" ] || D="$T"      # 允许把已解开的目录打包后再验
        [ -d "$D" ] || { echo "!! 包内没有 audiobook/ 或包根不是目录"; exit 1; }

        fail=0
        # 该有的东西：少一样就起不来或没法升级
        for f in Dockerfile docker-compose.yml myreader-dist/app/server.js \
                 conf/supervisor/mybooks.conf conf/nginx/mybooks.conf \
                 scripts/upgrade.sh scripts/deploy.sh scripts/check-reader.sh \
                 scripts/check-myreader-links.sh scripts/myreader-links.manifest \
                 scripts/pack.sh scripts/hotfix.sh scripts/sync-hotfix.sh \
                 tools/category_backfill.py update/manifest.json; do
            [ -e "$D/$f" ] || { echo "  !! 缺 $f"; fail=1; }
        done

        # 不该有的东西：版本库/构建缓存，两种模式都一样；
        # 归档、tests、skills、.claude 这些开发侧内容只在部署包里算杂物，源码整包必须保留。
        # app/node_modules 默认排除（--full 才保留），两种口径都不判失败。
        # app/.nuxt / app/.next 是构建中间产物，任何模式都不该有。
        if [ "$IS_SRC" = "1" ]; then
            junk=".git .build-trash .pack-stage app/.nuxt app/.next"
        else
            junk="scripts/archive docs/archive docs/settings-redesign audiobook-src .git skills .claude tests \
                  .build-trash .pack-stage app/.nuxt app/.next"
        fi
        for j in $junk; do
            [ -e "$D/$j" ] && { echo "  !! 包里混入不该有的内容: $j"; fail=1; }
        done
        # 只报数、不判失败：默认排除、--full 保留，两种口径都合法
        if [ -d "$D/app/node_modules" ]; then
            echo "  app/node_modules: 在包内（$(find "$D/app/node_modules" \( -type f -o -type l \) | wc -l | tr -d ' ') 条，--full 完整包）"
        else
            echo "  app/node_modules: 不在包内（默认瘦身包）"
        fi

        # 换行纪律（fix2 事故防复发，2026-11-07）：容器/宿主要执行的文本必须 LF。
        # CRLF 进镜像后 start.sh 的 shebang 变成 "#!/bin/sh\r" → exec 报 no such file。
        # POSIX sh 没有 $'\r'，用 printf 造。
        CR=$(printf '\r')
        crhit=$(grep -rlI "$CR" "$D/docker" "$D/conf" "$D/scripts" \
                      "$D/Dockerfile" "$D/Dockerfile.base" "$D/docker-compose.yml" \
                      "$D/run_webserver.sh" 2>/dev/null | head -5) || true
        if [ -n "$crhit" ]; then
            echo "  !! 以下文件含 CR（CRLF 换行），容器/宿主脚本会无法执行："
            echo "$crhit" | sed 's/^/     /'
            fail=1
        fi

        # dist 与 src 同步粗检：dist 语言包里必须能找到较新的键（抽查归一化指引 openClean）。
        # 缺了说明 dist 早于 src —— 先 npm run build-spa 再打包，或人工补键。
        if [ -d "$D/app/dist/_nuxt" ]; then
            if ! grep -lq "openClean" "$D"/app/dist/_nuxt/*.js 2>/dev/null; then
                echo "  !! app/dist 落后于 app/src（语言包缺 authorNorm.openClean）—— 重建前端后再打包"
                fail=1
            fi
        fi

        # dist 整目录完整性（r24 事故）：非构建资源会被 generate 清掉。
        # 只看「构建产物」数量会漏 395 个文件，必须按整目录基线校验。
        if [ -d "$D/app/dist" ]; then
            if [ ! -f "$D/app/dist/static/pdfjs/web/viewer.html" ]; then
                echo "  !! app/dist 缺 static/pdfjs/web/viewer.html（PDF 入口会 404）"
                fail=1
            fi
            dtotal=$(find "$D/app/dist" -type f 2>/dev/null | wc -l | tr -d ' ')
            # r31 基线 768（r30 是 766）：+2 来自 CategoryTabs.vue 抽成公共组件
            # 后的新 chunk 与 manifest 变化；已用 .nuxt/dist/server/client.manifest.json
            # 对比磁盘确认零残留零丢失后才挪的基线，别在未做引用核对时随手改这个数。
            if [ "$dtotal" -ne 768 ]; then
                echo "  !! app/dist 文件数 $dtotal != 基线 768 —— 先跑 sh scripts/check-dist.sh 定位缺什么"
                fail=1
            fi
        fi

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
        # 2026-11-09：新包带权威清单时逐根比对（旧包无清单则沿用上面的模糊判据）。
        # 这一步能抓出「有效链接数够、但 .next 层带哈希的链接全丢」这类隐性损坏。
        if [ -f "$D/scripts/check-myreader-links.sh" ] && [ -f "$D/scripts/myreader-links.manifest" ]; then
            if ! sh "$D/scripts/check-myreader-links.sh" \
                    --manifest "$D/scripts/myreader-links.manifest" \
                    "$D/myreader-dist" >/dev/null 2>&1; then
                echo "  !! 按 myreader-links.manifest 逐根校验不通过（链接缺失或目标不符）"
                fail=1
            else
                echo "  ✓ 119 根链接清单校验通过"
            fi
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

        # 下面两条是部署包专属断言：源码整包保留仓库原貌，srt-tool/tools 的开发侧文件
        # 本来就该在（要打包成 exe、要抓书源），不能按部署包口径判它「混入」。
        if [ "$IS_SRC" = "0" ]; then
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
        fi   # IS_SRC=0（部署包专属断言结束）

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

# ---------- 模式 ----------
# 默认 deploy；--src 打源码整包。两者共用同一套暂存/清理/门禁，只有三处不同：
#   1) 产物命名与顶层结构；2) 不裁开发侧目录（tools/tests/skills/.claude/归档）；
#   3) 不覆盖 update/manifest.json（源码包要仓库原貌，不是发布清单）。
# 默认瘦身（SLIM=1）：排除 app/node_modules。r29 真机 + r33 沙箱构建均已验证，
# 见脚本头部第 3 条。--full 才保留；--slim 保留为兼容别名（等价于默认）。
MODE=deploy
SLIM=1
while [ $# -gt 0 ]; do
    case "$1" in
        --src)  MODE=src; shift ;;
        --slim) SLIM=1;   shift ;;
        --full) SLIM=0;   shift ;;
        *) break ;;
    esac
done

# ---------- 确定版本号 ----------
VER="${1:-}"
if [ -z "$VER" ]; then
    VER=$(grep -m1 -oE '^## [0-9]+\.[0-9]+\.[0-9]+-(build\.)?[0-9]+' CHANGELOG.md | sed 's/^## //')
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

if [ "$MODE" = src ]; then
    NAME="audiobook-src-$VER-full"
    PFX=""                     # 源码整包：仓库根即包根
else
    NAME="audiobook-deploy-$VER"
    PFX="audiobook/"           # 部署包：统一收在 audiobook/ 下
fi
# 默认（瘦身）就是正式包，名字不带后缀；只有显式 --full 才另取名，避免覆盖
[ "$SLIM" = "0" ] && NAME="$NAME-full"
# 输出目录：显式 OUTDIR 优先；否则用可写的 /workspace（构建机常见），
# 普通用户在家目录下跑时 /workspace 建不出来（根目录不可写），退回 ~/audiobook-out。
if [ -n "${OUTDIR:-}" ]; then
    :
elif [ -d /workspace ] && [ -w /workspace ]; then
    OUTDIR=/workspace
else
    OUTDIR="$HOME/audiobook-out"
fi
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

echo "==> [1b/4] 前端产物整目录校验（不是只数构建产物）"
if [ -f scripts/check-dist.sh ]; then
    sh scripts/check-dist.sh || { echo "  !! 前端产物不完整，禁止出包"; exit 1; }
else
    echo "  !! 缺 scripts/check-dist.sh（dist 完整性无法校验），禁止出包"; exit 1
fi

echo "==> [2/4] MyReader 产物自检（清单驱动，119 根逐根校验）"
[ -d myreader-dist/node_modules ] || { echo "  !! 缺 myreader-dist/node_modules（产物不完整，见 .gitignore 例外区）"; exit 1; }
mr_total=$(find myreader-dist \( -type f -o -type l \) | wc -l)
mr_valid=0
for l in $(find myreader-dist -type l); do [ -e "$l" ] && mr_valid=$((mr_valid + 1)); done
echo "  $mr_total 条，有效链接 $mr_valid"
# 2026-11-09：光数「有效链接 >=100」不够——static/ 里的悬空链接也会凑数，
# 而 .next/node_modules 那 24 根带哈希的链接全丢时，myreader 照样显示
# Ready、打开书却 500。必须按权威清单逐根比对。
# 注意：本脚本若在 Windows 工作区运行（core.symlinks=false 把链接压扁成
# 普通文件），这一步会明确失败——这正是目的：**不要从压扁的工作区出包**。
# 请先在 Linux/WSL 里 `git checkout` 还原符号链接，或以完好部署包为底重打。
if [ -f scripts/check-myreader-links.sh ] && [ -f scripts/myreader-links.manifest ]; then
    sh scripts/check-myreader-links.sh || {
        echo "  !! MyReader 链接不全，禁止出包。"
        echo "     先修好再打： sh scripts/check-myreader-links.sh --fix myreader-dist"
        echo "     （Windows 工作区无法创建符号链接时，须在 Linux 上重新检出或解包）"
        exit 1
    }
else
    echo "  !! 缺 scripts/check-myreader-links.sh 或 myreader-links.manifest，禁止出包"
    exit 1
fi

# 发布清单必须随包发布：/admin/version 拿它当本地修订基线，缺了会一直误报「有新版本」。
# 生成命令见 scripts/gen-update-manifest.py 顶部说明。
if [ ! -f update/manifest.json ] || ! grep -q '"revision"' update/manifest.json; then
    echo "  !! 缺 update/manifest.json 或清单里没有 revision，禁止出包"
    echo "     生成： python3 scripts/gen-update-manifest.py --revision <新> --base-revision <旧> --base-commit <sha>"
    exit 1
fi
echo "  发布清单 OK: $(grep -m1 '"revision"' update/manifest.json | tr -d ' ,')"

# 清单 revision 必须与本次出包的修订号一致：先推清单、后出包（协作备忘 §4）。
# 这条断言是硬的——r27 就是栽在这里：清单还停在 r26，照它出包，页面装完仍报有新版本。
MANIFEST_REV=$(grep -m1 -oE '"revision"[[:space:]]*:[[:space:]]*"[^"]+"' update/manifest.json | sed 's/.*"\([^"]*\)"$/\1/')
if ! printf '%s' "$VER" | grep -qE -- '-r[0-9]+$'; then
    echo "  !! 版本号 $VER 不含 -rN 修订号，无法与清单 revision 比对"
    echo "     CHANGELOG 首条只有基础版本（4.6.0-build.27），出修订包请显式传参："
    echo "     bash scripts/pack.sh 4.6.0-build.27-r27"
    exit 1
fi
[ "$MANIFEST_REV" = "$VER" ] || {
    echo "  !! 包内清单 revision=$MANIFEST_REV 与本次版本 $VER 不一致（先推清单、后出包）"
    exit 1
}
echo "  清单 revision 与包版本一致: $MANIFEST_REV"


# ---------- 打包 ----------
echo "==> [3/4] 打包（cd 到父目录对目录名打包，不用 --transform）"

# 同一份源码要能出同一个 md5，否则「包没传坏吧」这个问题永远说不清。
# 变数有两个，都钉死：
#   1. gzip 会把压缩时间戳写进文件头 → -n 去掉
#   2. tar 按文件名排序时，同一批命令产生的 mtime 精度不同 → --mtime + --sort=name
# gzip -n 而不是 export GZIP：新版 gzip 会对该变量告警，且它不是给 tar 用的接口
TAR_OPTS="--sort=name --mtime=@$REPRO_MTIME --owner=0 --group=0 --numeric-owner"
# 暂存区放在仓库同文件系统（ROOT 下），原因：
#   1) 避免 mktemp 默认落在 /tmp（tmpfs / 其他卷）导致跨设备，进而 cp 退化、92M 产物撑爆 tmpfs；
#   2) 让拷贝与原仓库同盘，空间/权限都最稳。
# 用 tar 管道拷贝（而非 cp -al/cp -a）：不碰硬链接/软链边界，目录、符号链接、权限一律原样保留，
# 最不容易漏文件。用完由 trap 清理。
STAGE="$ROOT/.pack-stage.$$"
rm -rf "$STAGE"
mkdir -p "$STAGE/audiobook"
trap 'rm -rf "$STAGE"' EXIT
if [ "$MODE" = src ]; then
    # 源码整包：只打 git 跟踪的文件（r29 起）。
    # 起因：r28 的 src 包混进约 4.3MB 测试生成物（tests/library/、tests/cases/library/、
    # old.epub/new.epub），都是本机跑 pytest 留下的、被 .gitignore 忽略的残留。
    # 改成 ls-files 白名单后，被忽略的生成物永远不会入包，也不用维护排除规则。
    # 需要但未跟踪的例外在这里显式追加（当前没有）。
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
        || { echo "  !! --src 必须在 git 工作树里打（找不到 .git）"; exit 1; }
    rm -f "$STAGE/.files"
    git ls-files -z > "$STAGE/.files"
    ( cd "$ROOT" && tar --null --no-recursion -T "$STAGE/.files" -cf - ) \
        | ( cd "$STAGE/audiobook" && tar -xf - ) \
        || { echo "  !! 按 git ls-files 暂存失败"; exit 1; }
else
for item in $(ls -A); do
    # 两种模式共同的排除项：版本库、仓库根 node_modules、运行期数据、各类缓存、本脚本的暂存目录
    # 注意：这里只排顶层名字，app/node_modules 不在其中（默认保留，--slim 才删，见下方清理段）
    case "$item" in
        .git|node_modules|cache|sync|books|data|__pycache__|logs) continue ;;
        # app/build.sh 的构建归档目录：它把旧的 .nuxt / dist 改名挪到这里（rename 不删除），
        # 一份能到 40M 以上。属于本机构建垃圾，混进包里既撑大体积又让人以为要部署它。
        .build-trash) continue ;;
        # pytest 缓存在仓库根也会生成（在 srt-tool/ 里跑测试时 rootdir 会往上找到仓库根）
        .pytest_cache) continue ;;
        # 误提交的嵌套仓库条目（历史上 clone 自己的残留），空目录，无内容
        audiobook-src) continue ;;
        # 本脚本自己建的暂存目录，不能递归进包
        .pack-stage*) continue ;;
    esac
    # 仅部署包排除的开发侧目录，源码整包要保留（它们是仓库的一部分）
    if [ "$MODE" = deploy ]; then
        case "$item" in
            # skills/ 是给 AI 客户端（clawdbot / openclaw）加载的 skill 包，走 HTTP API
            # 操作书库，不是服务端依赖。NAS 上用不到，要用的在 PC 上装。
            .claude|skills) continue ;;
        esac
    fi
    tar -cf - "$item" 2>/dev/null | ( cd "$STAGE/audiobook" && tar -xf - ) \
        || { echo "  !! 暂存失败: $item"; exit 1; }
done
fi
rm -f "$STAGE/.files"
# 暂存自检：关键目录/文件必须进暂存区，否则打出来的包必缺文件（不再静默验到旧包）
for must in Dockerfile docker-compose.yml app conf scripts update tools myreader-dist; do
    [ -e "$STAGE/audiobook/$must" ] || { echo "  !! 暂存区缺 $must（staging 失败，未进包）"; exit 1; }
done
echo "  暂存 OK: $(ls "$STAGE/audiobook" | tr '\n' ' ')"

# 以下裁剪只针对部署包；源码整包（--src）保留仓库原貌。
if [ "$MODE" = deploy ]; then
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
fi

# app/.nuxt / app/.next 是 nuxt generate 的中间产物与 Next 构建缓存，任何模式都不进包：
# 部署只用 app/dist，Dockerfile 见到 dist 就走「跳过 npm ci/generate」的快路。
# 注意：这两个目录被排除不影响 --check（它只认 app/dist）与首屏（首屏只读 dist 静态文件）。
rm -rf "$STAGE/audiobook/app/.nuxt" "$STAGE/audiobook/app/.next"

# app/node_modules 是构建期依赖，默认排除（依据见脚本头部第 3 条）。
# 早期「删了会出运行异常」的说法来自 r11 时代的旧构建链路，且常伴随误伤
# myreader-dist 的依赖；v3 的「带 dist 就跳过 npm ci」已把它根除，勿再照抄。
# myreader-dist 下三层 node_modules 是 MyReader 运行期解析路径，任何模式都不动。
if [ "$SLIM" = "1" ]; then
    rm -rf "$STAGE/audiobook/app/node_modules"
    echo "  app/node_modules 已排除（默认）：包体约 153MB，构建仍走预构建 dist 快路"
else
    if [ -d "$STAGE/audiobook/app/node_modules" ]; then
        echo "  app/node_modules 保留（--full）：$(find "$STAGE/audiobook/app/node_modules" \( -type f -o -type l \) | wc -l | tr -d ' ') 条"
    else
        echo "  --full 但构建机上没有 app/node_modules，包内自然没有"
    fi
fi

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

# ---------- 包内发布清单基线（仅部署包） ----------
# 旧做法：出包前从 Gitee raw 拉清单覆盖包内那份，理由是「本仓库清单往往落后」。
# 但 Gitee raw 有缓存：r27 与 r33 都出现过「仓库已是新清单、raw 还停在上一版」，
# 结果把旧 revision 打进包里，装完页面一直误报有新版本 / 反复要求重新部署。
# 现在的口径：本脚本前面的断言已确认仓库里的 update/manifest.json 的 revision == $VER，
# 它就是本次要发布的清单，直接以它为准；远端只打印一个「是否已同步」的提示，
# 绝不覆盖产物。这样也避免重出清单时远端的旧字节混进包里。
if [ "$MODE" = deploy ]; then
    echo "==> [3b/4] 包内发布清单基线"
    MANIFEST_URL="${MANIFEST_URL:-https://gitee.com/wxgoo/audiobook-src/raw/master/update/manifest.json}"
    MF_TMP="$STAGE/.manifest.remote.json"
    mf_get() {
        python3 -c 'import json,sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
print(d.get(sys.argv[2], ""))' "$1" "$2" 2>/dev/null || true
    }
    mf_fetch() {
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL --max-time 20 "$MANIFEST_URL" -o "$MF_TMP" 2>/dev/null && return 0
        fi
        if command -v wget >/dev/null 2>&1; then
            wget -q -T 20 -O "$MF_TMP" "$MANIFEST_URL" 2>/dev/null && return 0
        fi
        return 1
    }
    if command -v python3 >/dev/null 2>&1 && mf_fetch && [ -s "$MF_TMP" ] \
            && python3 -c 'import json,sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if isinstance(d, dict) and d.get("revision") else 1)' "$MF_TMP" 2>/dev/null; then
        MF_REV=$(mf_get "$MF_TMP" revision)
        if [ "$MF_REV" = "$VER" ]; then
            echo "  · 远端清单已是 $MF_REV（仅作参考，不覆盖包内产物）"
        else
            echo "  · 远端清单 revision=$MF_REV 落后于本次 $VER（Gitee raw 缓存），跳过"
        fi
    else
        echo "  · 远端清单不可读（网络/缓存/JSON），不影响出包：以仓库内清单为准"
    fi
    rm -f "$MF_TMP"

    # 一律用仓库里已通过断言的那份，并在写进包后再校验一次（防止今后又被人改成远端覆盖）
    cp update/manifest.json "$STAGE/audiobook/update/manifest.json"
    STAGE_REV=$(mf_get "$STAGE/audiobook/update/manifest.json" revision)
    [ "$STAGE_REV" = "$VER" ] || {
        echo "  !! 包内清单 revision=$STAGE_REV != 本次版本 $VER，禁止出包"; exit 1; }
    echo "  ✓ 包内清单基线: revision=$STAGE_REV（取自仓库，字节与提交一致）"
fi


mkdir -p "$OUTDIR" 2>/dev/null || { echo "  !! 无法创建输出目录: $OUTDIR（用 OUTDIR=<可写目录> 重跑）"; exit 1; }
if [ "$MODE" = src ]; then
    # 源码整包：以仓库根为包根（成员不带 audiobook/ 前缀）
    ( cd "$STAGE/audiobook" && tar $TAR_OPTS -cf - $(ls -A) | gzip -n > "$OUT" )
else
    # 部署包：cd 到暂存父目录对目录名打包，不用 --transform（会改坏符号链接目标）
    ( cd "$STAGE" && tar $TAR_OPTS -cf - audiobook | gzip -n > "$OUT" )
fi
# pipefail 已保证 tar 失败即退出；再确认产物非空，避免验到上一次遗留的坏包
[ -s "$OUT" ] || { echo "  !! 打包产物为空，tar 可能失败"; exit 1; }
echo "  产物: $OUT"

# ---------- 打包后门禁 ----------
# 打包前的检查只能证明「树里齐」，证明不了「包里齐」：暂存排除规则、tar 参数、
# 稀疏检出/缺文件都可能让成员在归档时静默消失。这里直接对产物说话，
# 不符就删包退出，绝不留半成品当交付物。
# 注意：下面先把成员清单落到文件再查，不能用 `tar -tzf | grep -q`——grep 提前退出
# 会让 tar 吃到 SIGPIPE，配合 pipefail 会被误判成「没找到」。
gate_fail=0
gate_bad() { echo "  !! 门禁失败：$1"; gate_fail=1; }
LIST="$STAGE/.pkg.list"
tar -tzf "$OUT" > "$LIST" || gate_bad "无法读取包内成员清单"
grep -v '/$' "$LIST" > "$LIST.f" || true

DIST_FILES=$(grep -c "^${PFX}app/dist/" "$LIST.f" || true)
[ "$DIST_FILES" = "768" ] || gate_bad "包内 app/dist 文件数=$DIST_FILES（应为 768）"

DIST_IDX=$(tar -xzOf "$OUT" "${PFX}app/dist/index.html" 2>/dev/null | sha256sum | cut -d' ' -f1)
[ "$DIST_IDX" = "2c02df40e218bbbdd282fc1c7d818c6b0768f3b8941410a9d8c966e3cdf6084d" ] \
    || gate_bad "包内 app/dist/index.html sha256=$DIST_IDX（应为 2c02df40…，4901 字节）"

grep -qx "${PFX}app/dist/static/pdfjs/web/viewer.html" "$LIST" \
    || gate_bad "包内缺 app/dist/static/pdfjs/web/viewer.html"

PKG_FILES=$(wc -l < "$LIST.f" | tr -d ' ')
if grep -qx "${PFX}MANIFEST" "$LIST"; then
    MF_FILES=$(tar -xzOf "$OUT" "${PFX}MANIFEST" | sed -n 's/^files[: ]*//p' | head -1)
    [ "${MF_FILES:-}" = "$PKG_FILES" ] \
        || gate_bad "包内 MANIFEST 记 $MF_FILES 个成员，实际 $PKG_FILES 个"
else
    STAGE_FILES=$(find "$STAGE/audiobook" \( -type f -o -type l \) | wc -l | tr -d ' ')
    [ "$STAGE_FILES" = "$PKG_FILES" ] \
        || gate_bad "包内成员数=$PKG_FILES 与暂存区=$STAGE_FILES 不一致（归档丢成员）"
    echo "  包内无 MANIFEST，成员数改与暂存区比对：$PKG_FILES"
fi
rm -f "$LIST" "$LIST.f"

if [ "$gate_fail" != "0" ]; then
    echo "  !! 门禁未通过，删除半成品包: $OUT"
    rm -f "$OUT"
    exit 1
fi
echo "  门禁 OK：app/dist $DIST_FILES 个文件，index.html 2c02df40…（4901 字节），pdfjs viewer 在包内，成员共 $PKG_FILES 个"

# ---------- 验包 ----------
echo "==> [4/4] 验包"
bash "$SELF_DIR/pack.sh" --check "$OUT"

ls -lh "$OUT"
echo "md5: $(md5sum "$OUT" | cut -d' ' -f1)"
