#!/usr/bin/env python3
"""
네이버 카페 자동 모니터링 — GitLab CI/CD 전용 독립 실행 스크립트
1시간마다 스케줄 실행 → 신규 게시글 수집 → Google Sheets 저장 → Slack 알림

환경변수:
  NAVER_SESSION_B64       - naver_session.json base64 인코딩
  GOOGLE_CREDENTIALS_B64  - google_credentials.json base64 인코딩
  SLACK_WEBHOOK_URL       - Slack Incoming Webhook URL
  GOOGLE_SHEETS_URL       - 대상 스프레드시트 URL
"""
import os
import sys
import json
import base64
import asyncio
from pathlib import Path

# ── 환경 설정 ──────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

# 대상 URL
TARGET_URLS = [
    "https://cafe.naver.com/f-e/cafes/23611966/popular",
    "https://cafe.naver.com/f-e/cafes/23611966/menus/460",
]

MAX_POSTS_PER_URL = 30


def _decode_env_file(env_var: str, output_path: str) -> bool:
    """환경변수에서 base64 디코딩하여 파일 생성 (CI 환경용)"""
    value = os.environ.get(env_var, "")
    if not value:
        return False
    try:
        decoded = base64.b64decode(value)
        Path(output_path).write_bytes(decoded)
        print(f"[설정] {env_var} → {output_path} 생성 완료")
        return True
    except Exception as e:
        print(f"[설정] {env_var} 디코딩 실패: {e}")
        return False


def setup_credentials():
    """CI 환경변수에서 인증 파일 생성 (로컬에 파일이 이미 있으면 스킵)"""
    # Google Credentials
    cred_path = BASE_DIR / "google_credentials.json"
    if not cred_path.exists():
        if not _decode_env_file("GOOGLE_CREDENTIALS_B64", str(cred_path)):
            print("[오류] google_credentials.json이 없고 GOOGLE_CREDENTIALS_B64도 미설정")
            sys.exit(1)

    # Naver Session
    session_path = BASE_DIR / "naver_session.json"
    if not session_path.exists():
        if not _decode_env_file("NAVER_SESSION_B64", str(session_path)):
            print("[오류] naver_session.json이 없고 NAVER_SESSION_B64도 미설정")
            sys.exit(1)

    # Slack Webhook (환경변수 → .env 호환)
    if os.environ.get("SLACK_WEBHOOK_URL"):
        os.environ.setdefault("SLACK_WEBHOOK_URL", os.environ["SLACK_WEBHOOK_URL"])

    # Google Sheets URL
    sheets_url = os.environ.get("GOOGLE_SHEETS_URL", "")
    if not sheets_url:
        # sheets_config.json에서 읽기
        config_path = BASE_DIR / "sheets_config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            sheets_url = config.get("sheet_url", "")
    return sheets_url


