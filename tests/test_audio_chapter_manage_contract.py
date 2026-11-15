# -*- coding: UTF-8 -*-
"""契约 + 行为：章节级管理（替换 / 删除单集 / 上传新章节）。

r40：用户要求「既可以更换，也可以删除、上传」。同时修掉替换接口现场报错
「无效的音频文件名」——目标定位全部改为「前端只传 URL query，后端自己枚举」：

  - 替换 / 删除：``?index=<播放页列表序号>``，后端 ``chapter_by_index`` 定位；
  - 上传：``?name=<章节文件名>``（URL 编码），文件本体走 multipart；
  - 任何接口都**不再从 multipart 普通文本字段读文件名**。

配套修复：``natural_sort_key`` 原来是 [str, int, str] 混合列表，
「0001.mp3」与「平凡的世界10.m4a」混排时 Python 3 排序会 TypeError，
整个播放页 500。允许上传自带文件名后这种混合必然出现，故改为带类型标签的 key。
"""

import ast
import os
import stat

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AUDIO_PY = os.path.join(REPO_ROOT, "webserver", "handlers", "audio.py")
VUE = os.path.join(REPO_ROOT, "app", "src", "pages", "audio", "_id.vue")


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _class_source(name):
    t = _text(AUDIO_PY)
    start = t.index("class " + name)
    nxt = t.find("\nclass ", start + 1)
    return t[start:nxt if nxt > 0 else len(t)]


# ---------- 静态契约：路由与权限 ----------

def test_all_chapter_routes_before_wildcard_audiofile():
    t = _text(AUDIO_PY)
    i_wild = t.index('(r"/api/audio/([0-9]+)/([^/]+)", AudioFile)')
    for route in ("/replace", "/delete-chapter", "/upload-chapter"):
        i = t.index('(r"/api/audio/([0-9]+)' + route + '"')
        assert i < i_wild, "%s 必须在通配路由之前" % route


def test_all_three_handlers_are_admin_only():
    tree = ast.parse(_text(AUDIO_PY))
    for name in ("AudioReplace", "AudioChapterDelete", "AudioChapterUpload"):
        cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef) and n.name == name)
        post = next(n for n in cls.body
                    if isinstance(n, ast.FunctionDef) and n.name == "post")
        decs = [ast.unparse(d) for d in post.decorator_list]
        assert "is_admin" in decs, name
        assert "js" in decs, name
        assert "self.is_admin()" in _class_source(name), name


def test_no_filename_read_from_form_text_field():
    """r40 现场教训：文本字段不可靠，定位信息一律走 URL query。"""
    t = _text(AUDIO_PY)
    # audio.py 其它 handler 可能仍用 filename（AudioFile 读文件），只约束三个管理类
    for name in ("AudioReplace", "AudioChapterDelete", "AudioChapterUpload"):
        src = _class_source(name)
        assert 'get_argument("filename"' not in src, name
    assert 'form.append(\'filename\'' not in _text(VUE)


def test_replace_and_delete_use_index_from_url():
    for name in ("AudioReplace", "AudioChapterDelete"):
        src = _class_source(name)
        assert "_parse_chapter_index(self)" in src, name
        assert "chapter_by_index(audio_dir, index)" in src, name
    tree = ast.parse(_text(AUDIO_PY))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_parse_chapter_index")
    body = ast.unparse(fn)
    assert "get_argument" in body and "index" in body, "序号必须来自 URL query"
    assert "request.files" not in body, "序号不能来自 multipart"


def test_upload_name_comes_from_url_query():
    src = _class_source("AudioChapterUpload")
    assert 'get_argument("name", "")' in src
    assert "encodeURIComponent(this.uploadName)" in _text(VUE)


def test_delete_removes_one_file_only():
    """只看 post 方法体，避免把类 docstring 里提到 rmtree 的说明文字算成代码。"""
    tree = ast.parse(_text(AUDIO_PY))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "AudioChapterDelete")
    post = next(n for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "post")
    body = ast.unparse(post)
    assert "os.remove(dst)" in body
    assert "shutil.rmtree" not in body, "删除单集不能删整本音频"
    assert "_sync_audio_set(book_id, False)" in body, "删掉最后一章要同步集合"


