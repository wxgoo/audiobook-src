#!/usr/bin/env pytest
# -*- coding: UTF-8 -*-

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
sys.path.append("/home/batkiz/code/talebook")

import webserver.main
from webserver.plugins.meta.youshu import YoushuApi

webserver.main.init_calibre()


YOUSHU_DATA = {
    "info": {
        "title": "黜龙",
        "author": "榴弹怕水",
        "url": "https://www.youshu.me/book/268231",
    },
    "tags": ["架空历史", "历史" ],
    "summary": "此方天地有龙。龙形百态，不一而足，或游于江海，或翔于高山，或藏于九幽，或腾于云间。一旦奋起，便可吞风降雪，引江划河，落雷喷火，分山避海。此处人间也有龙。人中之龙，胸怀大志，腹有良谋，有包藏宇宙之机，吞吐天地之志。一时机发，便可翻云覆雨，决势分野，定鼎问道，证位成龙。作为一个迷路的穿越者，张行一开始也想成龙，但后来，他发现这个行当卷的太厉害了，就决定改行，去黜落群龙。所谓行尽天下路，使天地处处通，黜遍天下龙，使世间人人可为龙。这是一个老套的穿越故事。",
    "id": "268231",
    "image": "https://qidian.qpic.cn/qdbimg/349573/1031516087/600",
}


def get_mock_page():
    p = mock.Mock()
    p.get_id.return_value = YOUSHU_DATA['id']
    p.get_tags.return_value = YOUSHU_DATA['tags']
    p.get_info.return_value = YOUSHU_DATA['info']
    p.get_image.return_value = YOUSHU_DATA['image']
    p.get_summary.return_value = YOUSHU_DATA['summary']
    p.get_plat.return_value = '优书网'
    p.http.url = YOUSHU_DATA['info']['url']
    p.url = YOUSHU_DATA['info']['url']
    return p

YOUSHU_PAGE = get_mock_page()

class TestYoushu(unittest.TestCase):
    def test_youshu_api(self):
        api = YoushuApi(copy_image=False)
        with mock.patch.object(api, "_youshu") as mk:
            mk.return_value = None
            d = api.get_book("黜龙")
            self.assertEqual(d, None)

            mk.return_value = YOUSHU_PAGE
            d = api.get_book("黜龙")
            self.assertTrue(d != None)
            self.assertEqual(d.title, "黜龙")

if __name__ == "__main__":
    unittest.main()
