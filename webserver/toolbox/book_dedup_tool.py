"""重复书清理——工具箱内置工具的注册壳。

实际的页面在 app/src/pages/toolbox/book_dedup.vue（/toolbox/book_dedup），
后端在 webserver/handlers/book_dedup.py（/api/admin/book_dedup/*），
业务逻辑在 webserver/services/book_dedup.py。

这里只提供 info() 供 ToolSet 注册，让工具出现在 /admin/toolbox 列表里。
管理菜单入口保留，工具箱里也能看到，两边不冲突。
"""


class BookDedupTool:
    @staticmethod
    def info() -> dict:
        return {
            "tool_id": "book_dedup",
            "name": "重复书清理",
            "description": "扫描同名/同作者/同 ISBN 的重复书籍，预览合并方案后一键合并：保留主记录、迁移格式与音频、删除冗余",
            "revision": "0.1.0",
            "author": "MyBooks",
            "publish_date": "2026-11-04",
        }
