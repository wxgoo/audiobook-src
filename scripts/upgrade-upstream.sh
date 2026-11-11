#!/bin/sh
# ============================================================
# upgrade-upstream.sh —— 跟随上游 mybooks 升级，一条命令走完全链路
#
# 用法（NAS 上执行）：
#   sh upgrade-upstream.sh [上游tag]
#   例：sh upgrade-upstream.sh 4.6.0
#   不给 tag 则自动查上游最新 release
#   （推送/克隆 Gitee 需要的凭据只从环境变量 GITEE_TOKEN 读取：
#     export GITEE_TOKEN=<私人令牌>
#    未设置时退回无凭据地址，交互式输入或 ~/.netrc 提供凭据）
#
# 链路：clone → merge 上游 tag → 冲突处理(暂停等人工) →
#       测试确认 → push → 出成品包 → upgrade.sh 生效
#
# 特性：
#   * 每步之间停下来等你确认，随时 Ctrl+C 退出
#   * 有合并冲突时自动暂停，告诉你改哪个文件；
#     改完重新运行同一命令，脚本从断点继续
#   * 断点记录在 /tmp/up-upgrade/state，全程可中断可续跑
# ============================================================

set -e

TOKEN="${GITEE_TOKEN:-}"                      # gitee 私人令牌只从环境变量读取，不写入脚本
TAG="$2"
WORK=/tmp/up-upgrade
REPO=$WORK/audiobook          # 目录名直接叫 audiobook，打包顶层即正确
SRC=/volume1/docker/audiobook                 # NAS 现役源码（取 myreader-dist 用）
GITEE="gitee.com/wxgoo/audiobook-src.git"
UPSTREAM="https://github.com/PoxenStudio/mybooks.git"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*"; exit 1; }
pause(){ printf '\n  回车继续，Ctrl+C 退出 ...'; read dummy; }

if [ -n "$TOKEN" ]; then
    GITEE_URL="https://wxgoo:${TOKEN}@${GITEE}"
else
    GITEE_URL="https://${GITEE}"
    warn "未设置 GITEE_TOKEN，使用无凭据地址 https://${GITEE}"
    warn "免交互推送可任选其一：export GITEE_TOKEN=<私人令牌>，或写入 ~/.netrc（chmod 600）"
fi
mkdir -p "$WORK"

# ---------- 步骤 1：准备本地仓库 ----------
step "1/7 准备仓库（clone/pull gitee master）"
if [ -d "$REPO/.git" ]; then
    cd "$REPO"
    if [ -f .git/MERGE_HEAD ]; then
        warn "合并进行中，保留你的冲突修改，不重置"
    else
        git fetch origin && git reset --hard origin/master && git clean -fd
    fi
else
    rm -rf "$REPO" && mkdir -p "$REPO"
    git clone "$GITEE_URL" "$REPO" 2>/dev/null || die "clone 失败：检查网络与 Gitee 凭据（GITEE_TOKEN 或 ~/.netrc）"
    cd "$REPO"
fi
git checkout master -q
ok "当前 HEAD: $(git log --oneline -1)"

# ---------- 步骤 2：取上游 ----------
step "2/7 拉取上游 tags"
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$UPSTREAM"
git fetch upstream --tags -q || die "fetch upstream 失败（NAS 访问 GitHub 受阻？请改用可联网环境执行本脚本，或先手动 fetch）"

if [ -z "$TAG" ]; then
    TAG=$(curl -s "https://api.github.com/repos/PoxenStudio/mybooks/releases/latest" \
          | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)
    [ -n "$TAG" ] || { warn "自动查询失败"; printf "  请输入上游 tag（如 4.6.0）: "; read TAG; }
fi
git rev-parse -q --verify "$TAG^{commit}" >/dev/null || die "上游没有 tag: $TAG"
ok "目标上游版本: $TAG"

# 已合并过就跳过
if git merge-base --is-ancestor "$TAG" master 2>/dev/null; then
    warn "上游 $TAG 已在 master 中，本次仅重新出包"
fi
# 找 protect-custom.sh：先看自己所在目录（仓库里两个在同一层 scripts/），
# 再看上一层的 scripts/（脚本被单独拷出去、但仓库整个在别处时），
# 最后看 NAS 上的老位置（脚本历史上放在 /volume1/docker 根）。
PROTECT="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/protect-custom.sh"
[ -f "$PROTECT" ] || PROTECT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/scripts/protect-custom.sh"
[ -f "$PROTECT" ] || PROTECT=/volume1/docker/scripts/protect-custom.sh
[ -f "$PROTECT" ] || PROTECT=/volume1/docker/protect-custom.sh
[ -f "$PROTECT" ] || PROTECT="$SRC/protect-custom.sh"
[ -f "$PROTECT" ] || PROTECT=

if git merge-base --is-ancestor "$TAG" master 2>/dev/null; then
    :
