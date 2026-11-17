/**
 * 内置 EPUB 阅读器的浏览器内朗读（r46）。
 *
 * 设计要点：
 *  - 纯原生 JS，作为普通 <script> 在 epubjs.html 里加载，不依赖 Vue/Nuxt。
 *  - 复用后端 /api/tts/edge 代理（GET 列声音 / POST 合成 audio/mpeg）。
 *  - 朗读文本来源：优先当前选区（用户拖选），否则取当前可见 iframe 的正文。
 *  - 分段朗读（按中文句号/换行切，过长再按长度切），逐段请求 + 播放，
 *    支持暂停/继续/停止、声音与语速切换。
 *  - 可选消费响应头 X-TTS-Word-Boundaries 做逐词高亮（epub.js 的 iframe 是
 *    同源 srcdoc，可注入高亮 span）。高亮失败不影响朗读本身。
 *
 * 与 MyReader 默认阅读器完全解耦：本文件只有切换到内置 epubjs 阅读器时才加载。
 */
(function () {
  "use strict";

  var TTS_API = "/api/tts/edge";
  var HEADER = "x-tts-word-boundaries";

  // ---- 文案（三语，随 <html lang> 或浏览器语言）----
  var LANGS = {
    zh: {
      title: "朗读", play: "朗读本章", pause: "暂停", resume: "继续", stop: "停止",
      voice: "声音", rate: "语速", loading: "加载声音中…", noText: "当前页没有可朗读的文本",
      selectHint: "提示：选中文字可只朗读选中部分", err: "朗读失败，请稍后重试",
      r0: "0.75x", r1: "1.0x", r2: "1.25x", r3: "1.5x", none: "暂无可用声音"
    },
    "zh-TW": {
      title: "朗讀", play: "朗讀本章", pause: "暫停", resume: "繼續", stop: "停止",
      voice: "聲音", rate: "語速", loading: "載入聲音中…", noText: "目前頁沒有可朗讀的文字",
      selectHint: "提示：選取文字可只朗讀選取部分", err: "朗讀失敗，請稍後重試",
      r0: "0.75x", r1: "1.0x", r2: "1.25x", r3: "1.5x", none: "暫無可用聲音"
    },
    en: {
      title: "Read aloud", play: "Read this page", pause: "Pause", resume: "Resume", stop: "Stop",
      voice: "Voice", rate: "Speed", loading: "Loading voices…", noText: "No readable text on this page",
      selectHint: "Tip: select text to read only the selection", err: "Playback failed, please retry",
      r0: "0.75x", r1: "1.0x", r2: "1.25x", r3: "1.5x", none: "No voices available"
    }
  };

  function pickLang() {
    var docLang = (document.documentElement && document.documentElement.lang) || "";
    var raw = (docLang || navigator.language || "zh").toLowerCase();
    if (raw.indexOf("zh-tw") === 0 || raw.indexOf("zh-hant") === 0 || raw.indexOf("zh-hk") === 0) return "zh-TW";
    if (raw.indexOf("zh") === 0) return "zh";
    return "en";
  }

  var L = LANGS[pickLang()];

  // ---- 状态 ----
  var audio = null;
  var segments = [];
  var segIndex = 0;
  var playing = false;
  var voices = [];
  var ui = {};

  function log() { /* 静默：阅读器里不打扰用户 */ }

  // 取朗读文本：选区优先，否则当前可见 iframe 正文
  function collectText() {
    var frames = document.querySelectorAll("#viewer iframe");
    var selected = "";
    var bodyText = "";
    for (var i = 0; i < frames.length; i++) {
      try {
        var d = frames[i].contentDocument;
        if (!d) continue;
        var sel = d.getSelection && d.getSelection().toString().trim();
        if (sel) selected += (selected ? "\n" : "") + sel;
        if (d.body && d.body.innerText) bodyText += (bodyText ? "\n" : "") + d.body.innerText;
      } catch (e) { /* 跨域 iframe 读不到则跳过 */ }
    }
    var text = selected || bodyText;
    return (text || "").replace(/\s+/g, " ").trim();
  }

  // 分段：先按句末标点切，单段过长再按长度硬切（Edge TTS 单次输入不宜过长）
  function splitSegments(text, maxLen) {
    maxLen = maxLen || 120;
    // 不用 lookbehind（老 WebView 不支持）：在每个句末标点后插入分隔再切
    var parts = text.replace(/([。！？!?；;\n])/g, "$1\u0000").split("\u0000");
    var out = [];
    var buf = "";
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      while (p.length > maxLen) {
        if (buf) { out.push(buf); buf = ""; }
        out.push(p.slice(0, maxLen));
        p = p.slice(maxLen);
      }
      if ((buf + p).length > maxLen) { out.push(buf); buf = p; }
      else { buf += p; }
    }
    if (buf) out.push(buf);
    return out.filter(function (s) { return s.trim().length; });
  }

  function currentVoice() { return ui.voiceSel ? ui.voiceSel.value : ""; }
  function currentRate() { return ui.rateSel ? parseFloat(ui.rateSel.value) : 1.0; }

  function setStatus(msg) { if (ui.status) ui.status.textContent = msg || ""; }

  function highlightBoundaries(boundaries) {
    // 尽力而为：在当前可见 iframe 里按 text 匹配加高亮 class，失败不影响朗读
    if (!boundaries || !boundaries.length) return;
    try {
      var frames = document.querySelectorAll("#viewer iframe");
      var doc = frames.length ? frames[0].contentDocument : null;
      if (!doc || !doc.body) return;
      var old = doc.querySelectorAll(".tts-active-word");
      for (var j = 0; j < old.length; j++) old[j].classList.remove("tts-active-word");
      // 只做简单整段高亮：给 body 加一个标记，避免复杂 range 计算破坏 epub 布局
      doc.body.setAttribute("data-tts-reading", "1");
    } catch (e) { /* ignore */ }
  }

  function playSegment() {
    if (!playing) return;
    if (segIndex >= segments.length) { stop(); setStatus(""); return; }
    var text = segments[segIndex];
    var voice = currentVoice();
    setStatus("(" + (segIndex + 1) + "/" + segments.length + ")");

    fetch(TTS_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ input: text, voice: voice, rate: currentRate() })
    })
      .then(function (res) {
        if (!res.ok) throw new Error("tts http " + res.status);
        var raw = res.headers.get(HEADER);
        if (raw) {
          try { highlightBoundaries(JSON.parse(decodeURIComponent(raw))); } catch (e) { /* ignore */ }
        }
        return res.blob();
      })
      .then(function (blob) {
        if (!playing) return;
        if (audio) { audio.pause(); audio = null; }
        audio = new Audio(URL.createObjectURL(blob));
        audio.onended = function () {
          segIndex++;
          if (playing) playSegment();
        };
        audio.onerror = function () { stop(); setStatus(L.err); };
        return audio.play();
      })
      .catch(function (err) {
        log(err);
        stop();
        setStatus(L.err);
      });
  }

  function start() {
    var text = collectText();
    if (!text) { setStatus(L.noText); return; }
    segments = splitSegments(text);
    segIndex = 0;
    playing = true;
    updateButtons();
    playSegment();
  }

  function pause() {
    playing = false;
    if (audio) audio.pause();
    updateButtons();
  }

  function resume() {
    if (segIndex >= segments.length) { start(); return; }
    playing = true;
    updateButtons();
    if (audio) { audio.play(); } else { playSegment(); }
  }

  function stop() {
    playing = false;
    segIndex = 0;
    segments = [];
    if (audio) { audio.pause(); audio = null; }
    updateButtons();
  }

  function updateButtons() {
    if (!ui.playBtn) return;
    if (playing) {
      ui.playBtn.style.display = "none";
      ui.pauseBtn.style.display = "";
    } else {
      ui.playBtn.style.display = "";
      ui.pauseBtn.style.display = "none";
      ui.pauseBtn.textContent = L.resume;
      // 暂停（有残留段）显示“继续”，纯停止后 pause 按钮隐藏
      if (segIndex > 0 && segments.length) ui.pauseBtn.style.display = "";
    }
  }

  function loadVoices() {
    setStatus(L.loading);
    fetch(TTS_API + "?lang=zh-CN", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        voices = data.voices || [];
        ui.voiceSel.innerHTML = "";
        if (!voices.length) {
          var o = document.createElement("option");
          o.textContent = L.none;
          ui.voiceSel.appendChild(o);
          setStatus("");
          return;
        }
        voices.forEach(function (v, i) {
          var opt = document.createElement("option");
          opt.value = v.id;
          opt.textContent = v.name || v.id;
          // 默认选一个中文声音
          if ((v.language || "").indexOf("zh") === 0 && i < 5) opt.selected = true;
          ui.voiceSel.appendChild(opt);
        });
        setStatus(L.selectHint);
      })
      .catch(function () { setStatus(L.err); });
  }

  function buildUI() {
    var box = document.createElement("div");
    box.id = "mybooks-tts";
    box.style.cssText =
      "position:fixed;right:12px;bottom:12px;z-index:99999;" +
      "background:rgba(20,22,28,.92);color:#fff;border-radius:10px;" +
      "box-shadow:0 4px 18px rgba(0,0,0,.35);padding:10px 12px;" +
      "font:13px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;" +
      "max-width:min(320px,92vw);display:flex;flex-direction:column;gap:8px;";

    var title = document.createElement("div");
    title.textContent = "🔊 " + L.title;
    title.style.cssText = "font-weight:600;font-size:13px;opacity:.9;";
    box.appendChild(title);

    var row1 = document.createElement("div");
    row1.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;";
    ui.playBtn = mkBtn(L.play, primaryStyle);
    ui.pauseBtn = mkBtn(L.pause, "");
    ui.pauseBtn.style.display = "none";
    var stopBtn = mkBtn(L.stop, "");
    ui.playBtn.onclick = start;
    ui.pauseBtn.onclick = function () { playing ? pause() : resume(); };
    stopBtn.onclick = stop;
    row1.appendChild(ui.playBtn);
    row1.appendChild(ui.pauseBtn);
    row1.appendChild(stopBtn);
    box.appendChild(row1);

    var row2 = document.createElement("div");
    row2.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;";
    var voiceLabel = document.createElement("span");
    voiceLabel.textContent = L.voice + ":";
    ui.voiceSel = document.createElement("select");
    ui.voiceSel.style.cssText = baseInputStyle;
    ui.rateSel = document.createElement("select");
    ui.rateSel.style.cssText = baseInputStyle;
    [["0.75", L.r0], ["1.0", L.r1], ["1.25", L.r2], ["1.5", L.r3]].forEach(function (p) {
      var o = document.createElement("option");
      o.value = p[0]; o.textContent = p[1];
      if (p[0] === "1.0") o.selected = true;
      ui.rateSel.appendChild(o);
    });
    row2.appendChild(voiceLabel);
    row2.appendChild(ui.voiceSel);
    row2.appendChild(ui.rateSel);
    box.appendChild(row2);

    ui.status = document.createElement("div");
    ui.status.style.cssText = "font-size:11px;opacity:.7;min-height:14px;";
    box.appendChild(ui.status);

    (document.body || document.documentElement).appendChild(box);
    loadVoices();
  }

  var baseInputStyle =
    "background:#2c2f38;color:#fff;border:1px solid #454a57;border-radius:5px;" +
    "padding:3px 6px;font-size:12px;max-width:150px;";
  var primaryStyle =
    "background:#1976D2;color:#fff;border:none;border-radius:5px;padding:5px 10px;cursor:pointer;";
  function mkBtn(text, style) {
    var b = document.createElement("button");
    b.textContent = text;
    b.style.cssText = "background:#3a3f4a;color:#fff;border:none;border-radius:5px;padding:5px 10px;cursor:pointer;" + (style || "");
    return b;
  }

  function init() {
    if (document.getElementById("mybooks-tts")) return;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", buildUI);
    } else {
      buildUI();
    }
  }

  init();
})();
