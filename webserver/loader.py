#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import logging
import os
import shutil
import sys
import traceback

DEFAULT_GOOGLE_ANALYTICS_ID = "G-LLF01B5ZZ8"


class SettingsLoader(dict):
    def __init__(self, *args, **kwargs):
        super(SettingsLoader, self).__init__(*args, **kwargs)
        self.loadfile()

    def clear(self):
        for key in list(self.keys()):
            self.pop(key)

    def set_store_path(self):
        p = self.get("settings_path", "").strip()
        if not os.path.isdir(p):
            p = os.path.dirname(__file__)
        if sys.path[0] != p:
            sys.path.insert(0, p)
        return p

    def loadfile(self):
        try:
            import webserver.settings

            self.update(webserver.settings.settings)
        except Exception:
            logging.error(traceback.format_exc())
            pass

        self.set_store_path()

        try:
            import auto
            self.update(auto.settings)
        except Exception:
            pass

        try:
            import manual
            self.update(manual.settings)
        except Exception:
            pass

    def dumpfile(self, filename="auto.py"):
        s = "\n".join("%-30s: %s," % (repr(k), repr(v)) for k, v in sorted(self.items()))
        code = (
            u"""#!/usr/bin/env python3
#-*- coding: UTF-8 -*-

import os
settings = {
"""
            + s
            + """
}
"""
        )

        d = self.set_store_path()
        py = os.path.join(d, filename)
        pyc = os.path.join(d, filename + "c")
        logging.info("saving settings file: %s" % py)
        # 覆盖前先留一份上一版：设置被误抹时（历史上有分组配置丢过两次），
        # auto.py.bak 是唯一能把内容捞回来的地方。只留最近一份，不会无限增长。
        # 备份失败只告警——磁盘满/只读不该让这次保存一起失败。
        try:
            if os.path.exists(py):
                shutil.copyfile(py, py + ".bak")
        except Exception:
            logging.warning("backup %s failed", py, exc_info=True)
        with open(py, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            os.remove(pyc)
        except Exception:
            pass

    def loads(self, text):
        self.update(json.loads(text))

    def dumps(self):
        return json.dumps(self)


_settings = SettingsLoader()
CONF = _settings
if CONF.get("google_analytics_id", "").strip() == DEFAULT_GOOGLE_ANALYTICS_ID:
    CONF["google_analytics_id"] = ""  # disable it by default


def get_settings():
    CHECKING_KEYS = ("nuxt_env_path", "html_path", "i18n_path", "static_path", "resource_path")
    for key in CHECKING_KEYS:
        key_value = _settings.get(key, "")
        if key_value and key_value.startswith("/var/www/talebook/"):
            _settings[key] = key_value.replace("/var/www/talebook/", "/var/www/mybooks/")
    return _settings
