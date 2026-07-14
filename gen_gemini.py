#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_gemini.py
관심사 카테고리별로 Gemini(gemini-2.5-flash) + google_search 그라운딩을 호출해,
최근 1~2일 실제 뉴스를 근거로 브리핑 데이터(JSON)를 생성한다.

출력 스키마(= build_page.py가 그대로 먹는 형식):
{
  "date_iso", "date_label", "focus", "summary", "closer",
  "cat_summaries": {카테고리: 요약},
  "items": [
    {category, color, tier("essential"|"pick"), title, hook,
     detail:[블록], why?, source_title, source_url}
  ]
}
블록 type: "p"(문단) "h"(소제목) "list"(목록) "table"(표) "bars"(막대그래프) "note"(강조)

- 카테고리당 essential 1~2 + pick 5~7 (priority 높은=숫자 작은 → 7, 낮으면 5).
- essential detail: 문단 + (수치 있으면 table/bars) + list + note 조합으로 3~6블록.
- pick detail: 문단 2~3개. hook은 detail과 다르게 짧게.
- Gemini가 JSON만 반환하도록 유도하되, 코드펜스/설명이 섞여 와도 견고하게 추출·검증한다.
- 실제 호출: 표준 라이브러리 urllib (POST generateContent, tools:[{"google_search":{}}]).
- 그라운딩 소스 URL을 source_url에 채운다.

의존성: 표준 라이브러리(urllib) + read_interests(psycopg2)만.

사용:
  python gen_gemini.py [config.json] [--only "AI & Tech,국제"] [--out briefing_data.json]
  (--only 로 특정 카테고리만 테스트 호출 — quota 절약)
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import read_interests

MODEL = "gemini-2.5-flash"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

KST = dt.timezone(dt.timedelta(hours=9))
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


# ───────────────────────── 설정/키 로딩 ─────────────────────────
def load_gemini_key(cfg=None, here=None):
    """GEMINI_API_KEY: os.environ 우선, 없으면 ../.env.local(또는 cfg.env_local_path)에서."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    if here is None:
        here = os.path.dirname(os.path.abspath(__file__))
    env_path = (cfg or {}).get("env_local_path", "../.env.local")
    if not os.path.isabs(env_path):
        env_path = os.path.normpath(os.path.join(here, env_path))
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("GEMINI_API_KEY not found (env 또는 .env.local 확인)")


def kst_now():
    return dt.datetime.now(KST)


def date_fields(now=None):
    now = now or kst_now()
    iso = now.date().isoformat()
    label = f"{now.year}년 {now.month}월 {now.day}일 {_WEEKDAY_KO[now.weekday()]}요일"
    return iso, label


# ───────────────────────── Gemini 호출 ─────────────────────────
def call_gemini(prompt, key, temperature=0.4, retries=3, timeout=120):
    """generateContent 호출. 반환: (text, grounding_chunks[list of {title,uri}])."""
    url = ENDPOINT.format(model=MODEL, key=key)
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 20000,
            # 2.5-flash는 thinking 모델 — thinking이 토큰 예산을 잡아먹어 JSON이 잘리므로 끈다.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            cands = d.get("candidates") or []
            if not cands:
                raise RuntimeError(f"no candidates: {json.dumps(d)[:300]}")
            cand = cands[0]
            parts = (cand.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
            gm = cand.get("groundingMetadata") or {}
            chunks = []
            for ch in gm.get("groundingChunks") or []:
                web = ch.get("web") or {}
                if web.get("uri"):
                    chunks.append({"title": web.get("title", ""), "uri": web["uri"]})
            return text, chunks
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            last_err = f"HTTP {e.code}: {msg[:400]}"
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(4 * (attempt + 1))
                continue
            raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(4 * (attempt + 1))
                continue
            raise RuntimeError(last_err)
    raise RuntimeError(last_err or "unknown gemini error")


# ───────────────────────── JSON 추출 파서 ─────────────────────────
def extract_json(text):
    """코드펜스/설명이 섞여 와도 첫 번째 완결 JSON 오브젝트를 견고하게 추출한다."""
    if not text:
        raise ValueError("empty text")
    candidates = []
    # 1) 코드펜스 우선(greedy: 오브젝트 전체를 잡는다)
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    # 2) 중괄호 매칭(문자열/이스케이프 인식)으로 최상위 첫 오브젝트 스캔
    start = text.find("{")
    if start != -1:
        depth = 0
        in_str = False
        esc = False
        for j in range(start, len(text)):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start:j + 1])
                        break
    for cand in candidates:
        for variant in (cand, _loose_fix(cand)):
            try:
                return json.loads(variant)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no valid JSON found. head={text[:200]!r}")


def _loose_fix(s):
    """흔한 오류 완화: 트레일링 콤마 제거."""
    return re.sub(r",(\s*[}\]])", r"\1", s)


# ───────────────────────── 블록 검증/정규화 ─────────────────────────
_ALLOWED_BLOCK = {"p", "h", "list", "table", "bars", "note"}


def _norm_block(b):
    if not isinstance(b, dict):
        return {"type": "p", "text": str(b)}
    ty = b.get("type", "p")
    if ty not in _ALLOWED_BLOCK:
        ty = "p"
    if ty in ("p", "h", "note"):
        txt = str(b.get("text", "")).strip()
        return {"type": ty, "text": txt} if txt else None
    if ty == "list":
        items = [str(x).strip() for x in (b.get("items") or []) if str(x).strip()]
        return {"type": "list", "items": items} if items else None
    if ty == "table":
        rows = [[str(c) for c in r] for r in (b.get("rows") or []) if isinstance(r, list)]
        if not rows:
            return None
        return {
            "type": "table",
            "caption": str(b.get("caption", "")),
            "headers": [str(h) for h in (b.get("headers") or [])],
            "rows": rows,
        }
    if ty == "bars":
        data = []
        for d in b.get("data") or []:
            if isinstance(d, dict) and d.get("label") is not None and d.get("value") is not None:
                try:
                    data.append({"label": str(d["label"]), "value": float(d["value"])})
                except (TypeError, ValueError):
                    continue
        if not data:
            return None
        return {"type": "bars", "caption": str(b.get("caption", "")),
                "unit": str(b.get("unit", "")), "data": data}
    return None


def _norm_detail(detail):
    if isinstance(detail, str):
        return [{"type": "p", "text": p.strip()} for p in re.split(r"\n\n+", detail) if p.strip()]
    out = []
    for b in detail or []:
        nb = _norm_block(b)
        if nb:
            out.append(nb)
    return out


def _block_text_blob(detail):
    parts = []
    for b in detail:
        if b["type"] in ("p", "h", "note"):
            parts.append(b.get("text", ""))
        elif b["type"] == "list":
            parts.extend(b.get("items", []))
    return " ".join(parts)


def _pick_source(item, chunk_pool):
    """item의 source_url을 그라운딩 소스로 채운다.

    모델이 준 http(s) URL이 있으면 그대로 두되, 없거나 가짜면 그라운딩 chunk에서 배정.
    """
    url = str(item.get("source_url") or "").strip()
    title = str(item.get("source_title") or "").strip()
    good = url.startswith("http://") or url.startswith("https://")
    if not good and chunk_pool:
        ch = chunk_pool.pop(0)
        url = ch["uri"]
        if not title:
            title = ch["title"] or "출처"
    item["source_url"] = url or None
    item["source_title"] = title or "출처"
    return item


# ───────────────────────── 프롬프트 ─────────────────────────
def build_prompt(category, essential_n, pick_n, date_iso, date_label):
    return f"""너는 한국어 뉴스 브리핑 에디터다. 지금은 KST {date_label}({date_iso}) 이다.
