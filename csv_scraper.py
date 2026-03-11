import asyncio
import re
import random
import os
import csv
from datetime import datetime
from playwright.async_api import async_playwright, Page
import database as db

# ── CSV 구조에 맞는 스크래퍼 설정 ────────────────────────────────────────────────
CAFE_URL = "https://cafe.naver.com/jihosoccer123"
BOARD_URL = "https://cafe.naver.com/f-e/cafes/23611966/menus/0?q=%EB%B0%B0%EB%8B%AC&ta=ARTICLE_COMMENT&iq=%EC%9E%A5%EC%82%AC%2C+%EB%B0%B0%EB%8B%AC%EC%9D%98%EB%AF%BC%EC%A1%B1%2C+%EC%BF%A0%ED%8C%A1%EC%9D%B4%EC%B8%A0&page=1&size=50"
CAFE_ID = "23611966"

# CSV 컬럼 정의 (목업 데이터 구조 기반)
CSV_COLUMNS = [
    "년", "월", "일", "주차", "모니터링명", "위험도", "a", "b", "c", "언급KEYWORD",
    "주체구분", "서비스구분", "검색어", "제목", "내용", "대상구분", "채널구분", "감성구분",
    "리스크분류", "분류_대분류", "분류_중분류", "분류_소분류", "사이트그룹", "사이트명",
    "작성자명", "조회 수", "댓글 수", "등록일", "등록 시간", "게시글 원문 URL",
    "원문 캡쳐 URL", "컨텐츠키", "분석일시", "요약", "취합일", "취합시간", "취합자", "수집경로"
]

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


# ── CSV 형식으로 수집 시작 ──────────────────────────────────────────────────────
async def start_csv_scraping(max_posts: int = 0, monitoring_name: str = "1인분(한그릇)",
                            search_keyword: str = "배민", date_from: str = "", 
                            date_to: str = "", board_url: str = "", output_file: str = ""):
    """CSV 구조에 맞춰 데이터 수집"""
    if _state["status"] == "scraping":
        return
    if _state["task"] and not _state["task"].done():
        _state["task"].cancel()
    _state["task"] = asyncio.create_task(
        _do_csv_scrape(max_posts, monitoring_name, search_keyword, 
                      date_from, date_to, board_url, output_file)
    )


async def _do_csv_scrape(max_posts: int, monitoring_name: str, search_keyword: str,
                        date_from: str, date_to: str, board_url: str = "", 
                        output_file: str = ""):
    page: Page = _state["page"]
    if not page:
        _state.update(status="error", message="브라우저가 열려있지 않습니다.")
        return

    # 출력 파일명 설정
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"아프니까사장이다_{monitoring_name}_{timestamp}.csv"

    # 기본 URL 설정
    base_url = board_url.strip() if board_url.strip() else BOARD_URL

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
        # 검색 URL 구성
        search_url = base_url
        if date_from:
            search_url += "&from=" + date_from.replace("-", "")
        if date_to:
            search_url += "&to=" + date_to.replace("-", "")
        
        print(f"[CSV수집URL] {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        
        _state["message"] = f"게시글 목록 수집 중{date_label}..."
        
        # 게시글 링크 수집
        unlimited = (max_posts == 0)
        fetch_limit = 9999 if unlimited else max_posts * 3
        article_infos = await _collect_article_links(page, fetch_limit, date_from, date_to)

        if not article_infos:
            _state.update(status="error",
                          message="게시글 목록을 찾지 못했습니다. 게시판 목록 화면인지 확인 후 다시 시도해주세요.")
            return

        # 날짜 필터링
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

        # CSV 파일 생성 및 헤더 작성
        csv_data = []
        csv_data.append(CSV_COLUMNS)  # 헤더 추가

        saved = []
        skipped_date = 0
        
        for i, info in enumerate(article_infos):
            _state["progress"] = i + 1
            _state["message"] = f"수집 중 ({i+1}/{len(article_infos)}): {info.get('title','')[:28]}..."
            
            post = await _scrape_article(page, info)
            if post:
                # CSV 행 데이터 생성
                csv_row = _convert_to_csv_row(post, monitoring_name, search_keyword, info)
                csv_data.append(csv_row)
                saved.append(post)
                
            await asyncio.sleep(random.uniform(1.2, 2.5))

        # CSV 파일 저장
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_data)

        _state.update(results=saved, status="done",
                      message=f"CSV 저장 완료! {len(saved)}개 게시글을 {output_file}에 저장했습니다.")

    except asyncio.CancelledError:
        _state.update(status="idle", message="수집이 취소되었습니다.")
    except Exception as e:
        _state.update(status="error", message=f"오류: {e}")


