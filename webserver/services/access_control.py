#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""统一访问控制门面（AccessControl）。

为什么有这个文件
----------------
项目的权限判定历史上分散在 5 套机制里，口径靠人肉同步，反复出
「分类树计数走一套、书列表走另一套」「管理员豁免这边写那边漏」的 bug
（见 CHANGELOG r14/r16/r20）。随 r45 移除读者组定制层、跟上游 4.7.0 对齐后，
判定收敛为：

  * **管理员豁免**  is_admin()          —— 散落在 74 处（42 处是安全闸）
  * **阅读范围**    is_book_visible()   —— 已收敛到 base._book_matches_limits
  * **操作权限位**  Reader.can_*()      —— 已是模型方法（models.py）
  * **访客/分享**   BookAccessService   —— 已是门面服务
  * **模块门控**    modules.module_enabled + ModuleGateMixin —— 已是门面/装饰器

其中后三套本身已经是"统一入口"，再包一层只是换名字、零行为收益。
所以本门面只做两件事：

1. **真正散落的判定收口到这里**：is_admin / reading_range / book_visible。
   `BaseHandler.is_admin()` 等方法内部转调本门面 —— 调用点一行不改，
   口径却只有一个来源（改这里，全站生效）。
2. **提供统一 import 入口**：re-export BookAccessService / modules 的判定，
   新代码从这一个模块 import 即可，不必记住判定散在哪个文件。

设计原则：**门面本身不复制任何判定逻辑**，只做转发与单一来源收口。
这样"统一口径"与"零行为变化"可以同时成立。
"""

from webserver.services.book_access_service import BookAccessService
from webserver.services.reading_range import is_admin as _is_admin, reading_range_of as _reading_range_of
from webserver.base import modules as _modules


class AccessControl:
    """权限判定统一门面（全部静态方法，无状态、可直接单测）。"""

    # ---- 管理员豁免：单一口径来源 ----
    @staticmethod
    def is_admin(user, superuser: bool = False) -> bool:
        """用户是否为管理员。None/匿名一律 False；superuser 是运维快捷身份。

        BaseHandler.is_admin() 内部转调这里；所有需要管理员豁免的判定
        （包括阅读范围、书籍归属、后台接口）共用这一份语义。
        """
        # r47：判定本体抽到 services/reading_range.py（WebDAV 也共用），此处转调。
        return _is_admin(user, superuser)

    # ---- 阅读范围：直接读用户字段（上游 4.7.0 口径）----
    @staticmethod
    def reading_range_of(user, allow_range_setting: bool = True) -> dict:
        """用户的阅读范围限制，返回 {read_limit, limit_categories, limit_tags}。

        上游口径：直接读用户自己的三个字段（读者组定制层已随 r45 移除）。
        allow_range_setting=False 时视为不限（全局开关关闭的快路）。
        """
        return _reading_range_of(user, allow_range_setting)

    @staticmethod
    def book_visible(handler, book) -> bool:
        """复用 BaseHandler.is_book_visible 的判定（避免在门面里复制逻辑）。"""
        return handler.is_book_visible(book)

    # ---- re-export：已有门面，提供统一 import 入口（纯别名，不复制逻辑）----
    guest_read_allowed = staticmethod(BookAccessService.guest_read_allowed)
    guest_download_allowed = staticmethod(BookAccessService.guest_download_allowed)
    guest_upload_allowed = staticmethod(BookAccessService.guest_upload_allowed)
    guest_push_allowed = staticmethod(BookAccessService.guest_push_allowed)
    share_read_granted = staticmethod(BookAccessService.share_read_granted)
    share_download_granted = staticmethod(BookAccessService.share_download_granted)

    module_on = staticmethod(_modules.module_enabled)
    require_login_effective = staticmethod(_modules.require_login_effective)
    opds_anonymous_allowed = staticmethod(_modules.opds_anonymous_allowed)
