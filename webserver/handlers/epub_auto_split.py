# -*- coding: UTF-8 -*-
"""合集自动分册 —— HTTP 接口 + 自带 UI 的独立工具页。

为什么要自带 HTML 页：mybooks 前端是 Nuxt 编译后的 dist，改动 .vue 需要重新
build 才能生效；本页用 BaseHandler 直接 self.write(HTML) 输出，配合后端 .py
即可热更新，无需重新编译前端。鉴权沿用 cookie session + 管理员校验。

路由（在 toolbox.routes() 里注册）：
  GET  /api/toolbox/epub_auto_split/page    独立工具页（HTML，走 /api/ 反代）
  POST /api/toolbox/epub_auto_split/detect 解析目录 + 自动检测分册
  POST /api/toolbox/epub_auto_split/batch  按确认的分组批量拆分
"""
import logging

import tornado

from webserver.i18n import _
from webserver.handlers.base import BaseHandler, js, is_admin
from webserver.toolbox.epub_auto_split import EpubAutoSplitTool

logger = logging.getLogger(__name__)


class AdminEpubAutoSplitPage(BaseHandler):
    """独立工具页：直接输出自包含 HTML（无需 Nuxt 编译）。"""

    def get(self):
        if not self.current_user:
            return self.redirect("/login")
        if not self.admin_user:
            self.set_status(403)
            return self.write("403 Forbidden — 仅管理员可用")
        self.set_header("Content-Type", "text/html; charset=UTF-8")
        self.set_header("Cache-Control", "no-store")
        self.write(HTML_PAGE)


class AdminEpubAutoSplitDetect(BaseHandler):
    @js
    @is_admin
    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        book_id = data.get("book_id")
        if not book_id:
            return {"err": "params.missing", "msg": _("请提供书籍ID")}
        try:
            result = EpubAutoSplitTool().detect(int(book_id))
        except RuntimeError as err:
            return {"err": "epub_auto_split.failed", "msg": str(err)}
        except Exception as err:
            logger.exception("[EpubAutoSplit] detect failed")
            return {"err": "epub_auto_split.failed", "msg": "解析失败：%s" % err}
        return {"err": "ok", "data": result}


class AdminEpubAutoSplitBatch(BaseHandler):
    @js
    @is_admin
    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        book_id = data.get("book_id")
        volumes = data.get("volumes")
        use_chapter_cover = bool(data.get("use_chapter_cover", True))
        if not book_id:
            return {"err": "params.missing", "msg": _("请提供书籍ID")}
        if not isinstance(volumes, list) or not volumes:
            return {"err": "params.missing", "msg": _("请至少保留一个分册")}
        # 清洗参数，避免脏数据进入后端
        clean = []
        for v in volumes:
            try:
                clean.append({
                    "name": str(v.get("name") or "未命名分册"),
                    "start": int(v["start"]),
                    "end": int(v["end"]),
                })
            except Exception:
                return {"err": "params.invalid", "msg": _("分册参数无效")}
        try:
            result = EpubAutoSplitTool().batch_split(
                int(book_id), clean, self.user_id(),
                use_chapter_cover=use_chapter_cover,
            )
        except RuntimeError as err:
            return {"err": "epub_auto_split.failed", "msg": str(err)}
        except Exception as err:
            logger.exception("[EpubAutoSplit] batch failed")
            return {"err": "epub_auto_split.failed", "msg": "拆分失败：%s" % err}
        return {"err": "ok", "msg": _("拆分完成"), "data": result}


