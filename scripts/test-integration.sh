#!/bin/bash
# 搭好「能跑 tests/test_main.py」的环境，然后跑它。
#
# ## 为什么需要这个脚本
#
# tests/test_main.py 有 63 个用例，真启动整站发 HTTP 请求，是覆盖最广的
# 一组测试。但它要两样平时没有的东西：
#
#   1. **calibre 的 Python 库**。书库是 calibre 的 metadata.db，
#      测试直接 import calibre.db.backend。
#   2. **python3.12**。calibre 只支持 3.12（3.11/3.13 都 import 不了）。
#
# 以前没人把这两件事写下来，于是这 63 个用例在任何一台新机器上都是红的，
# 也就没人跑。这个脚本把它们固化成一条命令。
#
# ## 用法
#
#     ./scripts/test-integration.sh                # 建夹具（如缺）+ 跑测试
#     ./scripts/test-integration.sh --rebuild      # 强制重建夹具再跑
#     ./scripts/test-integration.sh -k test_read   # 透传给 pytest
#
# ## 前置（Debian/Ubuntu）
#
#     apt install calibre python3.12 python3.12-dev libzbar0
#
# calibre 的版本无所谓新旧，只要 `import calibre.db.backend` 能成功。

set -o pipefail

cd "$(dirname "$0")/.." || exit 1
ROOT=$(pwd)

PY=""
for cand in python3.12 /usr/bin/python3.12; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "✗ 找不到 python3.12。calibre 只支持 3.12，装一个："
    echo "    apt install calibre python3.12 python3.12-dev libzbar0"
    exit 1
fi

# calibre 的库存放在 /usr/lib/calibre（Debian 打包位置），也支持别的发行版
CALIBRE_LIB=${CALIBRE_PYTHON_PATH:-/usr/lib/calibre}
if [ ! -d "$CALIBRE_LIB" ]; then
    echo "✗ 找不到 calibre：$CALIBRE_LIB 不存在"
    echo "    apt install calibre"
    exit 1
fi

# 直接验证「垫片 + import」这条真实路径，而不是裸 import
# （calibre 永远需要那 5 个 sys 属性，裸 import 必然失败）
if ! "$PY" -c "
import sys
lib = '$CALIBRE_LIB'
sys.path.append(lib)
sys.resources_location = '${CALIBRE_RESOURCES_PATH:-/usr/share/calibre}'
sys.extensions_location = lib + '/calibre/plugins'
sys.executables_location = '/usr/bin'
sys.system_plugins_location = None
import calibre.db.backend
" 2>/dev/null; then
    echo "✗ python3.12 里 import calibre.db.backend 失败。"
    echo "  常见原因：calibre 装的是别的 Python 版本，或缺 libzbar0。"
    echo "  手工排查："
    echo "    python3.12 -c \"import sys; sys.path.append('$CALIBRE_LIB'); \\"
    echo "      sys.resources_location='/usr/share/calibre'; \\"
    echo "      sys.extensions_location='$CALIBRE_LIB/calibre/plugins'; \\"
    echo "      sys.executables_location='/usr/bin'; sys.system_plugins_location=None; \\"
    echo "      import calibre.db.backend\""
    exit 1
fi

# ---- 依赖 ----
if ! "$PY" -c "import tornado, sqlalchemy, social_sqlalchemy" 2>/dev/null; then
    echo "→ 安装 Python 依赖（首次会比较慢）..."
    "$PY" -m pip install --break-system-packages -q -r requirements.txt || {
        echo "✗ 依赖安装失败。手工试："
        echo "    $PY -m pip install --break-system-packages -r requirements.txt"
        exit 1
    }
fi

# ---- 夹具 ----
FORCE=""
ARGS=()
for a in "$@"; do
    if [ "$a" = "--rebuild" ]; then FORCE="--force"; else ARGS+=("$a"); fi
done

if [ -n "$FORCE" ] || [ ! -f tests/cases/library/metadata.db ] || [ ! -f tests/cases/users.db ]; then
    echo "→ 生成测试夹具（用真 calibre 建库，约 30 秒）..."
    "$PY" tests/make_fixtures.py $FORCE || exit 1
fi

# ---- 跑 ----
# 必须在 -c 里先 import 引导垫片：calibre 要求 sys 上有 5 个私有属性，
# 缺一个就 AttributeError: module 'sys' has no attribute 'extensions_location'。
# 垫片用 sys.path.append，不会顶掉项目自己的同名包。
echo
echo "→ 跑 tests/test_main.py"
# 没给文件路径时默认只跑 test_main.py。
# 裸着把 tests/ 全收进来会碰到一批和本脚本无关的收集错误
# （test_upload 要 tests/cases/old.epub 之类的老夹具），噪音太大。
has_path=0
for a in "${ARGS[@]}"; do
    case "$a" in
        tests/*|*/*.py) has_path=1 ;;
    esac
done
if [ $has_path -eq 0 ]; then
    ARGS=("tests/test_main.py" "${ARGS[@]}")
fi

# 用环境变量把参数传给 -c 里的小引导脚本，避免拼引号拼错
PYTHONPATH="$ROOT:$ROOT/..:$CALIBRE_LIB" \
CALIBRE_LIB="$CALIBRE_LIB" \
PYTEST_ARGS="$(printf '%s\n' "${ARGS[@]}")" \
"$PY" -c '
import os, sys
lib = os.environ["CALIBRE_LIB"]
sys.path.append(lib)
if not hasattr(sys, "extensions_location"):
    sys.resources_location = os.path.join(os.path.dirname(lib), "share", "calibre")
    sys.extensions_location = os.path.join(lib, "calibre", "plugins")
    sys.executables_location = "/usr/bin"
    sys.system_plugins_location = None
import pytest
args = [a for a in os.environ["PYTEST_ARGS"].splitlines() if a]
sys.exit(pytest.main(args + ["-q", "-p", "no:cacheprovider"]))
'
rc=$?
if [ $rc -eq 0 ]; then
    echo
    echo "✓ 全部通过"
else
    echo
    echo "✗ 有失败（退出码 $rc）。加 -x 看第一个失败："
    echo "    $0 -x"
fi
exit $rc
