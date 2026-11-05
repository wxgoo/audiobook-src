"""弹窗 ↔ 播放页进度同步（4.6.0-19 r9）的静态契约测试。

背景：详情页的「有声书」试听弹窗与 /audio/<id> 播放页各自维护一份进度，
用户在弹窗里听了一半、直接点顶部「有声书」进播放页，那边却从零开始 ——
也就是「两个单独的进度」。r9 把弹窗的进度写进播放页用的同一条键
（audio_progress_<uid>_<bookId>）与服务端。

这一组测试不跑浏览器（真实播放链路由 /tmp/probe_dialog_browser.py 覆盖），
只锁住「容易在重构中被改回去」的几条契约：

  1. 弹窗写的是播放页认的那套键名与字段（trackIndex/currentTime/timestamp）
  2. 进度必须在**播放中**周期性落盘，不能只靠「关弹窗时保存一次」
  3. 同步调用放在 _keyOf() 的早退之后会成为死代码（bookId 晚到时永远不执行）
  4. 播放页要能识别「刚从弹窗过来」，不被缓存的旧进度盖掉
  5. 章节序号在两侧同序（都用后端 natural_sort_key 的结果）
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIALOG = os.path.join(ROOT, "app", "src", "components", "AudioListDialog.vue")
PAGE = os.path.join(ROOT, "app", "src", "pages", "audio", "_id.vue")
BACKEND = os.path.join(ROOT, "webserver", "handlers", "audio.py")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _method_body(src, name):
    """粗暴地截出 methods 里某个方法的源码（按缩进对齐到大括号收尾）。"""
    m = re.search(r"\n(\s+)" + re.escape(name) + r"\(", src)
    assert m, f"找不到方法 {name}"
    indent = m.group(1)
    start = m.start() + 1
    # 找下一个同级 key 或同级闭合括号
    tail = src[start:]
    depth = 0
    i = 0
    started = False
    while i < len(tail):
        ch = tail[i]
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                return tail[: i + 1]
        i += 1
    raise AssertionError(f"方法 {name} 大括号不匹配")


def test_dialog_writes_same_key_schema_as_player():
    """弹窗写共享键时用的字段名/语义必须与播放页一致。"""
    src = _read(DIALOG)
    body = _method_body(src, "_syncSharedProgress")
    assert "trackIndex" in body, "缺 trackIndex：播放页 restorePlaybackPosition 读的就是它"
    assert "currentTime" in body, "缺 currentTime"
    assert "timestamp" in body, "缺 timestamp：播放页靠它比较新旧"
    # 键名必须与播放页 getStorageKey() 同构
    assert "audio_progress_" in _read(DIALOG)
    page_src = _read(PAGE)
    assert "audio_progress_${userId}_${this.bookId}" in page_src


def test_dialog_saves_periodically_while_playing():
    """进度要在播放中周期落盘 —— 只在退出时保存会漏掉「没关弹窗就跳页」。"""
    src = _read(DIALOG)
    # 文件里有多个 timeupdate（诊断裸播那个也注册过），按周期保存的基准
    # 字段定位到真正播放器那个回调
    hits = [m.start() for m in re.finditer(r"addEventListener\('timeupdate'", src)]
    assert hits, "找不到 timeupdate 回调"
    seg = None
    for start in hits:
        chunk = src[start: start + 1600]
        if "_lastSaveAt" in chunk or "saveProgress()" in chunk:
            seg = chunk
            break
    assert seg is not None, (
        "timeupdate 里没调 saveProgress：用户播到一半直接切到播放页，"
        "那边一条进度都没有（r9 修复的问题会复发）"
    )
    assert "saveProgress()" in seg, "timeupdate 里没调 saveProgress"
    assert "_lastSaveAt" in seg, "缺少节流基准，不能每秒都写一次 localStorage"
    # 节流窗口要够短：太长则「听 10 秒就切走」仍然丢进度
    m = re.search(r">=\s*(\d{4,5})", seg)
    assert m and int(m.group(1)) <= 10000, "周期保存的间隔不应超过 10 秒"


def test_dialog_sync_not_skipped_when_key_missing():
    """_syncSharedProgress 必须在 key 缺失时也能执行（不能放在早退之后）。"""
    src = _read(DIALOG)
    body = _method_body(src, "saveProgress")
    idx_sync = body.find("_syncSharedProgress")
    assert idx_sync > 0, "saveProgress 没有调用 _syncSharedProgress"
    # 找出所有 `return` 的位置：同步调用之前不允许有「直接返回」
    head = body[:idx_sync]
    returns = [m for m in re.finditer(r"\breturn\b", head)]
    assert len(returns) <= 2, (
        "同步调用前有过多 return 守卫（应为 playing_index 与 _el 两道）；"
        "bookId 晚到时会整个跳过同步"
    )


def test_player_prefers_fresh_progress_from_dialog():
    """播放页要识别「刚写入的最新进度」，避免用缓存旧值把它盖掉。"""
    src = _read(PAGE)
    body = _method_body(src, "restorePlaybackPosition")
    assert "_freshFromDialog" in body or "age" in body, (
        "restorePlaybackPosition 没有判断进度新鲜度："
        "keep-alive 回来的旧实例会用自己的 currentTime 覆盖弹窗刚写的进度"
    )


def test_chapter_order_matches_between_dialog_and_player():
    """两侧章节列表同源同序，才能让「弹窗第 N 章」等同「播放页 trackIndex=N」。"""
    backend = _read(BACKEND)
    assert "sorted(audio_files, key=natural_sort_key)" in backend, (
        "后端 AudioDetail 的排序方式变了；弹窗与播放页都吃这份输出，"
        "排序一变章节序号就对不上"
    )
    page_src = _read(PAGE)
    assert "audioResponse.audios" in page_src