async def run_monitor():
    """메인 모니터링 루프"""
    print("=" * 60)
    print("  네이버 카페 자동 모니터링 시작")
    print("=" * 60)

    # 1. 인증 설정
    sheets_url = setup_credentials()
    if not sheets_url:
        print("[오류] Google Sheets URL이 설정되지 않았습니다.")
        sys.exit(1)

    # 2. Google Sheets 연결 → 기존 URL 로드
    from google_sheets_sync import GoogleSheetsSync
    sync = GoogleSheetsSync(
        credentials_file=str(BASE_DIR / "google_credentials.json"),
        sheet_url=sheets_url or "https://docs.google.com/spreadsheets/d/1R-UYFToNFWsP1sFEOHHYiYzgYoKi6wSKOPYo5Qe-NVI/edit?gid=0#gid=0",
        sheet_name="아프니까 사장이다",
    )
    if not sync.setup_connection():
        print("[오류] Google Sheets 연결 실패")
        sys.exit(1)

    existing_urls = sync.get_existing_urls()
    print(f"[시트] 기존 URL {len(existing_urls):,}건 로드")

    # 3. 브라우저 시작 (headless, 세션 쿠키 복원)
    import scraper
    await scraper.open_browser(
        cafe_url=TARGET_URLS[0],
        force_headless=True,
    )

    # 세션 유효성 확인
    if scraper._state.get("status") == "error":
        error_msg = scraper._state.get("message", "세션 오류")
        print(f"[오류] {error_msg}")

        # Slack 세션 만료 알림
        from slack_notifier import send_slack_message
        send_slack_message(
            "⚠️ [아프니까 사장이다] 네이버 세션 만료.\n"
            "갱신 후 GitLab 변수 업데이트 필요:\n"
            "1. 로컬: `python update_naver_session.py`\n"
            "2. GitLab > Settings > CI/CD > Variables > NAVER_SESSION_B64 업데이트"
        )
        await scraper.close_browser()
        sys.exit(1)

    page = scraper._state["page"]
    logged_in = await scraper._check_naver_login(page)
    if not logged_in:
        print("[오류] 네이버 로그인 실패 — 세션 만료")
        from slack_notifier import send_slack_message
        send_slack_message(
            "⚠️ [아프니까 사장이다] 네이버 세션 만료.\n"
            "갱신 후 GitLab 변수 업데이트 필요."
        )
        await scraper.close_browser()
        sys.exit(1)

    print("[로그인] 네이버 세션 유효 확인")

    # 4. 대상 URL 순회 → 링크 수집 → 본문 수집
    all_new_posts = []

    for url in TARGET_URLS:
        print(f"\n[수집] {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(3)

            # 링크 수집
            links = await scraper._collect_naver_cafe_links(
                page, max_count=MAX_POSTS_PER_URL
            )
            print(f"  링크 {len(links)}건 수집")

            # 기존 URL 필터링
            new_links = [
                lnk for lnk in links
                if lnk.get("url", "") and lnk["url"] not in existing_urls
            ]
            print(f"  신규 {len(new_links)}건 (기존 {len(links) - len(new_links)}건 스킵)")

            # 본문 수집
            for i, link_info in enumerate(new_links):
                if i >= 20:  # 안전 제한
                    break
                article = await scraper._scrape_article(page, link_info)
                if article and not article.get("_fail_reason"):
                    article["post_url"] = link_info["url"]
                    article["site"] = "네이버 카페"
                    article["cafe_name"] = "아프니까사장이다"
                    article["monitoring_name"] = "아프니까사장이다"
                    all_new_posts.append(article)
                    existing_urls.add(link_info["url"])  # 중복 방지
                await asyncio.sleep(1)

        except Exception as e:
            print(f"  [오류] {url}: {e}")

    print(f"\n[결과] 총 신규 게시글: {len(all_new_posts)}건")

    # 5. Google Sheets 저장
    if all_new_posts:
        # 분류기 적용
        try:
            from intelligent_classifier import classify_post_restaurant_business
            classified = []
            for post in all_new_posts:
                enhanced = classify_post_restaurant_business(
                    post, "아프니까사장이다", ""
                )
                classified.append(enhanced)
            all_new_posts = classified
        except ImportError:
            pass

        if sync.add_new_posts(all_new_posts):
            print(f"[시트] {len(all_new_posts)}건 Google Sheets 저장 완료")
        else:
            print("[시트] 저장 실패")

    # 6. Slack 알림 (키워드 무관, 수집된 전체 신규 글 알림)
    if all_new_posts:
        from slack_notifier import send_slack_message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 아프니까 사장이다 — 신규 게시글 {len(all_new_posts)}건",
                    "emoji": True,
                },
            }
        ]
        for i, post in enumerate(all_new_posts[:20]):
            title = (post.get("title") or "제목 없음")[:50]
            author = post.get("author") or "-"
            date = post.get("post_date") or "-"
            url = post.get("post_url") or ""
            line = f"*{i+1}. {title}*\n작성자: {author} | {date}"
            if url:
                line += f"\n<{url}|원문 보기>"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": line}})
        if len(all_new_posts) > 20:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"_...외 {len(all_new_posts) - 20}건 더_"},
            })
        blocks.append({"type": "divider"})
        send_slack_message(f"[아프니까 사장이다] 신규 게시글 {len(all_new_posts)}건", blocks)
        print(f"[Slack] {len(all_new_posts)}건 알림 전송")
    else:
        print("[완료] 신규 게시글 없음")

    # 7. 정리
    await scraper.close_browser()
    print("\n[완료] 모니터링 종료")


if __name__ == "__main__":
    asyncio.run(run_monitor())
