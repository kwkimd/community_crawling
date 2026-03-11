import asyncio
import re
import random
import os
from playwright.async_api import async_playwright, Page
import database as db

# ── 설정 ────────────────────────────────────────────────────────────────────────
CAFE_URL  = "https://cafe.naver.com/jihosoccer123"
BOARD_URL = "https://cafe.naver.com/f-e/cafes/23611966/menus/0?q=%EB%B0%B0%EB%8B%AC&ta=ARTICLE_COMMENT&iq=%EC%9E%A5%EC%82%AC%2C+%EB%B0%B0%EB%8B%AC%EC%9D%98%EB%AF%BC%EC%A1%B1%2C+%EC%BF%A0%ED%8C%A1%EC%9D%B4%EC%B8%A0&page=1&size=50"
CAFE_ID   = "23611966"

# ── 전역 상태 ───────────────────────────────────────────────────────────────────
_state = {
    "pw": None, "browser": None, "context": None, "page": None,
    "status": "idle",   # idle | open | scraping | done | error
    "message": "", "progress": 0, "total": 0, "results": [], "task": None,
}


def get_status() -> dict:
    return {
        "status": _state["status"],
        "message": _state["message"],
        "progress": _state["progress"],
        "total": _state["total"],
        "result_count": len(_state["results"]),
    }

def get_results() -> list:
    return list(_state["results"])


# ── 브라우저 열기 ───────────────────────────────────────────────────────────────
async def open_browser(cafe_url: str = CAFE_URL):
    if _state["browser"] and not _state["browser"].is_connected():
        await _cleanup()
    if _state["browser"]:
        await _state["page"].bring_to_front()
        _state["message"] = "브라우저가 이미 열려 있습니다."
        return

    pw = await async_playwright().start()

    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    executable_path = next((p for p in chrome_paths if os.path.exists(p)), None)

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run", "--no-default-browser-check",
        "--disable-infobars", "--start-maximized", "--foreground",
    ]
    browser = await pw.chromium.launch(
        headless=False,
        executable_path=executable_path,
        args=launch_args,
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        no_viewport=True,
        locale="ko-KR",
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )

    page = await context.new_page()
    _state.update(pw=pw, browser=browser, context=context, page=page,
                  status="open",
                  message="브라우저가 열렸습니다. 네이버에 로그인 후 수집할 게시판으로 이동하세요.")
    await page.goto(cafe_url, wait_until="domcontentloaded")


# ── 수집 시작 ───────────────────────────────────────────────────────────────────
async def start_scraping(max_posts: int = 0, category: str = "",
                         date_from: str = "", date_to: str = "",
                         board_url: str = "", cafe_name: str = "",
                         monitoring_name: str = "", search_keyword: str = ""):
    if _state["status"] == "scraping":
        return
    if _state["task"] and not _state["task"].done():
        _state["task"].cancel()
    _state["task"] = asyncio.create_task(
        _do_scrape(max_posts, category, date_from, date_to, board_url, cafe_name)
    )