def test_upload_never_overwrites_existing_file():
    src = _class_source("AudioChapterUpload")
    assert "_atomic_create_file(dst, body)" in src
    assert "os.path.exists(dst)" in src
    assert "FileExistsError" in src
    assert "_sync_audio_set(book_id, True)" in src
    assert "os.replace(tmp, dst)" not in src, "上传不得用覆盖语义"


def test_atomic_create_helper_uses_link():
    tree = ast.parse(_text(AUDIO_PY))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_atomic_create_file")
    src = ast.unparse(fn)
    assert "os.link(tmp, dst)" in src
    assert "os.fsync" in src
    assert "st.st_uid" in src


# ---------- 静态契约：前端接线 ----------

def test_frontend_chapter_management_wiring():
    t = _text(VUE)
    for token in ("mdi-delete-outline", "mdi-upload-outline",
                  "openDeleteChapterDialog(index, audio)", "openUploadDialog",
                  "`/audio/${this.bookId}/delete-chapter?index=${this.deleteChapterIndex}`",
                  "`/audio/${this.bookId}/upload-chapter?name=${encodeURIComponent(this.uploadName)}`",
                  "refreshAudioFiles()", "suggestNextChapterName()"):
        assert token in t, "前端缺少接线: " + token


def test_delete_and_upload_buttons_admin_only():
    t = _text(VUE)
    for cls in ("delete-track-btn", "upload-chapter-btn"):
        i = t.index('class="' + cls + '"')
        block = t[max(0, i - 200):i]
        assert 'v-if="isAdmin"' in block, cls + " 必须仅管理员可见"


# ---------- 真实行为 ----------

def test_natural_sort_key_handles_mixed_str_and_int():
    """中文/字母/纯数字开头的文件名混排不能抛 TypeError（修复前的真实崩溃）。"""
    from webserver.handlers.audio import natural_sort_key
    names = ["平凡的世界10.m4a", "0001.mp3", "平凡的世界09.m4a",
             "chapter11.mp3", "平凡的世界11.m4a"]
    ordered = sorted(names, key=natural_sort_key)
    assert ordered[0] == "0001.mp3"
    assert ordered[-1] == "平凡的世界11.m4a"
    assert ordered.index("平凡的世界09.m4a") < ordered.index("平凡的世界10.m4a")


def test_list_chapter_files_matches_player_order(tmp_path):
    """r41：与播放页 AudioDetail 口径一致——不按大小过滤、跳过 CIP 前缀。

    播放页并不跳过 0 字节坏文件；r40 这里过滤 <=1KB 会让 index 与页面列表
    错位（删第 10 集会误伤第 11 集），故改为文件粒度 + 自然排序。
    """
    from webserver.handlers.audio import list_chapter_files, chapter_by_index
    for name, size in [("平凡的世界10.m4a", 2048),
                       ("平凡的世界09.m4a", 2048),
                       ("平凡的世界02.m4a", 2048)]:
        (tmp_path / name).write_bytes(b"x" * size)
    (tmp_path / "平凡的世界03.m4a").write_bytes(b"")  # 损坏的 0 字节，播放页仍会显示
    (tmp_path / "cover.jpg").write_bytes(b"x" * 2048)  # 非音频
    (tmp_path / "图书在版编目CIP数据.m4a").write_bytes(b"x" * 2048)  # 播放页跳过
    assert list_chapter_files(str(tmp_path)) == [
        "平凡的世界02.m4a", "平凡的世界03.m4a",
        "平凡的世界09.m4a", "平凡的世界10.m4a"]
    assert chapter_by_index(str(tmp_path), 2) == "平凡的世界09.m4a"
    assert chapter_by_index(str(tmp_path), 99) is None


def test_atomic_create_does_not_overwrite_and_cleans_tmp(tmp_path):
    from webserver.handlers.audio import _atomic_create_file
    dst = tmp_path / "平凡的世界11.m4a"
    parent_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    _atomic_create_file(str(dst), b"good-audio" * 200)
    assert dst.read_bytes() == b"good-audio" * 200
    assert not list(tmp_path.glob(".upload-*.tmp"))
    assert stat.S_IMODE(dst.stat().st_mode) == parent_mode
    try:
        _atomic_create_file(str(dst), b"evil")
        raise AssertionError("同名文件必须拒绝创建")
    except FileExistsError:
        pass
    assert dst.read_bytes() == b"good-audio" * 200, "原文件不能被覆盖"
    assert not list(tmp_path.glob(".upload-*.tmp"))
