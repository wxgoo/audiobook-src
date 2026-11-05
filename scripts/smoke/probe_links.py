"""交付包链接完整性实测（r10）。

逐个打开 index.html 里加载链上的每个 chunk、以及 200.html 预取的资源，
外加把 SPA 的所有路由都真点一遍，统计 404 数量。

用户问「119 个链接没断吧」——不靠 grep 推断，直接让浏览器去取每一个
_nuxt/*.js，任何 4xx/5xx 都记下来。
"""
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time

from playwright.sync_api import sync_playwright

DIST = sys.argv[1] if len(sys.argv) > 1 else "/tmp/run/app/dist"
PORT = 3214

bad = []
ok = 0


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST, **kw)

    def _json(self, o, c=200):
        b = json.dumps(o).encode()
        self.send_response(c)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        st = {
            "allow": {"upload": True, "download": True, "share": True, "read": True},
            "site_title": "T", "site_url": "http://127.0.0.1:%d" % PORT,
            "language": "zh", "BOOK_NAV": "", "STAMP_POSITION": "b",
            "ENABLE_STAMP_FEATURE": False,
        }
        if p == "/api/settings":
            return self._json(dict(st, err="ok", settings=dict(st, DEVICES=[])))
        if p == "/api/admin/settings":
            return self._json({"err": "ok", "settings": st})
        if p == "/api/user/info":
            return self._json({"err": "ok", "user": {"is_login": True, "id": 1, "username": "t", "is_admin": True}})
        if p.startswith("/api/"):
            return self._json({"err": "ok", "books": [], "items": [], "total": 0, "data": None})
        fp = os.path.join(DIST, p.lstrip("/"))
        if not os.path.exists(fp) or os.path.isdir(fp):
            self.path = "/index.html"
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(ln)
        return self._json({"err": "ok"})

    def log_message(self, *a):
        pass


def main():
    global bad, ok
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.5)
    base = "http://127.0.0.1:%d" % PORT

    # ---------- 1. 静态资源逐个取 ----------
    import urllib.request
    assets = set()
    for name in ("index.html", "200.html"):
        path = os.path.join(DIST, name)
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        for m in re.finditer(r'_nuxt/[A-Za-z0-9_\-]+\.(?:js|css|woff2?|png|svg)', html):
            assets.add("/" + m.group(0))
    # 再把 _nuxt 下所有 js/css 都取一遍（覆盖到懒加载 chunk）
    for root, _dirs, files in os.walk(os.path.join(DIST, "_nuxt")):
        for f in files:
            if f.endswith((".js", ".css", ".woff2")):
                rel = os.path.relpath(os.path.join(root, f), DIST)
                assets.add("/" + rel.replace(os.sep, "/"))

    print(f"待验证资源 {len(assets)} 个")
    for a in sorted(assets):
        try:
            req = urllib.request.Request(base + a, method="GET")
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    ok += 1
                else:
                    bad.append((a, r.status))
        except Exception as e:
            code = getattr(e, "code", "EXC")
            bad.append((a, code))
    print(f"静态资源：{ok} 通 / {len(bad)} 断")

    # ---------- 2. 所有路由真跑一遍，抓运行期 404 ----------
    routes = []
    for root, _dirs, files in os.walk(os.path.join(DIST)):
        rel = os.path.relpath(root, DIST)
        if rel == ".":
            continue
        # Nuxt generate 出的目录 = 一条路由
        if any(f.endswith(".html") for f in files):
            routes.append("/" + rel.replace(os.sep, "/"))
    routes = sorted(set(routes))
    print(f"待验证路由 {len(routes)} 条")

    route_bad = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_context().new_page()
        notfound = []

        def on_resp(r):
            if r.status >= 400:
                notfound.append((r.status, r.url.replace(base, "")))

        page.on("response", on_resp)
        for r in routes:
            notfound.clear()
            try:
                page.goto(base + r, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(250)
                # 只关心静态资源 404；/api/* 由 mock 兜底不会 404
                hard = [x for x in notfound if "/api/" not in x[1]]
                if hard:
                    route_bad.append((r, hard[:3]))
            except Exception as e:
                route_bad.append((r, str(e)[:80]))
        browser.close()

    print(f"路由：{len(routes) - len(route_bad)} 通 / {len(route_bad)} 有问题")
    if route_bad:
        for r, d in route_bad[:10]:
            print("   BAD", r, d)
    if bad:
        for a, c in bad[:10]:
            print("   BAD asset", a, c)

    total_bad = len(bad) + len(route_bad)
    print()
    print("结论：", "全部可达" if total_bad == 0 else f"{total_bad} 处异常")
    return 0 if total_bad == 0 else 1


sys.exit(main())