async def _do_scrape(max_posts: int, category: str, date_from: str, date_to: str,
                     board_url: str = "", cafe_name: str = "", 
                     monitoring_name: str = "", search_keyword: str = ""):
    page: Page = _state["page"]
    if not page:
        _state.update(status="error", message="브라우저가 열려있지 않습니다.")
        return

    # UI에서 전달된 board_url 우선 사용, 없으면 기본값
    base_url = board_url.strip() if board_url.strip() else BOARD_URL
    # 카페명 미입력 시 URL에서 추출 시도
    resolved_cafe_name = cafe_name.strip()
    if not resolved_cafe_name:
        import re as _re
        m = _re.search(r"cafe\.naver\.com/(?:f-e/cafes/\d+|([^/?#]+))", base_url)
        resolved_cafe_name = m.group(1) if (m and m.group(1)) else "네이버 카페"

    date_label = ""
    if date_from and date_to:
        date_label = f" ({date_from} ~ {date_to})"
    elif date_from:
        date_label = f" ({date_from} 이후)"
    elif date_to:
        date_label = f" ({date_to} 이전)"

    _state.update(status="scraping", progress=0, total=0, results=[],
                  message=f"게시판으로 이동 중...")
    try:
        # 수집 시작 전 게시판 URL로 자동 이동 (날짜 파라미터 동적 추가)
        search_url = base_url
        if date_from:
            search_url += "&from=" + date_from.replace("-", "")  # YYYY-MM-DD → YYYYMMDD
        if date_to:
            search_url += "&to=" + date_to.replace("-", "")
        print(f"[수집URL] {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        _state["message"] = f"게시글 목록 수집 중{date_label}..."
        # max_posts=0 이면 제한 없이 전체 수집 (내부적으로 매우 큰 수 사용)
        unlimited = (max_posts == 0)
        fetch_limit = 9999 if unlimited else max_posts * 3
        # 목록에서 링크 + 날짜 함께 수집 (페이지 자동 넘기기 포함)
        article_infos = await _collect_article_links(page, fetch_limit, date_from, date_to)

        if not article_infos:
            _state.update(status="error",
                          message="게시글 목록을 찾지 못했습니다. 게시판 목록 화면인지 확인 후 다시 시도해주세요.")
            return

        # 날짜 필터링 (목록에서 날짜를 알 수 있는 경우 미리 제외)
        if date_from or date_to:
            filtered, skipped = [], 0
            for info in article_infos:
                list_date = info.get("list_date", "")
                if list_date:
                    if date_from and list_date < date_from:
                        skipped += 1
                        continue
                    if date_to and list_date > date_to:
                        skipped += 1
                        continue
                filtered.append(info)
            article_infos = filtered if unlimited else filtered[:max_posts]
            _state["message"] = (f"날짜 필터 적용: {len(article_infos)}개 대상 "
                                 f"(범위 외 {skipped}개 제외){date_label}")
        else:
            article_infos = article_infos if unlimited else article_infos[:max_posts]

        _state["total"] = len(article_infos)

        saved = []
        skipped_date = 0
        for i, info in enumerate(article_infos):
            _state["progress"] = i + 1
            _state["message"] = f"수집 중 ({i+1}/{len(article_infos)}): {info.get('title','')[:28]}..."
            post = await _scrape_article(page, info)
            if post:
                # list_date(목록 페이지)가 있으면 우선 사용 — 본문 파싱보다 신뢰도 높음
                list_date = info.get("list_date", "")
                article_date = post.get("post_date", "")
                if list_date:
                    post["post_date"] = list_date
                post_date = post.get("post_date", "")
                print(f"[날짜확인] {post.get('title','')[:20]} → {post_date!r}  "
                      f"(목록:{list_date!r} / 본문:{article_date!r})")
                if post_date:
                    if date_from and post_date < date_from:
                        skipped_date += 1
                        continue
                    if date_to and post_date > date_to:
                        skipped_date += 1
                        continue
                # 카페 구분값 추가
                post["site"] = "네이버 카페"
                post["cafe_name"] = resolved_cafe_name
                post["post_url"] = info.get("url", "")
                saved.append(post)
            await asyncio.sleep(random.uniform(1.2, 2.5))

        # ── 자동 DB 저장 (CSV 구조 기반 확장)
        auto_saved, auto_skipped = 0, 0
        for post in saved:
            if db.post_exists(post["title"], post.get("post_date", "")):
                auto_skipped += 1
                continue
            
            # CSV 구조에 맞는 추가 분석 (지능형 분류 시스템 사용)
            try:
                from intelligent_classifier import classify_post_intelligent
                enhanced_post = classify_post_intelligent(post, monitoring_name or "일반모니터링", search_keyword or "")
            except ImportError:
                # 폴백: 기존 분류 시스템 사용
                enhanced_post = _enhance_post_with_csv_structure(post, monitoring_name or "일반모니터링", search_keyword or "")
            
            db.create_post(
                title=enhanced_post["title"],
                content=enhanced_post["content"],
                category=enhanced_post.get("category", "일반"),
                post_date=enhanced_post.get("post_date", ""),
                author=enhanced_post.get("author", ""),
                view_count=enhanced_post.get("view_count", 0),
                comment_count=enhanced_post.get("comment_count", 0),
                comments=enhanced_post.get("comments", []),
                site=enhanced_post.get("site", "네이버 카페"),
                cafe_name=enhanced_post.get("cafe_name", ""),
                post_url=enhanced_post.get("post_url", ""),
                # CSV 구조 추가 필드들
                monitoring_name=enhanced_post.get("monitoring_name", ""),
                risk_level=enhanced_post.get("risk_level", 0),
                sentiment=enhanced_post.get("sentiment", "중립"),
                subject_type=enhanced_post.get("subject_type", "소비자"),
                service_type=enhanced_post.get("service_type", "배달의민족"),
                channel_type=enhanced_post.get("channel_type", "카페"),
                risk_classification=enhanced_post.get("risk_classification", "NO RISK"),
                main_category=enhanced_post.get("main_category", "플랫폼 이용"),
                sub_category=enhanced_post.get("sub_category", "주문"),
                detail_category=enhanced_post.get("detail_category", "일반"),
                site_group=enhanced_post.get("site_group", "네이버"),
                keywords=enhanced_post.get("keywords", ""),
                summary=enhanced_post.get("summary", ""),
                week_info=enhanced_post.get("week_info", ""),
                content_key=enhanced_post.get("content_key", ""),
                analysis_datetime=enhanced_post.get("analysis_datetime", ""),
                collector=enhanced_post.get("collector", "SCA"),
            )
            auto_saved += 1

        # ── 구글 시트 자동 업로드 (새 데이터가 있을 때만)
        sheets_msg = ""
        if auto_saved > 0:
            try:
                from google_sheets_sync import GoogleSheetsSync
                sheet_url = "https://docs.google.com/spreadsheets/d/1qP37BDR68sqoegMI31FMZt74923JO8NklUY2-XVOk5A/edit?gid=0#gid=0"
                sync = GoogleSheetsSync(sheet_url=sheet_url)
                if sync.setup_connection():
                    if sync.sync_all_data():
                        sheets_msg = " + 구글시트 업데이트 완료"
                    else:
                        sheets_msg = " (구글시트 업데이트 실패)"
                else:
                    sheets_msg = " (구글시트 연결 실패)"
            except Exception as e:
                sheets_msg = f" (구글시트 오류: {str(e)[:30]})"

        extra = f" (날짜 범위 외 {skipped_date}개 제외)" if skipped_date else ""
        dup_msg = f", 중복 {auto_skipped}개 제외" if auto_skipped else ""
        _state.update(results=saved, status="done",
                      message=f"저장 완료! {auto_saved}개 게시글 DB 저장{extra}{dup_msg}{sheets_msg}")

    except asyncio.CancelledError:
        _state.update(status="idle", message="수집이 취소되었습니다.")
    except Exception as e:
        _state.update(status="error", message=f"오류: {e}")


# ── 게시글 링크 목록 수집 (멀티 페이지) ─────────────────────────────────────────
async def _collect_article_links(page: Page, max_count: int,
                                  date_from: str = "", date_to: str = "") -> list[dict]:
    """여러 페이지를 순회하며 게시글 링크 + 날짜 수집"""
    links: list[dict] = []
    seen: set[str] = set()

    js = """() => {
        const res = [], seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
            if (!href || !text || text.length < 2 || seen.has(href)) return;
            const ok = href.includes('/articles/') ||
                       href.includes('articleid') ||
                       href.includes('ArticleRead') ||
                       /cafe\\.naver\\.com\\/[^\\/\\?#]+\\/\\d+/.test(href);
            if (!ok) return;
            if (href.includes('/menus/') || href.includes('javascript:') ||
                href.includes('#')) return;
            // 주의: 'search' 필터 제거 - 검색결과 URL에 inCafeSearch=true 포함됨
            seen.add(href);

            // 같은 행(tr/li/div)에서 날짜 추출
            const row = a.closest('tr') || a.closest('li') || a.closest('[class*="item"]') || a.closest('[class*="article"]');
            let dateText = '';
            if (row) {
                // td_normal이 번호/날짜/조회수로 여러 개 → 날짜 패턴(YYYY.MM.DD)인 셀만 선택
                const tds = row.querySelectorAll('.td_normal');
                for (const td of tds) {
                    if (td.innerText.trim().match(/\\d{4}\\.\\d{1,2}\\.\\d{1,2}/)) {
                        dateText = td.innerText.trim();
                        break;
                    }
                }
                // td_normal 없으면 일반 날짜 셀렉터 시도
                if (!dateText) {
                    const dateEl = row.querySelector('.date, .td_date, [class*="date"], time, em.date, span.date');
                    if (dateEl) dateText = dateEl.innerText.trim();
                }
            }
            res.push({url: href, title: text.substring(0,120), list_date: dateText});
        });
        return res;
    }"""

    for page_num in range(1, 100):  # 최대 100페이지
        _state["message"] = f"게시글 목록 {page_num}페이지 수집 중..."
        new_count = 0
        oldest_on_page = ""

        for frame in [page] + list(page.frames):
            try:
                batch = await frame.evaluate(js)
                for item in (batch or []):
                    u = item.get("url", "")
                    if not u:
                        continue
                    # 게시글 ID 기준으로 중복 제거 (URL 형식이 달라도 같은 글)
                    m = re.search(r"/articles/(\d+)|/(\d{6,})(?:\?|$)", u)
                    article_key = m.group(1) or m.group(2) if m else u
                    if article_key in seen:
                        continue
                    seen.add(article_key)
                    item["list_date"] = _parse_date(item.get("list_date", ""))
                    d = item["list_date"]
                    if d and (not oldest_on_page or d < oldest_on_page):
                        oldest_on_page = d
                    links.append(item)
                    new_count += 1
            except Exception:
                pass

        if new_count == 0:
            break  # 더 이상 새 링크 없음

        if len(links) >= max_count:
            break

        # 이 페이지의 가장 오래된 글이 date_from보다 이전이면 더 볼 필요 없음
        if date_from and oldest_on_page and oldest_on_page < date_from:
            break

        # 다음 페이지로 이동
        went = await _goto_next_board_page(page, page_num)
        if not went:
            break
        await asyncio.sleep(2)

    return links[:max_count]


async def _goto_next_board_page(page: Page, current_num: int) -> bool:
    """게시판 다음 페이지로 이동. 성공 True, 실패 False"""
    # 전략 1: 보드 iframe URL에 page 파라미터 추가/증가
    for frame in list(page.frames):
        fu = frame.url
        if ("f-e/cafes" in fu or "ca-fe/cafes" in fu) and "menus" in fu:
            if "page=" in fu:
                next_url = re.sub(r"page=\d+", f"page={current_num + 1}", fu)
            else:
                sep = "&" if "?" in fu else "?"
                next_url = f"{fu}{sep}page={current_num + 1}"
            try:
                await frame.goto(next_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1.5)
                return True
            except Exception:
                pass

    # 전략 2: 메인 페이지 URL에 page 파라미터 추가/증가
    current_url = page.url
    if "menus" in current_url or "cafe.naver.com" in current_url:
        if "page=" in current_url:
            next_url = re.sub(r"page=\d+", f"page={current_num + 1}", current_url)
        else:
            sep = "&" if "?" in current_url else "?"
            next_url = f"{current_url}{sep}page={current_num + 1}"
        try:
            await page.goto(next_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)
            return True
        except Exception:
            pass

    # 전략 3: 다음 페이지 버튼 클릭
    next_sels = [
        "a.pgR", ".btn_next", "button.btn_next",
        "[class*='pagination'] [class*='next']",
        "a[aria-label*='다음']", ".pg_next",
    ]
    for frame in [page] + list(page.frames):
        for sel in next_sels:
            try:
                el = await frame.query_selector(sel)
                if el:
                    await el.click()
                    await asyncio.sleep(2)
                    return True
            except Exception:
                pass

    return False


# ── 개별 게시글 수집 ─────────────────────────────────────────────────────────────
async def _scrape_article(page: Page, info: dict) -> dict | None:
    url = info["url"]
    art = None
    try:
        art = await page.context.new_page()
        await art.goto(url, wait_until="domcontentloaded", timeout=25000)
        # 네이버 카페 동적 콘텐츠 로딩 대기
        await asyncio.sleep(2)

        # ── 콘텐츠 프레임 탐색
        # 메인 프레임(페이지 자체)을 건너뛰고 자식 iframe만 탐색
        # 자식 iframe 없으면 메인 프레임(art)을 그대로 사용
        target = art
        for frame in art.frames:
            if frame == art.main_frame:
                continue  # 메인 프레임 건너뜀 (페이지 URL 자체)
            fu = frame.url
            if ("f-e/cafes" in fu or
                "ca-fe/cafes" in fu or
                "ArticleRead" in fu or
                ("cafe.naver.com" in fu and "articleid" in fu)):
                target = frame
                # 본문 셀렉터 중 하나가 나타날 때까지 최대 5초 대기
                try:
                    await target.wait_for_selector(
                        ".se-main-container, #tbody, .article_body, .CafeViewer, .view_content",
                        timeout=5000,
                    )
                except Exception:
                    await asyncio.sleep(0.5)
                break
        # 디버그: 프레임 구조 출력 (iframe 탐지 확인용)
        frame_urls = [f.url[:70] for f in art.frames]
        print(f"[프레임] target={'iframe' if target != art else 'main'} | {frame_urls}")

        # ── 제목
        title = await _text(target, [
            ".title_text", "h3[class*='title']",
            "h3.title", ".tit-box em", ".article_title",
            ".ucc-title", ".article-head h3",
        ]) or info.get("title", "제목 없음")

        # ── 본문
        content = await _extract_body(target)

        # ── 날짜 (셀렉터 + time[datetime] 속성 + body 텍스트 regex 폴백)
        date_raw = await _text(target, [
            "em.date", ".date", "span.date",
            ".article_info .date", ".article_head .date",
            ".write_info", ".post-time", ".publish_date",
            "span[class*='date']", "[class*='date']",
            "p.date", "time",
        ])
        date = _parse_date(date_raw)

        # time[datetime] 속성 시도
        if not date:
            try:
                dt_attr = await target.evaluate(
                    "()=>{ const t=document.querySelector('time[datetime]');"
                    " return t?t.getAttribute('datetime'):''; }"
                )
                date = _parse_date(dt_attr or "")
            except Exception:
                pass

        # body 텍스트 폴백 — 2019년 이전 날짜(카페 개설일 등)는 제외
        if not date:
            try:
                body_text = await target.evaluate(
                    "()=>document.body?document.body.innerText.substring(0,500):''"
                )
                candidate = _parse_date(body_text)
                # 카페 개설일(2011-09-24) 등 오래된 날짜는 신뢰하지 않음
                if candidate and candidate >= "2019-01-01":
                    date = candidate
            except Exception:
                pass

        # ── 작성자
        author = await _text(target, [
            ".nick", ".member_info .writer", "span.writer",
            ".article_head .nick", ".writer_nick", "a.m-tcol-c",
            "[class*='nick']", "[class*='author']",
        ])

        # ── 조회수
        view_str = await _text(target, [
            ".count_view", ".view_count", "em[class*='view']", "[class*='view_count']",
        ])
        view_count = _to_int(view_str)

        # ── 댓글
        comments = await _extract_comments(target, art)

        if not title and not content:
            return None

        return {
            "title": title or "제목 없음",
            "content": content or "(내용 없음)",
            "comments": comments,               # list[str]
            "post_date": date,
            "author": author or "",
            "view_count": view_count,
            "comment_count": len(comments),
            "category": "일반",
        }
    except Exception as e:
        print(f"[스크래퍼] 수집 실패 ({url}): {e}")
        try:
            frames_info = [f.url[:80] for f in art.frames]
            print(f"  → 탐색된 frames: {frames_info}")
        except Exception:
            pass
        return None
    finally:
        if art:
            try: await art.close()
            except: pass


async def _extract_body(target) -> str:
    """SmartEditor 2/3 및 구형 에디터 본문 추출"""
    selectors = [
        ".se-main-container",   # SmartEditor 3
        "#tbody",               # SmartEditor 2
        ".article_body",
        ".content_wrap",
        ".CafeViewer",
        ".article-content",
        "div#content",
        ".view_content",
    ]
    # 1) 직접 셀렉터
    text = await _text(target, selectors)
    if text and len(text) > 10:
        return text

    # 2) JavaScript fallback
    try:
        text = await target.evaluate("""() => {
            const sels = [
                '.se-main-container','#tbody','.article_body',
                '.content_wrap','.CafeViewer','.article-content',
                'div#content','.view_content'
            ];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el) { const t = el.innerText.trim(); if (t.length > 10) return t; }
            }
            return '';
        }""")
        if text and len(text) > 10:
            return text
    except Exception:
        pass
    return ""


async def _extract_comments(target, page: Page) -> list[str]:
    """댓글 목록 추출 - 스크롤 2회 + 더보기 버튼 + 구/신형 UI 모두 지원"""
    # 댓글 영역이 뷰포트에 들어오도록 스크롤 2회
    for t in [target, page]:
        try:
            await t.evaluate("()=>window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            await t.evaluate("()=>window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.0)
        except Exception:
            pass

    # "댓글 더보기" 버튼이 있으면 클릭
    more_sels = [
        ".comment_more", ".btn_more_comment", "[class*='CommentMore']",
        "button[class*='more']",
    ]
    for t in [target, page]:
        for sel in more_sels:
            try:
                btn = await t.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1.5)
                    break
            except Exception:
                pass

    selectors = [
        # 신형 ca-fe UI (2024~)
        ".CommentItem .text_comment",
        ".comment_text_box .text_comment",
        "._commentContent",
        ".u_cbox_contents",
        # 신형 변형
        "[class*='CommentItem'] [class*='text']",
        "[class*='comment'] [class*='content']",
        # 구형
        ".comment_list .comment_box .text",
        ".cmt_area .cmt_cont",
        "li.comment span.text",
        ".reply_content",
    ]

    for frame in [target, page]:
        for sel in selectors:
            try:
                els = await frame.query_selector_all(sel)
                if not els:
                    continue
                texts = [(await el.inner_text()).strip() for el in els]
                texts = [t for t in texts if t and len(t) > 1]
                if texts:
                    return texts
            except Exception:
                pass
    return []