google_search 도구로 '{category}' 분야의 **최근 1~2일(어제~오늘) 실제 뉴스**를 검색해 근거를 확보한 뒤,
아래 스키마의 **JSON 오브젝트 하나만** 출력하라. 설명·인사말·코드펜스 없이 순수 JSON만.

요구 사항:
- "cat_summary": 이 분야 오늘의 흐름을 1~2문장으로 요약.
- "items": 정확히 essential {essential_n}건 + pick {pick_n}건.
- 각 item 필드: tier("essential"|"pick"), title(핵심 헤드라인), hook(짧은 한 줄 요약 — detail과 겹치지 않게 detail보다 훨씬 짧게), detail(블록 배열), why(선택, "왜 중요한가" 한 줄), source_title(매체명 — 헤드라인), source_url(검색으로 확인한 실제 기사 URL).
- essential detail: 블록 3~6개. 반드시 문단("p") 1개 이상 + 목록("list") + 강조("note")를 포함하고, **수치·통계가 있으면** 표("table") 또는 막대그래프("bars")를 넣어라.
- pick detail: 문단("p") 2~3개.
- 실제로 검색된 사실만 사용하고, 확인 안 된 수치는 만들지 마라.

블록 형식(정확히 이 키만 사용):
- 문단:   {{"type":"p","text":"..."}}
- 소제목: {{"type":"h","text":"..."}}
- 목록:   {{"type":"list","items":["...","..."]}}
- 강조:   {{"type":"note","text":"..."}}
- 표:     {{"type":"table","caption":"...","headers":["열1","열2"],"rows":[["a","b"],["c","d"]]}}
- 막대:   {{"type":"bars","caption":"...","unit":"%","data":[{{"label":"항목","value":-8.9}}]}}

