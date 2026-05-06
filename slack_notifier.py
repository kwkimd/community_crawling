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
    """새 게시글 목록에서 키워드 매칭된 것만 채널별로 묶어서 Slack 알림 1건 전송
    
    Args:
        posts: 게시글 목록 (title, content, post_url, author, post_date 포함)
        source: 출처 (유튜브, 커뮤니티 등)
    
    Returns:
        알림에 포함된 게시글 수
    """
    if not SLACK_WEBHOOK_URL:
        return 0

    from services.keyword_service import load_keyword_config
    kw_config = load_keyword_config()
    or_keywords = kw_config.get("or_keywords", "").strip()
    if not or_keywords:
        return 0

    keywords = [k.strip().lower() for k in or_keywords.split(",") if k.strip()]
    notified = _load_notified()
    matched_posts = []

    for post in posts:
        post_url = post.get("post_url", "")
        post_id = post_url or post.get("title", "")

        if post_id in notified:
            continue

        title = (post.get("title") or "").lower()
        content = (post.get("content") or "")[:500].lower()
        text = title + " " + content

        matched = [kw for kw in keywords if kw in text]
        if not matched:
            continue

        matched_posts.append({
            "title": post.get("title", "제목 없음"),
            "matched": matched,
            "author": post.get("author", ""),
            "post_date": post.get("post_date", ""),
            "post_url": post_url,
            "post_id": post_id,
        })

    if not matched_posts:
        return 0

    # 채널별 묶음 메시지 구성
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔔 {source} 수집 완료 — 키워드 매칭 {len(matched_posts)}건", "emoji": True}
        },
    ]

    for i, mp in enumerate(matched_posts[:20]):  # 최대 20건
        title_text = mp["title"][:50]
        kw_text = ", ".join(mp["matched"][:3])
        date_text = mp["post_date"] or "-"
        author_text = mp["author"] or "-"
        
        line = f"*{i+1}. {title_text}*\n키워드: `{kw_text}` | 작성자: {author_text} | {date_text}"
        if mp["post_url"]:
            line += f"\n<{mp['post_url']}|원문 보기>"
        
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": line}})

    if len(matched_posts) > 20:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"_...외 {len(matched_posts) - 20}건 더_"}})

    blocks.append({"type": "divider"})

    fallback_text = f"[{source}] 키워드 매칭 {len(matched_posts)}건 수집 완료"

    if send_slack_message(fallback_text, blocks):
        for mp in matched_posts:
            notified.add(mp["post_id"])
        _save_notified(notified)
        print(f"[Slack] {source} 묶음 알림 전송: {len(matched_posts)}건")
        return len(matched_posts)

    return 0