def _enhance_post_with_csv_structure(post: dict, monitoring_name: str, search_keyword: str) -> dict:
    """게시글 데이터를 CSV 구조에 맞게 자동 분석하고 분류"""
    from datetime import datetime
    import re
    
    enhanced = post.copy()
    
    # 기본 정보
    enhanced["monitoring_name"] = monitoring_name
    enhanced["keywords"] = search_keyword
    
    # 날짜 분석
    post_date = post.get("post_date", "")
    if post_date:
        try:
            date_obj = datetime.strptime(post_date, "%Y-%m-%d")
            week_num = (date_obj.day - 1) // 7 + 1
            enhanced["week_info"] = f"{date_obj.month}월 {week_num}주차"
        except:
            enhanced["week_info"] = ""
    
    # 텍스트 분석을 위한 전체 텍스트
    content = post.get("content", "")
    title = post.get("title", "")
    author = post.get("author", "")
    site_name = post.get("cafe_name", "")
    full_text = f"{title} {content}".lower()
    
    # === 자동 감성 분석 ===
    sentiment = _analyze_sentiment(full_text)
    enhanced["sentiment"] = sentiment
    
    # === 자동 위험도 계산 ===
    risk_level = _calculate_risk_level(sentiment, full_text)
    enhanced["risk_level"] = risk_level
    
    # === 자동 주체 구분 ===
    subject_type = _classify_subject_type(author, full_text, site_name)
    enhanced["subject_type"] = subject_type
    
    # === 자동 서비스 구분 ===
    service_type = _classify_service_type(full_text, search_keyword)
    enhanced["service_type"] = service_type
    
    # === 자동 채널 구분 ===
    channel_type = _classify_channel_type(site_name, post.get("post_url", ""))
    enhanced["channel_type"] = channel_type
    
    # === 자동 리스크 분류 ===
    risk_classification = _classify_risk_category(risk_level, full_text, subject_type)
    enhanced["risk_classification"] = risk_classification
    
    # === 자동 분류 체계 ===
    main_cat, sub_cat, detail_cat = _classify_business_category(full_text, subject_type, sentiment)
    enhanced["main_category"] = main_cat
    enhanced["sub_category"] = sub_cat
    enhanced["detail_category"] = detail_cat
    
    # === 사이트 그룹 자동 분류 ===
    site_group = _classify_site_group(site_name, post.get("post_url", ""))
    enhanced["site_group"] = site_group
    enhanced["site_name"] = site_name or "알 수 없음"
    
    # === 자동 요약 생성 ===
    summary_text = _generate_auto_summary(title, content)
    enhanced["summary"] = summary_text
    
    # === 컨텐츠 키 생성 ===
    now = datetime.now()
    content_key = f"{post_date.replace('-', '') if post_date else now.strftime('%Y%m%d')}{now.strftime('%H%M%S%f')[:-3]}"
    enhanced["content_key"] = content_key
    
    # === 분석 일시 ===
    enhanced["analysis_datetime"] = now.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]
    
    # === 수집자 ===
    enhanced["collector"] = "SCA"
    
    return enhanced


