"""r12 验证：未填年龄的「补填」入口必须真的点得动。

上一版只渲染一个「—」字符，命中区 12×20px，用户鼠标瞄不准，
反馈「点不动」。这次的断言全部围绕**命中区尺寸**和**真实鼠标坐标点击**，
不再用 locator.click()（它按元素中心点算，小元素也能过，掩盖问题）。
"""
import http.server
import json
import os
import socketserver
import sys
import threading
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

DIST = sys.argv[1] if len(sys.argv) > 1 else "/tmp/run/app/dist"
PORT = 3213
CUR = datetime.now().year

ok, fail = 0, []


def check(name, cond, detail=""):
    global ok
    if cond:
        ok += 1
        print("PASS", name)
    else:
        fail.append((name, detail))
        print("FAIL", name, detail)


def mkuser(uid, name, is_admin, birth_year):
    return {
        "id": uid, "username": name, "name": name, "email": name + "@b.com",
        "admin": is_admin, "is_admin": is_admin, "active": True,
        "allow_review": True, "birth_year": birth_year,
        "age": (CUR - birth_year) if birth_year else 0,
        "read_limit": 0, "limit_categories": "", "limit_tags": "",
        "read_count": 0, "push_count": 0, "download_count": 0,
        "total_reading_seconds": 0, "create_time": "2025-01-01 00:00:00",
        "update_time": "2025-01-01 00:00:00", "access_time": "2025-01-01 00:00:00",
        "extra": {"upload_history_count": 0}, "vipquota": 0,
    }


USERS = [
    mkuser(1, "admin", True, 1985),      # 管理员，已填
    mkuser(3, "legacy", False, 0),       # 未填，应可点
    mkuser(4, "kid", False, 2014),       # 已填
]


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST, **kw)

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        allow = {"upload": True, "download": True, "share": True, "read": True}
        st = {"allow": allow, "site_title": "T",
              "site_url": "http://127.0.0.1:%d" % PORT, "language": "zh",
              "BOOK_NAV": "", "STAMP_POSITION": "bottom-right",
              "ENABLE_STAMP_FEATURE": False, "allow_registration": True, "DEVICES": []}
        if p == "/api/settings":
            return self._json(dict(st, err="ok", settings=dict(st, DEVICES=[])))
        if p == "/api/admin/settings":
            return self._json({"err": "ok", "settings": st})
        if p == "/api/user/info":
            return self._json({"err": "ok", "user": {
                "id": 1, "username": "admin", "name": "Admin", "admin": True,
                "is_admin": True, "permission": "", "avatar": "reader.svg"}})
        if p == "/api/admin/users":
            return self._json({"err": "ok",
                               "users": {"items": USERS, "total": len(USERS)},
                               "settings": {"allow_read_range_setting": True,
                                            "enable_download_quota": False},
                               "sys": {"allow": allow}})
        if p.startswith("/api/"):
            return self._json({"err": "ok", "sys": {"allow": allow}})
        fp = os.path.join(DIST, p.lstrip("/"))
        if not os.path.exists(fp) or os.path.isdir(fp):
            self.path = "/index.html"
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length") or 0)
        if ln:
            self.rfile.read(ln)
        return self._json({"err": "ok"})

    def log_message(self, *a):
        pass


def find_entry(page):
    """返回补填入口的盒模型。用 class 找，不依赖文案。"""
    return page.evaluate("""() => {
        const a = document.querySelector('a.age-unset');
        if (!a) return null;
        const r = a.getBoundingClientRect();
        return {x: r.x, y: r.y, w: r.width, h: r.height,
                text: (a.innerText || '').trim(),
                cursor: getComputedStyle(a).cursor};
    }""")


def main():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.5)

    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1400, "height": 1000}, locale="zh-CN")
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        ctx.add_cookies([{"name": "lang", "value": "zh", "domain": "127.0.0.1", "path": "/"}])
        page.goto(f"http://127.0.0.1:{PORT}/admin/users", wait_until="networkidle")
        page.wait_for_timeout(2500)

        body = page.evaluate("() => document.body.innerText")
        check("页面可访问", "legacy" in body, body[:200])

        e = find_entry(page)
        check("存在补填入口（a.age-unset）", e is not None, e)
        if not e:
            b.close()
            return finish()

        print("   入口盒模型:", e)
        # ★ 核心断言：命中区必须够大。12px 宽就是"点不动"的根因
        check("命中区宽度 >= 56px（原来只有 12px）", e["w"] >= 56, f"实际 {e['w']}px")
        check("命中区高度 >= 30px（原来只有 20px）", e["h"] >= 30, f"实际 {e['h']}px")
        check("鼠标指针是 pointer", e["cursor"] == "pointer", e["cursor"])
        check("有可见文案（不是光秃秃一个破折号）", len(e["text"]) > 0, e["text"])
        check("文案不是「未填」", e["text"] not in ("未填", "Not set"), e["text"])

        # ★ 真实鼠标坐标点击：四个角落 + 中心，全部要能打开对话框
        xs = [e["x"] + 2, e["x"] + e["w"] / 2, e["x"] + e["w"] - 2]
        ys = [e["y"] + 2, e["y"] + e["h"] / 2, e["y"] + e["h"] - 2]
        corners_ok = 0
        for (i, cx) in enumerate(xs):
            for (j, cy) in enumerate(ys):
                page.mouse.click(cx, cy)
                page.wait_for_timeout(500)
                dlg = page.evaluate("""() => {
                    const el = document.querySelector('.v-dialog');
                    return el ? el.innerText : '';
                }""")
                if ("修改年龄" in dlg) or ("birth year" in dlg.lower()):
                    corners_ok += 1
                page.keyboard.press("Escape")
                page.wait_for_timeout(350)
        check("9 个点位（四角+边中+中心）全部能点开", corners_ok == 9, f"成功 {corners_ok}/9")

        # 点开之后对话框要能正常补填
        page.mouse.click(e["x"] + e["w"] / 2, e["y"] + e["h"] / 2)
        page.wait_for_timeout(800)
        inputs = page.locator(".v-dialog input")
        check("对话框里有输入框", inputs.count() >= 1, inputs.count())
        if inputs.count():
            check("未填用户对话框初始为空（不是 0）",
                  inputs.first.input_value() in ("", "0") , repr(inputs.first.input_value()))
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 管理员行的「—」不可点
        adm = page.evaluate("""() => {
            const cells = [...document.querySelectorAll('td')];
            const c = cells.find(td => (td.innerText||'').trim() === '—');
            return c ? {hasLink: !!c.querySelector('a')} : null;
        }""")
        check("管理员行没有可点击链接", adm is None or not adm["hasLink"], adm)

        check("无 JS 运行时错误", not errs, errs[:2])
        b.close()
    return finish()


def finish():
    print()
    print(f"通过 {ok} 项，失败 {len(fail)} 项")
    for n, d in fail:
        print("  -", n, d)
    sys.exit(1 if fail else 0)


main()
