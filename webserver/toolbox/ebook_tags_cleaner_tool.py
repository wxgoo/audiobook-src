# -*- coding: UTF-8 -*-
"""电子书标签清理——工具箱内置工具的注册壳。

实际的页面在 app/src/pages/toolbox/ebook_tags_cleaner.vue（/toolbox/ebook_tags_cleaner），
后端 API 在 webserver/handlers/ebook_tags_cleaner.py（/api/toolbox/ebook_tags_cleaner/*），
业务逻辑在 webserver/services/ebook_tags_cleaner.py。

这里只提供 info() 供 ToolSet 注册，让工具出现在 /admin/toolbox 列表里。

内置化说明：本工具源自外部工具 PoxenStudio/tool_tags_cleaner v0.2.0（「标签清理」），
功能与清理规则保持原版一致，随内置固化进发行版——不再依赖商店安装，也就不会出现
外部 zip 安装/更新把内置槽位顶掉（固化不可卸载）一类的问题。tool_id 用
ebook_tags_cleaner，与商店版 tags_cleaner 完全隔离：即使再安装商店版也互不影响。
"""


class EbookTagsCleanerTool:
    @staticmethod
    def info() -> dict:
        return {
            "tool_id": "ebook_tags_cleaner",
            "page": "ebook_tags_cleaner",
            "name": "电子书标签清理",
            "description": "使用基础规则清理书库中无效的标签，包括广告名称、工具名称、网址等标签",
            "revision": "1.0.0",
            "author": "MyBooks",
            "publish_date": "2026-11-25",
        }