def _analyze_sentiment(text: str) -> str:
    """텍스트 기반 감성 분석"""
    # 강한 부정 키워드
    strong_negative = ["미친", "최악", "ㅅㅂ", "개같", "돈뜯어", "사기", "망했", "짜증", "화나", "열받"]
    # 일반 부정 키워드  
    negative = ["불만", "문제", "싫어", "안됨", "못하", "어려", "힘들", "걱정", "우려", "반대"]
    # 긍정 키워드
    positive = ["좋아", "최고", "감사", "만족", "훌륭", "완벽", "추천", "괜찮", "편리", "도움"]
    # 강한 긍정 키워드
    strong_positive = ["대박", "완전좋", "최고", "감동", "완벽"]
    
    if any(word in text for word in strong_negative):
        return "부정"
    elif any(word in text for word in strong_positive):
        return "긍정"
    elif any(word in text for word in negative):
        return "부정"
    elif any(word in text for word in positive):
        return "긍정"
    else:
        return "중립"


def _calculate_risk_level(sentiment: str, text: str) -> int:
    """위험도 자동 계산 (0: 낮음, 1: 보통, 2: 높음)"""
    if sentiment == "긍정":
        return 0
    elif sentiment == "중립":
        return 0
    else:  # 부정
        # 높은 위험도 키워드
        high_risk_keywords = ["미친", "최악", "ㅅㅂ", "돈뜯어", "사기", "망했", "파업", "시위", "고발"]
        if any(word in text for word in high_risk_keywords):
            return 2
        else:
            return 1


