# -*- coding: UTF-8 -*-
"""升级检测版本比较器 _ver_key 单测（首个无 r 版本 build.05 起）。

取消 -rN 后缀后，revision 形如 4.7.0-build.05，升级检测靠 build 号区分；
换上游基线时 build 会重置（4.6.0-build.27 → 4.7.0-build.01），所以比较器
必须解析成 (major, minor, patch, build) 四元组，才能正确判断跨基线先后。
此前版本比较零覆盖，这里补齐。
"""
import pytest

from webserver.services.version_check import _ver_key, _rev_num


@pytest.mark.parametrize(
    "rev,expected",
    [
        # 无 r 新体系
        ("4.7.0-build.05", (4, 7, 0, 5)),
        ("4.7.0-build.04", (4, 7, 0, 4)),
        ("4.6.0-build.27", (4, 6, 0, 27)),
        ("4.7.0-build.1", (4, 7, 0, 1)),      # build 号位数可变
        ("4.7.0-build.005", (4, 7, 0, 5)),    # 前导零归一
        # 旧 -rN 串兼容读取（忽略 r 值，防御 Gitee raw 旧清单缓存）
        ("4.6.0-build.27-r7", (4, 6, 0, 27)),
        ("4.7.0-build.03-r46", (4, 7, 0, 3)),
        # 非法串 → None
        ("", None),
        ("garbage", None),
        ("4.7.0", None),                       # 裸 tag 无 build 号
        ("v4.7.0-build.05", None),             # 带 v 前缀
        (None, None),
    ],
)
def test_ver_key_parsing(rev, expected):
    assert _ver_key(rev) == expected


def test_same_baseline_build_ordering():
    assert _ver_key("4.7.0-build.05") > _ver_key("4.7.0-build.04")
    assert _ver_key("4.7.0-build.04") < _ver_key("4.7.0-build.05")
    assert _ver_key("4.7.0-build.04") == _ver_key("4.7.0-build.04")


def test_cross_baseline_ordering():
    """跨基线 build 号重置后，仍按基线优先判断先后（这是取消 -rN 的关键）。"""
    assert _ver_key("4.7.0-build.01") > _ver_key("4.6.0-build.27")
    assert _ver_key("4.8.0-build.01") > _ver_key("4.7.0-build.99")


def test_old_r_suffix_ignored():
    """旧清单带 -rN 时按其 build 号比较，不因 r 值产生误判。"""
    assert _ver_key("4.7.0-build.05") > _ver_key("4.7.0-build.04-r99")
    assert _ver_key("4.7.0-build.04-r46") == _ver_key("4.7.0-build.04")


def test_rev_num_backcompat():
    """_rev_num 兼容旧引用：仍能抽 -r 数字，无 -r 返回 0。"""
    assert _rev_num("4.6.0-build.27-r7") == 7
    assert _rev_num("4.7.0-build.05") == 0
