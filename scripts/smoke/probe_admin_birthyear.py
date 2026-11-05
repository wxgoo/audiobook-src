"""浏览器实测 r11：管理员用户页的「出生年份」列与「修改年龄」对话框。

为什么必须真点一遍：这两处的数据流是
    后端 {"birth_year": 1996, "age": 30}
      → 列表列展示 age + (birth_year)
      → 打开对话框要回填 birth_year（回填 age 的话管理员一保存就变成
        「1900 年出生」或直接被范围校验拦下）
  只看源码很容易漏掉第二步，r10 就吃过「函数写好了却没人调用」的亏。

后端在这里是 mock：只关心前端有没有正确把 birth_year 送出去、有没有
把派生年龄显示出来。
"""
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

DIST = sys.argv[1] if len(sys.argv) > 1 else "/tmp/run/app/dist"
PORT = 3212
CUR_YEAR = datetime.now().year

ok_count = 0
fail = []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
        print("PASS " + name)
    else:
        fail.append((name, detail))
        print("FAIL " + name + ("  " + str(detail) if detail else ""))


USERS = [
    {
        "id": 1, "username": "admin", "name": "Admin", "email": "a@b.com",
        "admin": True, "is_admin": True, "active": True, "allow_review": True,
        "birth_year": 1985, "age": CUR_YEAR - 1985,
        "read_limit": 0, "limit_categories": "", "limit_tags": "",
        "read_count": 0, "push_count": 0, "download_count": 0,
        "total_reading_seconds": 0, "create_time": "2025-01-01 00:00:00",
        "update_time": "2025-01-01 00:00:00", "access_time": "2025-01-01 00:00:00",
        "extra": {"upload_history_count": 0}, "vipquota": 0,
    },
    {
        "id": 2, "username": "kid", "name": "Kid", "email": "k@b.com",
        "admin": False, "is_admin": False, "active": True, "allow_review": True,
        "birth_year": 2014, "age": CUR_YEAR - 2014,
        "read_limit": 0, "limit_categories": "", "limit_tags": "",
        "read_count": 0, "push_count": 0, "download_count": 0,
        "total_reading_seconds": 0, "create_time": "2025-01-01 00:00:00",
        "update_time": "2025-01-01 00:00:00", "access_time": "2025-01-01 00:00:00",
        "extra": {"upload_history_count": 0}, "vipquota": 0,
    },
    {
        # 历史用户：birth_year=0，列表应显示「未填」而不是 0 岁
        "id": 3, "username": "legacy", "name": "Legacy", "email": "l@b.com",
        "admin": False, "is_admin": False, "active": True, "allow_review": True,
        "birth_year": 0, "age": 0,
        "read_limit": 0, "limit_categories": "", "limit_tags": "",
        "read_count": 0, "push_count": 0, "download_count": 0,
        "total_reading_seconds": 0, "create_time": "2025-01-01 00:00:00",
        "update_time": "2025-01-01 00:00:00", "access_time": "2025-01-01 00:00:00",
        "extra": {"upload_history_count": 0}, "vipquota": 0,
    },
]

posts = []


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST, **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        allow = {"upload": True, "download": True, "share": True, "read": True}
        st = {
            "allow": allow, "site_title": "Test",
            "site_url": "http://127.0.0.1:%d" % PORT, "language": "zh",
            "BOOK_NAV": "", "STAMP_POSITION": "bottom-right",
            "ENABLE_STAMP_FEATURE": False, "allow_registration": True,
            "DEVICES": [],
        }
        if p == "/api/settings":
            return self._json(dict(st, err="ok", settings=dict(st, DEVICES=[])))
        if p == "/api/admin/settings":
            return self._json({"err": "ok", "settings": st})
        if p == "/api/user/info":
            return self._json({"err": "ok", "user": {
                "id": 1, "username": "admin", "name": "Admin", "admin": True,
                "is_admin": True, "permission": "", "avatar": "reader.svg",
            }})
        if p == "/api/admin/users":
            # 真实形状：{users: {items, total}, settings: {...}}
            return self._json({
                "err": "ok",
                "users": {"items": USERS, "total": len(USERS)},
                "settings": {"allow_read_range_setting": True,
                             "enable_download_quota": False},
                "sys": {"allow": allow},
            })
        if p.startswith("/api/"):
            return self._json({"err": "ok", "sys": {"allow": allow}})
        fp = os.path.join(DIST, p.lstrip("/"))
        if not os.path.exists(fp) or os.path.isdir(fp):
            self.path = "/index.html"
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln).decode() if ln else ""
        posts.append((self.path, body))
        return self._json({"err": "ok"})

    def log_message(self, *a):
        pass