def _classify_subject_type(author: str, text: str, site_name: str) -> str:
    """주체 구분 자동 분류"""
    author_lower = author.lower()
    
    # 업주 키워드
    if any(word in author_lower for word in ["사장", "업주", "점주", "ceo"]) or \
       any(word in text for word in ["우리가게", "우리매장", "저희가게", "장사", "매출", "손님들"]):
        return "업주"
    
    # 라이더 키워드
    elif any(word in author_lower for word in ["라이더", "배달", "기사"]) or \
         any(word in text for word in ["배달하", "콜량", "배차", "픽업", "드롭"]):
        return "라이더"
    
    # 기자 키워드
    elif any(word in text for word in ["기자", "뉴스", "보도", "취재"]) or \
         "기자" in author_lower:
        return "기자"
    
    # 기본값은 소비자
    else:
        return "소비자"


def _classify_service_type(text: str, search_keyword: str) -> str:
    """서비스 구분 자동 분류"""
    # 검색 키워드 우선 확인
    if "쿠팡" in search_keyword.lower():
        return "쿠팡이츠"
    elif "요기요" in search_keyword.lower():
        return "요기요"
    
    # 텍스트 내용 분석
    if any(word in text for word in ["쿠팡이츠", "쿠팡"]):
        return "쿠팡이츠"
    elif any(word in text for word in ["요기요"]):
        return "요기요"
    else:
        return "배달의민족"  # 기본값


