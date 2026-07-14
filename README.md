# daily-dev-briefing

관심사 기반 데일리 브리핑을 **서버(GitHub Actions cron)**에서 매일 자동 생성해
**GitHub Pages로 발행**하고 **카카오톡('나에게 보내기')으로 전송**한다.
PC·앱·로컬 폴더와 무관하게 동작한다.

## 실행 시각
- 스케줄: 매일 **KST 08:00 / 17:00** (워크플로 cron은 UTC `0 8,23 * * *`).
- 수동 실행: Actions 탭 → `daily-briefing` → **Run workflow**.

## 파이프라인 (`ci_run.py`)
1. `read_interests.py` — Neon DB에서 관심사 카테고리 조회(읽기 전용).
2. `gen_gemini.py` — 카테고리별로 **Gemini `gemini-2.5-flash` + Google Search 그라운딩**
   호출 → 최근 1~2일 실제 뉴스 근거로 `briefing_data.json` 생성.
3. `build_page.py` — 블록 렌더러로 `index.html` / `YYYY-MM-DD.html` 생성.
4. `publish_github.py` — GitHub Contents API로 발행(= GitHub Pages 소스).
5. `send_kakao.py` — refresh_token 갱신 후 요약 카드 + 링크 전송.

## 페이지
- 최신: https://ysg00245.github.io/daily-dev-briefing/
- 아카이브: `.../YYYY-MM-DD.html`

## 설정
- 시크릿 목록과 출처는 저장소 관리자용 문서(로컬 `SECRETS.md`) 참고.
- `kakao_config.json`은 워크플로가 시크릿에서 매 실행마다 생성한다(저장소에 커밋하지 않음).

## 로컬 실행
```
pip install -r requirements.txt
python ci_run.py            # ../.env.local(DATABASE_URL, GEMINI_API_KEY) + kakao_config.json 사용
python gen_gemini.py --only "AI & Tech" --out briefing_data.json   # 단일 카테고리 테스트
```
