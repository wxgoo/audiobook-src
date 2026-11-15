"""契约 + 行为：音频章节替换（r39）。

背景：某本书某一章音频损坏时，站点此前只能「删整本音频」或「重新导入」，
而导入对同名文件是纯增量（``_copy_or_convert_file`` 遇到已存在目标直接
return），用户只能去 NAS 的 FileStation 里手动覆盖。r39 补上站内入口：
``POST /api/audio/<id>/replace``，只覆盖内容、文件名与章节顺序保持不变。

不变式：
1. 路由必须注册在 ``/api/audio/<id>/([^/]+)``（AudioFile）之前，否则 ``/replace``
   会被 AudioFile 抢走；
2. 只允许管理员，目标必须是 .audio/ 里**已存在**的文件名且不含任何路径成分；
3. 上传文件扩展名必须与原文件一致，大小在 1KB~300MB；
4. 原子覆盖、保留原属主/权限、不留 .tmp；
5. 前端用 FormData 提交，并给播放 url 加 ``?v=`` 破浏览器 1 小时缓存
   （AudioFile 带 ``Cache-Control: private, max-age=3600``）。
"""

import ast
import os
import re
import stat

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AUDIO_PY = os.path.join(REPO_ROOT, "webserver", "handlers", "audio.py")
VUE = os.path.join(REPO_ROOT, "app", "src", "pages", "audio", "_id.vue")


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _replace_class_source():
    t = _text(AUDIO_PY)
    start = t.index("class AudioReplace")
    end = t.index("class AudioFile", start)
    return t[start:end]


# ---------- 静态契约 ----------

def test_route_registered_before_audiofile():
    """Tornado 按注册顺序匹配，/replace 必须在通配的 /([^/]+) 之前。"""
    t = _text(AUDIO_PY)
    i_replace = t.index('(r"/api/audio/([0-9]+)/replace", AudioReplace)')
    i_file = t.index('(r"/api/audio/([0-9]+)/([^/]+)", AudioFile)')
    assert i_replace < i_file


def test_post_is_admin_and_js():
    tree = ast.parse(_text(AUDIO_PY))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "AudioReplace")
    post = next(n for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "post")
    decs = [ast.unparse(d) for d in post.decorator_list]
    assert "is_admin" in decs
    assert "js" in decs


def test_path_traversal_guard():
    """目标只认 .audio/ 下已存在的 basename，拒绝任何路径成分。"""
    s = _replace_class_source()
    for token in ("os.path.basename(target)", '".." in target',
                  '"/" in target', "os.path.isfile(dst)",
                  "tuple(SUPPORTED_AUDIO_FORMATS)"):
        assert token in s, "缺少防护: " + token


def test_upload_validation():
    s = _replace_class_source()
    for token in ("up_ext != ext", "len(body) <= 1024",
                  "self.MAX_BYTES", "self.request.files.get(\"file\")"):
        assert token in s, "缺少校验: " + token
    assert "MAX_BYTES = 300 * 1024 * 1024" in s


def test_atomic_replace_called():
    s = _replace_class_source()
    assert "_atomic_write_file(dst, body)" in s
    # 绝不直接对目标文件做覆盖式 open
    assert 'open(dst, "wb")' not in s


def test_atomic_helper_is_module_level():
    tree = ast.parse(_text(AUDIO_PY))
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "_atomic_write_file"),
              None)
    assert fn is not None
    src = ast.unparse(fn)
    assert "os.replace(tmp, dst)" in src
    assert "os.fsync" in src
    assert "st.st_uid" in src


# ---------- 前端接线 ----------

def test_frontend_replace_wiring():
    t = _text(VUE)
    assert "openReplaceDialog(index, audio)" in t
    assert "mdi-file-replace-outline" in t
    assert "`/audio/${this.bookId}/replace`" in t
    assert "form.append('filename', this.replaceFilename)" in t
    assert "form.append('file', this.replaceFile)" in t
    assert "?v=${Date.now()}" in t


def test_frontend_button_admin_only():
    t = _text(VUE)
    m = re.search(r'<v-btn\s+(.*?)class="replace-track-btn"(.*?)>', t, re.S)
    assert m, "找不到替换按钮"
    assert 'v-if="isAdmin"' in m.group(0)
    assert "@click.stop" in m.group(0), "不能触发整行的 selectTrack"


# ---------- 真实行为 ----------

def test_atomic_write_replaces_content_and_keeps_mode(tmp_path):
    from webserver.handlers.audio import _atomic_write_file

    dst = tmp_path / "0009_chapter.mp3"
    dst.write_bytes(b"old-broken-audio-content" * 100)
    os.chmod(str(dst), 0o640)
    before_mode = stat.S_IMODE(dst.stat().st_mode)
    before_uid, before_gid = dst.stat().st_uid, dst.stat().st_gid

    good = b"new-good-audio-content" * 200
    _atomic_write_file(str(dst), good)

    assert dst.read_bytes() == good
    assert stat.S_IMODE(dst.stat().st_mode) == before_mode
    assert (dst.stat().st_uid, dst.stat().st_gid) == (before_uid, before_gid)
    assert not list(tmp_path.glob(".replace-*.tmp")), "临时文件没清干净"
    assert [p.name for p in tmp_path.iterdir()] == ["0009_chapter.mp3"]


def test_atomic_write_keeps_original_on_failure(tmp_path):
    """目标不存在时应当抛错，而不是凭空造出一个文件。"""
    import pytest
    from webserver.handlers.audio import _atomic_write_file

    dst = tmp_path / "missing.mp3"
    with pytest.raises(OSError):
        _atomic_write_file(str(dst), b"whatever")
    assert not dst.exists()