def _convert_to_csv_row(post: dict, monitoring_name: str, search_keyword: str, info: dict) -> list:
    """게시글 데이터를 CSV 행으로 변환"""
    post_date = post.get("post_date", "")
    
    # 날짜 파싱
    year, month, day = "", "", ""
    week_info = ""
    if post_date:
        try:
            date_obj = datetime.strptime(post_date, "%Y-%m-%d")
            year = str(date_obj.year)
            month = str(date_obj.month)
            day = str(date_obj.day)
            # 주차 계산 (월의 몇 번째 주)
            week_num = (date_obj.day - 1) // 7 + 1
            week_info = f"{month}월 {week_num}주차"
        except:
            pass

    # 감성 분석 (간단한 키워드 기반)
    content = post.get("content", "")
    title = post.get("title", "")
    full_text = f"{title} {content}".lower()
    
    sentiment = "중립"
    negative_keywords = ["미친", "짜증", "화나", "최악", "싫어", "불만", "문제", "개같", "ㅅㅂ", "ㅋㅋㅋㅋ"]
    positive_keywords = ["좋아", "최고", "감사", "만족", "훌륭", "완벽", "추천"]
    
    if any(keyword in full_text for keyword in negative_keywords):
        sentiment = "부정"
    elif any(keyword in full_text for keyword in positive_keywords):
        sentiment = "긍정"

    # 위험도 계산 (0: 낮음, 1: 보통, 2: 높음)
    risk_level = 0
    if sentiment == "부정":
        risk_level = 1
        if any(word in full_text for word in ["미친", "최악", "ㅅㅂ"]):
            risk_level = 2

    # 주체 구분 (작성자 기반 추정)
    author = post.get("author", "")
    subject_type = "소비자"  # 기본값
    if "사장" in author or "업주" in author or "점주" in author:
        subject_type = "업주"
    elif "라이더" in author or "배달" in author:
        subject_type = "라이더"

    # 현재 시간
    now = datetime.now()
    analysis_time = now.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]
    collect_date = now.strftime("%Y-%m-%d")
    collect_time = now.strftime("%H:%M")

    # 컨텐츠 키 생성
    content_key = f"{post_date.replace('-', '')}{now.strftime('%H%M%S%f')[:-3]}"

    return [
        year,                           # 년
        month,                          # 월  
        day,                            # 일
        week_info,                      # 주차
        monitoring_name,                # 모니터링명
        risk_level,                     # 위험도
        "",                             # a
        "",                             # b
        "",                             # c
        search_keyword,                 # 언급KEYWORD
        "당사",                         # 주체구분
        "배달의민족",                   # 서비스구분
        search_keyword,                 # 검색어
        post.get("title", ""),          # 제목
        post.get("content", ""),        # 내용
        subject_type,                   # 대상구분
        "카페",                         # 채널구분
        sentiment,                      # 감성구분
        "OPERATIONAL EXCELLENCE",       # 리스크분류
        "플랫폼 이용",                  # 분류_대분류
        "주문",                         # 분류_중분류
        "최소 주문 금액",               # 분류_소분류
        "네이버",                       # 사이트그룹
        "아프니까사장이다",             # 사이트명
        post.get("author", ""),         # 작성자명
        post.get("view_count", 0),      # 조회 수
        post.get("comment_count", 0),   # 댓글 수
        post_date,                      # 등록일
        "",                             # 등록 시간
        info.get("url", ""),            # 게시글 원문 URL
        "확인불가",                     # 원문 캡쳐 URL
        content_key,                    # 컨텐츠키
        analysis_time,                  # 분석일시
        _generate_summary(post),        # 요약
        collect_date,                   # 취합일
        collect_time,                   # 취합시간
        "자동수집",                     # 취합자
        "SCA"                           # 수집경로
    ]


def _generate_summary(post: dict) -> str:
    """게시글 요약 생성"""
    content = post.get("content", "")
    title = post.get("title", "")
    
    # 간단한 요약 로직
    if len(content) > 100:
        summary = content[:100] + "..."
    else:
        summary = content
    
    return summary