def _classify_channel_type(site_name: str, url: str) -> str:
    """채널 구분 자동 분류"""
    site_lower = site_name.lower()
    url_lower = url.lower()
    
    if "youtube" in url_lower or "유튜브" in site_name:
        return "유튜브"
    elif "cafe.naver" in url_lower or "카페" in site_name:
        return "카페"
    elif any(word in url_lower for word in ["dcinside", "fmkorea", "clien"]) or \
         any(word in site_name for word in ["디시", "에펨", "클리앙"]):
        return "커뮤니티"
    elif any(word in url_lower for word in ["news", "naver.com/news", "daum.net/news"]) or \
         "뉴스" in site_name:
        return "뉴스"
    elif any(word in url_lower for word in ["twitter", "instagram", "facebook"]):
        return "SNS"
    else:
        return "카페"  # 기본값


def _classify_risk_category(risk_level: int, text: str, subject_type: str) -> str:
    """리스크 분류 자동 분류"""
    if risk_level == 0:
        return "NO RISK"
    
    # 컴플라이언스 리스크
    if any(word in text for word in ["파업", "노조", "시위", "고발", "신고", "법적"]):
        return "COMPLIANCE RISK"
    
    # 운영 리스크
    elif any(word in text for word in ["배달", "라이더", "배차", "픽업", "콜량"]) and subject_type == "라이더":
        return "OPERATIONAL RISK"
    
    # 운영 우수성
    elif any(word in text for word in ["수수료", "정책", "할인", "프로모션", "서비스", "시스템"]):
        return "OPERATIONAL EXCELLENCE"
    
    else:
        return "NO RISK"


