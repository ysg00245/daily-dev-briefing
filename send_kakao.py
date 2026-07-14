#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_kakao.py
카카오 '나에게 보내기'(메시지 API)로 브리핑 요약 카드 + 링크를 전송한다.

흐름:
  1) refresh_token으로 access_token 갱신 (POST kauth.kakao.com/oauth/token)
  2) 갱신 응답에 새 refresh_token이 오면 config에 저장(로테이션 대응)
  3) feed 템플릿(제목/요약/버튼 링크)으로 memo/default/send 전송

함수: send_briefing(cfg_path, title, description, url) -> None
의존성: 표준 라이브러리(urllib)만 사용.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def _post(url, data, headers):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "ignore")}


def refresh_access_token(cfg, cfg_path):
    params = {
        "grant_type": "refresh_token",
        "client_id": cfg["kakao_rest_api_key"],
        "refresh_token": cfg["kakao_refresh_token"],
    }
    if cfg.get("kakao_client_secret"):
        params["client_secret"] = cfg["kakao_client_secret"]
    status, body = _post(
        TOKEN_URL,
        params,
        {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    if status != 200 or "access_token" not in body:
        raise RuntimeError(f"token refresh failed: {status} {body}")

    # refresh_token 로테이션: 새 값이 오면 저장
    if body.get("refresh_token"):
        cfg["kakao_refresh_token"] = body["refresh_token"]
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    return body["access_token"]


def send_briefing(cfg_path, title, description, url):
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    access_token = refresh_access_token(cfg, cfg_path)

    link = {"web_url": url, "mobile_web_url": url}
    template = {
        "object_type": "feed",
        "content": {
            "title": title,
            "description": description[:190],  # feed description 길이 여유 있게 컷
            "link": link,
        },
        "buttons": [
            {"title": "자세히 보기", "link": link},
        ],
    }
    status, body = _post(
        SEND_URL,
        {"template_object": json.dumps(template, ensure_ascii=False)},
        {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        },
    )
    if status != 200:
        raise RuntimeError(f"kakao send failed: {status} {body}")
    return body


if __name__ == "__main__":
    # 단독 테스트: python3 send_kakao.py <config> "제목" "요약" "https://url"
    cfg_path = sys.argv[1]
    send_briefing(cfg_path, sys.argv[2], sys.argv[3], sys.argv[4])
    print("kakao sent.")
