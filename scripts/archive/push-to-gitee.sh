#!/bin/sh
# 【已归档 · 一次性脚本】
# 推 4.6.0-9 改动到 Gitee。现在直接 git push；令牌若失效见 docs/操作总纲.md。
# 不随版本更新，不要在这些文件上打补丁；需要类似能力请新写一个放 scripts/ 根。
# 下面保留原始内容：
# ============================================================
# push-to-gitee.sh —— 把本地已提交的 4.6.0-9 改动推到 Gitee
#
# 用法（三选一）：
#   1) 在 NAS / 开发机上，仓库目录里直接跑：
#        sh push-to-gitee.sh
#      走已保存的凭据（Git 凭据管理器 / SSH key）
#
#   2) 用 Gitee 私人令牌（推荐，免交互）：
#        GITEE_TOKEN=你的令牌 sh push-to-gitee.sh
#      令牌在 https://gitee.com/profile/personal_access_tokens 生成，
#      勾选 projects 权限即可。
#
#   3) 用 SSH（仓库已配好 key 的话）：
#        sh push-to-gitee.sh git@gitee.com:wxgoo/audiobook-src.git
# ============================================================
set -e

REPO_URL_HTTPS="https://gitee.com/wxgoo/audiobook-src.git"
REMOTE="${1:-}"

cd "$(dirname "$0")"
[ -d .git ] || { echo "!! 当前目录不是 git 仓库：$(pwd)"; exit 1; }

echo "==> 待推送的提交"
git log --oneline origin/master..HEAD 2>/dev/null | sed 's/^/    /' || echo "    （无法比较，继续）"

if [ -n "$REMOTE" ]; then
    echo "==> 使用指定地址: $REMOTE"
    git push "$REMOTE" master
elif [ -n "$GITEE_TOKEN" ]; then
    echo "==> 使用 GITEE_TOKEN 推送"
    # 令牌走一次性的 URL，不写进 .git/config，也不落盘
    git push "https://wxgoo:${GITEE_TOKEN}@gitee.com/wxgoo/audiobook-src.git" master
else
    echo "==> 使用已保存的凭据推送"
    git push origin master
fi

echo
echo "✅ 推送完成"
git log --oneline -1
