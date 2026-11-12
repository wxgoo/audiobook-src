#!/bin/sh
# 前端产物整目录校验：重编前端后必须跑，不许只数「构建产物」。
#
# 背景（r24 事故）：nuxt generate 会先清空 app/dist，而 dist 里还有一批
# 非构建资源（static/pdfjs、字体、壁纸、图片、jQuery、toolbox-bridge、icons、robots.txt）。
# 按「构建产物 348 + logo/avatar 14 = 362」的口径清点，会漏掉 395 个真实文件，
# 线上表现是 PDF 直接 404、字体/壁纸/图标静默 404，而 docker build 照样成功。
#
# 用法：
#   sh scripts/check-dist.sh              # 校验仓库里的 app/dist
#   sh scripts/check-dist.sh /path/pkg/audiobook
#   BASELINE=766 sh scripts/check-dist.sh
#
# 退出码：0 通过；1 缺文件/数量不符；2 用法或目录缺失。

set -u
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
DIST="$ROOT/app/dist"
BASELINE="${BASELINE:-766}"

[ -d "$DIST" ] || { echo "!! 找不到 $DIST（先 npm run generate）"; exit 2; }

fail=0
miss() { echo "  !! 缺 $1"; fail=1; }

# 1) 非构建资源：缺一个就报一个（这些不会由 generate 产生）
for p in \
    static/pdfjs/web/viewer.html \
    static/toolbox-bridge.js \
    static/js/jquery-1.11.1.min.js \
    static/fonts \
    static/wallpaper \
    static/images \
    static/mimo_tts/samples/mimo_default.wav \
    icons \
    robots.txt \
    logo \
    avatar
do
    [ -e "$DIST/$p" ] || miss "$p"
done

# 2) 关键目录的数量下限（目录在但空 = generate 把它清了）
for pair in "static/pdfjs:369" "static/fonts:3" "static/wallpaper:4" "static/images:4" "static/mimo_tts/samples:9" "icons:1"
do
    d=${pair%%:*}; n=${pair##*:}
    [ -d "$DIST/$d" ] || continue
    c=$(find "$DIST/$d" -type f | wc -l | tr -d ' ')
    echo "  $d: $c 个文件（下限 $n）"
    [ "$c" -ge "$n" ] || { echo "  !! $d 只有 $c 个，少了——多半被 generate 清空后没从 public/ 带出"; fail=1; }
done

# 3) 整目录文件数基线：dist 的完整性只能按整目录算
total=$(find "$DIST" -type f | wc -l | tr -d ' ')
echo "  app/dist 文件总数: $total（基线 $BASELINE）"
if [ "$total" -ne "$BASELINE" ]; then
    echo "  !! 文件数与基线不一致：$total != $BASELINE"
    echo "     - 偏少：generate 清空 dist 后丢非构建资源 → 确认 public/ 完整（dir.static=../public）"
    echo "     - 偏多：可能有旧 chunk 残留 → 引用扫描确认后再删，别按「看起来像垃圾」处理"
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    echo ""
    echo "前端产物校验失败：不要打包、不要构建镜像。"
    echo "修复参考：docs/开发指南.md 踩坑 #19；复盘：docs/故障复盘-读者组转圈.md"
    exit 1
fi

echo "OK：app/dist 整目录校验通过（$total 个文件，pdfjs/toolbox/字体/壁纸/图标齐全）"