출력 스키마:
{{
  "cat_summary": "...",
  "items": [
    {{"tier":"essential","title":"...","hook":"...","detail":[ ...블록... ],"why":"...","source_title":"...","source_url":"https://..."}},
    {{"tier":"pick","title":"...","hook":"...","detail":[{{"type":"p","text":"..."}},{{"type":"p","text":"..."}}],"source_title":"...","source_url":"https://..."}}
  ]
}}
JSON만 출력."""


# ───────────────────────── 카테고리별 생성 ─────────────────────────
def counts_for(index, total):
    """priority 순서(index=0이 최상위). 상위 절반=essential2/pick7, 하위=essential1/pick5."""
    top_half = index < max(1, total // 2)
    return (2, 7) if top_half else (1, 5)


def generate_category(cat, index, total, key, date_iso, date_label, verbose=True):
    name = cat["name"]
    color = cat.get("color") or "#4f46e5"
    ess_n, pick_n = counts_for(index, total)
    prompt = build_prompt(name, ess_n, pick_n, date_iso, date_label)
    text, chunks = call_gemini(prompt, key)
    parsed = extract_json(text)

    cat_summary = str(parsed.get("cat_summary", "")).strip()
    raw_items = parsed.get("items") or []
    chunk_pool = list(chunks)
    items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        tier = "essential" if str(it.get("tier")) == "essential" else "pick"
        detail = _norm_detail(it.get("detail"))
        if not detail:
            continue
        hook = str(it.get("hook", "")).strip()
        blob = _block_text_blob(detail)
        # hook이 detail과 사실상 동일하면 앞문장으로 축약
        if hook and blob and (hook in blob and len(hook) > 60):
            hook = (blob.split(".")[0] or hook)[:70]
        norm = {
            "category": name,
            "color": color,
            "tier": tier,
            "title": str(it.get("title", "")).strip(),
            "hook": hook,
            "detail": detail,
        }
        if it.get("why"):
            norm["why"] = str(it["why"]).strip()
        norm["source_title"] = it.get("source_title")
        norm["source_url"] = it.get("source_url")
        _pick_source(norm, chunk_pool)
        items.append(norm)

    if verbose:
        ne = sum(1 for i in items if i["tier"] == "essential")
        print(f"  [{name}] items={len(items)} (essential={ne}) chunks={len(chunks)}", file=sys.stderr)
    return cat_summary, items


# ───────────────────────── 상위 요약 합성(추가 호출 없이) ─────────────────────────
def synthesize_top(items, n_cats):
    essentials = [i for i in items if i["tier"] == "essential"]
    lead = essentials[:3] if essentials else items[:3]
    hooks = [i["hook"] or i["title"] for i in lead if (i.get("hook") or i.get("title"))]
    summary = " / ".join(h.strip().rstrip(".") for h in hooks)[:400] or "오늘의 주요 소식을 분야별로 정리했습니다."
    focus = f"관심사 {n_cats}개 종합"
    closer = "숫자와 원문으로 확인하며 차분하게 — 오늘도 좋은 하루 보내세요."
    return focus, summary, closer


# ───────────────────────── 엔트리 ─────────────────────────
def build_briefing(cfg, only=None, verbose=True):
    here = os.path.dirname(os.path.abspath(__file__))
    key = load_gemini_key(cfg, here)
    interests = read_interests.fetch_interests(cfg, here)
    categories = interests.get("categories") or []
    if only:
        wanted = {c.strip() for c in only}
        categories = [c for c in categories if c["name"] in wanted]
    if not categories:
        raise RuntimeError("no categories to generate")

    date_iso, date_label = date_fields()
    total = len(categories)
    all_items = []
    cat_summaries = {}
    for i, cat in enumerate(categories):
        try:
            csum, items = generate_category(cat, i, total, key, date_iso, date_label, verbose)
            if csum:
                cat_summaries[cat["name"]] = csum
            all_items.extend(items)
        except Exception as e:  # noqa: BLE001
            print(f"  [WARN] {cat['name']} 생성 실패: {e}", file=sys.stderr)

    focus, summary, closer = synthesize_top(all_items, len(cat_summaries) or total)
    return {
        "date_iso": date_iso,
        "date_label": date_label,
        "focus": focus,
        "summary": summary,
        "closer": closer,
        "cat_summaries": cat_summaries,
        "items": all_items,
    }


def main():
    args = sys.argv[1:]
    cfg_path = None
    only = None
    out_path = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--only":
            only = args[i + 1].split(",")
            i += 2
        elif a == "--out":
            out_path = args[i + 1]
            i += 2
        else:
            cfg_path = a
            i += 1
    here = os.path.dirname(os.path.abspath(__file__))
    if not cfg_path:
        cfg_path = os.path.join(here, "kakao_config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    data = build_briefing(cfg, only=only)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {out_path}: {len(data['items'])} items", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
