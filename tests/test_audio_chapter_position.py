# -*- coding: UTF-8 -*-
"""r41：上传章节可指定「插入为第 N 集」。

用户现场：223 集里第 10 集坏了，删掉后补传，r40 的建议名是「最后一集 +1」，
于是新文件排到 224。现在按 1-based 顺序号插入。

不变式：
  - 只新增一个文件，**绝不重命名/移动任何现有章节**（播放进度按 index 记、
    字幕按同名 stem 匹配，批量重命名会把它们全部打乱）；
  - 生成的文件名按 natural_sort_key 恰好排在 position-1；
  - 补空位优先复用被删章节原名，扩展名跟随上传文件；
  - 越界或无法命名时明确报错，不静默排到末尾。
"""

import ast
import os

import pytest

from webserver.handlers.audio import (
    chapter_name_for_position,
    list_chapter_files,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AUDIO_PY = os.path.join(REPO_ROOT, "webserver", "handlers", "audio.py")
VUE = os.path.join(REPO_ROOT, "app", "src", "pages", "audio", "_id.vue")


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _make_book(tmp_path, stems, ext=".m4a", size=2048):
    for stem in stems:
        (tmp_path / (stem + ext)).write_bytes(b"x" * size)
    return str(tmp_path)


def _snapshot(directory):
    return {n: (open(os.path.join(directory, n), "rb").read())
            for n in os.listdir(directory)}


def _insert(directory, position, ext, preferred=None):
    """生成名字、写入文件（模拟 _atomic_create_file），返回 (name, err)。"""
    name, err = chapter_name_for_position(directory, position, ext, preferred)
    if err:
        return name, err
    with open(os.path.join(directory, name), "wb") as f:
        f.write(b"y" * 2048)
    return name, ""


def _assert_slot(directory, name, position, before):
    """端到端校验：新文件确实排在请求位置，且原有文件一个字节都没动。"""
    names = list_chapter_files(directory)
    assert names[position - 1] == name, (position, names)
    assert names.count(name) == 1
    after = _snapshot(directory)
    for old_name, old_body in before.items():
        assert after.get(old_name) == old_body, "现有章节被改动: " + old_name
    assert set(after) - set(before) == {name}


# ---------- 行为：真实场景 ----------

def test_refill_deleted_chapter_reuses_original_name(tmp_path):
    """删掉第 10 集后补传：复用原名，排回第 10 位，其它 222 集纹丝不动。"""
    stems = ["平凡的世界%02d" % i for i in range(1, 13)]
    directory = _make_book(tmp_path, stems)
    deleted = "平凡的世界10.m4a"
    os.remove(os.path.join(directory, deleted))
    before = _snapshot(directory)
    name, err = _insert(directory, 10, ".m4a", deleted)
    assert not err, err
    assert name == deleted, "补空位应复用原文件名（字幕/进度才对得上）"
    _assert_slot(directory, name, 10, before)


def test_position_without_preferred_still_lands_in_slot(tmp_path):
    """换台设备/清了缓存，只填顺序号也要能排回原位。"""
    stems = ["平凡的世界%02d" % i for i in range(1, 13)]
    directory = _make_book(tmp_path, stems)
    os.remove(os.path.join(directory, "平凡的世界10.m4a"))
    before = _snapshot(directory)
    name, err = _insert(directory, 10, ".m4a")
    assert not err, err
    _assert_slot(directory, name, 10, before)


def test_upload_extension_wins_over_preferred(tmp_path):
    """补传的是 mp3：名字扩展名必须跟着文件走，不能造出 .m4a 装 mp3。"""
    stems = ["平凡的世界%02d" % i for i in range(1, 13)]
    directory = _make_book(tmp_path, stems)
    os.remove(os.path.join(directory, "平凡的世界10.m4a"))
    before = _snapshot(directory)
    name, err = _insert(directory, 10, ".mp3", "平凡的世界10.m4a")
    assert not err, err
    assert name.endswith(".mp3"), name
    assert not name.endswith(".m4a"), name
    _assert_slot(directory, name, 10, before)


@pytest.mark.parametrize("position", [1, 2, 5, 10, 12, 13])
def test_any_position_inserts_exactly(tmp_path, position):
    """任意顺序号（含插到最前、追加到末尾）都精确落位。"""
    directory = _make_book(tmp_path, ["平凡的世界%02d" % i for i in range(1, 13)])
    before = _snapshot(directory)
    name, err = _insert(directory, position, ".m4a")
    assert not err, (position, err)
    _assert_slot(directory, name, position, before)


def test_between_consecutive_numbers(tmp_path):
    """1/2/3 之间插入：数字已连续，靠「数字后加字母」找中间名。"""
    directory = _make_book(tmp_path, ["1", "2", "3"], ext=".mp3")
    before = _snapshot(directory)
    name, err = _insert(directory, 2, ".mp3")
    assert not err, err
    _assert_slot(directory, name, 2, before)


def test_non_numeric_chapter_names(tmp_path):
    """纯文字章节名也要能插到指定位置。"""
    directory = _make_book(tmp_path, ["A回", "B回", "C回"], ext=".mp3")
    before = _snapshot(directory)
    name, err = _insert(directory, 2, ".mp3")
    assert not err, err
    _assert_slot(directory, name, 2, before)


def test_preferred_name_still_taken_must_not_overwrite(tmp_path):
    """没删就补（原名还在）：不能覆盖，改用另一个能排到该位置的名字。"""
    directory = _make_book(tmp_path, ["平凡的世界%02d" % i for i in range(1, 13)])
    before = _snapshot(directory)
    taken = "平凡的世界10.m4a"
    name, err = _insert(directory, 10, ".m4a", taken)
    assert not err, err
    assert name != taken, "绝不能覆盖已有章节"
    _assert_slot(directory, name, 10, before)


def test_empty_book_first_position(tmp_path):
    """一本没有音频的书，第一集也能按位置创建。"""
    directory = str(tmp_path)
    before = _snapshot(directory)
    name, err = _insert(directory, 1, ".m4a")
    assert not err, err
    _assert_slot(directory, name, 1, before)


@pytest.mark.parametrize("position", [0, -1, 99])
def test_out_of_range_position_reports_error(tmp_path, position):
    directory = _make_book(tmp_path, ["1", "2", "3"], ext=".mp3")
    before = _snapshot(directory)
    name, err = chapter_name_for_position(directory, position, ".mp3")
    assert name is None and err
    assert _snapshot(directory) == before, "报错时不能写任何文件"


# ---------- 静态契约 ----------

def test_backend_reads_position_from_url_query_and_never_renames():
    t = _text(AUDIO_PY)
    start = t.index("class AudioChapterUpload")
    nxt = t.find("\nclass ", start + 1)
    cls_src = t[start:nxt if nxt > 0 else len(t)]
    # ast.unparse 会把双引号改写成单引号，字面量断言直接看源码文本
    assert 'get_argument("position"' in cls_src
    assert 'get_argument("preferred"' in cls_src
    assert "chapter_name_for_position" in cls_src
    tree = ast.parse(t)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "AudioChapterUpload")
    post = next(n for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "post")
    body = ast.unparse(post)
    assert "os.rename" not in body, "不允许重命名现有章节"
    assert "shutil.move" not in body
    assert "_atomic_create_file" in body, "仍然只做原子新建"


