import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "cafe_posts.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            comments TEXT DEFAULT '[]',
            category TEXT DEFAULT '일반',
            post_date TEXT,
            author TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            view_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            site TEXT DEFAULT '네이버 카페',
            cafe_name TEXT DEFAULT '',
            post_url TEXT DEFAULT '',
            -- CSV 구조 추가 필드들
            monitoring_name TEXT DEFAULT '',
            risk_level INTEGER DEFAULT 0,
            sentiment TEXT DEFAULT '중립',
            subject_type TEXT DEFAULT '소비자',
            service_type TEXT DEFAULT '배달의민족',
            risk_classification TEXT DEFAULT 'NO RISK',
            main_category TEXT DEFAULT '플랫폼 이용',
            sub_category TEXT DEFAULT '주문',
            detail_category TEXT DEFAULT '일반',
            keywords TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            week_info TEXT DEFAULT '',
            content_key TEXT DEFAULT '',
            analysis_datetime TEXT DEFAULT '',
            collector TEXT DEFAULT 'SCA'
        );

        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            analysis_type TEXT NOT NULL,
            post_ids TEXT,
            result TEXT NOT NULL
        );

        -- 중복 확인 쿼리 (title + post_date) 최적화
        CREATE INDEX IF NOT EXISTS idx_posts_title_date
            ON posts (title, post_date);

        -- 날짜 범위 조회 및 정렬 최적화
        CREATE INDEX IF NOT EXISTS idx_posts_post_date
            ON posts (post_date DESC);

        -- 카테고리 필터링 최적화
        CREATE INDEX IF NOT EXISTS idx_posts_category
            ON posts (category);

    """)
    conn.commit()

    # ── 기존 DB 마이그레이션: 컬럼이 없으면 추가
    existing = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    migrations = [
        ("site",      "TEXT DEFAULT '네이버 카페'"),
        ("cafe_name", "TEXT DEFAULT ''"),
        ("post_url",  "TEXT DEFAULT ''"),
        # CSV 구조 추가 필드들
        ("monitoring_name", "TEXT DEFAULT ''"),
        ("risk_level", "INTEGER DEFAULT 0"),
        ("sentiment", "TEXT DEFAULT '중립'"),
        ("subject_type", "TEXT DEFAULT '소비자'"),
        ("service_type", "TEXT DEFAULT '배달의민족'"),
        ("channel_type", "TEXT DEFAULT '카페'"),
        ("risk_classification", "TEXT DEFAULT 'NO RISK'"),
        ("main_category", "TEXT DEFAULT '플랫폼 이용'"),
        ("sub_category", "TEXT DEFAULT '주문'"),
        ("detail_category", "TEXT DEFAULT '일반'"),
        ("site_group", "TEXT DEFAULT '네이버'"),
        ("keywords", "TEXT DEFAULT ''"),
        ("summary", "TEXT DEFAULT ''"),
        ("week_info", "TEXT DEFAULT ''"),
        ("content_key", "TEXT DEFAULT ''"),
        ("analysis_datetime", "TEXT DEFAULT ''"),
        ("collector", "TEXT DEFAULT 'SCA'"),
    ]
    for col, col_def in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {col_def}")
    conn.commit()

    # 마이그레이션 완료 후 cafe_name 인덱스 생성 (컬럼이 반드시 존재하는 시점)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_posts_cafe_name ON posts (cafe_name)"
    )
    conn.commit()
    conn.close()


# ── Posts ──────────────────────────────────────────────────────────────────────

def post_exists(title: str, post_date: str) -> bool:
    """제목 + 작성일 기준 중복 게시글 여부 확인"""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM posts WHERE title=? AND post_date=?", (title, post_date)
    ).fetchone()
    conn.close()
    return row is not None


def create_post(title: str, content: str, category: str, post_date: str,
                author: str, view_count: int, comment_count: int,
                comments: list = None,
                site: str = "네이버 카페",
                cafe_name: str = "",
                post_url: str = "",
                # CSV 구조 추가 필드들 (선택적)
                monitoring_name: str = "",
                risk_level: int = 0,
                sentiment: str = "중립",
                subject_type: str = "소비자",
                service_type: str = "배달의민족",
                channel_type: str = "카페",
                risk_classification: str = "NO RISK",
                main_category: str = "플랫폼 이용",
                sub_category: str = "주문",
                detail_category: str = "일반",
                site_group: str = "네이버",
                keywords: str = "",
                summary: str = "",
                week_info: str = "",
                content_key: str = "",
                analysis_datetime: str = "",
                collector: str = "SCA") -> int:
    conn = get_connection()
    comments_json = json.dumps(comments or [], ensure_ascii=False)
    cur = conn.execute(
        """INSERT INTO posts
               (title, content, comments, category, post_date, author,
                view_count, comment_count, site, cafe_name, post_url,
                monitoring_name, risk_level, sentiment, subject_type, service_type, channel_type,
                risk_classification, main_category, sub_category, detail_category, site_group,
                keywords, summary, week_info, content_key, analysis_datetime, collector)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, content, comments_json, category, post_date, author,
         view_count, comment_count, site, cafe_name, post_url,
         monitoring_name, risk_level, sentiment, subject_type, service_type, channel_type,
         risk_classification, main_category, sub_category, detail_category, site_group,
         keywords, summary, week_info, content_key, analysis_datetime, collector),
    )
    conn.commit()
    post_id = cur.lastrowid
    conn.close()
    return post_id


def get_all_posts(category: str = None, keyword: str = None,
                  date_from: str = None, date_to: str = None,
                  cafe_name: str = None) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM posts WHERE 1=1"
    params = []

    if category and category != "전체":
        query += " AND category = ?"
        params.append(category)
    if cafe_name:
        query += " AND cafe_name = ?"
        params.append(cafe_name)
    if keyword:
        query += " AND (title LIKE ? OR content LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if date_from:
        query += " AND post_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND post_date <= ?"
        params.append(date_to)

    query += " ORDER BY post_date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_post(post_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_post(post_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    categories = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM posts GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    monthly = conn.execute(
        """SELECT substr(post_date, 1, 7) as month, COUNT(*) as cnt
           FROM posts WHERE post_date IS NOT NULL AND post_date != ''
           GROUP BY month ORDER BY month DESC LIMIT 12"""
    ).fetchall()
    cafe_names = conn.execute(
        "SELECT DISTINCT cafe_name FROM posts WHERE cafe_name IS NOT NULL AND cafe_name != '' ORDER BY cafe_name"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "categories": [dict(r) for r in categories],
        "monthly": [dict(r) for r in monthly],
        "cafe_names": [r[0] for r in cafe_names],
    }


def get_categories() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT category FROM posts WHERE category IS NOT NULL ORDER BY category"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_cafe_names() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT cafe_name FROM posts WHERE cafe_name IS NOT NULL AND cafe_name != '' ORDER BY cafe_name"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── Analyses ───────────────────────────────────────────────────────────────────

def save_analysis(analysis_type: str, post_ids: list[int], result: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO analyses (analysis_type, post_ids, result) VALUES (?, ?, ?)",
        (analysis_type, json.dumps(post_ids), result),
    )
    conn.commit()
    analysis_id = cur.lastrowid
    conn.close()
    return analysis_id


def get_analysis_by_id(analysis_id: int) -> dict | None:
    """특정 분석 결과 조회"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_analyses(limit: int = 10) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM analyses ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