def main():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.5)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        page.goto(f"http://127.0.0.1:{PORT}/admin/users", wait_until="networkidle")
        page.wait_for_timeout(2000)

        body = page.evaluate("() => document.body.innerText")
        if "404" in body[:200] and "This page could not be found" in body:
            check("管理员页可访问", False, body[:300])
            browser.close()
            return

        check("管理员页可访问", "kid" in body or "admin" in body, body[:300])
        check("表头出现年龄（出生年份）",
              ("出生年份" in body) or ("birth year" in body.lower()), body[:600])

        # 列表：派生年龄 + 括号里的出生年份
        check("显示派生的年龄", str(CUR_YEAR - 2014) in body, body[:800])
        check("显示出生年份", "2014" in body, body[:800])
        # r12 改版：未填不再显示「未填」chip，改为可点击的灰色「—」
        check("未填用户不再显示「未填」chip",
              ("未填" not in body) and ("Not set" not in body), body[:800])

        # 打开 kid 行的账号管理菜单
        menus = page.locator("button", has_text="账号管理")
        if not menus.count():
            menus = page.locator("button", has_text="Account")
        n = menus.count()
        print("  账号管理按钮数:", n)
        check("每行都有账号管理入口", n >= 1, n)

        # 第 2 行（kid）的菜单
        target = menus.nth(1) if n > 1 else menus.first
        target.click()
        page.wait_for_timeout(700)
        menu_txt = page.evaluate("() => document.body.innerText")
        check("菜单有「修改年龄（出生年份）」",
              ("修改年龄" in menu_txt) or ("Change age" in menu_txt), menu_txt[-500:])

        item = page.locator("text=/修改年龄|Change age/").last
        item.click()
        page.wait_for_timeout(900)

        dlg = page.evaluate("() => document.body.innerText")
        check("对话框标题含出生年份",
              ("修改年龄（出生年份）" in dlg) or ("birth year" in dlg.lower()), dlg[-600:])

        # 关键：回填的必须是出生年份（2014），不是年龄（12）
        inputs = page.locator(".v-dialog input")
        print("  对话框 input 数:", inputs.count())
        if inputs.count():
            val = inputs.first.input_value()
            check("对话框回填出生年份 2014（不是年龄）", val == "2014",
                  "实际回填: %r" % val)

        # 改成 2012，确认预览年龄与提交体
        inputs.first.fill("2012")
        page.wait_for_timeout(600)
        dlg2 = page.evaluate("() => document.body.innerText")
        check("对话框实时回显年龄", str(CUR_YEAR - 2012) in dlg2, dlg2[-500:])

        save = page.locator(".v-dialog button", has_text="保存")
        if not save.count():
            save = page.locator(".v-dialog button", has_text="Save")
        posts.clear()
        save.last.click()
        page.wait_for_timeout(1200)

        age_posts = [p for p in posts if p[0].startswith("/api/")]
        check("发出了保存请求", bool(age_posts), posts)
        if age_posts:
            payload = age_posts[-1][1]
            check("请求体带 birth_year=2012", '"birth_year"' in payload and "2012" in payload,
                  payload[:300])
            check("请求体不再带整数岁 age",
                  not re.search(r'"age"\s*:', payload), payload[:300])

        # 未填行「补填」入口的可点性由 probe_dash_click.py 专门验（盒模型 + 9 点位
        # 真实鼠标点击）。这里不再重复，避免两处断言各自随文案漂移——
        # 之前就因为文案从「—」改成「补填」，这里的旧断言一直红着。
        check("无 JS 运行时错误",
              not [e for e in errs if "ResizeObserver" not in e], errs[:3])
        browser.close()


main()
print()
print(f"通过 {ok_count} 项，失败 {len(fail)} 项")
if fail:
    for nm, d in fail:
        print("  -", nm, d)
sys.exit(1 if fail else 0)
