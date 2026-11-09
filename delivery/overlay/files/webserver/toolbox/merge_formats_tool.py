"""
格式合并工具

将两本书名相同但格式不同的书籍合并：把来源书籍的格式文件复制到目标书籍，
然后删除来源书籍。执行速度较快，不需要后台任务进度追踪。
@author: PoxenStudio, 2026
"""
import logging

from webserver.i18n import _
from webserver.services import AsyncService
from webserver.toolbox.base_tool import BaseTool


class MergeFormatsTool(BaseTool):
    service_item_name = ""  # 不使用后台任务

    @staticmethod
    def info():
        # 4.6.0-build.27：工具箱入口合并。「格式合并」（两本书格式归一）与
        # 「格式精简」（全库批量删格式）统一由 format_tools 页的两个 Tab 承载。
        # 两个后端工具类和各自的 API 都保留，只合并入口与工具卡。
        return {
            "tool_id": "merge_formats_tool",
            "name": "格式合并 / 精简",
            "description": "格式整理：两本书的格式合并去重（原格式合并）＋全库批量删除指定格式（原格式精简）",
            "revision": "0.2.0",
            "author": "PoxenStudio",
            "publish_date": "2025-05-19",
            "page": "format_tools",
        }

    @AsyncService.register_function
    def merge(self, source_book_id: int, target_book_id: int) -> dict:
        """合并 source 书籍的格式到 target 书籍，并删除 source 书籍。

        :param source_book_id: 来源书籍 ID（合并后删除）
        :param target_book_id: 目标书籍 ID（保留）
        :return: {"added_formats": [...], "deleted_book_id": int}
        :raises RuntimeError: 合并或删除失败时抛出
        """
        if source_book_id == target_book_id:
            raise RuntimeError(_("来源书籍和目标书籍不能相同"))

        added = self.api.calibre.merge_formats(source_book_id, target_book_id)

        if not added:
            raise RuntimeError(_("没有可合并的格式"))

        logging.info(
            "[MergeFormatsTool] Merged formats %s from book %d to %d; deleting source",
            added, source_book_id, target_book_id,
        )

        self.api.calibre.delete_book(source_book_id)

        return {
            "added_formats": added,
            "deleted_book_id": source_book_id,
        }
