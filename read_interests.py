#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
read_interests.py
jarvis-board의 Neon DB에서 사용자의 브리핑 관심사를 '읽기 전용'으로 조회한다.
관심사 수정은 jarvis-board 대시보드에서 하고, 이 스크립트는 그 결과를 읽기만 한다.

출력: stdout에 JSON
{
  "user_id": "...",
  "items_per_category": 3,
  "categories": [{"name":"AI & Tech","slug":"ai-tech","color":"#059669","priority":5}, ...],
  "custom_categories": [...]
}

DATABASE_URL 해석(하위호환):
  - 로컬: kakao_config.json의 env_local_path(기본 ../.env.local) 파일에서 읽는다.
  - CI:   그 파일이 없으면 os.environ["DATABASE_URL"] 로 폴백한다.

사용: python3 read_interests.py [config.json 경로]
"""
import json
import os
import sys

import psycopg2


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_database_url(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(f"DATABASE_URL not found in {env_path}")


def resolve_database_url(cfg, here):
    """env_local_path 파일이 있으면 거기서, 없으면 os.environ["DATABASE_URL"]에서 읽는다."""
    env_path = cfg.get("env_local_path", "../.env.local")
    if not os.path.isabs(env_path):
        env_path = os.path.normpath(os.path.join(here, env_path))
    if os.path.isfile(env_path):
        return load_database_url(env_path)
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    raise RuntimeError(
        f"DATABASE_URL not found: {env_path} 파일도 없고 os.environ['DATABASE_URL']도 비어 있음"
    )


def normalize_dsn(dsn):
    # verify-full은 root 인증서 파일을 요구하므로, 실행 환경 호환을 위해 require로 낮춘다.
    base = dsn.split("?")[0]
    return base + "?sslmode=require"


def fetch_interests(cfg, here=None):
    """cfg(dict)를 받아 관심사 딕셔너리를 반환한다(읽기 전용). gen_gemini/ci_run에서 재사용."""
    if here is None:
        here = os.path.dirname(os.path.abspath(__file__))
    dsn = normalize_dsn(resolve_database_url(cfg, here))
    uid = cfg["db_user_id"]

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT ic.name, ic.slug, ic.color_hex, ui.priority
        FROM user_interests ui
        JOIN interest_categories ic ON ic.id = ui.category_id
        WHERE ui.user_id = %s AND ui.use_briefing = true
        ORDER BY ui.priority NULLS LAST, ic.name
        """,
        (uid,),
    )
    categories = [
        {"name": r[0], "slug": r[1], "color": r[2], "priority": r[3]}
        for r in cur.fetchall()
    ]

    exclude = set(cfg.get("exclude_categories") or [])
    if exclude:
        categories = [c for c in categories if c["name"] not in exclude]

    items_per_category = 3
    custom_categories = []
    try:
        cur.execute(
            "SELECT items_per_category, custom_categories FROM briefing_settings WHERE user_id = %s",
            (uid,),
        )
        row = cur.fetchone()
        if row:
            if row[0]:
                items_per_category = int(row[0])
            if row[1]:
                custom_categories = row[1] if isinstance(row[1], list) else json.loads(row[1])
    except Exception as e:  # noqa: BLE001
        print(f"# warn: briefing_settings read failed: {e}", file=sys.stderr)

    cur.close()
    conn.close()

    return {
        "user_id": uid,
        "items_per_category": items_per_category,
        "categories": categories,
        "custom_categories": custom_categories,
    }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "kakao_config.json")
    cfg = load_config(cfg_path)
    out = fetch_interests(cfg, here)
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
