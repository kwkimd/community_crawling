#!/usr/bin/env python3
"""
Slack 알림 모듈 — 유튜브/커뮤니티 키워드 매칭 시 알림 전송
"""
import os
import json
import httpx
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
NOTIFIED_FILE = Path(__file__).parent / "notified_posts.json"


def _load_notified() -> set:
    """이미 알림 보낸 게시글 ID/URL 목록 로드"""
    try:
        if NOTIFIED_FILE.exists():
            data = json.loads(NOTIFIED_FILE.read_text(encoding="utf-8"))
            return set(data)
    except Exception:
        pass
    return set()


def _save_notified(notified: set):
    """알림 보낸 목록 저장 (최근 5000건만 유지)"""
    data = list(notified)[-5000:]
    NOTIFIED_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def send_slack_message(text: str, blocks: list = None) -> bool:
    """Slack Webhook으로 메시지 전송"""
    if not SLACK_WEBHOOK_URL:
        print("[Slack] Webhook URL이 설정되지 않았습니다.")
        return False

    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(SLACK_WEBHOOK_URL, json=payload)
            if resp.status_code == 200:
                return True
            else:
                print(f"[Slack] 전송 실패: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        print(f"[Slack] 전송 오류: {e}")
        return False


def notify_new_posts(posts: list, source: str = "유튜브") -> int:
    """새 게시글 목록에서 키워드 매칭된 것만 Slack으로 일괄 알림

    Args:
        posts: 게시글 목록 (title, content, post_url, author, post_date 포함)
        source: 출처 레이블 (유튜브, 커뮤니티, 자동 수집 등)

    Returns:
        알림에 포함된 게시글 수
    """
    if not SLACK_WEBHOOK_URL:
        return 0

    try:
        from services.keyword_service import load_keyword_config
        kw_config = load_keyword_config()
        or_keywords = kw_config.get("or_keywords", "").strip()
    except Exception:
        or_keywords = ""

    notified = _load_notified()
    matched_posts = []

    for post in posts:
        post_url = post.get("post_url", "")
        post_id = post_url or post.get("title", "")

        if post_id in notified:
            continue

        # 키워드 필터 (설정 없으면 전체 허용)
        if or_keywords:
            keywords = [k.strip().lower() for k in or_keywords.split(",") if k.strip()]
            title_content = (post.get("title") or "").lower() + " " + (post.get("content") or "")[:500].lower()
            matched = [kw for kw in keywords if kw in title_content]
            if not matched:
                continue
        else:
            matched = []

        matched_posts.append({**post, "_matched": matched, "_post_id": post_id})

    if not matched_posts:
        return 0

    today = datetime.now().strftime("%Y. %m. %d.")
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🌿 {source} — 신규 게시글 {len(matched_posts)}건 ({today})",
                "emoji": True,
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📌 수집 내용*"},
        },
    ]

    for post in matched_posts[:20]:
        title    = (post.get("title") or "제목 없음")[:60]
        author   = post.get("author") or "-"
        date     = (post.get("post_date") or "-").replace("-", ".")
        views    = post.get("view_count") or 0
        comments = post.get("comment_count") or 0
        url      = post.get("post_url") or ""
        matched  = post.get("_matched") or []

        # 카테고리 태그
        category = (
            post.get("detail_category")
            or post.get("sub_category")
            or post.get("main_category")
            or post.get("risk_classification")
            or (f"키워드: {matched[0]}" if matched else "기타")
        )

        # 요약 불렛 (summary → criticism_point → opinion_summary → 본문 앞부분)
        bullets = []
        for field in ["summary", "criticism_point", "opinion_summary"]:
            text = (post.get(field) or "").strip()
            if text and len(bullets) < 2:
                bullets.append(text[:80])
        if not bullets:
            content = (post.get("content") or "").strip()
            if content:
                bullets.append(content[:80])

        title_line = (
            f"*[{category}]* <{url}|{title}>"
            if url else
            f"*[{category}] {title}*"
        )
        bullet_lines = "\n".join(f"• {b}" for b in bullets)
        meta_line = f"👤 {author}  |  📅 {date}  |  👁 {views}  |  💬 {comments}"

        body = f"{title_line}\n{bullet_lines}\n{meta_line}" if bullet_lines else f"{title_line}\n{meta_line}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})

    if len(matched_posts) > 20:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"_...외 {len(matched_posts) - 20}건 더_"},
        })

    blocks.append({"type": "divider"})

    fallback_text = f"[{source}] 신규 게시글 {len(matched_posts)}건"
    if send_slack_message(fallback_text, blocks):
        for post in matched_posts:
            notified.add(post["_post_id"])
        _save_notified(notified)
        print(f"[Slack] {source} 알림 전송: {len(matched_posts)}건")
        return len(matched_posts)

    return 0
