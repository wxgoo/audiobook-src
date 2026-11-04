#!/usr/bin/env python3
"""sidecar 音频收集（4.6.0-19 扩展）的单元测试。

覆盖：同目录音频、下一级子目录音频、混合布局、隐藏子目录跳过、
无音频返回空、纯文件系统操作不需要 mock 数据库。
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from webserver.services.scan_service import collect_sidecar_audio_dirs


def make_tree(root, files):
    """files: {相对路径: 内容}"""
    for rel, content in files.items():
        p = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode("utf-8"))


class TestCollectSidecarAudioDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb_sidecar_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_dir_audio_only(self):
        make_tree(self.tmp, {"书.epub": "x", "01.mp3": "a", "02.mp3": "b", "cover.jpg": "c"})
        entries = collect_sidecar_audio_dirs(self.tmp)
        self.assertEqual(len(entries), 1)
        d, audios = entries[0]
        self.assertEqual(os.path.abspath(d), os.path.abspath(self.tmp))
        self.assertEqual(audios, ["01.mp3", "02.mp3"])

    def test_subdir_audio_picked_up(self):
        """核心场景：音频在电子书的下一级子目录（分季打包）。"""
        make_tree(self.tmp, {
            "书.epub": "x",
            "第一季/01.mp3": "a",
            "第二季/01.mp3": "b",
        })
        entries = collect_sidecar_audio_dirs(self.tmp)
        self.assertEqual(len(entries), 2)
        names = [os.path.basename(d) for d, _ in entries]
        self.assertEqual(names, ["第一季", "第二季"])
        self.assertEqual(entries[0][1], ["01.mp3"])
        self.assertEqual(entries[1][1], ["01.mp3"])

    def test_mixed_same_and_subdir(self):
        make_tree(self.tmp, {
            "书.epub": "x",
            "00.mp3": "z",
            "第一季/01.mp3": "a",
        })
        entries = collect_sidecar_audio_dirs(self.tmp)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0][0], os.path.abspath(self.tmp))  # 同目录在前
        self.assertEqual(entries[0][1], ["00.mp3"])
        self.assertEqual(os.path.basename(entries[1][0]), "第一季")

    def test_hidden_and_temp_subdirs_skipped(self):
        make_tree(self.tmp, {
            "书.epub": "x",
            ".hidden/01.mp3": "a",
            "~temp/01.mp3": "b",
            "normal/01.mp3": "c",
        })
        entries = collect_sidecar_audio_dirs(self.tmp)
        self.assertEqual([os.path.basename(d) for d, _ in entries], ["normal"])

    def test_no_audio_returns_empty(self):
        make_tree(self.tmp, {"书.epub": "x", "notes.txt": "n"})
        self.assertEqual(collect_sidecar_audio_dirs(self.tmp), [])

    def test_missing_dir_returns_empty(self):
        self.assertEqual(collect_sidecar_audio_dirs(os.path.join(self.tmp, "nope")), [])

    def test_non_audio_subdir_files_ignored(self):
        make_tree(self.tmp, {
            "书.epub": "x",
            "subs/01.srt": "s",
        })
        self.assertEqual(collect_sidecar_audio_dirs(self.tmp), [])


if __name__ == "__main__":
    unittest.main()