else
    # ---------- 步骤 3：合并 ----------
    step "3/7 合并上游 $TAG"
    if [ -f .git/MERGE_HEAD ]; then
        warn "检测到上次合并未完成，继续处理冲突"
    else
        # 合并前先给自定义内容拍快照（BOOK_NAV + 六份三语文案）
        if [ -f "$PROTECT" ]; then
            step "3.1 存自定义内容快照（合并前）"
            sh "$PROTECT" save "$REPO" || warn "快照失败，继续（风险：BOOK_NAV/文案可能被覆盖）"
        else
            warn "找不到 protect-custom.sh，BOOK_NAV 与三语文案没有保护"
        fi
        git merge --no-edit "$TAG" || true
    fi
    CONFLICTS=$(git diff --name-only --diff-filter=U)
    if [ -n "$CONFLICTS" ]; then
        echo "$CONFLICTS" | sed 's/^/    冲突: /'
        cat <<EOF

  ┌──────────────────────────────────────────────────────┐
  │ 人工处理冲突，原则：                                  │
  │   webserver/settings.py → 保留 /data 路径+吸收新配置  │
  │   docker-compose.yml    → 保留你的挂载                │
  │   myreader-dist 冲突    → git checkout --ours myreader-dist && git add myreader-dist │
  │   其它                   → 一般保留上游               │
  │ 改完后:                                               │
  │   cd $REPO                                            │
  │   git add -A && git commit                            │
  │ 然后重新运行本命令，从断点继续                         │
  └──────────────────────────────────────────────────────┘
EOF
        exit 2
    fi
    ok "合并完成: $(git log --oneline -1)"

    # ---------- 步骤 3.2：回灌 + 校验自定义内容 ----------
    if [ -f "$PROTECT" ]; then
        step "3.2 回灌自定义内容（BOOK_NAV / 三语文案）"
        if [ -d /tmp/custom-snap ]; then
            sh "$PROTECT" apply "$REPO" || \
                die "回灌失败。手动：sh $PROTECT apply $REPO"
        else
            warn "没有快照（可能是上次已合并过），只做校验"
        fi

        sh "$PROTECT" check "$REPO" || die "自定义内容校验不通过，先修好再继续"
        if ! git diff --quiet; then
            warn "回灌后有改动，请 git diff 确认这几处只涉及自定义内容："
            git diff --stat | sed 's/^/    /'
            echo
            echo "  确认无误后执行："
            echo "    cd $REPO && git add -A && git commit -m 'restore custom BOOK_NAV/locales after merge $TAG'"
            pause
        fi
        ok "自定义内容完好"
    fi
fi

# ---------- 步骤 4：测试确认 ----------
step "4/7 静态自检 + 等你测试"
# myreader-dist 完整性（只在仓库里有时检查）
if [ -d myreader-dist ]; then
    n=$(find myreader-dist -type l | wc -l)
    [ "$n" -lt 100 ] && die "myreader-dist 符号链接只剩 $n（应≥100），构建产物损坏"
    ok "myreader-dist 符号链接: $n"
fi
python3 -c "import compileall,sys; sys.exit(0) if compileall.compile_dir('webserver', quiet=2) else sys.exit(1)" \
    && ok "webserver Python 语法检查通过" || die "webserver 有语法错误"
find . -name '__pycache__' -exec rm -rf {} + 2>/dev/null; find . -name '*.pyc' -delete 2>/dev/null

# 打包前对自定义内容再校验一次（防止后面又手滑覆盖回去）
if [ -n "$PROTECT" ] && [ -f "$PROTECT" ]; then
    sh "$PROTECT" check . || die "自定义内容丢失，不要出包"
    ok "BOOK_NAV 与三语文案完好"
fi

warn "请先部署测试（容器换源码跑一遍），确认能听书/上传/导入后回来"
pause

# ---------- 步骤 5：push ----------
step "5/7 推送 Gitee"
git push "$GITEE_URL" master 2>&1 | sed 's/^/    /'
ok "已推送 master"

# ---------- 步骤 6：出成品包 ----------
step "6/7 出成品包（版本号 $TAG-1）"
VER="${TAG}-1"
[ -d "$SRC/myreader-dist" ] || die "NAS 现役源码 $SRC/myreader-dist 不存在"
cp -R "$SRC/myreader-dist" ./myreader-dist
rm -rf .git
find . -name '__pycache__' -exec rm -rf {} + 2>/dev/null
find . -name '*.pyc' -delete 2>/dev/null
OUT="/volume1/docker/audiobook-deploy-${VER}.tar.gz"
cd "$WORK" && tar -czf "$OUT" audiobook
ls -lh "$OUT"
n=$(tar -tzf "$OUT" | grep -c 'myreader-dist/.*-> ' || true)
echo "  包内 myreader-dist 符号链接: $n（应约127）"
[ "$n" -lt 100 ] && die "符号链接数不对，包有问题，中止"
ok "成品包: $OUT"

# ---------- 步骤 7：upgrade.sh 生效 ----------
step "7/7 升级生效"
warn "接下来将执行 upgrade.sh（备份→停容器→换源码→构建→启动验证）"
pause
sh /volume1/docker/audiobook/upgrade.sh "$OUT" || die "upgrade.sh 执行失败，按其提示处理"

echo ""
ok "全部完成！版本 $VER 已上线。确认网页正常后：rm -rf /volume1/docker/audiobook.old-*"
rm -rf "$WORK"
