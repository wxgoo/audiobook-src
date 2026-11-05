#!/usr/bin/env pytest
# -*- coding: UTF-8 -*-


import json
import logging
import os
import sys
import unittest
from unittest import mock

# 项目根 = tests/ 的父目录。**不要**用原来那句
#   testdir = .. / "../../../"   +  sys.path.append(testdir)
# 它有两个毛病，单跑这个文件时都看不出来、只有全量跑才炸：
#   1. `tests/../../../` 比项目根还高两层，压根没有 `webserver/`；
#   2. `append` 把路径排在 sys.path 末尾。pytest 以 `tests/` 为 rootdir 收集时，
#      `tests/` 的父目录（= 项目根）本来就已经在 sys.path 里，只是**排在后面**；
#      而 `tests/` 自己的目录也在里面。于是 `import webserver` 会先命中
#      别的东西（同名目录被当成命名空间包），得到一个空的 `webserver` 模块，
#      后面 `webserver.main` / `webserver.utils` 全部 AttributeError。
# 用 insert(0) 抢到最前面，路径也只到项目根为止。
_PROJECT_ROOT = os.path.realpath(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
testdir = _PROJECT_ROOT

import webserver.main
from webserver.plugins.meta.baike import BaiduBaikeApi

webserver.main.init_calibre()


BAIKE_DATA = {
    "info": {
        "作品名称": "东周列国志",
        "作者": "冯梦龙、蔡元放",
        "创作年代": "明代、清代",
        "文学体裁": "长篇历史演义小说",
        "字数": "800000",
        "title": "东周列国志（冯梦龙所著长篇历史小说）",
        "url": "https://baike.baidu.com/item/%E4%B8%9C%E5%91%A8%E5%88%97%E5%9B%BD%E5%BF%97/2653",
    },
    "tags": ["明代","长篇小说", "历史" ],
    "summary": "《东周列国志》是明末小说家冯梦龙著、清代蔡元放改编的长篇历史演义小说，成书于清代乾隆年间。《东周列国志》写的是西周结束（公元前789年）至秦统一六国（公元前221年），包括春秋、战国五百多年间的历史故事，内容相当丰富复杂。小说描写了周幽王凶残无道，周平王东迁，诸侯国争霸，士大夫势力日益壮大，最终形成七雄对峙局面；批判了昏庸愚昧的昏君暴君，揭示了战争给人民带来的深重灾难；歌颂了赏罚分明的王侯和有胆识的将相勇夫。小说的布局谋篇主次分明，错落有致。每一故事既可独立成篇，又可贯穿一体。人物形象栩栩如生，故事描写引人入胜。[1]",
    "id": "2653",
    "image": "https://bkimg.cdn.bcebos.com/pic/bd3eb13533fa828b9d95cebbf21f4134970a5a37?x-bce-process=image/resize,m_lfit,w_536,limit_1/format,f_jpg",
}


def get_mock_page():
    p = mock.Mock()
    p.get_id.return_value = BAIKE_DATA['id']
    p.get_tags.return_value = BAIKE_DATA['tags']
    p.get_info.return_value = BAIKE_DATA['info']
    # `_metadata` 里是 `normal_cover, mi.cover_url = baike.get_image()` —— 要返回二元组，
    # 给单个字符串会 ValueError: too many values to unpack。
    p.get_image.return_value = (True, BAIKE_DATA['image'])
    p.get_summary.return_value = BAIKE_DATA['summary']
    p.http.url = BAIKE_DATA['info']['url']
    return p

BAIKE_PAGE = get_mock_page()

class TestBaike(unittest.TestCase):
    def test_baike_api(self):
        api = BaiduBaikeApi(copy_image=False)

        # 这一层被重命名过：原先是 `self._baike(page)`，后来拆成
        # 模块级 `Page(title)` + `_metadata(page)`（见 api.py 的 get_book），
        # 再 patch `_baike` 会 AttributeError。现在 patch `Page` 喂假页面，
        # 让真正的 `_metadata` 跑一遍——这样断言的是「字段映射对不对」，
        # 而不是「mock 返回什么就是什么」。
        with mock.patch("webserver.plugins.meta.baike.api.Page", return_value=BAIKE_PAGE):
            # 拿不到合法页面（info 里没有中文名）时返回 None
            BAIKE_PAGE.get_info.return_value = {}
            self.assertIsNone(api.get_book("东周列国志"))

            BAIKE_PAGE.get_info.return_value = BAIKE_DATA["info"]
            d = api.get_book("东周")
            self.assertIsNotNone(d)
            self.assertEqual(d.title, "东周列国志（冯梦龙所著长篇历史小说）")
            self.assertEqual(d.source, "百度百科")

    def test_get_book_strips_numeric_prefix_before_lookup(self):
        """`123_书名` / `7-书名` 这类文件名前缀要先剥掉再查——扫盘导入时
        文件名常带序号，不剥就永远查不到。"""
        api = BaiduBaikeApi(copy_image=False)
        with mock.patch("webserver.plugins.meta.baike.api.Page") as page_cls:
            page_cls.return_value = BAIKE_PAGE
            with mock.patch.object(api, "_metadata", return_value=None):
                api.get_book("12-东周列国志")
            page_cls.assert_called_with("东周列国志")

    def test_get_book_returns_none_when_page_lookup_fails(self):
        """`Page()` 抛异常（网络不可达/词条不存在）时返回 None，不能把异常
        抛给刮削队列——一次查询失败不该中断整批。"""
        api = BaiduBaikeApi(copy_image=False)
        with mock.patch("webserver.plugins.meta.baike.api.Page", side_effect=RuntimeError("boom")):
            self.assertIsNone(api.get_book("东周列国志"))
