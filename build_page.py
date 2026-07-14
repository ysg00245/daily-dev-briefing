#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_page.py — 브리핑 데이터(JSON) -> C 대시보드 + 필수/추천 2단 + 리치 상세.
- 카테고리 위젯: 요약 + 🔖 필수(풀 상세) / ✨ 추천(요약). 상단 탭 필터.
- 상세 모달: detail 이 문자열이면 문단 분리, 배열이면 블록 렌더
  블록 type: "p"(문단) "h"(소제목) "list"(목록) "table"(표) "bars"(막대그래프) "note"(강조)
- 하위호환: tier 없으면 pick, detail 없으면 body/hook. 외부 CDN 없음.
"""
import html
import json
import sys

PALETTE = ["#4f46e5", "#be123c", "#0e7490", "#b45309", "#15803d", "#7e22ce", "#0369a1", "#b91c1c"]
EMOJI = {"국제": "🌐", "주식 정보": "📈", "IT·과학": "🔬", "반려동물/동물": "🐾", "세계 경제": "💵",
         "IT 정보": "💻", "경제": "🏦", "음악": "🎵", "Creator Watch": "🎬", "자동차/교통": "🚗",
         "정치": "🏛️", "AI & Tech": "🤖", "영화/애니메이션": "🎞️"}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def tint(hexc):
    return (hexc + "22") if hexc.startswith("#") and len(hexc) in (4, 7) else "#eef2ff"


def hook_of(it):
    return it.get("hook") or (it.get("body", "").split(".")[0] if it.get("body") else "")


CSS = """
  :root{--bg:#f4f6fb;--card:#fff;--text:#1e293b;--muted:#64748b;--line:#e6eaf1;--line2:#eef2f7;
    --brand:#4f46e5;--shadow:0 1px 2px rgba(15,23,42,.04),0 8px 24px rgba(15,23,42,.06);}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
    background:var(--bg);color:var(--text);line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:660px;margin:0 auto;padding:20px 16px 56px}
  .eyebrow{font-size:12px;font-weight:800;letter-spacing:1.2px;color:var(--brand)}
  h1{font-size:24px;margin:6px 0 8px;letter-spacing:-.5px;line-height:1.25}
  .date{font-size:13px;color:var(--muted)}
  .key{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;border-radius:18px;padding:17px 19px;margin:16px 0 14px;box-shadow:var(--shadow)}
  .key b{font-size:11px;letter-spacing:1px;opacity:.9;font-weight:800}
  .key .k1{font-size:15px;line-height:1.6;margin-top:7px}
  .stat{display:flex;gap:10px;margin:0 0 6px}
  .scard{flex:1;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 8px;text-align:center;box-shadow:var(--shadow)}
  .snum{font-size:21px;font-weight:800;color:var(--brand)}.slab{font-size:11px;color:#94a3b8;margin-top:2px}
  .tabs{display:flex;gap:8px;overflow-x:auto;padding:14px 2px 10px;margin:0 -2px;position:sticky;top:0;z-index:20;
    background:linear-gradient(var(--bg) 80%,rgba(244,246,251,0));-ms-overflow-style:none;scrollbar-width:none}
  .tabs::-webkit-scrollbar{display:none}
  .tab{flex:0 0 auto;min-height:42px;border:1px solid var(--line);background:#fff;color:var(--muted);font-size:13px;
    font-weight:600;padding:9px 14px;border-radius:999px;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:6px;transition:.15s}
  .tab .count{font-size:11px;background:var(--line2);color:var(--muted);border-radius:999px;padding:1px 7px}
  .tab[aria-selected="true"]{background:var(--brand);border-color:var(--brand);color:#fff;box-shadow:var(--shadow)}
  .tab[aria-selected="true"] .count{background:rgba(255,255,255,.25);color:#fff}
  .widget{background:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);margin-bottom:13px;overflow:hidden}
  .whead{display:flex;align-items:center;gap:9px;padding:13px 16px 11px;border-left:5px solid var(--c,#cbd5e1)}
  .wemoji{font-size:17px}.wname{font-size:14.5px;font-weight:800;color:#334155;flex:1;letter-spacing:.2px}
  .wn{font-size:11.5px;font-weight:700;border-radius:999px;padding:2px 9px}
  .wsum{padding:0 16px 12px;border-left:5px solid var(--c);margin-top:-2px;font-size:13px;color:#64748b;line-height:1.6}
  .tier{padding:2px 12px 12px}
  .tlabel{font-size:11.5px;font-weight:800;letter-spacing:.5px;color:#94a3b8;padding:8px 4px 6px;display:flex;align-items:center;gap:5px}
  .ess{background:#fff;border:1px solid var(--line);border-left:3px solid var(--c);border-radius:12px;padding:12px 14px;margin:5px 0;cursor:pointer;transition:.12s}
  .ess:hover{box-shadow:0 5px 16px rgba(15,23,42,.09);transform:translateY(-1px)}
  .ess:focus-visible,.pick:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
  .ess .badge{display:inline-block;font-size:10px;font-weight:800;color:#fff;background:var(--c);border-radius:5px;padding:2px 7px;margin-bottom:6px}
  .ess .etitle{font-size:15.5px;font-weight:700;line-height:1.4;margin-bottom:4px}
  .ess .ehook{font-size:13px;color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .pick{display:flex;align-items:center;gap:11px;padding:11px 6px;border-top:1px solid #f1f5f9;cursor:pointer}
  .pick:first-of-type{border-top:none}
  .pdot{width:7px;height:7px;border-radius:50%;background:var(--c);flex:0 0 auto}
  .pmain{flex:1;min-width:0}.ptitle{font-size:14px;font-weight:700;line-height:1.38}
  .phook{font-size:12px;color:#94a3b8;margin-top:2px;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
  .parr{color:#cbd5e1;font-size:19px}
  .more{display:none}.more.show{display:flex}
  .morebtn{width:100%;margin-top:8px;padding:9px;background:#f8fafc;border:1px dashed var(--line);border-radius:10px;font-size:12.5px;font-weight:700;color:var(--brand);cursor:pointer}
  .hidden{display:none !important}
  footer{margin-top:22px;text-align:center;font-size:11px;color:#94a3b8}
  /* modal */
  .modal{position:fixed;inset:0;z-index:50;display:none;align-items:flex-end;justify-content:center;background:rgba(15,23,42,.52);backdrop-filter:blur(2px)}
  .modal.open{display:flex;animation:fade .18s ease}@keyframes fade{from{opacity:0}to{opacity:1}}
  .sheet{background:#fff;width:100%;max-width:660px;max-height:88vh;overflow-y:auto;border-radius:20px 20px 0 0;padding:14px 20px 32px;position:relative;animation:slup .24s cubic-bezier(.2,.8,.2,1)}
  @keyframes slup{from{transform:translateY(28px)}to{transform:translateY(0)}}
  .grip{width:38px;height:4px;border-radius:99px;background:#e2e8f0;margin:0 auto 12px}
  .close{position:absolute;top:12px;right:12px;width:44px;height:44px;border:none;background:#f1f5f9;border-radius:50%;font-size:20px;color:#475569;cursor:pointer}
  .d-pill{display:inline-block;font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px}
  .d-title{font-size:21px;line-height:1.35;margin:11px 44px 6px 0;letter-spacing:-.3px}
  .d-hook{font-size:14px;color:var(--muted);margin:0 0 14px;padding-bottom:13px;border-bottom:1px solid var(--line2)}
  /* rich blocks */
  .d-text p{font-size:15px;color:#334155;line-height:1.78;margin:0 0 13px}
  .d-text h4{font-size:14px;font-weight:800;color:#1e293b;margin:18px 0 8px;padding-left:9px;border-left:3px solid var(--brand)}
  .d-text ul{margin:0 0 14px;padding-left:2px;list-style:none}
  .d-text li{font-size:14.5px;color:#334155;line-height:1.7;padding-left:18px;position:relative;margin-bottom:6px}
  .d-text li:before{content:"";position:absolute;left:2px;top:10px;width:5px;height:5px;border-radius:50%;background:var(--brand)}
  .d-cap{font-size:12px;font-weight:700;color:#64748b;margin:2px 0 7px}
  .tblwrap{margin:4px 0 16px;overflow-x:auto}
  table{width:100%;border-collapse:collapse;font-size:13.5px;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
  th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line2)}
  th{background:#f8fafc;font-weight:800;color:#475569;font-size:12px}
  td{color:#334155}tr:last-child td{border-bottom:none}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  .bars{margin:4px 0 16px}
  .bar{display:flex;align-items:center;gap:9px;margin-bottom:8px}
  .blab{flex:0 0 76px;font-size:12.5px;color:#475569;font-weight:600;text-align:right}
  .btrack{flex:1;background:#f1f5f9;border-radius:7px;height:20px;overflow:hidden}
  .bfill{height:100%;background:linear-gradient(90deg,var(--brand),#7c3aed);border-radius:7px;min-width:2px}
  .bval{flex:0 0 auto;font-size:12.5px;font-weight:700;color:#334155;font-variant-numeric:tabular-nums}
  .d-note{margin:4px 0 14px;padding:11px 13px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;font-size:13.5px;color:#92400e;line-height:1.6}
  .d-why{margin-top:15px;padding:13px 15px;background:#eef2ff;border:1px solid #e0e7ff;border-radius:12px;font-size:13.5px;color:#3730a3}
  .d-why b{display:block;color:var(--brand);font-size:11.5px;letter-spacing:.4px;margin-bottom:3px}
  .d-src{display:inline-flex;align-items:center;gap:7px;min-height:48px;padding:12px 20px;margin-top:16px;background:var(--brand);color:#fff;text-decoration:none;border-radius:12px;font-size:14px;font-weight:700}
  @media(min-width:660px){.modal{align-items:center;padding:24px}.sheet{border-radius:20px}.grip{display:none}}
  @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

SCRIPT = r"""
(function(){
  var DB=JSON.parse(document.getElementById('briefing-db').textContent);
  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  var secs=[].slice.call(document.querySelectorAll('.sec'));
  tabs.forEach(function(t){t.addEventListener('click',function(){
    tabs.forEach(function(x){x.setAttribute('aria-selected',String(x===t));});
    var c=t.dataset.cat;
    secs.forEach(function(s){s.classList.toggle('hidden', c!=='all' && s.dataset.cat!==c);});
    window.scrollTo({top:0,behavior:'smooth'});
  });});
  [].slice.call(document.querySelectorAll('.morebtn')).forEach(function(b){
    b.addEventListener('click',function(){
      [].slice.call(b.previousElementSibling.querySelectorAll('.more')).forEach(function(m){m.classList.add('show');});
      b.style.display='none';
    });
  });
  function el(t,c,txt){var e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e;}
  function renderDetail(box,detail){
    box.innerHTML='';
    if(!detail){return;}
    if(typeof detail==='string'){
      detail.split(/\n\n+/).forEach(function(t){if(t.trim())box.appendChild(el('p',null,t.trim()));});
      return;
    }
    detail.forEach(function(b){
      if(!b)return;
      var ty=b.type||'p';
      if(ty==='h'){box.appendChild(el('h4',null,b.text));}
      else if(ty==='note'){box.appendChild(el('div','d-note',b.text));}
      else if(ty==='list'){var ul=el('ul');(b.items||[]).forEach(function(i){ul.appendChild(el('li',null,i));});box.appendChild(ul);}
      else if(ty==='table'){
        var w=el('div','tblwrap');if(b.caption)w.appendChild(el('div','d-cap',b.caption));
        var tb=el('table');
        if(b.headers){var tr=el('tr');b.headers.forEach(function(h,i){var th=el('th',i>0?'num':null,h);tr.appendChild(th);});tb.appendChild(tr);}
        (b.rows||[]).forEach(function(r){var tr=el('tr');r.forEach(function(cll,i){tr.appendChild(el('td',i>0?'num':null,cll));});tb.appendChild(tr);});
        w.appendChild(tb);box.appendChild(w);
      }
      else if(ty==='bars'){
        var w=el('div','bars');if(b.caption)w.appendChild(el('div','d-cap',b.caption));
        var vals=(b.data||[]).map(function(d){return Math.abs(Number(d.value))||0;});
        var max=Math.max.apply(null,vals.concat([1]));
        (b.data||[]).forEach(function(d){
          var row=el('div','bar');row.appendChild(el('span','blab',d.label));
          var tr=el('div','btrack');var fi=el('div','bfill');
          fi.style.width=(Math.abs(Number(d.value))/max*100)+'%';
          if(Number(d.value)<0)fi.style.background='linear-gradient(90deg,#e11d48,#fb7185)';
          tr.appendChild(fi);row.appendChild(tr);
          row.appendChild(el('span','bval',(d.value)+(b.unit||'')));
          w.appendChild(row);
        });
        box.appendChild(w);
      }
      else{box.appendChild(el('p',null,b.text||''));}
    });
  }
  var modal=document.getElementById('detail');
  function q(id){return document.getElementById(id);}
  function open(idx){
    var it=DB[idx];if(!it)return;
    var p=q('d-pill');p.textContent=it.category;p.style.background=it.bg;p.style.color=it.fg;
    q('d-title').textContent=it.title;
    q('d-hook').textContent=it.hook||'';q('d-hook').style.display=it.hook?'block':'none';
    renderDetail(q('d-text'),it.detail);
    var w=q('d-why');if(it.why){w.style.display='block';q('d-whytext').textContent=it.why;}else{w.style.display='none';}
    var s=q('d-src');if(it.source_url){s.style.display='inline-flex';s.href=it.source_url;}else{s.style.display='none';}
    modal.classList.add('open');document.body.style.overflow='hidden';
  }
  window.closeDetail=function(){modal.classList.remove('open');document.body.style.overflow='';};
  [].slice.call(document.querySelectorAll('[data-idx]')).forEach(function(node){
    node.setAttribute('tabindex','0');node.setAttribute('role','button');
    node.addEventListener('click',function(e){if(e.target.closest('a'))return;open(+node.dataset.idx);});
    node.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();open(+node.dataset.idx);}});
  });
  modal.addEventListener('click',function(e){if(e.target===modal)window.closeDetail();});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')window.closeDetail();});
})();
"""


def build_html(data):
    date_label = data.get("date_label", "")
    summary = data.get("summary", "")
    items = data.get("items", []) or []
    cat_summaries = data.get("cat_summaries", {}) or {}

    order, colors = [], {}
    for it in items:
        c = (it.get("category") or "기타").strip()
        if c not in colors:
            hexc = (it.get("color") or "").strip()
            colors[c] = hexc if (hexc.startswith("#") and len(hexc) in (4, 7)) else PALETTE[len(order) % len(PALETTE)]
            order.append(c)

    # 모달용 JSON DB (index = items 순서)
    db = []
    for it in items:
        col = colors[(it.get("category") or "기타").strip()]
        db.append({
            "category": it.get("category"), "title": it.get("title"), "hook": hook_of(it),
            "detail": it.get("detail") if it.get("detail") is not None else (it.get("body") or hook_of(it)),
            "why": it.get("why"), "source_url": it.get("source_url"),
            "bg": tint(col), "fg": col,
        })
    db_json = json.dumps(db, ensure_ascii=False).replace("</", "<\\/")

    n_ess = sum(1 for it in items if it.get("tier") == "essential")
    n_pick = sum(1 for it in items if it.get("tier") != "essential")

    tabs = ['<button class="tab" role="tab" aria-selected="true" data-cat="all">전체 <span class="count">'
            + str(len(items)) + '</span></button>']
    for i, c in enumerate(order):
        cnt = sum(1 for it in items if (it.get("category") or "기타").strip() == c)
        tabs.append('<button class="tab" role="tab" aria-selected="false" data-cat="c' + str(i) + '">'
                    + EMOJI.get(c, "") + ' ' + esc(c) + ' <span class="count">' + str(cnt) + '</span></button>')
    tabs_html = "\n      ".join(tabs)

    idx = 0
    secs = []
    for i, c in enumerate(order):
        col = colors[c]
        cat_items = [it for it in items if (it.get("category") or "기타").strip() == c]
        ess = [it for it in cat_items if it.get("tier") == "essential"]
        picks = [it for it in cat_items if it.get("tier") != "essential"]
        # 전역 인덱스: items 순서와 동일해야 하므로 재계산
        base = items.index(cat_items[0]) if cat_items else 0

        def gi(it):
            return items.index(it)

        ess_html = ""
        if ess:
            rows = ""
            for it in ess:
                rows += ('<div class="ess" data-idx="' + str(gi(it)) + '"><span class="badge">필수</span>'
                         + '<div class="etitle">' + esc(it.get("title")) + '</div>'
                         + '<div class="ehook">' + esc(hook_of(it)) + '</div></div>')
            ess_html = '<div class="tier"><div class="tlabel">🔖 꼭 봐야 할 것</div>' + rows + '</div>'

        pick_html = ""
        if picks:
            visible, hidden = picks[:5], picks[5:]

            def prow(it, extra=""):
                return ('<div class="pick' + extra + '" data-idx="' + str(gi(it)) + '"><span class="pdot"></span>'
                        + '<div class="pmain"><div class="ptitle">' + esc(it.get("title")) + '</div>'
                        + '<div class="phook">' + esc(hook_of(it)) + '</div></div><span class="parr">›</span></div>')
            rows = "".join(prow(it) for it in visible) + "".join(prow(it, " more") for it in hidden)
            btn = ('<button class="morebtn">추천 ' + str(len(hidden)) + '건 더 보기 ▾</button>') if hidden else ""
            pick_html = '<div class="tier"><div class="tlabel">✨ 관심사 추천</div><div class="pickbox">' + rows + '</div>' + btn + '</div>'

        csum = cat_summaries.get(c)
        sum_html = ('<div class="wsum">' + esc(csum) + '</div>') if csum else ""

        secs.append(
            '<section class="sec" data-cat="c' + str(i) + '"><div class="widget" style="--c:' + col + '">'
            + '<div class="whead"><span class="wemoji">' + EMOJI.get(c, "📰") + '</span>'
            + '<span class="wname">' + esc(c) + '</span>'
            + '<span class="wn" style="background:' + tint(col) + ';color:' + col + '">' + str(len(cat_items)) + '</span></div>'
            + sum_html + ess_html + pick_html + '</div></section>'
        )
    secs_html = "\n".join(secs)

    head = ('<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            '<title>오늘 브리핑 · ' + esc(date_label) + '</title>\n<style>' + CSS + '</style>\n</head>\n<body>\n')
    body = (
        '  <div class="wrap">\n    <div class="eyebrow">오늘 브리핑</div>\n'
        '    <h1>한눈에 보는 맞춤 브리핑</h1>\n    <div class="date">' + esc(date_label) + '</div>\n'
        '    <div class="key"><b>오늘의 핵심</b><div class="k1">' + esc(summary) + '</div></div>\n'
        '    <div class="stat">'
        '<div class="scard"><div class="snum">' + str(len(order)) + '</div><div class="slab">관심 분야</div></div>'
        '<div class="scard"><div class="snum">' + str(n_ess) + '</div><div class="slab">필수</div></div>'
        '<div class="scard"><div class="snum">' + str(n_pick) + '</div><div class="slab">추천</div></div></div>\n'
        '    <div class="tabs" role="tablist">\n      ' + tabs_html + '\n    </div>\n'
        + secs_html +
        '\n    <footer>매일 08·17시 · 백사장님을 위한 자동 브리핑</footer>\n  </div>\n\n'
        '  <div id="detail" class="modal" role="dialog" aria-modal="true"><div class="sheet"><div class="grip"></div>'
        '<button class="close" onclick="closeDetail()" aria-label="닫기">×</button>\n'
        '    <span id="d-pill" class="d-pill"></span>\n    <h2 id="d-title" class="d-title"></h2>\n'
        '    <p id="d-hook" class="d-hook"></p>\n    <div id="d-text" class="d-text"></div>\n'
        '    <div id="d-why" class="d-why"><b>왜 유용한가</b><span id="d-whytext"></span></div>\n'
        '    <a id="d-src" class="d-src" target="_blank" rel="noopener">🔗 원문 보기 ↗</a>\n  </div></div>\n'
        '  <script id="briefing-db" type="application/json">' + db_json + '</script>\n'
    )
    tail = '<script>' + SCRIPT + '</script>\n</body>\n</html>\n'
    return head + body + tail


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "briefing_data.json"
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    sys.stdout.write(build_html(data))


if __name__ == "__main__":
    main()
