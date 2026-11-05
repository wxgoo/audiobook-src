"""交付产物形态测试（4.6.0-19 r11）。

r11 出包时踩过一个坑：构建用的是 `nuxt generate`（默认会预渲染每页 HTML），
而不是 `nuxt generate --spa`。产物里的 `/admin/users/index.html` 变成带
`data-server-rendered` 的完整 DOM，运行时 hydrate 与该 DOM 不匹配，
/admin/users 直接落到 error 布局显示「500 服务正在启动中」。

这个错误只在浏览器里点得出来——`nuxt generate` 自己退出码是 0，
链接探测（只查文件在不在）也全绿。所以这里钉住两件事：
  1. 构建命令必须是 --spa（防止有人照着 package.json 的 generate 直接跑）
  2. 产物里的页面 HTML 不能带 data-server-rendered（兜住"手滑重生成"）
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
DIST = os.path.join(APP, "dist")


def test_build_script_uses_spa_flag():
    """package.json 的 generate 必须带 --spa，否则产物会预渲染。"""
    import json

    with open(os.path.join(APP, "package.json"), encoding="utf-8") as fp:
        pkg = json.load(fp)
    scripts = pkg.get("scripts", {})
    gen = scripts.get("generate", "")
    assert "--spa" in gen, (
        "generate 脚本必须用 `nuxt generate --spa`：本项目页面全依赖客户端会话，"
        "预渲染的 DOM 会与 hydrate 不匹配，导致 /admin/* 落到 500 错误页"
    )


def test_dist_pages_are_spa_shells():
    """产物里的每个路由 HTML 都应该是同一份 SPA 外壳，不带服务端标记。

    dist 不存在时跳过（CI 里可能只跑源码测试）。
    """
    if not os.path.isdir(DIST):
        return

    offenders = []
    sampled = 0
    for dirpath, _dirnames, filenames in os.walk(DIST):
        if "index.html" not in filenames:
            continue
        rel = os.path.relpath(os.path.join(dirpath, "index.html"), DIST)
        # _nuxt 下没有页面；static 是阅读器/字体等纯静态资源
        if rel.startswith("_nuxt") or rel.startswith("static"):
            continue
        sampled += 1
        with open(os.path.join(dirpath, "index.html"), encoding="utf-8") as fp:
            head = fp.read(4000)
        if "data-server-rendered" in head:
            offenders.append(rel)

    assert sampled > 0, "dist 里没有找到任何页面 HTML，产物可能没生成"
    assert not offenders, (
        "以下页面被预渲染了（应只有 SPA 外壳）：%s\n"
        "请用 `npx nuxt generate --spa` 重新生成" % offenders[:5]
    )


def test_spa_shell_size_is_uniform():
    """所有页面 HTML 应当几乎等长（同一份外壳），长度差异大说明混进了预渲染页。"""
    if not os.path.isdir(DIST):
        return
    sizes = {}
    for dirpath, _dirnames, filenames in os.walk(DIST):
        if "index.html" not in filenames:
            continue
        rel = os.path.relpath(os.path.join(dirpath, "index.html"), DIST)
        if rel.startswith("_nuxt") or rel.startswith("static"):
            continue
        sizes[rel] = os.path.getsize(os.path.join(dirpath, "index.html"))

    if len(sizes) < 5:
        return
    vals = sorted(sizes.values())
    smallest, largest = vals[0], vals[-1]
    assert largest <= smallest * 1.5, (
        "页面 HTML 体积差异过大（%d ~ %d），疑似混入预渲染页：%s"
        % (smallest, largest, [k for k, v in sizes.items() if v > smallest * 1.5][:5])
    )
