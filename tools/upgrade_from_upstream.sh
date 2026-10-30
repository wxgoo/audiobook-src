#!/bin/bash
# =====================================================================
# 上游 mybooks 更新后的升级脚本（git 补丁法）
#
# 思路：本改版不是上游的"配置"，而是一份有十几个文件改动的 fork，
# 直接用上游新代码覆盖会把我们的修改全部抹掉（封面修复、nginx 屏蔽、
# 读者组模板、分类重整、MyReader 接入……）。正确做法：
#
#   本站代码 = 上游代码 + 我们的补丁层
#   上游更新 = 把补丁层"重新盖"到新版上游上（git merge / rebase）
#
# 前提（只需做一次）：把本站目录初始化成 git 仓库并做首个提交。
# 本脚本自动检测，没初始化就先帮你初始化。
# =====================================================================
set -eu

OUR_DIR="/volume1/docker/audiobook"
UPSTREAM_REPO="https://github.com/PoxenStudio/mybooks.git"   # 上游仓库

# git 仓库放在站点目录外面：rm -rf audiobook 重装时不会把提交历史一起删掉。
# 只要在 /volume1/docker 下、且不叫 audiobook，重装后跑本脚本会自动接回去。
GIT_DIR_PATH="/volume1/docker/audiobook-git"

# 不带参数时自动选上游最新的 v*.*.* 版本分支（正式版），而非 develop。
# 显式传参则用传入的分支/tag：sh tools/upgrade_from_upstream.sh v4.5.1
UPSTREAM_REF="${1:-}"

export GIT_DIR="$GIT_DIR_PATH"
export GIT_WORK_TREE="$OUR_DIR"

mkdir -p "$GIT_DIR_PATH"
cd "$OUR_DIR"

# ---------- 0. 一次性初始化 ----------
if [ ! -f "$GIT_DIR_PATH/HEAD" ]; then
    echo "==> 首次运行：初始化 git 仓库（存放在 $GIT_DIR_PATH，站点目录外）"
    git init -q "$GIT_DIR_PATH"
    # 排除构建产物等大文件：git 里只管「代码 + 配置 + 文档」。
    # 注：运行数据（书库/音频/数据库）v4.8.2 起已整体外置到 /volume1/docker/audiobook-data，
    # 本来就不在站点目录里；下面这些排除是防御性的（老布局目录残留也不会进 git）。
    cat > "$GIT_DIR_PATH/info/exclude" <<'EXCL'
# ---- 运行数据（有独立备份，不进 git）----
books/
audiobook-backup-*/
*.db
*.db-journal

# ---- 构建产物与依赖（可由包/构建恢复）----
app/node_modules/
app/.nuxt/
app/dist/
app/.next/
myreader-dist/

# ---- 系统垃圾 ----
.DS_Store
Thumbs.db
__pycache__/
*.pyc
EXCL
    git add -A
    git -c user.name=local -c user.email=local@nas commit -qm "v4.8.2 改版基线（数据目录已排除）" \
        || echo "    （没有可提交的文件，跳过基线提交）"
    git remote add upstream "$UPSTREAM_REPO" 2>/dev/null || true
    echo "    完成。重装站点目录后，本 git 历史仍在 $GIT_DIR_PATH，跑本脚本自动接回。"
    echo "    以后每次手工改动本站代码后，记得 git add -A && git commit，"
    echo "    否则升级时你的改动和补丁层分不开。"
fi

# 确保有 upstream 远端
git remote | grep -qx upstream || git remote add upstream "$UPSTREAM_REPO"

# ---------- 1. 记录当前运行版本 ----------
echo "==> 当前版本: $(git log --oneline -1)"

# ---------- 2. 拉上游 ----------
# 不带参数：自动探测上游最新的 v*.*.* 版本分支作为升级目标（正式版优先）。
# develop 是开发进度，可能含未稳定功能，此处仅显式传参时才会使用。
if [ -z "$UPSTREAM_REF" ]; then
    echo "==> 自动探测上游最新正式版分支..."
    UPSTREAM_REF=$(git ls-remote --heads upstream \
        | grep -oP 'refs/heads/v[\d.]+' \
        | sort -V | tail -1 | sed 's|refs/heads/||')
    if [ -z "$UPSTREAM_REF" ]; then
        echo "    !! 没探测到 v*.*.* 分支，回退用 main"
        UPSTREAM_REF="main"
    fi
fi
echo "==> 拉取上游 $UPSTREAM_REF"
git fetch -q upstream "$UPSTREAM_REF"
echo "    上游最新: $(git log --oneline -1 upstream/$UPSTREAM_REF)"

# ---------- 3. 合并（保留我们的提交，冲突手动解决） ----------
echo "==> 合并上游到本站"
if git merge upstream/$UPSTREAM_REF --no-edit; then
    echo "    合并干净，无冲突。"
else
    cat <<'EOF'
    !! 有冲突。冲突文件已列出，逐个处理：
    git status                     # 看冲突清单
    # 对每个文件：
    #   打开文件，找 <<<<<<< 标记，保留"我们的"或"上游的"或手工融合
    #   原则：webserver/ app/src 下优先保我们的改动（那是移植价值所在）；
    #         纯上游新功能文件直接 git add 即可
    git add <解决完的文件>
    git commit
    # 然后重新执行本脚本剩下的步骤（docker compose build && up -d）
EOF
    exit 1
fi

# ---------- 4. 重建镜像并重启 ----------
echo "==> 重建镜像并重启容器"
docker compose build
docker compose up -d

echo "==> 等 25 秒做启动自检"
sleep 25
docker compose exec mybooks supervisorctl status || true
echo
echo "==> 升级完成。回滚方法（升级后 24 小时内都能秒回）："
echo "    git reset --hard ORIG_HEAD && docker compose build && docker compose up -d"