def test_naming_helper_validates_position_with_real_sort():
    tree = ast.parse(_text(AUDIO_PY))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "chapter_name_for_position")
    src = ast.unparse(fn)
    assert "_sorts_at(" in src, "生成的名字必须用 natural_sort_key 实测落位"
    assert "list_chapter_files" in src
    assert "os.path.exists" in src, "不能与现有文件同名"


def test_extension_must_match_uploaded_file():
    tree = ast.parse(_text(AUDIO_PY))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "AudioChapterUpload")
    post = next(n for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "post")
    assert "target_ext != ext" in ast.unparse(post)


def test_frontend_position_wiring():
    t = _text(VUE)
    for token in ("upload-chapter?position=", "uploadPosition", "uploadPreferred",
                  "hasUploadPosition", "rememberDeletedChapter", "clearDeletedChapter",
                  "encodeURIComponent(this.uploadName)", "suggestNextChapterName()"):
        assert token in t, "前端缺少接线: " + token


def test_player_order_no_size_filter():
    tree = ast.parse(_text(AUDIO_PY))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "list_chapter_files")
    src = ast.unparse(fn)
    assert "getsize" not in src, "播放页不按大小过滤，坏文件也要能被定位"
    assert "SKIP_AUDIO_FILE_PREFIX" in src
