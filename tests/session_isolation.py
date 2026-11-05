# -*- coding: utf-8 -*-
"""测试之间的 session 隔离小工具。

`webserver.models` 的 session 绑定、`AsyncService` 单例上的 db / scoped_session
都是**进程级全局状态**。测试为了用独立内存库，会把它们临时改掉；不还原就会
把脏值漏给后面的用例——典型症状是「单跑每个文件都绿，连跑成片 500」：

    test_service → test_scan_snapshot → test_upload
      snapshot 把单例的 scoped_session 换成自己的内存库，tearDown 里 remove 掉；
      upload 里上传接口触发注册服务，`AsyncService.setup()` 拿到那个已失效的
      session，`'str'/'_Session' object has no attribute execute`，整个上传 500。

所以凡是 `models.bind_session()` 或改写单例属性的用例，都应当在 setUp 里记下
旧值、tearDown 里还原。
"""

_MISSING = object()


def restore_models_session(previous):
    """把 `webserver.models` 的 session 绑定还原成 `previous`（None 表示解绑）。

    用 `bind_session(None)` 不做「解绑」——那之后任何模型调用都会炸在
    `RuntimeError: models._session() 未绑定`。这里要的是「恢复成测试开始前的样子」，
    没绑过就保持没绑，绑过就绑回原来那个 factory。
    """
    from webserver import models

    if previous is None:
        return
    models.bind_session(previous)