def routes():
    return [
        # 注意：页面必须挂在 /api/ 前缀下。nginx 只把 ^/(api|get|read|opds|auth)/ 反代到
        # tornado，其它路径落到 Nuxt 的 SPA 兜底返回 index.html（见 nginx 配置）。
        (r"/api/toolbox/epub_auto_split/page", AdminEpubAutoSplitPage),
        (r"/api/toolbox/epub_auto_split/detect", AdminEpubAutoSplitDetect),
        (r"/api/toolbox/epub_auto_split/batch", AdminEpubAutoSplitBatch),
    ]


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>合集自动分册 · MyBooks</title>
<style>
  :root{--bg:#0d1b2a;--card:#16263a;--card2:#1b3350;--line:#2a4360;--fg:#e6eef7;--muted:#9fb3c8;
        --pri:#4f8cff;--pri2:#3a6fd8;--ok:#37c98a;--warn:#ffb84d;--err:#ff6b6b}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.5}
  .wrap{max-width:1080px;margin:0 auto;padding:28px 18px 80px}
  h1{font-size:24px;margin:0 0 6px;color:#fff}
  .sub{color:var(--muted);font-size:14px;margin-bottom:22px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:18px}
  .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  input[type=text],input[type=number],select{background:var(--card2);border:1px solid var(--line);color:var(--fg);
        border-radius:8px;padding:9px 12px;font-size:14px;outline:none}
  input[type=text]:focus,input[type=number]:focus,select:focus{border-color:var(--pri)}
  input.grow{flex:1;min-width:200px}
  button{border:0;border-radius:8px;padding:9px 16px;font-size:14px;cursor:pointer;font-weight:600;transition:.15s}
  button:disabled{opacity:.45;cursor:not-allowed}
  .btn-pri{background:var(--pri);color:#fff}
  .btn-pri:hover:not(:disabled){background:var(--pri2)}
  .btn-ghost{background:var(--card2);color:var(--fg);border:1px solid var(--line)}
  .btn-ghost:hover:not(:disabled){border-color:var(--pri)}
  .btn-danger{background:transparent;color:var(--err);border:1px solid #5a2a2a}
  .btn-danger:hover{background:#3a1f1f}
  .btn-ok{background:var(--ok);color:#06281c}
  .hint{color:var(--muted);font-size:13px}
  .alert{padding:12px 16px;border-radius:10px;margin-bottom:16px;font-size:14px}
  .alert.err{background:#3a1f22;border:1px solid #7a3540;color:#ffc3c3}
  .alert.ok{background:#12382b;border:1px solid #2a6b50;color:#a8f0cf}
  .alert.info{background:#1b2f4a;border:1px solid var(--line);color:#bcd6f5}
  .search-results{margin-top:12px;display:grid;gap:8px;max-height:300px;overflow:auto}
  .book-item{display:flex;gap:12px;align-items:center;padding:10px;border:1px solid var(--line);
        border-radius:10px;cursor:pointer;background:var(--card2)}
  .book-item:hover{border-color:var(--pri)}
  .book-item.sel{border-color:var(--pri);background:#1e3c63}
  .book-thumb{width:42px;height:56px;background:#0b1626;border-radius:4px;object-fit:cover;flex:none}
  .book-meta b{font-size:14px}.book-meta span{display:block;color:var(--muted);font-size:12px}
  .vols{display:grid;gap:12px}
  .vol{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
  .vol-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .vol-idx{width:28px;height:28px;border-radius:50%;background:var(--pri);color:#fff;display:grid;
        place-items:center;font-weight:700;flex:none}
  .vol-name{flex:1;min-width:180px}
  .vol-range{display:flex;gap:6px;align-items:center;color:var(--muted);font-size:13px}
  .vol-range select{max-width:200px}
  .vol-tags{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
  .tag{background:#0b1626;border:1px solid var(--line);border-radius:20px;padding:3px 10px;font-size:12px;color:var(--muted)}
  .conf{font-size:12px;padding:2px 8px;border-radius:20px}
  .conf.high{background:#12382b;color:#7fe0b4}.conf.mid{background:#3a3018;color:#ffd488}
  .vol-actions{display:flex;gap:6px;margin-left:auto}
  .icon-btn{background:transparent;border:1px solid var(--line);color:var(--muted);border-radius:8px;
        padding:6px 10px;cursor:pointer;font-size:13px}
  .icon-btn:hover{color:var(--fg);border-color:var(--pri)}
  .bar{position:sticky;bottom:0;background:linear-gradient(transparent,#0d1b2a 30%);padding:16px 0 8px;margin-top:10px}
  .bar-inner{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 18px;
        display:flex;gap:12px;align-items:center;flex-wrap:wrap;box-shadow:0 8px 28px rgba(0,0,0,.4)}
  .stat{color:var(--muted);font-size:13px}.stat b{color:var(--fg)}
  .spin{width:16px;height:16px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;
        display:inline-block;animation:sp .7s linear infinite;vertical-align:-3px;margin-right:6px}
  @keyframes sp{to{transform:rotate(360deg)}}
  .result-item{display:flex;gap:10px;align-items:center;padding:9px 12px;border-radius:9px;
        background:var(--card2);border:1px solid var(--line);font-size:14px}
  .result-item.ok a{color:var(--ok)}.result-item.fail{color:var(--err)}
  .empty{text-align:center;color:var(--muted);padding:30px}
  code{background:#0b1626;padding:1px 6px;border-radius:4px;font-size:12px}
</style>
</head>
<body>
<div class="wrap">
  <h1>📚 合集自动分册</h1>
  <div class="sub">自动识别套装/全集 EPUB 的每一册，微调确认后一次拆成多本新书。新书沿用原书的作者、标签、分类；封面优先取该册第一张大图。</div>

  <div id="alertBox"></div>

  <!-- 步骤 1：搜索 -->
  <div class="card">
    <div class="row">
      <input id="q" class="grow" type="text" placeholder="输入合集书名搜索，例如：莫言经典作品集" autocomplete="off">
      <button class="btn-pri" id="btnSearch">搜索</button>
    </div>
    <div class="search-results" id="results"></div>
  </div>

  <!-- 步骤 2：选书后自动检测 -->
  <div class="card" id="detectCard" style="display:none">
    <div class="row">
      <div style="flex:1">
        <b id="selTitle"></b>
        <div class="hint" id="selMeta"></div>
      </div>
      <button class="btn-ghost" id="btnRedetect">重新检测</button>
    </div>
    <div id="detectStatus" class="hint" style="margin-top:10px"></div>
  </div>

  <!-- 步骤 3：分册微调 -->
  <div class="card" id="editCard" style="display:none">
    <div class="row" style="justify-content:space-between">
      <b>分册预览与微调</b>
      <span class="hint">可改书名、调整每册起止章节、删除或合并分册</span>
    </div>
    <div class="vols" id="vols" style="margin-top:14px"></div>
  </div>

  <!-- 步骤 4：一键拆分 -->
  <div class="bar" id="actionBar" style="display:none">
    <div class="bar-inner">
      <label class="stat"><input type="checkbox" id="useCover" checked> 用各册大图作封面</label>
      <span class="stat">共 <b id="statVol">0</b> 册 · <b id="statCh">0</b> 章节</span>
      <button class="btn-pri" id="btnSplit" style="margin-left:auto">🚀 一键拆成多本</button>
    </div>
  </div>

  <!-- 结果 -->
  <div class="card" id="resultCard" style="display:none">
    <b>拆分结果</b>
    <div id="resultList" style="margin-top:12px;display:grid;gap:8px"></div>
  </div>
</div>

<script>
(function(){
  var state = {book:null, chapters:[], volumes:[]};
  var $ = function(id){return document.getElementById(id);};
  function api(path, body){
    return fetch(path, {method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{})})
      .then(function(r){return r.json();});
  }
  function alertBox(msg, type){
    $('alertBox').innerHTML = msg ? '<div class="alert '+type+'">'+msg+'</div>' : '';
  }
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

  // ---- 搜索 ----
  $('btnSearch').onclick = search;
  $('q').addEventListener('keyup', function(e){if(e.key==='Enter')search();});
  function search(){
    var q = ($('q').value||'').trim();
    if(!q){alertBox('请输入书名关键词','info');return;}
    alertBox('');
    $('results').innerHTML='<div class="empty"><span class="spin"></span>搜索中…</div>';
    fetch('/api/search?title=title:'+encodeURIComponent(q), {credentials:'same-origin'})
      .then(function(r){return r.json();})
      .then(function(rsp){
        var books=(rsp&&rsp.books)||[];
        if(!books.length){$('results').innerHTML='<div class="empty">未找到相关书籍</div>';return;}
        $('results').innerHTML = books.map(function(b,i){
          var thumb=(b.thumb||'');
          var fmt=(b.files||[]).map(function(f){return f.format;}).join(', ');
          return '<div class="book-item" data-i="'+i+'">'+
            (thumb?'<img class="book-thumb" src="'+esc(thumb)+'" alt="">':'<div class="book-thumb"></div>')+
            '<div class="book-meta"><b>'+esc(b.title)+'</b><span>'+esc((b.authors||[]).join(', '))+
            ' · '+esc(fmt)+'</span></div></div>';
        }).join('');
        Array.prototype.forEach.call($('results').querySelectorAll('.book-item'),function(el){
          el.onclick=function(){selectBook(books[+el.getAttribute('data-i')], el);};
        });
      }).catch(function(e){$('results').innerHTML='<div class="empty">搜索失败：'+esc(e)+'</div>';});
  }

  // ---- 选书 + 检测 ----
  function selectBook(book, el){
    Array.prototype.forEach.call($('results').querySelectorAll('.book-item'),function(x){x.classList.remove('sel');});
    if(el) el.classList.add('sel');
    var hasEpub=(book.files||[]).some(function(f){return f.format==='EPUB';});
    if(!hasEpub){alertBox('所选书籍没有 EPUB 格式，无法拆分','err');return;}
    state.book=book;
    $('selTitle').textContent=book.title;
    $('selMeta').textContent='正在解析目录…';
    $('detectCard').style.display='';
    $('editCard').style.display='none';$('actionBar').style.display='none';$('resultCard').style.display='none';
    $('detectStatus').innerHTML='<span class="spin"></span>正在自动识别分册，请稍候…';
    detect(book.id);
  }
  $('btnRedetect').onclick=function(){if(state.book)detect(state.book.id);};
  function detect(bookId){
    alertBox('');
    api('/api/toolbox/epub_auto_split/detect',{book_id:bookId})
      .then(function(rsp){
        if(rsp.err!=='ok'){alertBox(esc(rsp.msg||'检测失败'),'err');
          $('detectStatus').textContent='检测失败';return;}
        var d=rsp.data;
        state.chapters=d.chapters||[];state.volumes=d.volumes||[];
        $('selMeta').textContent='作者：'+(d.authors||[]).join('、')+' · 共 '+d.total_chapters+' 个章节节点';
        $('detectStatus').textContent='自动识别出 '+state.volumes.length+' 个分册'+
          (state.volumes.length===1?'（未检测到合集边界，已按整本处理，可手动调整）':'');
        renderVolumes();
      }).catch(function(e){alertBox('检测失败：'+esc(e),'err');$('detectStatus').textContent='检测失败';});
  }

  // ---- 渲染分册（可微调）----
  function chapterOptions(sel){
    return state.chapters.map(function(c){
      return '<option value="'+c.num+'"'+(c.num===sel?' selected':'')+'>'+esc(c.title)+'</option>';
    }).join('');
  }
  function renderVolumes(){
    var box=$('vols');
    box.innerHTML=state.volumes.map(function(v,i){
      var conf=v.confidence>=0.85?'high':'mid';
      var tags=(v.titles||[]).slice(0,5).map(function(t){return '<span class="tag">'+esc(t)+'</span>';}).join('');
      return '<div class="vol" data-i="'+i+'">'+
        '<div class="vol-head">'+
          '<div class="vol-idx">'+(i+1)+'</div>'+
          '<input class="vol-name" type="text" value="'+esc(v.name)+'" data-f="name">'+
          '<span class="conf '+conf+'">'+(v.confidence||0)+' 置信</span>'+
          '<div class="vol-actions">'+
            (i>0?'<button class="icon-btn" data-act="merge" title="与上一册合并">⇤合并</button>':'')+
            '<button class="icon-btn" data-act="del" title="删除该分册">删除</button>'+
          '</div>'+
        '</div>'+
        '<div class="vol-range" style="margin-top:8px">'+
          '<span>起</span><select data-f="start">'+chapterOptions(v.start)+'</select>'+
          '<span>止</span><select data-f="end">'+chapterOptions(v.end)+'</select>'+
          '<span class="hint">('+(v.end-v.start+1)+' 节点)</span>'+
        '</div>'+
        (tags?'<div class="vol-tags">'+tags+'</div>':'')+
      '</div>';
    }).join('');
    // 事件绑定
    Array.prototype.forEach.call(box.querySelectorAll('.vol'),function(el){
      var i=+el.getAttribute('data-i');
      el.querySelector('[data-f=name]').oninput=function(e){state.volumes[i].name=e.target.value;};
      el.querySelector('[data-f=start]').onchange=function(e){
        state.volumes[i].start=+e.target.value; refreshStats();};
      el.querySelector('[data-f=end]').onchange=function(e){
        state.volumes[i].end=+e.target.value; refreshStats();};
      Array.prototype.forEach.call(el.querySelectorAll('[data-act]'),function(b){
        b.onclick=function(){
          var act=b.getAttribute('data-act');
          if(act==='del'){ state.volumes.splice(i,1); }
          else if(act==='merge' && i>0){
            var prev=state.volumes[i-1], cur=state.volumes[i];
            prev.end=cur.end; // 扩展到当前册末尾
            state.volumes.splice(i,1);
          }
          renderVolumes();
        };
      });
    });
    $('editCard').style.display='';$('actionBar').style.display='';$('resultCard').style.display='none';
    refreshStats();
  }
  function refreshStats(){
    var vol=state.volumes.length, ch=0;
    state.volumes.forEach(function(v){ch+=Math.max(0,v.end-v.start+1);});
    $('statVol').textContent=vol;$('statCh').textContent=ch;
    $('btnSplit').disabled=(vol===0);
  }

  // ---- 一键拆分 ----
  $('btnSplit').onclick=function(){
    if(!state.book||!state.volumes.length)return;
    // 简单校验范围
    for(var i=0;i<state.volumes.length;i++){
      var v=state.volumes[i];
      if(v.end<v.start){alertBox('第'+(i+1)+'册的结束章节早于开始章节','err');return;}
    }
    var btn=$('btnSplit');
    btn.disabled=true;btn.innerHTML='<span class="spin"></span>拆分中…';
    alertBox('');$('resultCard').style.display='none';
    api('/api/toolbox/epub_auto_split/batch',{
      book_id:state.book.id, volumes:state.volumes,
      use_chapter_cover:$('useCover').checked
    }).then(function(rsp){
      btn.disabled=false;btn.textContent='🚀 一键拆成多本';
      if(rsp.err!=='ok'){alertBox(esc(rsp.msg||'拆分失败'),'err');return;}
      var d=rsp.data;
      alertBox('完成：成功 '+d.succeeded+' 本，失败 '+d.failed+' 本',
        d.failed?'info':'ok');
      $('resultList').innerHTML=d.results.map(function(r){
        if(r.ok) return '<div class="result-item ok">✅ <a href="/book/'+r.book_id+'" target="_blank">'+esc(r.name)+'</a> <span class="hint">book_id='+r.book_id+'</span></div>';
        return '<div class="result-item fail">❌ '+esc(r.name)+' — '+esc(r.error||'失败')+'</div>';
      }).join('');
      $('resultCard').style.display='';
    }).catch(function(e){
      btn.disabled=false;btn.textContent='🚀 一键拆成多本';
      alertBox('拆分失败：'+esc(e),'err');
    });
  };
})();
</script>
</body>
</html>"""
