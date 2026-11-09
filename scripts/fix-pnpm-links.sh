#!/bin/sh
# fix-pnpm-links.sh —— 修复被 Windows 打包丢掉符号链接的 pnpm node_modules
#
# 现象：pnpm 的 node_modules 顶层与每个 .pnpm/*/node_modules 内的符号链接，
#       经 Windows 拷贝/打包后变成 0 字节文件或空目录，运行时报
#       "Cannot find module" 或加载到残缺包（version: undefined）。
#
# 原理：.pnpm/<pkg>@<ver>[_peer后缀]/node_modules/<pkg> 是实体（完好），
#       各依赖处的链接按「包名 → .pnpm 同名条目」重建；
#       同名多版本歧义时，用所在 .pnpm 目录名里的 peer 后缀（形如
#       next@16.2.6_@babel+core@7.29.0_react@19.2.5 中的 react@19.2.5）过滤。
#
# 用法：sh fix-pnpm-links.sh <node_modules 目录绝对路径>
#       例：sh fix-pnpm-links.sh /var/www/myreader/node_modules

set -u

NM=$(cd "$1" 2>/dev/null && pwd) || { echo "!! 目录不存在: $1" >&2; exit 1; }
PNPM_DIR="$NM/.pnpm"
[ -d "$PNPM_DIR" ] || { echo "!! $NM 下没有 .pnpm，不是 pnpm 结构" >&2; exit 1; }

FIXED=0
SKIP=0

# is_broken <path>：退出码 0 = 是丢失符号链接的残留（0 字节文件或空目录）
is_broken() {
    [ -L "$1" ] && return 1                    # 正常链接，不动
    if [ -f "$1" ] && [ ! -s "$1" ]; then return 0; fi
    if [ -d "$1" ] && [ -z "$(ls -A "$1" 2>/dev/null)" ]; then return 0; fi
    return 1
}

# resolve_cand <name> <cont-dirname>：输出唯一候选的 .pnpm 目录名
# 失败返回非 0（1=无候选，2=歧义）
resolve_cand() {
    name=$1; cont=$2
    key=$(printf '%s' "$name" | tr '/' '+')
    cands=""
    for d in "$PNPM_DIR"/"$key"@*; do
        [ -d "$d" ] && cands="$cands ${d##*/}"
    done
    [ -n "$cands" ] || return 1
    set -- $cands
    [ $# -eq 1 ] && { printf '%s' "$1"; return 0; }
    if [ -n "$cont" ]; then
        uniq=""
        for c in $cands; do
            rest=${c#"$key"@}; ver=${rest%%_*}
            case "$cont" in *"$key@$ver"*) uniq="$uniq $c";; esac
        done
        set -- $uniq
        [ $# -eq 1 ] && { printf '%s' "$1"; return 0; }
    fi
    return 2
}

# fix_one <name> <cont-dirname> <目标node_modules目录>
fix_one() {
    name=$1; cont=$2; dir=$3
    cand=$(resolve_cand "$name" "$cont") || {
        SKIP=$((SKIP + 1))
        echo "  ?? $name：候选缺失或歧义（$dir），跳过"
        return 0
    }
    target="$PNPM_DIR/$cand/node_modules/$name"
    if [ ! -d "$target" ]; then
        SKIP=$((SKIP + 1))
        echo "  ?? $name：目标实体不存在（$target），跳过"
        return 0
    fi
    rm -rf "$dir/$name"
    ln -s "$target" "$dir/$name"
    FIXED=$((FIXED + 1))
    echo "  ++ $name -> .pnpm/$cand/node_modules/$name"
}

# repair_dir <node_modules目录> <所属.pnpm目录名，顶层为空>
repair_dir() {
    dir=$1; cont=$2
    [ -d "$dir" ] || return 0
    for entry in "$dir"/*; do
        [ -e "$entry" ] || continue
        base=${entry##*/}
        # 作用域目录 @scope：先修内部 0 字节子项
        if [ -d "$entry" ] && [ "${base#@}" != "$base" ]; then
            for child in "$entry"/*; do
                [ -e "$child" ] || continue
                if is_broken "$child"; then
                    fix_one "$base/${child##*/}" "$cont" "$dir"
                fi
            done
            # 作用域目录整个空了：按 peer 后缀重建内部链接
            if [ -z "$(ls -A "$entry" 2>/dev/null)" ]; then
                scope=${base#@}
                built=0
                for d in "$PNPM_DIR"/"$scope"+*@*; do
                    [ -d "$d" ] || continue
                    dname=${d##*/}                          # 形如 @scope+pkg@1.0.0[_peers]
                    pkg=${dname#"$scope"+}                  # pkg@1.0.0[_peers]
                    pkgname=${pkg%%@*}
                    [ -n "$pkgname" ] || continue
                    pkgver=${pkg#"$pkgname"@}; pkgver=${pkgver%%_*}
                    # 多候选时只在有 peer 后缀可用的情况下过滤，否则跳过
                    if [ -z "$cont" ]; then
                        SKIP=$((SKIP + 1))
                        echo "  ?? $base/$pkgname：顶层空作用域且多候选，跳过"
                        continue
                    fi
                    case "$cont" in
                        *"$scope+$pkgname@$pkgver"*) ;;
                        *) continue;;
                    esac
                    target="$d/node_modules/$base/$pkgname"
                    [ -d "$target" ] || continue
                    rm -rf "$dir/$base/$pkgname"
                    ln -s "$target" "$dir/$base/$pkgname"
                    FIXED=$((FIXED + 1))
                    echo "  ++ $base/$pkgname -> .pnpm/$dname/node_modules/$base/$pkgname"
                    built=$((built + 1))
                done
                [ "$built" -gt 0 ] || rmdir "$entry" 2>/dev/null
            fi
        elif is_broken "$entry"; then
            fix_one "$base" "$cont" "$dir"
        fi
    done
}

echo "==> 修复 .pnpm/*/node_modules 内部链接层"
for d in "$PNPM_DIR"/*/node_modules; do
    [ -d "$d" ] || continue
    dname=${d#"$PNPM_DIR/"}
    dname=${dname%/node_modules}
    repair_dir "$d" "$dname"
done

echo "==> 修复顶层链接层"
repair_dir "$NM" ""

echo "==> 完成：重建 $FIXED 个链接，跳过 $SKIP 个"
[ "$SKIP" -eq 0 ] || echo "    （跳过项请人工确认：多版本歧义或实体缺失）"