def _classify_business_category(text: str, subject_type: str, sentiment: str) -> tuple:
    """비즈니스 분류 체계 자동 분류 (대분류, 중분류, 소분류)"""
    
    # 프로모션 관련
    if any(word in text for word in ["할인", "쿠폰", "이벤트", "프로모션", "혜택"]):
        return ("프로모션", "쿠폰/이벤트", "쿠폰/이벤트")
    
    # 배달/라이더 관련
    elif any(word in text for word in ["라이더", "배달원", "배차", "픽업", "콜량"]):
        if subject_type == "라이더":
            return ("배달/라이더", "라이더", "라이더 정책")
        else:
            return ("배달/라이더", "배달", "배차")
    
    # 가게/서비스 관련
    elif any(word in text for word in ["가게", "매장", "업주", "사장"]) and subject_type == "업주":
        return ("서비스", "가게", "가게 평가/경험")
    
    # 시스템/앱 관련
    elif any(word in text for word in ["앱", "시스템", "오류", "버그", "업데이트"]):
        return ("시스템", "앱 이용", "앱 평가/문의")
    
    # 중대이슈
    elif any(word in text for word in ["파업", "노조", "시위"]):
        return ("중대이슈", "노무", "시위/노조")
    
    # 광고 관련
    elif any(word in text for word in ["광고", "마케팅", "홍보"]):
        return ("플랫폼 이용", "광고", "광고/정책")
    
    # 주문 관련 (기본값)
    else:
        if any(word in text for word in ["최소주문", "주문금액"]):
            return ("플랫폼 이용", "주문", "최소 주문 금액")
        elif any(word in text for word in ["배달료", "배달팁"]):
            return ("플랫폼 이용", "주문", "배달팁")
        else:
            return ("플랫폼 이용", "주문", "일반")


