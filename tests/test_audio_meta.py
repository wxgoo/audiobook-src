#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""有声书标签解析：`audios_import._extract_audio_metadata` 的单元测试。

## 这个文件以前为什么一跑就是「no tests ran」

它是一个**手写调试脚本**：把被测函数抄了一份内联在文件里，末尾是
`if __name__ == "__main__":` + 一个硬编码的 macOS 路径。pytest 收不到任何
`test_*` 函数，于是报 0 个用例——顺带也从来没有真正测过源码：抄进来的
那份副本和 `audios_import.py` 里的实现早就分叉了（副本把第二个返回值叫
`author`，源码 4.6.0 起已经改叫 `narrator`：中文有声资源的 ID3 TPE1
填的是播音员，不能当作者）。

现在改成直接 import 源码，用真实音频标签文件驱动。标签文件用 mutagen
现场写一个极小的空音频壳子——只需要容器头和标签，不需要真音频数据。
"""

import os
import tempfile
import unittest

import mutagen
import mutagen.id3

from webserver.services.audios_import import _extract_audio_metadata, _fix_mojibake


# mutagen 的 easy 键 -> ID3v2.3 帧名
_EASY_TO_ID3 = {"album": "TALB", "title": "TIT2", "artist": "TPE1", "albumartist": "TPE2"}


def _make_mp3(dirname, name, tags):
    """在 dirname 下造一个带 ID3v2.3 标签的空 mp3，返回路径。

    两个坑，都是实测踩出来的：

    1. **不能只写标签不写音频帧**。`mutagen.File()` 对 mp3 走 MP3 解析器，
       它会去同步 MPEG 帧头；一个只有 ID3 头、后面什么都没有的文件会抛
       `HeaderNotFoundError: can't sync to MPEG frame`，被测函数把它吞成
       `(fallback_title, None)`，于是所有断言都变成「标签没读出来」。
       所以要补一帧合法的 MPEG-1 Layer III 帧头（0xFF 0xFB 0x90 0x00，
       128kbps/44.1kHz），后面跟满 413 字节凑够 417 字节的整帧，重复几帧。
    2. **标签要用 `mutagen.id3.ID3()` 对象写**，不能对 `easy=True` 的
       代理直接赋值后 save —— 那条路在空壳文件上同样会先挂掉。
    """
    path = os.path.join(dirname, name)
    # 一帧 128kbps/44.1kHz 的 MPEG-1 Layer III = 417 字节（含 4 字节帧头）
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
    with open(path, "wb") as fh:
        fh.write(frame * 8)

    id3 = mutagen.id3.ID3()
    for key, value in tags.items():
        frame_cls = getattr(mutagen.id3, _EASY_TO_ID3[key])
        id3.add(frame_cls(encoding=3, text=[value]))
    id3.save(path, v2_version=3)
    return path


class TestExtractAudioMetadata(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_title_and_narrator(self):
        path = _make_mp3(self.dir, "a.mp3", {"album": "三体", "artist": "李野墨"})
        title, narrator = _extract_audio_metadata(path, "兜底书名")
        self.assertEqual(title, "三体")
        self.assertEqual(narrator, "李野墨")

    def test_artist_lands_in_narrator_not_author(self):
        """第二个返回值必须是「演播者」语义。

        `artist` 在中文有声书里填播音员，把它当作者会让库里凭空多出
        一个伪作者（「李慧敏」这种）。这个断言把语义钉死在测试里，
        以后谁想改回 author 都会先红一次。
        """
        path = _make_mp3(self.dir, "b.mp3", {"album": "哈利波特与魔法石", "artist": "李慧敏"})
        _title, second = _extract_audio_metadata(path, "")
        self.assertEqual(second, "李慧敏")

    def test_title_falls_back_when_tag_missing(self):
        path = _make_mp3(self.dir, "c.mp3", {"artist": "某主播"})
        title, narrator = _extract_audio_metadata(path, "文件名书名")
        self.assertEqual(title, "文件名书名")
        self.assertEqual(narrator, "某主播")

    def test_album_preferred_over_title_tag(self):
        # 有声书按「一本书 = 一张专辑」组织，album 才是书名
        path = _make_mp3(self.dir, "d.mp3", {"album": "专辑书名", "title": "第 01 章"})
        self.assertEqual(_extract_audio_metadata(path, "x")[0], "专辑书名")

    def test_albumartist_used_when_artist_absent(self):
        path = _make_mp3(self.dir, "e.mp3", {"album": "某书", "albumartist": "专辑演播"})
        self.assertEqual(_extract_audio_metadata(path, "")[1], "专辑演播")

    def test_tags_are_stripped(self):
        path = _make_mp3(self.dir, "f.mp3", {"album": "  空格书  ", "artist": " 空格人 "})
        title, narrator = _extract_audio_metadata(path, "")
        self.assertEqual((title, narrator), ("空格书", "空格人"))

    def test_missing_file_returns_fallback(self):
        title, narrator = _extract_audio_metadata(os.path.join(self.dir, "nope.mp3"), "兜底")
        self.assertEqual(title, "兜底")
        self.assertIsNone(narrator)

    def test_non_audio_file_returns_fallback(self):
        path = os.path.join(self.dir, "notaudio.txt")
        with open(path, "w") as fh:
            fh.write("hello")
        title, narrator = _extract_audio_metadata(path, "兜底")
        self.assertEqual(title, "兜底")
        self.assertIsNone(narrator)


class TestFixMojibake(unittest.TestCase):
    """GBK 被按 latin-1 读坏之后的还原。台湾版 mp3 的标签是 BIG5，
    被误读后形态和 GBK 一样，所以要 GBK 优先、BIG5 兜底。"""

    def test_restores_gbk_mojibake(self):
        broken = "三体".encode("gbk").decode("latin-1")
        self.assertEqual(_fix_mojibake(broken), "三体")

    def test_restores_big5_mojibake(self):
        broken = "哈利波特".encode("big5").decode("latin-1")
        self.assertEqual(_fix_mojibake(broken), "哈利波特")

    def test_ascii_passes_through(self):
        self.assertEqual(_fix_mojibake("Atlas Shrugged"), "Atlas Shrugged")

    def test_real_chinese_passes_through(self):
        # 本来就是正常中文（latin-1 编不出来），必须原样返回
        self.assertEqual(_fix_mojibake("三体"), "三体")

    def test_empty_and_none_pass_through(self):
        self.assertEqual(_fix_mojibake(""), "")
        self.assertIsNone(_fix_mojibake(None))


if __name__ == "__main__":
    unittest.main()
