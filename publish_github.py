#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_github.py
정적 HTML 파일들을 GitHub 저장소(=GitHub Pages 소스)로 발행한다.
GitHub Contents API(PUT /repos/{owner}/{repo}/contents/{path})만 사용 -> git/로컬 클론 불필요.

함수:
  publish_files(cfg, files) -> None
    files: {repo_path: html_string}  예) {"2026-07-13.html": "<html>...", "index.html": "..."}

의존성: 표준 라이브러리(urllib)만 사용.
"""
import base64
import json
import urllib.error
import urllib.request


def _api(cfg, method, path, payload=None):
    owner = cfg["github_owner"]
    repo = cfg["github_repo"]
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {cfg['github_token']}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "daily-dev-briefing-bot")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "ignore")}


def _get_sha(cfg, path):
    branch = cfg.get("github_branch", "main")
    status, body = _api(cfg, "GET", f"{path}?ref={branch}")
    if status == 200 and isinstance(body, dict):
        return body.get("sha")
    return None


def publish_file(cfg, repo_path, content, message):
    branch = cfg.get("github_branch", "main")
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    sha = _get_sha(cfg, repo_path)
    if sha:
        payload["sha"] = sha  # 기존 파일 갱신
    status, body = _api(cfg, "PUT", repo_path, payload)
    if status not in (200, 201):
        raise RuntimeError(f"publish failed {repo_path}: {status} {body}")
    return body


def publish_files(cfg, files, message="chore: daily briefing"):
    for repo_path, content in files.items():
        publish_file(cfg, repo_path, content, message)


if __name__ == "__main__":
    # 단독 테스트: python3 publish_github.py <config> <local_html> <repo_path>
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = json.load(f)
    with open(sys.argv[2], encoding="utf-8") as f:
        html = f.read()
    publish_file(cfg, sys.argv[3], html, "test: manual publish")
    print("published:", sys.argv[3])
