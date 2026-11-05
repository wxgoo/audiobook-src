"""浏览器实测 r11：注册页「出生年份」+ 密码强度提示。

只验前端行为（后端校验由 tests/test_account_password_age_rules.py 覆盖），
除了 r10 已有的三条，r11 新增两条关键点：
  4. 填出生年份后要实时回显「今年几岁」——填错年份能当场发现
  5. 提交的是 birth_year=YYYY 而不是 age=NN（否则后端 parse_birth_year
     永远收不到值，注册直接报「请填写出生年份」）
"""
import http.server
import json
import os
import socketserver
import sys
import threading
import time

from playwright.sync_api import sync_playwright

DIST = sys.argv[1] if len(sys.argv) > 1 else "/tmp/run/app/dist"
PORT = 3211

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


def handler_factory(posts):
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
            st = {
                "allow": {"upload": True, "download": True, "share": True, "read": True},
                "site_title": "Test", "site_url": "http://127.0.0.1:%d" % PORT,
                "language": "zh", "BOOK_NAV": "", "STAMP_POSITION": "bottom-right",
                "ENABLE_STAMP_FEATURE": False, "allow_registration": True,
            }
            if p == "/api/settings":
                return self._json(dict(st, err="ok", settings=dict(st, DEVICES=[])))
            if p == "/api/user/info":
                return self._json({"err": "ok", "user": None})
            if p == "/api/admin/settings":
                return self._json({"err": "ok", "settings": st})
            if p.startswith("/api/"):
                return self._json({"err": "ok"})
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

    return H


def main():
    posts = []
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), handler_factory(posts))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.5)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_context().new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        page.goto(f"http://127.0.0.1:{PORT}/signup", wait_until="networkidle")
        page.wait_for_timeout(1200)

        body = page.evaluate("() => document.body.innerText")
        # 文案随语言变化，这里同时接受中英文（该站点语言由 settings 决定）
        check("注册页渲染出出生年份字段", ("出生年份" in body) or ("Birth year" in body), body[:300])
        check("显示密码强度提示",
              ("至少 6 位" in body) or ("At least 6 characters" in body), body[:300])
        check("显示出生年份用途说明",
              ("图书分级" in body) or ("content rating" in body), body[:300])
        check("显示不得虚报确认项",
              ("虚报" in body) or ("false declaration" in body), body[:500])
        check("勾选项说的是出生年份而非年龄",
              ("真实出生年份" in body) or ("birth year I entered" in body)
              or ("real birth year" in body), body[:500])

        inputs = page.locator("input")
        n = inputs.count()
        print("   input 数量:", n)

        # 填弱密码：纯数字 6 位
        # 顺序：username, password, password2, nickname, email, birthYear
        inputs.nth(0).fill("tester01")
        inputs.nth(1).fill("123456")
        page.wait_for_timeout(400)
        txt = page.evaluate("() => document.body.innerText")
        check("纯数字密码被实时拒绝（太简单）",
              ("太简单" in txt) or ("too weak" in txt), txt[:500])

        # 换成强密码
        inputs.nth(1).fill("Abc123")
        page.wait_for_timeout(400)
        txt2 = page.evaluate("() => document.body.innerText")
        check("Abc123 通过（大小写+数字）",
              ("太简单" not in txt2) and ("too weak" not in txt2), txt2[:500])

        inputs.nth(2).fill("Abc123")
        inputs.nth(3).fill("昵称")
        inputs.nth(4).fill("a@b.com")
        page.wait_for_timeout(300)

        # 年龄留空 + 不勾选，直接点注册
        reg_btn = page.locator("button", has_text="REGISTER").first
        if not reg_btn.count():
            reg_btn = page.locator("button", has_text="注册").first
        reg_btn.click()
        page.wait_for_timeout(800)
        txt3 = page.evaluate("() => document.body.innerText")
        check("出生年份留空不能提交",
              ("请填写出生年份" in txt3) or ("enter your birth year" in txt3), txt3[:500])
        check("未勾选确认不能提交",
              ("请勾选确认" in txt3) or ("confirm your real birth year" in txt3)
              or ("confirm your real age" in txt3), txt3[:500])
        check("提交被拦（没有发出 sign_up 请求）",
              not any("sign_up" in p[0] for p in posts), posts)

        # 先填一个非法年份（未来年份），确认被拦
        inputs.nth(5).fill("2099")
        page.wait_for_timeout(500)
        txt_bad = page.evaluate("() => document.body.innerText")
        check("未来年份被实时拒绝",
              ("出生年份需在" in txt_bad) or ("Birth year must be" in txt_bad), txt_bad[:500])

        # 补出生年份 + 勾选，再提交
        inputs.nth(5).fill("1996")
        page.wait_for_timeout(500)
        # Vuetify 的 checkbox 有 ripple 层挡住原生 input，直接派发 change/click
        page.evaluate("""() => {
            const cb = document.querySelector('input[type=checkbox]');
            cb.click();
        }""")
        page.wait_for_timeout(400)
        txt_age = page.evaluate("() => document.body.innerText")
        # 关键交互：填完年份立刻显示「今年几岁」，填错能当场发现
        expect_age = __import__("datetime").datetime.now().year - 1996
        check("实时回显换算出的年龄",
              str(expect_age) in txt_age, "期望 %d 岁，页面：%s" % (expect_age, txt_age[:400]))

        check("勾选确认后能提交", page.locator("input[type=checkbox]").first.is_checked(),
              page.evaluate("() => document.body.innerText")[:200])
        page.wait_for_timeout(300)
        reg_btn.click()
        page.wait_for_timeout(1200)
        sent = [p for p in posts if "sign_up" in p[0]]
        check("合法表单能提交", bool(sent), posts[-3:])
        if sent:
            check("提交的是 birth_year=1996", "birth_year=1996" in sent[0][1], sent[0][1][:300])
            check("不再提交整数岁 age", "age=19" not in sent[0][1] and "&age=" not in sent[0][1],
                  sent[0][1][:300])

        check("无 JS 运行时错误", not [e for e in errs if "ResizeObserver" not in e], errs[:2])
        browser.close()


main()
print()
print(f"通过 {ok_count} 项，失败 {len(fail)} 项")
if fail:
    for nm, d in fail:
        print("  -", nm, d)
sys.exit(1 if fail else 0)