def _classify_site_group(site_name: str, url: str) -> str:
    """사이트 그룹 자동 분류"""
    if "naver" in url.lower():
        return "네이버"
    elif "daum" in url.lower():
        return "다음"
    elif "youtube" in url.lower():
        return "유튜브"
    elif "dcinside" in url.lower():
        return "디시인사이드"
    elif "fmkorea" in url.lower():
        return "에펨코리아"
    elif any(word in url.lower() for word in ["twitter", "x.com"]):
        return "트위터"
    else:
        return "기타"


def _generate_auto_summary(title: str, content: str) -> str:
    """자동 요약 생성"""
    # 제목이 있으면 제목 기반 요약
    if title and len(title) > 5:
        return title[:50] + ("..." if len(title) > 50 else "")
    
    # 내용 기반 요약
    if content:
        # 첫 문장 추출 시도
        sentences = content.split('.')
        if sentences and len(sentences[0]) > 10:
            return sentences[0][:100] + ("..." if len(sentences[0]) > 100 else "")
        else:
            return content[:100] + ("..." if len(content) > 100 else "")
    
    return "내용 없음"


# ── 유틸 ────────────────────────────────────────────────────────────────────────
async def _text(target, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            el = await target.query_selector(sel)
            if el:
                t = (await el.inner_text()).strip()
                if t:
                    return t
        except Exception:
            pass
    return ""


def _parse_date(raw: str) -> str:
    if not raw:
        return ""
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return ""


def _to_int(s: str) -> int:
    return int(re.sub(r"[^0-9]", "", s or "") or 0)


# ── 브라우저 닫기 ───────────────────────────────────────────────────────────────
async def close_browser():
    await _cleanup()
    _state.update(status="idle", message="", results=[], progress=0, total=0)


async def _cleanup():
    for key in ("page", "context", "browser", "pw"):
        obj = _state.get(key)
        if obj:
            try:
                await (obj.stop() if key == "pw" else obj.close())
            except Exception:
                pass
            _state[key] = None