# ── 기존 스크래퍼 함수들 재사용 ──────────────────────────────────────────────────
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
            seen.add(href);

            // 같은 행에서 날짜 추출
            const row = a.closest('tr') || a.closest('li') || a.closest('[class*="item"]') || a.closest('[class*="article"]');
            let dateText = '';
            if (row) {
                const tds = row.querySelectorAll('.td_normal');
                for (const td of tds) {
                    if (td.innerText.trim().match(/\\d{4}\\.\\d{1,2}\\.\\d{1,2}/)) {
                        dateText = td.innerText.trim();
                        break;
                    }
                }
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
            break

        if len(links) >= max_count:
            break

        if date_from and oldest_on_page and oldest_on_page < date_from:
            break

        went = await _goto_next_board_page(page, page_num)
        if not went:
            break
        await asyncio.sleep(2)

    return links[:max_count]


async def _goto_next_board_page(page: Page, current_num: int) -> bool:
    """게시판 다음 페이지로 이동"""
    # URL 파라미터 방식
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

    # 메인 페이지 URL 방식
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

    return False


async def _scrape_article(page: Page, info: dict) -> dict | None:
    """개별 게시글 수집"""
    url = info["url"]
    art = None
    try:
        art = await page.context.new_page()
        await art.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2)

        # 콘텐츠 프레임 탐색
        target = art
        for frame in art.frames:
            if frame == art.main_frame:
                continue
            fu = frame.url
            if ("f-e/cafes" in fu or
                "ca-fe/cafes" in fu or
                "ArticleRead" in fu or
                ("cafe.naver.com" in fu and "articleid" in fu)):
                target = frame
                try:
                    await target.wait_for_selector(
                        ".se-main-container, #tbody, .article_body, .CafeViewer, .view_content",
                        timeout=5000,
                    )
                except Exception:
                    await asyncio.sleep(0.5)
                break

        # 제목
        title = await _text(target, [
            ".title_text", "h3[class*='title']",
            "h3.title", ".tit-box em", ".article_title",
            ".ucc-title", ".article-head h3",
        ]) or info.get("title", "제목 없음")

        # 본문
        content = await _extract_body(target)

        # 날짜
        date_raw = await _text(target, [
            "em.date", ".date", "span.date",
            ".article_info .date", ".article_head .date",
            ".write_info", ".post-time", ".publish_date",
            "span[class*='date']", "[class*='date']",
            "p.date", "time",
        ])
        date = _parse_date(date_raw)

        # 작성자
        author = await _text(target, [
            ".nick", ".member_info .writer", "span.writer",
            ".article_head .nick", ".writer_nick", "a.m-tcol-c",
            "[class*='nick']", "[class*='author']",
        ])

        # 조회수
        view_str = await _text(target, [
            ".count_view", ".view_count", "em[class*='view']", "[class*='view_count']",
        ])
        view_count = _to_int(view_str)

        # 댓글
        comments = await _extract_comments(target, art)

        if not title and not content:
            return None

        return {
            "title": title or "제목 없음",
            "content": content or "(내용 없음)",
            "comments": comments,
            "post_date": date,
            "author": author or "",
            "view_count": view_count,
            "comment_count": len(comments),
            "category": "일반",
        }
    except Exception as e:
        print(f"[CSV스크래퍼] 수집 실패 ({url}): {e}")
        return None
    finally:
        if art:
            try: await art.close()
            except: pass


async def _extract_body(target) -> str:
    """본문 추출"""
    selectors = [
        ".se-main-container",
        "#tbody",
        ".article_body",
        ".content_wrap",
        ".CafeViewer",
        ".article-content",
        "div#content",
        ".view_content",
    ]
    text = await _text(target, selectors)
    if text and len(text) > 10:
        return text

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
    """댓글 추출"""
    for t in [target, page]:
        try:
            await t.evaluate("()=>window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            await t.evaluate("()=>window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.0)
        except Exception:
            pass

    selectors = [
        ".CommentItem .text_comment",
        ".comment_text_box .text_comment",
        "._commentContent",
        ".u_cbox_contents",
        "[class*='CommentItem'] [class*='text']",
        "[class*='comment'] [class*='content']",
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


# ── 유틸 함수들 ─────────────────────────────────────────────────────────────────
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