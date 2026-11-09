#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""「版本与更新」独立功能的后端接口（仅管理员）。

路由：
  GET  /api/admin/version/status?force=1     当前/最新修订、更新方式、备份列表
  POST /api/admin/version/check              立即重新检测（绕过 5 分钟缓存）
  POST /api/admin/version/apply              一键在线热更新（仅后端修订可用）
  POST /api/admin/version/rollback           回滚到某次备份
  POST /api/admin/version/auto               自动检测开关
"""
import logging
import sys

import tornado
import tornado.ioloop

from webserver import loader
from webserver.base.setting_saver import SettingsSaver
from webserver.handlers.base import BaseHandler, js, is_admin
from webserver.i18n import _
from webserver.services import version_check as vc

CONF = loader.get_settings()
AUTO_KEY = "AUTO_CHECKING_NEW_VERSION"


def _schedule_restart(self):
    logging.warning("[VERSION] 在线更新完成，进程即将退出由 supervisor 拉起")
    tornado.ioloop.IOLoop.current().call_later(2, lambda: sys.exit(0))


class VersionStatus(BaseHandler):
    @js
    @is_admin
    def get(self):
        force = self.get_argument("force", "") in ("1", "true", "yes")
        rsp = vc.status(force=force)
        rsp["auto_check"] = bool(CONF.get(AUTO_KEY, True))
        return rsp


class VersionCheck(BaseHandler):
    @js
    @is_admin
    async def post(self):
        loop = tornado.ioloop.IOLoop.current()
        rsp = await loop.run_in_executor(None, vc.status, True)
        rsp["auto_check"] = bool(CONF.get(AUTO_KEY, True))
        rsp["msg"] = _("检测完成")
        return rsp


class VersionApply(BaseHandler):
    @js
    @is_admin
    async def post(self):
        revision = self.get_argument("revision", "").strip()
        if not revision:
            return {"err": "params.missing", "msg": _("缺少修订号")}
        loop = tornado.ioloop.IOLoop.current()
        rsp = await loop.run_in_executor(None, vc.apply_update, revision)
        rsp = dict(rsp)
        rsp["msg"] = _("更新已应用，服务正在重启，请稍候刷新页面")
        _schedule_restart(self)
        return rsp


class VersionRollback(BaseHandler):
    @js
    @is_admin
    async def post(self):
        backup_id = self.get_argument("backup_id", "").strip() or None
        loop = tornado.ioloop.IOLoop.current()
        rsp = await loop.run_in_executor(None, vc.rollback, backup_id)
        rsp = dict(rsp)
        rsp["msg"] = _("已回滚，服务正在重启，请稍候刷新页面")
        _schedule_restart(self)
        return rsp


class VersionAutoCheck(BaseHandler):
    @js
    @is_admin
    def post(self):
        enabled = self.get_argument("enabled", "") in ("1", "true", "yes")
        args = loader.SettingsLoader()
        args[AUTO_KEY] = enabled
        SettingsSaver().save_extra_settings(args)
        CONF[AUTO_KEY] = enabled
        return {"err": "ok", "auto_check": enabled,
                "msg": _("已开启自动检测") if enabled else _("已关闭自动检测")}


def routes():
    return [
        (r"/api/admin/version/status", VersionStatus),
        (r"/api/admin/version/check", VersionCheck),
        (r"/api/admin/version/apply", VersionApply),
        (r"/api/admin/version/rollback", VersionRollback),
        (r"/api/admin/version/auto", VersionAutoCheck),
    ]
