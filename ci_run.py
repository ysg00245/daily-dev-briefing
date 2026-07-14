#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ci_run.py — 서버(GitHub Actions) 오케스트레이터.

흐름:
  read_interests(관심사) → gen_gemini(Gemini+google_search로 briefing_data.json 생성)
  → build_page(site/index.html + 날짜.html) → publish_github(GitHub Pages 발행)
  → send_kakao(카카오톡 전송)

설정은 kakao_config.json + 환경변수(DATABASE_URL, GEMINI_API_KEY)에서 읽는다.
CI에서는 워크플로가 시크릿으로 kakao_config.json을 생성하고 env를 넣어 준다.
로컬에서도 그대로 동작한다(../.env.local + kakao_config.json).

사용: python ci_run.py [kakao_config.json]
"""
import datetime as dt
import json
import os
import sys

import build_page
import gen_gemini
import publish_github
import send_kakao


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "kakao_config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    # 1) 관심사 조회 + Gemini 그라운딩으로 브리핑 데이터 생성
    print("[1/5] Gemini로 브리핑 데이터 생성 중...", file=sys.stderr)
    data = gen_gemini.build_briefing(cfg)
    if not data.get("items"):
        raise RuntimeError("생성된 items가 0건입니다 — 발행/전송을 중단합니다.")

    date_iso = data.get("date_iso") or dt.date.today().isoformat()

    # 2) briefing_data.json 저장(디버그/아카이브용, 커밋 대상 아님)
    with open(os.path.join(here, "briefing_data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[2/5] briefing_data.json 저장 — items {len(data['items'])}건", file=sys.stderr)

    # 3) HTML 생성 + 로컬 백업(site/)
    html = build_page.build_html(data)
    site_dir = os.path.join(here, "site")
    os.makedirs(site_dir, exist_ok=True)
    for name in (f"{date_iso}.html", "index.html"):
        with open(os.path.join(site_dir, name), "w", encoding="utf-8") as f:
            f.write(html)
    print("[3/5] HTML 생성 완료", file=sys.stderr)

    # 4) GitHub Pages 발행 (index.html=최신, 날짜별=아카이브)
    publish_github.publish_files(
        cfg,
        {f"{date_iso}.html": html, "index.html": html},
        message=f"briefing: {date_iso}",
    )
    print("[4/5] GitHub Pages 발행 완료", file=sys.stderr)

    # 5) 카카오톡 전송
    base = cfg["public_base_url"].rstrip("/")
    url = f"{base}/{date_iso}.html"
    cats = []
    for it in data.get("items", []):
        c = (it.get("category") or "").strip()
        if c and c not in cats:
            cats.append(c)
    title = f"오늘 브리핑 · {data.get('date_label', date_iso)}"
    desc = f"{data.get('summary', '')}\n\n분야 {len(cats)} · 소식 {len(data['items'])}건 · " + " / ".join(cats[:5])
    send_kakao.send_briefing(cfg_path, title, desc, url)
    print(f"[5/5] 완료 — 발행 {url}, 카카오톡 전송됨", file=sys.stderr)


if __name__ == "__main__":
    main()
