"""电子书音频合并——工具箱内置工具的注册壳。

实际的页面在 app/src/pages/toolbox/book_dedup.vue（/toolbox/book_dedup），
后端在 webserver/handlers/book_dedup.py（/api/admin/book_dedup/*），
业务逻辑在 webserver/services/book_dedup.py。

这里只提供 info() 供 ToolSet 注册，让工具出现在 /admin/toolbox 列表里。
管理菜单入口保留，工具箱里也能看到，两边不冲突。

v0.1.1 改名与 tool_id 调整：原名「重复书清理」容易与外部「查重合并」类工具
混淆，且安装外部工具（tool_id 撞车 book_dedup）会覆盖本工具。改为
tool_id=ebook_audio_merge + page=book_dedup——page 决定跳转（页面与
后端路由不动），tool_id 只作注册键，外部 zip 装到 book_dedup 目录不再影响本工具。
"""


class BookDedupTool:
    @staticmethod
    def info() -> dict:
        return {
            "tool_id": "ebook_audio_merge",
            "page": "book_dedup",
            "name": "电子书音频合并",
            "description": "把「先导电子书、后加同名音频」留下的两条重复记录合并成一条：保留带电子书的那本，音频迁入它的 .audio/，删除冗余记录（合并前自动备份用户库）",
            "revision": "0.1.1",
            "author": "MyBooks",
            "publish_date": "2026-11-04",
        }
