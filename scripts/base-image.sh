#!/bin/sh
# ---------------------------------------------------------------------------
# 基础镜像预检（被 deploy.sh / upgrade.sh / recover.sh source，不单独执行）
#
# 背景：构建只需要 **一个** 外部镜像 —— docker.1ms.run/poxenstudio/mybooks_base:latest。
# 从 build.28 起，Dockerfile 的 builder 阶段也基于它（原来还有一个 node:20-alpine），
# 所以 `docker images` 里不再需要 node 镜像，构建期也不会再拉它。
#
# 这个函数解决的是 base 本身：现场出网常被中间人改写 TLS
# （x509: certificate is not valid for any names），任何 pull 都失败，
# 一旦本地没有 base，构建立刻在 FROM 那一步挂掉。所以按这个顺序拿：
#   1) 本地已有 → 直接用（绝大多数情况，零等待）
#   2) 包内 images/ 下有离线 tar/tar.gz → docker load（解压后自动，无需联网）
#   3) 都没有 → 才尝试 docker pull；失败则打印导出离线包的具体做法
#
# 环境变量：
#   BASE_REF      覆盖基础镜像名（默认见下）
#   NO_PULL=1     禁止联网拉取（纯离线现场用，失败更快）
# ---------------------------------------------------------------------------
BASE_REF="${BASE_REF:-docker.1ms.run/poxenstudio/mybooks_base:latest}"
NO_PULL="${NO_PULL:-0}"

base_image_present() {
    docker image inspect "$BASE_REF" >/dev/null 2>&1
}

# 从 $1/images/ 下导入所有离线镜像包。成功导入返回 0。
load_offline_images() {
    _loaded=0
    for _d in "$@"; do
        [ -d "$_d/images" ] || continue
        for _f in "$_d"/images/*.tar.gz "$_d"/images/*.tar; do
            [ -f "$_f" ] || continue
            echo "    + 导入离线镜像: $_f"
            if docker load -i "$_f"; then
                _loaded=1
            else
                echo "    !! 导入失败（文件可能没传完，核对 sha256 后重试）: $_f"
            fi
        done
    done
    [ "$_loaded" = "1" ] && return 0
    return 1
}

# 离线包里的标签未必就是 BASE_REF（导出机的 tag 可能不带 registry 前缀），
# 这时补一个同名标签即可，不必重新拉取。
fix_base_tag() {
    base_image_present && return 0
    _cand=$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -i 'mybooks_base' | head -1)
    [ -n "$_cand" ] || return 1
    echo "    ! 离线包里的标签是 $_cand，补一个 $BASE_REF"
    docker tag "$_cand" "$BASE_REF" || return 1
    base_image_present
}

# 主入口。参数是「可能放着 images/ 的目录」，按顺序找。
# 返回 0 = 镜像可用；1 = 拿不到（调用方应中止构建）。
ensure_base_image() {
    if base_image_present; then
        echo "    OK：基础镜像已在本地（$BASE_REF）"
        return 0
    fi
    echo "    本地没有 $BASE_REF"
    load_offline_images "$@" || true
    fix_base_tag || true
    if base_image_present; then
        echo "    OK：已从离线包导入基础镜像"
        return 0
    fi
    if [ "$NO_PULL" = "1" ]; then
        echo "    !! NO_PULL=1，跳过联网拉取"
    else
        echo "    尝试 docker pull（需要能出网；TLS 被拦截时会报 x509）..."
        if docker pull "$BASE_REF"; then
            echo "    OK：已拉取基础镜像"
            return 0
        fi
    fi
    echo ""
    echo "  !! 基础镜像拿不到，构建会在 FROM 那一步失败。离线做法："
    echo "     1) 在一台已经有该镜像的机器上执行： sh scripts/export-images.sh"
    echo "     2) 把生成的 images/ 整个目录拷到本包根目录（与 Dockerfile 同级）"
    echo "     3) 重跑本脚本 —— 会自动 docker load，全程不联网"
    echo "     镜像名必须是： $BASE_REF"
    return 1
}
