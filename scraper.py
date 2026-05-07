import asyncio
import re
import random
import os
import urllib.parse
import json
from pathlib import Path
from playwright.async_api import async_playwright, Page
import database as db
from community_search_engine import process_community_url, detect_url_type, get_supported_communities

# ── 설정 ────────────────────────────────────────────────────────────────────────
CAFE_URL  = "https://cafe.naver.com/jihosoccer123"
BOARD_URL = "https://cafe.naver.com/f-e/cafes/23611966/menus/0?q=%EB%B0%B0%EB%8B%AC&ta=ARTICLE_COMMENT&iq=%EC%9E%A5%EC%82%AC%2C+%EB%B0%B0%EB%8B%AC%EC%9D%98%EB%AF%BC%EC%A1%B1%2C+%EC%BF%A0%ED%8C%A1%EC%9D%B4%EC%B8%A0&page=1&size=50"
CAFE_ID   = "23611966"
SESSION_FILE = Path(__file__).parent / "naver_session.json"

# ── URL 타입 감지 및 자동 검색 기능 ──────────────────────────────────────────────

def _split_keywords(keywords: str) -> list[str]:
    """다중 키워드 분리 (OR 검색용)"""
    if not keywords or not keywords.strip():
        return []
    
    # 쉼표로 분리
    if ',' in keywords:
        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
    # 세미콜론으로 분리
    elif ';' in keywords:
        keyword_list = [k.strip() for k in keywords.split(';') if k.strip()]
    # 파이프로 분리
    elif '|' in keywords:
        keyword_list = [k.strip() for k in keywords.split('|') if k.strip()]
    # 분리자가 없으면 단일 키워드
    else:
        keyword_list = [keywords.strip()]
    
    return keyword_list

def detect_cafe_url_type(url: str) -> str:
    """네이버 카페 URL 타입 감지"""
    if not url or "cafe.naver.com" not in url:
        return "unknown"
    
    # 검색 관련 파라미터가 있는지 확인
    search_indicators = ["search", "query=", "q=", "ArticleSearchList", "menus/0?q="]
    if any(indicator in url for indicator in search_indicators):
        return "search_result"
    
    # 일반 카페 URL 패턴 확인
    cafe_patterns = [
        r"cafe\.naver\.com/[^/?#]+/?$",  # cafe.naver.com/cafename
        r"cafe\.naver\.com/f-e/cafes/\d+/?$",  # cafe.naver.com/f-e/cafes/12345
    ]
    
    for pattern in cafe_patterns:
        if re.search(pattern, url):
            return "cafe_main"
    
    return "unknown"

def extract_cafe_info(url: str) -> dict:
    """URL에서 카페 정보 추출"""
    info = {"cafe_name": "", "cafe_id": "", "base_url": ""}
    
    # 새로운 형식: cafe.naver.com/f-e/cafes/12345
    new_format = re.search(r"cafe\.naver\.com/f-e/cafes/(\d+)", url)
    if new_format:
        info["cafe_id"] = new_format.group(1)
        info["base_url"] = f"https://cafe.naver.com/f-e/cafes/{info['cafe_id']}"
        return info
    
    # 기존 형식: cafe.naver.com/cafename
    old_format = re.search(r"cafe\.naver\.com/([^/?#]+)", url)
    if old_format:
        info["cafe_name"] = old_format.group(1)
        info["base_url"] = f"https://cafe.naver.com/{info['cafe_name']}"
        return info
    
    return info

def build_search_url(cafe_url: str, search_keyword: str) -> str:
    """카페 메인 URL + 키워드 → 검색 URL 생성"""
    if not search_keyword.strip():
        return cafe_url
    
    cafe_info = extract_cafe_info(cafe_url)
    encoded_keyword = urllib.parse.quote(search_keyword.strip())
    
    if cafe_info["cafe_id"]:
        # 새로운 형식 (f-e/cafes/ID) - 아프니까사장이다 스타일
        return f"https://cafe.naver.com/f-e/cafes/{cafe_info['cafe_id']}/menus/0?q={encoded_keyword}&ta=SUBJECT"
    elif cafe_info["cafe_name"]:
        # 기존 형식 (cafename)
        return f"https://cafe.naver.com/{cafe_info['cafe_name']}/ArticleSearchList.nhn?search.query={encoded_keyword}"
    else:
        # 알 수 없는 형식 - 원본 반환
        return cafe_url

def process_cafe_url(url: str, search_keyword: str) -> tuple[str, str]:
    """URL 타입에 따른 처리 및 메시지 생성"""
    if not url.strip():
        return BOARD_URL, "기본 URL 사용"
    
    url_type = detect_cafe_url_type(url)
    
    if url_type == "search_result":
        # 이미 검색된 URL - 그대로 사용
        return url, "검색 결과 URL 감지 - 바로 크롤링"
    
    elif url_type == "cafe_main" and search_keyword.strip():
        # 메인 URL + 키워드 → 검색 URL 생성
        search_url = build_search_url(url, search_keyword)
        return search_url, f"자동 검색 URL 생성: '{search_keyword}' 키워드로 검색"
    
    elif url_type == "cafe_main":
        # 메인 URL만 있고 키워드 없음 → 최신 게시글
        return url, "카페 메인 URL - 최신 게시글 수집"
    
    else:
        # 알 수 없는 URL
        return url, "URL 형식을 인식할 수 없음 - 원본 URL 사용"

# ── 전역 상태 ───────────────────────────────────────────────────────────────────
_state = {
    "pw": None, "browser": None, "context": None, "page": None,
    "status": "idle",   # idle | open | scraping | done | error | stopped
    "message": "", "progress": 0, "total": 0, "results": [], "task": None,
    "should_stop": False,
}


def get_status() -> dict:
    # 브라우저 상태를 실시간으로 확인
    browser_status = "idle"
    browser_message = _state["message"]
    
    if _state["browser"]:
        try:
            if _state["browser"].is_connected():
                if _state["page"] and not _state["page"].is_closed():
                    browser_status = "open"
                    if not browser_message:
                        browser_message = "브라우저가 열려있습니다."
                else:
                    browser_status = "idle"
                    browser_message = "브라우저를 열어주세요."
            else:
                browser_status = "idle"
                browser_message = "브라우저 연결이 끊어졌습니다."
        except Exception:
            browser_status = "idle"
            browser_message = "브라우저 상태를 확인할 수 없습니다."
    
    # 스크래핑 중이면 원래 상태 유지
    if _state["status"] in ["scraping", "done", "error"]:
        browser_status = _state["status"]
        browser_message = _state["message"]
    
    return {
        "status": browser_status,
        "message": browser_message,
        "progress": _state["progress"],
        "total": _state["total"],
        "result_count": len(_state["results"]),
    }

def get_results() -> list:
    return list(_state["results"])


# ── 브라우저 열기 ───────────────────────────────────────────────────────────────
async def open_browser(cafe_url: str = CAFE_URL, headless: bool = True, force_headless: bool = False):
    """브라우저 열기. force_headless=True이면 세션 실패 시에도 절대 창을 열지 않음 (배치 수집용)"""
    # 브라우저가 연결되지 않았거나 닫혔으면 정리
    if _state["browser"] and not _state["browser"].is_connected():
        await _cleanup()
    
    # 브라우저가 이미 열려있고 페이지가 유효한지 확인
    if _state["browser"] and _state["page"]:
        try:
            if _state["page"].is_closed():
                await _cleanup()
            else:
                _state["message"] = "브라우저가 이미 열려 있습니다."
                return
        except Exception:
            await _cleanup()

    # 저장된 세션이 있으면 headless 모드로 쿠키 복원 시도
    use_saved_session = has_saved_session()
    # force_headless가 True이면 항상 headless 유지
    # headless=False로 명시적 요청 시에는 세션 유무와 관계없이 창 열기
    if force_headless:
        actual_headless = True
    elif not headless:
        actual_headless = False
    else:
        actual_headless = True if use_saved_session else headless

    pw = await async_playwright().start()

    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    executable_path = next((p for p in chrome_paths if os.path.exists(p)), None)

    # 공통 launch_args (헤드리스 여부와 무관하게 최대화/포커스 강제 없음)
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run", "--no-default-browser-check",
        "--disable-infobars",
        "--window-size=1280,900",
    ]

    # headless=False + 배치 수집 중일 때만 창을 화면 밖에 배치
    # (수동 브라우저 열기 시에는 로그인을 위해 정상 위치에 표시)
    is_batch = _state.get("batch_status") is not None
    if not actual_headless and is_batch:
        launch_args.append("--window-position=-32000,-32000")

    browser = await pw.chromium.launch(
        headless=actual_headless,
        executable_path=executable_path,
        args=launch_args,
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="ko-KR",
        extra_http_headers={
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        }
    )
    await context.add_init_script("""
        // webdriver 속성 제거
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        
        // 언어 설정
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ko-KR', 'ko', 'en-US', 'en'],
        });
        
        // chrome 객체 위조
        if (!window.chrome) {
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
        }
    """)

    # 불필요한 리소스 차단 (이미지, 폰트, 미디어) — 페이지 로드 속도 개선
    async def _block_resources(route):
        if route.request.resource_type in ("image", "font", "media"):
            await route.abort()
        else:
            await route.continue_()
    await context.route("**/*", _block_resources)

    # 저장된 세션 쿠키 복원
    if use_saved_session:
        try:
            cookies = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            await context.add_cookies(cookies)
        except Exception:
            # 쿠키 파일 손상 시 삭제하고 재시도
            SESSION_FILE.unlink(missing_ok=True)
            await browser.close()
            await pw.stop()
            _state.update(pw=None, browser=None, context=None, page=None)
            if force_headless:
                # 배치 수집 중: 세션 없이는 네이버 카페 수집 불가 → 에러 반환
                _state["message"] = "⚠️ 세션 쿠키 손상. 브라우저에서 재로그인이 필요합니다."
                _state["status"] = "error"
                return
            else:
                # 수동 모드: headless=False로 재귀 호출 (세션 파일 삭제했으므로 무한루프 없음)
                return await open_browser(cafe_url, headless=False)

    page = await context.new_page()
    _state.update(pw=pw, browser=browser, context=context, page=page,
                  status="open", headless=actual_headless,
                  message="브라우저가 열렸습니다. 네이버에 로그인 후 수집할 게시판으로 이동하세요.")
    
    try:
        await page.goto(cafe_url, wait_until="networkidle", timeout=30000)
    except Exception:
        await page.goto(cafe_url, wait_until="domcontentloaded", timeout=30000)

    # 세션 복원 후 로그인 상태 검증
    if use_saved_session:
        logged_in = await _check_naver_login(page)
        if logged_in:
            _state["message"] = "✅ 저장된 세션으로 백그라운드 로그인 성공. 바로 수집 가능합니다."
        else:
            # 로그인 실패 → 세션 파일 삭제, 브라우저 닫기
            SESSION_FILE.unlink(missing_ok=True)
            await _cleanup()
            _state.update(status="idle", message="")
            if force_headless:
                # 배치 수집 중: 네이버 카페는 로그인 없이 수집 불가 → 에러 반환
                _state["message"] = "⚠️ 세션 만료. 브라우저에서 재로그인이 필요합니다."
                _state["status"] = "error"
                return
            else:
                # 수동 모드: 로그인 창 열기
                return await open_browser(cafe_url, headless=False)


async def _check_naver_login(page: Page) -> bool:
    """네이버 로그인 상태 확인 (쿠키 기반 우선 판별)"""
    try:
        # 1차: 쿠키 기반 판단 (가장 신뢰할 수 있는 방법)
        cookies = await page.context.cookies()
        naver_cookies = [c for c in cookies if "naver.com" in c.get("domain", "")]
        auth_cookies = [c for c in naver_cookies if c["name"] in ("NID_AUT", "NID_SES", "NID_JKL", "nid_inf")]
        if auth_cookies:
            print(f"[로그인체크] 네이버 인증 쿠키 {len(auth_cookies)}개 확인 → 로그인 상태")
            return True
        
        # 2차: 페이지 URL에 로그인 리다이렉트가 포함되어 있는지 확인
        current_url = page.url
        if "nidlogin" in current_url or "nid.naver.com" in current_url:
            print(f"[로그인체크] 로그인 페이지로 리다이렉트됨 → 로그아웃 상태")
            return False
        
        # 3차: 페이지 내용에서 로그인 폼 감지
        page_content = await page.content()
        login_indicators = ["nid.naver.com/nidlogin", "로그인해 주세요", "로그인이 필요합니다"]
        if any(indicator in page_content for indicator in login_indicators):
            print(f"[로그인체크] 페이지에서 로그인 요구 감지 → 로그아웃 상태")
            return False
        
        # 쿠키도 없고 로그인 페이지도 아니면 → 판단 불가, 일단 True로 진행
        # (세션 파일을 삭제하지 않고 실제 수집 시 로그인 감지에 맡김)
        print(f"[로그인체크] 인증 쿠키 없지만 로그인 페이지도 아님 → 수집 시도 허용")
        return True
    except Exception as e:
        print(f"[로그인체크] 오류: {e}")
        return True  # 오류 시에도 세션 파일 삭제 방지


# ── 수집 시작 ───────────────────────────────────────────────────────────────────
async def start_scraping(max_posts: int = 0, category: str = "",
                         date_from: str = "", date_to: str = "",
                         board_url: str = "", cafe_name: str = "",
                         monitoring_name: str = "", search_keyword: str = ""):
    if _state["status"] == "scraping":
        return
    if _state["task"] and not _state["task"].done():
        _state["task"].cancel()
    # 이전 완료 상태를 idle로 리셋 — 대기 루프가 이전 완료 상태를 새 수집 완료로 오인하는 버그 방지
    _state["status"] = "idle"
    _state["results"] = []
    _state["task"] = asyncio.create_task(
        _do_scrape(max_posts, category, date_from, date_to, board_url, cafe_name, 
                   monitoring_name, search_keyword)
    )


async def _do_scrape(max_posts: int, category: str, date_from: str, date_to: str,
                     board_url: str = "", cafe_name: str = "", 
                     monitoring_name: str = "", search_keyword: str = ""):
    # 브라우저 상태 체크
    if not _state.get("browser") or not _state.get("page"):
        _state.update(status="error", message="브라우저가 열려있지 않습니다.")
        return
    
    page: Page = _state["page"]
    
    # 수집 시작 시 브라우저 창을 화면 밖으로 이동 (로그인 후 창이 보이지 않도록)
    try:
        if not _state.get("headless"):
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Browser.setWindowBounds", {
                "windowId": (await cdp.send("Browser.getWindowForTarget"))["windowId"],
                "bounds": {"left": -32000, "top": -32000}
            })
            await cdp.detach()
    except Exception:
        pass  # CDP 미지원 시 무시
    
    # 페이지가 닫혔는지 확인
    try:
        if page.is_closed():
            _state.update(status="error", message="브라우저 페이지가 닫혔습니다. 브라우저를 다시 열어주세요.")
            return
    except Exception:
        _state.update(status="error", message="브라우저 연결이 끊어졌습니다. 브라우저를 다시 열어주세요.")
        return

    # UI에서 전달된 board_url 우선 사용, 없으면 기본값
    base_url = board_url.strip() if board_url.strip() else BOARD_URL
    
    # 🔍 다중 키워드 분리 (OR 검색 구현)
    keywords_list = _split_keywords(search_keyword)
    print(f"[다중키워드] {len(keywords_list)}개 키워드로 개별 검색: {keywords_list}")
    
    # 첫 번째 키워드로 사이트 타입 확인
    url_result = process_community_url(base_url, keywords_list[0] if keywords_list else "")
    site_type = url_result["site_type"]
    site_name = url_result["site_name"]
    action = url_result["action"]
    
    # 등록되지 않은 URL인 경우 처리 중단
    if action == "reject" or site_type == "unregistered":
        _state.update(status="error", message=url_result["message"])
        return
    
    # 카페명 미입력 시 자동 감지된 사이트명 사용
    resolved_cafe_name = cafe_name.strip()
    if not resolved_cafe_name:
        if site_name and site_name != "알 수 없는 사이트":
            resolved_cafe_name = site_name
        else:
            m = re.search(r"cafe\.naver\.com/(?:f-e/cafes/\d+|([^/?#]+))", base_url)
            resolved_cafe_name = m.group(1) if (m and m.group(1)) else "커뮤니티 사이트"

    date_label = ""
    if date_from and date_to:
        date_label = f" ({date_from} ~ {date_to})"
    elif date_from:
        date_label = f" ({date_from} 이후)"
    elif date_to:
        date_label = f" ({date_to} 이전)"

    _state.update(status="scraping", progress=0, total=0, results=[],
                  message=f"다중 키워드 검색 시작... ({len(keywords_list)}개 키워드)")
    try:
        # 🔄 각 키워드별로 개별 검색 실행 및 결과 병합
        all_article_infos = []
        seen_urls = set()
        
        unlimited = (max_posts == 0)
        fetch_limit_per_keyword = 9999 if unlimited else max(max_posts, 50)
        
        for idx, keyword in enumerate(keywords_list, 1):
            if _state.get("should_stop"):
                break
                
            _state["message"] = f"키워드 {idx}/{len(keywords_list)} 검색 중: '{keyword}'{date_label}"
            print(f"\n[키워드 {idx}/{len(keywords_list)}] '{keyword}' 검색 시작")
            
            # 키워드별 검색 URL 생성
            url_result = process_community_url(base_url, keyword)
            search_url = url_result["final_url"]
            
            # 날짜 파라미터 추가
            if date_from or date_to:
                if "cafe.naver.com" in search_url:
                    if date_from:
                        search_url += "&from=" + date_from.replace("-", "")
                    if date_to:
                        search_url += "&to=" + date_to.replace("-", "")
            
            print(f"[검색URL] {search_url}")
            
            try:
                # 봇 탐지 회피용 랜덤 딜레이 (네이트판 포함 모든 사이트)
                import random
                is_nate = "pann.nate.com" in search_url or "nate.com" in search_url
                
                # 네이트판: httpx 기반 검색 우선 시도 (Playwright 차단 우회)
                if is_nate:
                    print(f"[네이트판] httpx 기반 검색 시도: '{keyword}'")
                    _state["message"] = f"네이트판 검색 중 (httpx): '{keyword}'"
                    httpx_links = await _search_nate_pann_via_httpx(keyword, fetch_limit_per_keyword)
                    if httpx_links:
                        new_count = 0
                        for link_info in httpx_links:
                            url = link_info.get("url", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                all_article_infos.append(link_info)
                                new_count += 1
                        print(f"[키워드 {idx}] '{keyword}': {new_count}개 신규 링크 수집 (총 {len(all_article_infos)}개)")
                        # 키워드 간 짧은 딜레이
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        continue  # 다음 키워드로
                    else:
                        print(f"[네이트판] httpx 실패, Playwright 폴백 시도")
                
                # 네이트판은 키워드 간 딜레이를 더 길게 (5~10초)
                if is_nate:
                    delay = random.uniform(5.0, 10.0)
                    print(f"[네이트판] 봇 탐지 회피 대기 {delay:.1f}초...")
                    await asyncio.sleep(delay)
                    # Referer 헤더 설정 (네이트 내부 탐색처럼 보이게)
                    await page.set_extra_http_headers({
                        "Referer": "https://pann.nate.com/",
                        "Accept-Language": "ko-KR,ko;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    })
                else:
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                
                await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                
                # 네이트 차단 페이지 감지 및 단계적 재시도
                if is_nate:
                    page_content = await page.content()
                    nate_blocked = ("이용에 불편을 드려 죄송합니다" in page_content 
                                    or "잠시 후에 다시 한번 시도" in page_content
                                    or "보안 정책" in page_content)
                    if nate_blocked:
                        # 1차 재시도: 짧은 대기 + 메인 페이지 쿠키 워밍업
                        wait_sec = random.uniform(15, 25)
                        print(f"[네이트차단] 차단 감지. {wait_sec:.0f}초 대기 후 재시도...")
                        _state["message"] = f"네이트판 차단 감지 - {int(wait_sec)}초 대기 후 재시도 중..."
                        await asyncio.sleep(wait_sec)
                        
                        # 네이트 메인 → 판 메인 순서로 방문 (자연스러운 탐색 흐름)
                        await page.goto("https://www.nate.com", wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(random.uniform(2, 4))
                        await page.goto("https://pann.nate.com", wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(random.uniform(2, 4))
                        
                        # 검색 페이지 재시도
                        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                        await asyncio.sleep(3)
                        
                        page_content_retry = await page.content()
                        still_blocked = ("이용에 불편을 드려 죄송합니다" in page_content_retry
                                         or "잠시 후에 다시 한번 시도" in page_content_retry
                                         or "보안 정책" in page_content_retry)
                        if still_blocked:
                            # 2차 재시도: 더 긴 대기
                            wait_sec2 = random.uniform(40, 60)
                            print(f"[네이트차단] 1차 재시도 실패. {wait_sec2:.0f}초 추가 대기...")
                            _state["message"] = f"네이트판 차단 지속 - {int(wait_sec2)}초 추가 대기 중..."
                            await asyncio.sleep(wait_sec2)
                            
                            await page.goto("https://pann.nate.com", wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(random.uniform(3, 5))
                            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                            await asyncio.sleep(3)
                            
                            page_content_final = await page.content()
                            if ("이용에 불편을 드려 죄송합니다" in page_content_final
                                or "잠시 후에 다시 한번 시도" in page_content_final):
                                print(f"[네이트차단] 최종 재시도 실패. 키워드 '{keyword}' 건너뜀.")
                                _state["message"] = f"네이트판 차단됨 - 키워드 '{keyword}' 건너뜀"
                                continue
                
                # 키워드별 링크 수집
                keyword_links = await _collect_article_links(page, fetch_limit_per_keyword, date_from, date_to)
                
                # 중복 제거하며 병합
                new_count = 0
                for link_info in keyword_links:
                    url = link_info.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_article_infos.append(link_info)
                        new_count += 1
                
                print(f"[키워드 {idx}] '{keyword}': {new_count}개 신규 링크 수집 (총 {len(all_article_infos)}개)")
                
            except Exception as e:
                print(f"[키워드 {idx}] '{keyword}' 검색 실패: {e}")
                continue
        
        article_infos = all_article_infos
        print(f"\n[병합완료] 총 {len(article_infos)}개 게시글 링크 수집 (중복 제거 완료)")

        if not article_infos:
            _state.update(status="error",
                          message="게시글 목록을 찾지 못했습니다. 게시판 목록 화면인지 확인 후 다시 시도해주세요.")
            return

        # 날짜 필터링 (목록에서 날짜를 알 수 있는 경우 미리 제외)
        skipped = 0
        if date_from or date_to:
            filtered = []
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

        # ── 1단계 완료: DB 중복 + URL 중복 일괄 제거 → 수집 예정 건수 확정 ──
        pre_dup_count = 0
        filtered_infos = []
        for info in article_infos:
            pre_title = info.get("title", "")
            pre_date = info.get("list_date", "")
            pre_url = info.get("url", "")
            # URL 기반 중복 체크 (DB에 이미 저장된 URL이면 스킵)
            if pre_url and db.post_exists_by_url(pre_url):
                pre_dup_count += 1
            elif pre_title and pre_date and db.post_exists(pre_title, pre_date):
                pre_dup_count += 1
            else:
                filtered_infos.append(info)
        
        article_infos = filtered_infos
        date_skip_in_scan = skipped
        planned_count = len(article_infos)
        _state["total"] = planned_count
        _state["planned_count"] = planned_count
        _state["message"] = (f"수집 예정 {planned_count}건"
                             f" (날짜 필터 {date_skip_in_scan}건 제외, 중복 {pre_dup_count}건 제외)")
        print(f"[수집예정] {planned_count}건 (날짜 제외 {date_skip_in_scan}, 중복 제외 {pre_dup_count})")

        if planned_count == 0:
            _state.update(status="done", results=[],
                          message=f"수집 대상 없음 (날짜 필터 {date_skip_in_scan}건, 중복 {pre_dup_count}건 제외)")
            return

        # ── 2단계: 본문 수집 ──
        saved = []
        skipped_date = 0
        skipped_dup = 0
        skipped_fail = 0  # 본문 수집 실패 카운터
        fail_reasons = {}  # 실패 사유별 카운트
        
        # 네이버 카페는 봇 탐지가 강하지만 2개 탭 병렬은 안전, 나머지는 5개 병렬
        is_naver = "cafe.naver.com" in base_url
        is_nate = "pann.nate.com" in base_url
        if is_naver or is_nate:
            concurrency = 2
        else:
            concurrency = 5
        
        async def _process_one(i, info):
            """게시글 하나를 수집하고 결과를 반환"""
            post = await _scrape_article(page, info)
            if not post:
                return ("fail", info, "알 수 없는 오류")
            # 실패 사유가 있는 경우
            if "_fail_reason" in post:
                reason = post["_fail_reason"]
                print(f"[수집실패] {info.get('url', '?')[:60]} → {reason}")
                return ("fail", info, reason)
            if post:
                list_date = info.get("list_date", "")
                article_date = post.get("post_date", "")
                if list_date:
                    post["post_date"] = list_date
                post_date = post.get("post_date", "")
                print(f"[날짜확인] {post.get('title','')[:20]} → {post_date!r}  "
                      f"(목록:{list_date!r} / 본문:{article_date!r})")
                if post_date:
                    if date_from and post_date < date_from:
                        return ("date_skip", info, None)
                    if date_to and post_date > date_to:
                        return ("date_skip", info, None)
                post["site"] = site_name if site_name != "알 수 없는 사이트" else "커뮤니티 사이트"
                post["cafe_name"] = resolved_cafe_name
                post["post_url"] = info.get("url", "")
                return ("ok", info, post)
            return ("fail", info, "데이터 없음")
        
        # 병렬 수집: concurrency개씩 묶어서 처리
        import time as _time
        _scrape_start = _time.time()
        
        for batch_start in range(0, len(article_infos), concurrency):
            if _state.get("should_stop"):
                _state.update(status="stopped", message=f"수집 중단됨. {len(saved)}개 저장됨")
                break
            
            batch = article_infos[batch_start:batch_start + concurrency]
            _state["progress"] = batch_start + len(batch)
            
            # ETA 계산 (batch_start = 이미 처리 완료된 아이템 수)
            eta_msg = ""
            if batch_start > 0:
                elapsed = _time.time() - _scrape_start
                avg_per_item = elapsed / batch_start
                remaining = planned_count - batch_start
                eta_sec = int(avg_per_item * remaining)
                _state["eta_seconds"] = eta_sec
                if eta_sec >= 60:
                    eta_msg = f" (약 {eta_sec // 60}분 {eta_sec % 60}초 남음)"
                else:
                    eta_msg = f" (약 {eta_sec}초 남음)"
            
            _state["message"] = f"본문 수집 중 ({batch_start}/{planned_count}건 처리)...{eta_msg}"
            
            tasks = [_process_one(batch_start + j, info) for j, info in enumerate(batch)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for res in results:
                if isinstance(res, Exception):
                    print(f"[수집오류] {res}")
                    skipped_fail += 1
                    fail_reasons["예외 발생"] = fail_reasons.get("예외 발생", 0) + 1
                    continue
                status, info, post_or_reason = res
                if status == "dup":
                    skipped_dup += 1
                elif status == "date_skip":
                    skipped_date += 1
                elif status == "fail":
                    skipped_fail += 1
                    reason = post_or_reason or "알 수 없음"
                    fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
                    print(f"[본문수집실패] {info.get('url', '?')[:60]} → {reason}")
                elif status == "ok" and post_or_reason:
                    saved.append(post_or_reason)
            
            # 사이트별 대기 시간 차등
            if is_naver or is_nate:
                await asyncio.sleep(random.uniform(1.5, 3.0))
            else:
                await asyncio.sleep(random.uniform(0.2, 0.5))

        # ── 자동 DB 저장 (CSV 구조 기반 확장)
        auto_saved, auto_skipped = 0, 0
        for post in saved:
            if db.post_exists(post["title"], post.get("post_date", "")):
                auto_skipped += 1
                continue
            
            # CSV 구조에 맞는 추가 분석 (지능형 분류 시스템 사용)
            try:
                from intelligent_classifier import classify_post_restaurant_business
                enhanced_post = classify_post_restaurant_business(post, monitoring_name or "일반모니터링", search_keyword or "")
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
                # 설정 파일에서 자동 업로드 여부 확인
                config_file = Path("sheets_config.json")
                auto_upload_enabled = True  # 기본값
                
                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    auto_upload_enabled = config.get("auto_upload", True)
                    sheet_url = config.get("sheet_url", "")
                    credentials_file = config.get("credentials_file", "google_credentials.json")
                else:
                    sheet_url = "https://docs.google.com/spreadsheets/d/1qP37BDR68sqoegMI31FMZt74923JO8NklUY2-XVOk5A/edit?gid=0#gid=0"
                    credentials_file = "google_credentials.json"
                
                if auto_upload_enabled and sheet_url:
                    from google_sheets_sync import GoogleSheetsSync
                    sync = GoogleSheetsSync(credentials_file=credentials_file, sheet_url=sheet_url)
                    if sync.setup_connection():
                        if sync.sync_all_data():
                            sheets_msg = " + 구글시트 업데이트 완료"
                        else:
                            sheets_msg = " (구글시트 업데이트 실패)"
                    else:
                        sheets_msg = " (구글시트 연결 실패)"
                else:
                    sheets_msg = " (구글시트 자동 업로드 비활성화)"
            except Exception as e:
                sheets_msg = f" (구글시트 오류: {str(e)[:30]})"

        extra = f" (날짜 범위 외 {skipped_date}개 제외)" if skipped_date else ""
        dup_msg = f", 중복 {auto_skipped}개 제외" if auto_skipped else ""
        pre_dup_msg = f", 사전 중복 스킵 {skipped_dup}개" if skipped_dup else ""
        fail_msg = f", 본문 수집 실패 {skipped_fail}개" if skipped_fail else ""
        
        # 수집 예정 대비 실제 저장 건수 차이 상세 안내
        gap = planned_count - auto_saved
        gap_detail = ""
        if gap > 0:
            reasons = []
            if skipped_date > 0:
                reasons.append(f"날짜 범위 외 {skipped_date}건")
            if auto_skipped > 0:
                reasons.append(f"DB 중복 {auto_skipped}건")
            if skipped_dup > 0:
                reasons.append(f"사전 중복 {skipped_dup}건")
            if skipped_fail > 0:
                # 실패 사유 상세 포함
                fail_detail_parts = [f"{r}({c}건)" for r, c in fail_reasons.items()]
                fail_detail = " / ".join(fail_detail_parts) if fail_detail_parts else ""
                reasons.append(f"본문 수집 실패 {skipped_fail}건")
                if fail_detail:
                    reasons.append(f"실패 상세: {fail_detail}")
            # 나머지 미분류 차이
            accounted = skipped_date + auto_skipped + skipped_dup + skipped_fail
            unaccounted = gap - accounted
            if unaccounted > 0:
                reasons.append(f"기타 {unaccounted}건")
            if reasons:
                gap_detail = f" | 미저장 사유: {', '.join(reasons)}"
        
        # Slack 알림은 배치 완료 시 일괄 전송 (개별 사이트에서는 보내지 않음)
        slack_msg = ""

        _state.update(results=saved, status="done",
                      message=f"저장 완료! {auto_saved}개 게시글 DB 저장{extra}{dup_msg}{pre_dup_msg}{fail_msg}{sheets_msg}{gap_detail}{slack_msg}")

    except asyncio.CancelledError:
        _state.update(status="idle", message="수집이 취소되었습니다.")
    except Exception as e:
        _state.update(status="error", message=f"오류: {e}")


# ── 게시글 링크 목록 수집 (멀티 페이지) ─────────────────────────────────────────
# ── 게시글 링크 목록 수집 (멀티 페이지) ─────────────────────────────────────────
async def _collect_article_links(page: Page, max_count: int,
                                  date_from: str = "", date_to: str = "") -> list[dict]:
    """다양한 커뮤니티 사이트에서 게시글 링크 + 날짜 수집 (적응형 크롤러 포함)"""
    links: list[dict] = []
    seen: set[str] = set()
    
    # 현재 페이지 URL 확인하여 사이트별 처리
    current_url = page.url.lower()
    print(f"[크롤링] 현재 URL: {current_url}")
    
    # 사이트별 전용 수집기 사용
    if "cafe.naver.com" in current_url:
        print("[크롤링] 네이버 카페 모드로 수집")
        links = await _collect_naver_cafe_links(page, max_count, date_from, date_to)
    elif "dcinside.com" in current_url:
        print("[크롤링] 디시인사이드 모드로 수집")
        links = await _collect_dcinside_links(page, max_count, date_from, date_to)
    elif "fmkorea.com" in current_url:
        print("[크롤링] 에펨코리아 모드로 수집")
        links = await _collect_fmkorea_links(page, max_count, date_from, date_to)
    elif "clien.net" in current_url:
        print("[크롤링] 클리앙 모드로 수집")
        links = await _collect_clien_links(page, max_count, date_from, date_to)
    elif "pann.nate.com" in current_url:
        print("[크롤링] 네이트판 모드로 수집")
        links = await _collect_pann_links(page, max_count, date_from, date_to)
    elif "search.naver.com" in current_url:
        print("[크롤링] 네이버 검색 모드로 수집")
        links = await _collect_naver_search_links(page, max_count, date_from, date_to)
    else:
        print("[크롤링] 범용 모드로 수집")
        links = await _collect_generic_links(page, max_count, date_from, date_to)
    
    # 수집 실패 시 로그만 출력
    if not links or len(links) == 0:
        print("[크롤링 실패] 게시글 링크를 찾지 못했습니다.")
        print(f"[크롤링 실패] URL: {current_url}")
        print("[크롤링 실패] 게시판 목록 페이지인지 확인하거나, 크롤링 URL 관리 탭에서 URL을 등록해주세요.")
    
    return links


async def _collect_naver_cafe_links(page: Page, max_count: int, date_from: str = "", date_to: str = "") -> list[dict]:
    """네이버 카페 전용 링크 수집"""
    links: list[dict] = []
    seen: set[str] = set()

    js = """() => {
        const res = [], seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
            if (!href || !text || text.length < 2 || seen.has(href)) return;
            
            // 댓글 수 텍스트 필터링 (예: "[10]", "댓글수 [3]", "10", "+99", "댓글 5")
            if (/^\\[?\\d+\\]?$/.test(text) || /^댓글/.test(text) || /^\\d+$/.test(text)) return;
            if (/^\\+\\d+$/.test(text) || /^\\(\\d+\\)$/.test(text)) return;
            // 숫자만으로 된 짧은 텍스트 (1~4자리) 필터링
            if (text.length <= 5 && /^[\\[\\(]?\\d{1,4}[\\]\\)]?$/.test(text)) return;
            
            const ok = href.includes('/articles/') ||
                       href.includes('articleid') ||
                       href.includes('ArticleRead') ||
                       /cafe\\.naver\\.com\\/[^\\/\\?#]+\\/\\d+/.test(href);
                       
            if (!ok) return;
            if (href.includes('/menus/') || href.includes('javascript:') || href.includes('#')) return;
            seen.add(href);

            const row = a.closest('tr') || a.closest('li') || a.closest('[class*="item"]');
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
                    const dateEl = row.querySelector('.date, .td_date, [class*="date"], time');
                    if (dateEl) dateText = dateEl.innerText.trim();
                }
            }
            res.push({url: href, title: text.substring(0,120), list_date: dateText});
        });
        return res;
    }"""

    for page_num in range(1, 50):
        _state["message"] = f"네이버 카페 {page_num}페이지 수집 중..."
        new_count = 0

        for frame in [page] + list(page.frames):
            try:
                batch = await frame.evaluate(js)
                for item in (batch or []):
                    u = item.get("url", "")
                    if not u or u in seen:
                        continue
                    seen.add(u)
                    item["list_date"] = _parse_date(item.get("list_date", ""))
                    links.append(item)
                    new_count += 1
                    if len(links) >= max_count:
                        break
            except Exception:
                pass

        if new_count == 0 or len(links) >= max_count:
            break

        went = await _goto_next_board_page(page, page_num)
        if not went:
            break
        await asyncio.sleep(2)

    return links[:max_count]


async def _collect_dcinside_links(page: Page, max_count: int, date_from: str = "", date_to: str = "") -> list[dict]:
    """디시인사이드 전용 링크 수집 (광고 필터링 포함)"""
    links: list[dict] = []
    seen: set[str] = set()
    
    # 현재 갤러리 ID 추출 (다른 갤러리 링크 필터링용)
    current_url = page.url
    gallery_id = ""
    import re as _re
    m = _re.search(r'[?&]id=([^&]+)', current_url)
    if m:
        gallery_id = m.group(1)

    js = """(galleryId) => {
        const res = [], seen = new Set();
        const adKeywords = ['광고', '협찬', '이벤트', '프로모션', 'AD', '제휴', '배너', '홍보'];
        
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
            if (!href || !text || text.length < 3 || seen.has(href)) return;
            
            // 광고 필터링
            if (adKeywords.some(kw => text.includes(kw))) return;
            
            if (!href.includes('/board/view/') && !href.includes('no=') && 
                !/gall\\.dcinside\\.com\\/board\\/view/.test(href)) return;
            if (href.includes('javascript:') || href.includes('#')) return;
            
            // 현재 갤러리 ID와 다른 갤러리 링크 제외
            if (galleryId) {
                const idMatch = href.match(/[?&]id=([^&]+)/);
                if (idMatch && idMatch[1] !== galleryId) return;
            }
            
            seen.add(href);

            const row = a.closest('tr') || a.closest('.ub-content') || a.closest('.gall_list') || a.closest('li');
            let dateText = '';
            if (row) {
                const dateSelectors = ['.gall_date', '.date', '.reply_date', '.time', '[class*="date"]', 'td'];
                for (const selector of dateSelectors) {
                    const dateEl = row.querySelector(selector);
                    if (dateEl && dateEl.innerText.trim().match(/\\d{2,4}[.\\/\\-]\\d{1,2}[.\\/\\-]\\d{1,2}/)) {
                        dateText = dateEl.innerText.trim();
                        break;
                    }
                }
            }
            
            res.push({url: href, title: text.substring(0,120), list_date: dateText});
        });
        return res;
    }"""

    for page_num in range(1, 10):
        _state["message"] = f"디시인사이드 {page_num}페이지 수집 중..."
        
        try:
            batch = await page.evaluate(js, gallery_id)
            new_count = 0
            print(f"[디시인사이드] 페이지 {page_num}에서 {len(batch or [])}개 링크 발견")
            
            for item in (batch or []):
                u = item.get("url", "")
                if not u or u in seen:
                    continue
                seen.add(u)
                item["list_date"] = _parse_date(item.get("list_date", ""))
                links.append(item)
                new_count += 1
                
                if len(links) >= max_count:
                    break
            
            if new_count == 0 or len(links) >= max_count:
                break
                
            next_clicked = await page.evaluate("""() => {
                const nextBtns = document.querySelectorAll('.next, .pg_next, [class*="next"], .btn_next');
                for (const btn of nextBtns) {
                    if (btn && !btn.classList.contains('disabled') && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
            
            if not next_clicked:
                break
                
            await asyncio.sleep(1.5)
            
        except Exception as e:
            print(f"[디시인사이드] 페이지 {page_num} 수집 오류: {e}")
            break

    print(f"[디시인사이드] 총 {len(links)}개 링크 수집 완료")
    return links[:max_count]


async def _collect_clien_links(page: Page, max_count: int, date_from: str = "", date_to: str = "") -> list[dict]:
    """클리앙 전용 링크 수집 (광고 필터링 포함)"""
    links: list[dict] = []
    seen: set[str] = set()

    # 클리앙 게시글 URL 패턴: /service/board/{게시판명}/{숫자}
    # 광고 배너 필터링: 제목에 광고 키워드 포함 시 제외
    js = """() => {
        const res = [], seen = new Set();
        const adKeywords = ['광고', '협찬', '이벤트', '프로모션', 'AD', '제휴', '배너'];
        
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
            if (!href || !text || text.length < 3 || seen.has(href)) return;
            if (href.includes('javascript:') || href.includes('#')) return;
            
            // 광고 필터링
            if (adKeywords.some(kw => text.includes(kw))) return;
            
            // 클리앙 게시글: /service/board/{게시판명}/{숫자} 형태만 허용
            if (!/\\/service\\/board\\/[^\\/]+\\/\\d+/.test(href)) return;
            
            seen.add(href);

            const row = a.closest('tr') || a.closest('li') || a.closest('.list_item') || a.closest('[class*="item"]');
            let dateText = '';
            if (row) {
                for (const sel of ['.timestamp', '.time', '[class*="date"]', 'td']) {
                    const el = row.querySelector(sel);
                    if (el && el.innerText.trim().match(/\\d{2,4}[.\\/\\-]\\d{1,2}[.\\/\\-]\\d{1,2}/)) {
                        dateText = el.innerText.trim();
                        break;
                    }
                }
            }
            res.push({url: href, title: text.substring(0,120), list_date: dateText});
        });
        return res;
    }"""

    for page_num in range(1, 10):
        if _state.get("should_stop"):
            break
        _state["message"] = f"클리앙 {page_num}페이지 수집 중..."
        
        try:
            batch = await page.evaluate(js)
            new_count = 0
            print(f"[클리앙] 페이지 {page_num}에서 {len(batch or [])}개 링크 발견")
            
            for item in (batch or []):
                u = item.get("url", "")
                if not u or u in seen:
                    continue
                seen.add(u)
                item["list_date"] = _parse_date(item.get("list_date", ""))
                links.append(item)
                new_count += 1
                if len(links) >= max_count:
                    break
            
            if new_count == 0 or len(links) >= max_count:
                break
            
            # 클리앙 다음 페이지: URL에 ?po=N 파라미터 사용
            current_url = page.url
            if "?po=" in current_url:
                next_url = re.sub(r"po=\d+", f"po={page_num * 20}", current_url)
            else:
                sep = "&" if "?" in current_url else "?"
                next_url = f"{current_url}{sep}po={page_num * 20}"
            
            await page.goto(next_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)
            
        except Exception as e:
            print(f"[클리앙] 페이지 {page_num} 수집 오류: {e}")
            break

    print(f"[클리앙] 총 {len(links)}개 링크 수집 완료")
    return links[:max_count]


async def _collect_fmkorea_links(page: Page, max_count: int, date_from: str = "", date_to: str = "") -> list[dict]:
    """에펨코리아 전용 링크 수집"""
    links: list[dict] = []
    seen: set[str] = set()

    js = """() => {
        const res = [], seen = new Set();
        
        // 에펨코리아 게시글 링크 찾기
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
            if (!href || !text || text.length < 3 || seen.has(href)) return;
            
            // 에펨코리아 게시글 URL 패턴 (더 넓게)
            if (!/fmkorea\\.com\\/\\d+/.test(href) && !href.includes('document_srl=')) return;
            if (href.includes('javascript:') || href.includes('#')) return;
            
            seen.add(href);

            // 에펨코리아 날짜 추출
            const row = a.closest('tr') || a.closest('li') || a.closest('.hotdeal_var8') || a.closest('[class*="item"]');
            let dateText = '';
            if (row) {
                const dateSelectors = ['.regdate', '.date', '.time', '[class*="date"]', 'td'];
                for (const selector of dateSelectors) {
                    const dateEl = row.querySelector(selector);
                    if (dateEl && dateEl.innerText.trim().match(/\\d{2,4}[.\\/\\-]\\d{1,2}[.\\/\\-]\\d{1,2}/)) {
                        dateText = dateEl.innerText.trim();
                        break;
                    }
                }
            }
            
            res.push({url: href, title: text.substring(0,120), list_date: dateText});
        });
        console.log('[에펨코리아] 수집된 링크 수:', res.length);
        return res;
    }"""

    for page_num in range(1, 10):
        _state["message"] = f"에펨코리아 {page_num}페이지 수집 중..."
        
        try:
            batch = await page.evaluate(js)
            new_count = 0
            
            print(f"[에펨코리아] 페이지 {page_num}에서 {len(batch or [])}개 링크 발견")
            
            for item in (batch or []):
                u = item.get("url", "")
                if not u or u in seen:
                    continue
                seen.add(u)
                item["list_date"] = _parse_date(item.get("list_date", ""))
                links.append(item)
                new_count += 1
                
                if len(links) >= max_count:
                    break
            
            if new_count == 0 or len(links) >= max_count:
                break
                
            # 다음 페이지로 이동
            next_clicked = await page.evaluate("""() => {
                const nextBtns = document.querySelectorAll('.next, .pg_next, [title="다음"], .btn_next');
                for (const btn of nextBtns) {
                    if (btn && !btn.classList.contains('disabled') && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
            
            if not next_clicked:
                break
                
            await asyncio.sleep(1.5)
            
        except Exception as e:
            print(f"[에펨코리아] 페이지 {page_num} 수집 오류: {e}")
            break

    print(f"[에펨코리아] 총 {len(links)}개 링크 수집 완료")
    return links[:max_count]


async def _collect_pann_links(page: Page, max_count: int, date_from: str = "", date_to: str = "") -> list[dict]:
    """네이트판 전용 링크 수집기 (검색 결과 페이지 파싱)"""
    links: list[dict] = []
    seen: set[str] = set()

    # 네이트판 검색 결과 / 목록 페이지 파싱용 JS
    js = """() => {
        const res = [], seen = new Set();

        // 검색 결과 페이지 선택자 (search/total 페이지)
        const selectors = [
            '.search-result-list a',
            '.post-list a',
            '.pann-talk-list a',
            'ul.list-talk li a',
            '.talk-list a',
            'div.talk a',
            'a[href*="/talk/"]',
            'a[href*="/qna/"]',
            'a[href*="/news/"]',
            'a[href*="/knowhow/"]'
        ];

        for (const sel of selectors) {
            document.querySelectorAll(sel).forEach(a => {
                const href = a.href || '';
                const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
                if (!href || !text || text.length < 3 || seen.has(href)) return;
                if (href.includes('javascript:') || href.includes('#')) return;

                // 네이트판 게시글 URL 패턴 확인
                const isPannPost = /pann\\.nate\\.com\\/(talk|qna|news|knowhow|photo|vote)\\//.test(href)
                                || /pann\\.nate\\.com\\/[a-zA-Z]+\\/\\d+/.test(href);
                if (!isPannPost) return;

                seen.add(href);

                // 날짜 추출 시도
                const row = a.closest('li') || a.closest('.item') || a.closest('[class*="list"]') || a.closest('div');
                let dateText = '';
                if (row) {
                    const dateEl = row.querySelector('.date, .time, [class*="date"], [class*="time"], span.info');
                    if (dateEl) dateText = dateEl.innerText.trim();
                }

                res.push({ url: href, title: text.substring(0, 120), list_date: dateText });
            });
            if (res.length > 0) break;  // 하나의 selector에서 결과 나오면 중단
        }

        // 위 selector로 못 찾은 경우 — 숫자 ID 포함 pann.nate.com URL 전체 탐색
        if (res.length === 0) {
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
                if (!href || !text || text.length < 3 || seen.has(href)) return;
                if (!href.includes('pann.nate.com')) return;
                if (href.includes('javascript:') || href.includes('#')) return;
                if (!/\\d{5,}/.test(href)) return;  // 게시글 ID (5자리 이상 숫자)
                // 내비게이션, 검색, 로그인 링크 제외
                if (href.includes('/search') || href.includes('/login') ||
                    href.includes('/member') || href.includes('/mypage')) return;
                seen.add(href);
                res.push({ url: href, title: text.substring(0, 120), list_date: '' });
            });
        }

        console.log('[네이트판] 수집된 링크 수:', res.length);
        return res;
    }""";

    try:
        # 페이지 로딩 대기
        await asyncio.sleep(2)
        batch = await page.evaluate(js)
        print(f"[네이트판] {len(batch or [])}개 링크 발견")

        for item in (batch or []):
            u = item.get("url", "")
            if not u or u in seen:
                continue
            seen.add(u)
            item["list_date"] = _parse_date(item.get("list_date", ""))
            links.append(item)
            if len(links) >= max_count:
                break

        # 결과가 없으면 페이지 HTML 일부 출력 (디버깅용)
        if not links:
            current_url = page.url
            print(f"[네이트판] 링크 수집 실패. 현재 URL: {current_url}")
            page_title = await page.title()
            print(f"[네이트판] 페이지 제목: {page_title}")

    except Exception as e:
        print(f"[네이트판] 수집 오류: {e}")

    print(f"[네이트판] 총 {len(links)}개 링크 수집 완료")
    return links


# ── 네이버 검색 결과 수집 ────────────────────────────────────────────────────────
async def _collect_naver_search_links(page: Page, max_count: int,
                                       date_from: str = "", date_to: str = "") -> list[dict]:
    """네이버 통합검색(VIEW 탭) 결과에서 블로그/카페/뉴스 링크 수집"""
    links: list[dict] = []
    seen: set[str] = set()

    try:
        # VIEW 탭 결과 페이지에서 링크 수집
        for page_num in range(1, 20):
            if _state.get("should_stop"):
                break
            _state["message"] = f"네이버 검색 {page_num}페이지 수집 중..."

            await asyncio.sleep(random.uniform(2, 4))

            # 검색 결과에서 링크 추출
            js = """() => {
                const res = [], seen = new Set();
                // VIEW 탭 결과 항목
                document.querySelectorAll('.view_wrap a, .total_wrap a, .news_wrap a, .blog_wrap a, .cafe_wrap a, a.api_txt_lines, a.total_tit, a.news_tit, a[class*="title"]').forEach(a => {
                    const href = a.href || '';
                    const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ');
                    if (!href || !text || text.length < 5 || seen.has(href)) return;
                    // 네이버 내부 링크, 광고, 검색 관련 링크 제외
                    if (href.includes('search.naver.com') || href.includes('ad.search') ||
                        href.includes('javascript:') || href.includes('#') ||
                        href.includes('login.naver') || href.includes('help.naver')) return;
                    // 블로그, 카페, 뉴스, 포스트 등 콘텐츠 링크만
                    const ok = href.includes('blog.naver.com') || href.includes('cafe.naver.com') ||
                               href.includes('news.naver.com') || href.includes('post.naver.com') ||
                               href.includes('n.news.naver.com') || href.includes('view.asiae.co.kr') ||
                               href.includes('.co.kr/') || href.includes('.com/') ||
                               href.includes('tistory.com') || href.includes('brunch.co.kr');
                    if (!ok) return;
                    seen.add(href);
                    // 날짜 추출 시도
                    const parent = a.closest('.view_cont, .total_group, .news_group, [class*="item"]');
                    let dateText = '';
                    if (parent) {
                        const dateEl = parent.querySelector('.sub_time, .date, time, [class*="date"], [class*="time"], .sub_txt');
                        if (dateEl) dateText = dateEl.innerText.trim();
                    }
                    res.push({url: href, title: text.substring(0, 120), list_date: dateText});
                });
                return res;
            }"""

            batch = await page.evaluate(js)
            new_count = 0
            for item in (batch or []):
                u = item.get("url", "")
                if not u or u in seen:
                    continue
                seen.add(u)
                item["list_date"] = _parse_date(item.get("list_date", ""))
                links.append(item)
                new_count += 1
                if len(links) >= max_count:
                    break

            print(f"[네이버검색] {page_num}페이지: {new_count}개 신규 (총 {len(links)}개)")

            if new_count == 0 or len(links) >= max_count:
                break

            # 다음 페이지로 이동 (더보기 버튼 또는 페이지네이션)
            try:
                more_btn = await page.query_selector('a.btn_more, a.pg_next, a[class*="next"]')
                if more_btn:
                    await more_btn.click()
                    await asyncio.sleep(2)
                else:
                    # URL 기반 페이지네이션
                    current_url = page.url
                    if "&start=" in current_url:
                        next_start = 1 + page_num * 10
                        next_url = re.sub(r'&start=\d+', f'&start={next_start}', current_url)
                    else:
                        next_url = current_url + f"&start={1 + page_num * 10}"
                    await page.goto(next_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
            except Exception:
                break

    except Exception as e:
        print(f"[네이버검색] 수집 오류: {e}")

    print(f"[네이버검색] 총 {len(links)}개 링크 수집 완료")
    return links


async def _search_nate_pann_via_httpx(keyword: str, max_count: int = 30) -> list[dict]:
    """네이트판 검색을 httpx로 수행 (Playwright 차단 우회)

    네이트판 자체 검색은 봇 탐지가 강력하므로,
    네이트 검색엔진(search.daum.net/nate)을 경유하여
    site:pann.nate.com 필터로 네이트판 게시글만 검색합니다.
    """
    import httpx
    import ssl
    import re
    from urllib.parse import quote

    links: list[dict] = []
    seen: set[str] = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    # SSL 자체 서명 인증서 환경 대응
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    # 네이트 검색엔진 경유 (다음 검색 기반)
    search_query = f"site:pann.nate.com {keyword}"
    search_url = f"https://search.daum.net/nate?q={quote(search_query)}&w=tot"

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers=headers,
            verify=ssl_ctx,
        ) as client:
            resp = await client.get(search_url)
            html = resp.text

            if resp.status_code != 200:
                print(f"[네이트판httpx] 검색 실패: HTTP {resp.status_code}")
                return []

            # data-href + c-title 패턴으로 URL과 제목 동시 추출
            card_pattern = re.compile(
                r'data-href="(https?://pann\.nate\.com/(?:talk|qna|news|knowhow|photo|vote)/\d+)"[^>]*>.*?<c-title[^>]*>(.*?)</c-title>',
                re.DOTALL
            )
            card_matches = card_pattern.findall(html)

            for url, raw_title in card_matches:
                if url in seen:
                    continue
                seen.add(url)
                # HTML 태그 및 엔티티 정리
                title = re.sub(r'<[^>]+>', '', raw_title).strip()
                title = title.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
                # " | 네이트 판" 접미사 제거
                title = re.sub(r'\s*\|\s*네이트\s*판\s*$', '', title)
                links.append({"url": url, "title": title})
                if len(links) >= max_count:
                    break

            # c-title 패턴 실패 시 URL만이라도 추출
            if not links:
                url_pattern = re.compile(
                    r'https?://pann\.nate\.com/(?:talk|qna|news|knowhow|photo|vote)/\d+'
                )
                for url in url_pattern.findall(html):
                    if url in seen:
                        continue
                    seen.add(url)
                    links.append({"url": url, "title": ""})
                    if len(links) >= max_count:
                        break

            print(f"[네이트판httpx] '{keyword}' 검색: {len(links)}개 링크 발견")

    except Exception as e:
        print(f"[네이트판httpx] 검색 오류: {e}")

    return links



async def _collect_generic_links(page: Page, max_count: int, date_from: str = "", date_to: str = "") -> list[dict]:
    """범용 링크 수집기 (기타 사이트)"""
    links: list[dict] = []
    
    js = """() => {
        const res = [], seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
            if (!href || !text || text.length < 5 || seen.has(href)) return;
            
            if (href.includes('javascript:') || href.includes('#') || 
                href.includes('login') || href.includes('register') ||
                text.length > 100) return;
                
            // 숫자가 포함된 URL (게시글 ID 가능성)
            if (/\\d{3,}/.test(href)) {
                seen.add(href);
                res.push({url: href, title: text.substring(0,120), list_date: ''});
            }
        });
        
        console.log('[범용] 수집된 링크 수:', res.length);
        return res.slice(0, 100);
    }"""
    
    try:
        batch = await page.evaluate(js)
        print(f"[범용] {len(batch or [])}개 링크 발견")
        
        for item in (batch or []):
            links.append(item)
            if len(links) >= max_count:
                break
    except Exception as e:
        print(f"[범용] 수집 오류: {e}")
    
    print(f"[범용] 총 {len(links)}개 링크 수집 완료")
    return links


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


# ── httpx 경량 본문 수집 (로그인 불필요 사이트용) ─────────────────────────────
_HTTPX_SITES = ("dcinside.com", "fmkorea.com", "clien.net")
_HTTPX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

async def _scrape_article_httpx(info: dict) -> dict | None:
    """httpx로 본문 수집 (Playwright 없이 빠르게)"""
    import httpx
    url = info["url"]
    try:
        async with httpx.AsyncClient(headers=_HTTPX_HEADERS, follow_redirects=True, timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            html = resp.text

        # HTML 파싱 (정규식 기반 경량 추출)
        # 제목
        title_m = re.search(r'<title[^>]*>([^<]+)</title>', html)
        title = title_m.group(1).strip() if title_m else info.get("title", "제목 없음")
        # 불필요한 접미사 제거
        for suffix in [" - 디시인사이드", " - 에펨코리아", " :: 클리앙"]:
            title = title.replace(suffix, "")

        # 본문 추출 (사이트별 셀렉터)
        content = ""
        # 디시인사이드
        body_m = re.search(r'<div class="write_div"[^>]*>(.*?)</div>\s*(?:<div class="btn|<div id="dcfoot)', html, re.DOTALL)
        if not body_m:
            # 에펨코리아
            body_m = re.search(r'<div class="xe_content"[^>]*>(.*?)</div>\s*(?:<div class="document|<footer)', html, re.DOTALL)
        if not body_m:
            # 클리앙
            body_m = re.search(r'<div class="post_article"[^>]*>(.*?)</div>\s*(?:<div class="post_|<section)', html, re.DOTALL)
        if body_m:
            raw = body_m.group(1)
            # HTML 태그 제거
            content = re.sub(r'<[^>]+>', ' ', raw)
            content = re.sub(r'\s+', ' ', content).strip()
            content = content[:5000]

        if not content:
            return None  # httpx로 본문 추출 실패 → Playwright 폴백

        # 날짜
        date = ""
        date_m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', html[:3000])
        if date_m:
            date = f"{date_m.group(1)}-{date_m.group(2).zfill(2)}-{date_m.group(3).zfill(2)}"

        # 작성자
        author = ""
        author_m = re.search(r'class="(?:nick|writer|author|user_info)[^"]*"[^>]*>([^<]+)', html[:3000])
        if author_m:
            author = author_m.group(1).strip()

        return {
            "title": title or "제목 없음",
            "content": content,
            "comments": [],
            "post_date": date,
            "author": author,
            "view_count": 0,
            "comment_count": 0,
            "category": "일반",
        }
    except Exception as e:
        print(f"[httpx] 수집 실패 ({url[:60]}): {e}")
        return None


# ── 개별 게시글 수집 ─────────────────────────────────────────────────────────────
async def _scrape_article(page: Page, info: dict) -> dict | None:
    url = info["url"]

    # ── 로그인 불필요 사이트는 httpx로 빠르게 시도 ──
    if any(site in url for site in _HTTPX_SITES):
        result = await _scrape_article_httpx(info)
        if result:
            return result
        # httpx 실패 시 Firecrawl 폴백 시도
        try:
            import firecrawl_scraper
            if firecrawl_scraper.is_available():
                fc_result = firecrawl_scraper.scrape_url(url)
                if fc_result:
                    print(f"[Firecrawl 폴백 성공] {url[:60]}")
                    return fc_result
        except Exception:
            pass
        # Firecrawl도 실패 시 Playwright 폴백
        print(f"[httpx→Playwright 폴백] {url[:60]}")
    
    # ── 네이버 카페 URL에서 만료되는 JWT 토큰 파라미터 제거 ──
    # art= 파라미터는 시간 제한이 있어 만료 시 로그인 페이지로 리다이렉트됨
    # 쿠키 기반 인증만으로 접근 가능하도록 정규화
    if "cafe.naver.com" in url and "art=" in url:
        cleaned = re.sub(r'[&?]art=[^&]*', '', url)
        # 첫 번째 파라미터가 제거되어 &로 시작하는 경우 수정
        cleaned = re.sub(r'\?&', '?', cleaned)
        # 끝에 ? 또는 & 만 남은 경우 제거
        cleaned = cleaned.rstrip('?&')
        if cleaned != url:
            print(f"[URL정규화] JWT 토큰 제거: {url[:80]}... → {cleaned[:80]}...")
            url = cleaned
    
    art = None
    try:
        # 수집 중단 체크 — new_page 열기 전
        if _state.get("should_stop"):
            return None

        art = await page.context.new_page()

        # 수집 중단 체크 — goto 전
        if _state.get("should_stop"):
            return None

        await art.goto(url, wait_until="domcontentloaded", timeout=25000)

        # 수집 중단 체크 — 대기 전
        if _state.get("should_stop"):
            return None

        # 네이버 카페는 iframe 로딩 대기 필요 (SPA라 로딩이 느림)
        if "cafe.naver.com" in url:
            # networkidle: 모든 네트워크 요청 완료 후 iframe이 생성될 때까지 대기
            # CI headless 환경에서 SPA 초기화가 느릴 수 있어 충분한 시간 확보
            try:
                await art.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(2)
        else:
            await asyncio.sleep(0.5)

        # ── 로그인 화면 감지 (네이버 카페 세션 만료 대응)
        if "cafe.naver.com" in url:
            page_content = await art.content()
            login_indicators = ["nid.naver.com/nidlogin", "로그인해 주세요", "로그인이 필요합니다", "nidlogin.login"]
            matched = [ind for ind in login_indicators if ind in page_content]
            if matched:
                # 오탐 방지: 실제 로그인 폼이 있는지 추가 확인
                # SPA 페이지의 JS 번들에 nidlogin URL이 포함될 수 있으므로
                # 실제 로그인 입력 폼이나 리다이렉트 여부로 재확인
                actual_login_page = False
                
                # 방법1: 현재 URL이 로그인 페이지인지
                current_url = art.url
                if "nid.naver.com" in current_url or "nidlogin" in current_url:
                    actual_login_page = True
                
                # 방법2: 로그인 입력 폼이 실제로 존재하는지
                if not actual_login_page:
                    login_form = await art.query_selector("input#id, input[name='id'], form#frmNIDLogin, .login_form")
                    if login_form:
                        actual_login_page = True
                
                # 방법3: 페이지 본문 텍스트(JS 제외)에 로그인 요구 문구가 있는지
                if not actual_login_page:
                    try:
                        body_text = await art.evaluate("() => document.body ? document.body.innerText : ''")
                        if any(ind in body_text for ind in ["로그인해 주세요", "로그인이 필요합니다"]):
                            actual_login_page = True
                    except Exception:
                        pass
                
                if actual_login_page:
                    print(f"[로그인감지] 실제 로그인 페이지 확인 (매칭: {matched}) — 세션 쿠키 재주입 후 재시도")
                    await art.close()
                    art = None

                    # 저장된 세션 쿠키를 context에 다시 주입하여 세션 갱신
                    if SESSION_FILE.exists():
                        try:
                            saved_cookies = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                            await page.context.add_cookies(saved_cookies)
                            print(f"[로그인감지] 세션 쿠키 {len(saved_cookies)}개 재주입 완료")
                        except Exception as e:
                            print(f"[로그인감지] 세션 쿠키 재주입 실패: {e}")

                    # 최대 2회 재시도 (쿠키 재주입 후)
                    for retry in range(2):
                        await asyncio.sleep(random.uniform(3, 5))
                        art = await page.context.new_page()
                        await art.goto(url, wait_until="domcontentloaded", timeout=25000)
                        await asyncio.sleep(3)
                        page_content_retry = await art.content()
                        if not any(ind in page_content_retry for ind in login_indicators):
                            print(f"[로그인감지] 재시도 {retry+1}회차 성공")
                            break
                        print(f"[로그인감지] 재시도 {retry+1}회차에도 로그인 필요")
                        await art.close()
                        art = None
                    else:
                        # 모든 재시도 실패
                        print(f"[로그인감지] 재시도 모두 실패 — 게시글 스킵: {url[:60]}")
                        return {"_fail_reason": "로그인 필요 (세션 만료)"}
                else:
                    print(f"[로그인감지] HTML에 로그인 문자열 포함되었으나 실제 로그인 페이지 아님 (오탐 무시) — 정상 진행")

        # ── 콘텐츠 프레임 탐색 (네이버 카페는 iframe, 그 외는 메인 프레임)
        target = art
        if "cafe.naver.com" in url:
            for frame in art.frames:
                if frame == art.main_frame:
                    continue
                fu = frame.url
                if ("f-e/cafes" in fu or "ca-fe/cafes" in fu or
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
        frame_urls = [f.url[:70] for f in art.frames]
        found_iframe = target != art
        print(f"[프레임] target={'iframe' if found_iframe else 'main'} | frames({len(frame_urls)}): {frame_urls}")
        if not found_iframe and "cafe.naver.com" in url:
            print(f"[프레임] [경고] ca-fe iframe 없음 — main frame 직접 시도: {url[:70]}")

        # ── 제목
        title = await _text(target, [
            ".title_text", "h3[class*='title']",
            "h3.title", ".tit-box em", ".article_title",
            ".ucc-title", ".article-head h3",
        ]) or info.get("title", "제목 없음")
        
        # 제목 끝에 붙은 댓글 수 제거 (예: "제목 [3]", "제목 (5)")
        if title:
            title = re.sub(r'\s*[\[\(]\d+[\]\)]\s*$', '', title).strip()
            # 제목이 숫자만인 경우 원래 info 제목 사용
            if re.match(r'^[\[\(]?\d+[\]\)]?$', title):
                title = info.get("title", "제목 없음")

        # ── 본문
        content = await _extract_body(target)

        # ── 네이버 카페 본문 비어있을 때 iframe 재탐색 (최대 2회)
        if "cafe.naver.com" in url and (not content or len(content) <= 10):
            for retry_body in range(2):
                print(f"[본문재시도] {retry_body+1}회차 — iframe 재탐색 ({url[:60]})")
                await asyncio.sleep(2)
                # iframe 다시 탐색
                target = art
                for frame in art.frames:
                    if frame == art.main_frame:
                        continue
                    fu = frame.url
                    if ("f-e/cafes" in fu or "ca-fe/cafes" in fu or
                        "ArticleRead" in fu or
                        ("cafe.naver.com" in fu and "articleid" in fu)):
                        target = frame
                        try:
                            await target.wait_for_selector(
                                ".se-main-container, #tbody, .article_body, .CafeViewer, .view_content",
                                timeout=8000,
                            )
                        except Exception:
                            await asyncio.sleep(1)
                        break
                content = await _extract_body(target)
                if content and len(content) > 10:
                    print(f"[본문재시도] {retry_body+1}회차 성공 ({len(content)}자)")
                    break

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
            return {"_fail_reason": "제목/본문 없음 (페이지 로딩 실패 또는 삭제된 게시글)"}

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
        return {"_fail_reason": f"수집 오류: {str(e)[:50]}"}
    finally:
        if art:
            try: await art.close()
            except: pass


async def _extract_body(target) -> str:
    """SmartEditor 2/3, 클리앙, 디시인사이드, 에펨코리아 등 본문 추출"""
    selectors = [
        ".se-main-container",   # SmartEditor 3 (네이버)
        "#tbody",               # SmartEditor 2 (네이버)
        ".article_body",
        ".content_wrap",
        ".CafeViewer",
        ".article-content",
        "div#content",
        ".view_content",
        # 클리앙
        ".post_content",
        ".post-content",
        "div.view",
        # 디시인사이드
        ".write_div",
        ".gallview_contents",
        # 에펨코리아
        ".rd_body",
        ".xe_content",
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
                'div#content','.view_content',
                '.post_content','.post-content','div.view',
                '.write_div','.gallview_contents',
                '.rd_body','.xe_content'
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
    import database as db
    
    enhanced = post.copy()
    
    # 기본 정보
    enhanced["monitoring_name"] = monitoring_name
    enhanced["keywords"] = search_keyword
    
    # 날짜 분석 - database.py의 calculate_week_info 함수 사용
    post_date = post.get("post_date", "")
    if post_date:
        enhanced["week_info"] = db.calculate_week_info(post_date)
    else:
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
    """외식업 특화 감성 분석"""
    
    # 외식업 특화 강한 부정 키워드
    strong_negative = [
        "미친", "최악", "ㅅㅂ", "개같", "돈뜯어", "사기", "망했", "짜증", "화나", "열받",
        # 외식업 특화 추가
        "망한다", "적자", "폐업", "문닫", "억울", "부당", "과도"
    ]
    
    # 외식업 특화 일반 부정 키워드  
    negative = [
        "불만", "문제", "싫어", "안됨", "못하", "어려", "힘들", "걱정", "우려", "반대",
        # 외식업 특화 추가
        "부담", "비싸", "올라", "인상", "손해", "어렵다", "힘들다", "밀려", "뒤처져"
    ]
    
    # 외식업 특화 긍정 키워드
    positive = [
        "좋아", "최고", "감사", "만족", "훌륭", "완벽", "추천", "괜찮", "편리", "도움",
        # 외식업 특화 추가
        "수익", "흑자", "성공", "개선", "발전", "효과", "합리적", "공정", "지원"
    ]
    
    # 외식업 특화 강한 긍정 키워드
    strong_positive = [
        "대박", "완전좋", "최고", "감동", "완벽",
        # 외식업 특화 추가
        "대성공", "완전만족", "최고의선택"
    ]
    
    # 중립/정보성 키워드
    neutral_info = [
        "알려드", "공지", "안내", "정보", "확인", "문의", "질문", "궁금"
    ]
    
    # 외식업자 발언 가중치 확인
    is_business_owner = any(word in text for word in ["우리가게", "저희매장", "장사", "업주", "사장"])
    
    # 감성 판단
    if any(word in text for word in strong_negative):
        return "매우부정" if is_business_owner else "부정"
    elif any(word in text for word in strong_positive):
        return "긍정"
    elif any(word in text for word in negative):
        # 업주 발언은 더 민감하게
        return "부정" if is_business_owner else "부정"
    elif any(word in text for word in positive):
        return "긍정"
    elif any(word in text for word in neutral_info):
        return "중립"
    else:
        return "중립"


def _calculate_risk_level(sentiment: str, text: str) -> int:
    """외식업 특화 위험도 자동 계산 (0: 낮음, 1: 보통, 2: 높음, 3: 매우높음)"""
    
    # 매우 높은 위험도 키워드 (외식업 특화)
    critical_risk = [
        "파업", "시위", "고발", "신고", "소송", "집단행동", "보이콧", "망한다", "폐업", "문닫"
    ]
    
    # 높은 위험도 키워드 (외식업 특화)
    high_risk = [
        "미친", "최악", "ㅅㅂ", "돈뜯어", "사기", "망했", "적자", "손해", "억울", "부당",
        "수수료인상", "과도한", "경쟁력상실", "매출급감"
    ]
    
    # 중간 위험도 키워드 (외식업 특화)
    medium_risk = [
        "불만", "문제", "어려", "힘들", "부담", "비싸", "올라", "걱정", "우려"
    ]
    
    # 감성별 기본 위험도
    if sentiment == "매우부정":
        base_risk = 2
    elif sentiment == "부정":
        base_risk = 1
    elif sentiment == "긍정":
        return 0
    else:  # 중립
        return 0
    
    # 키워드 기반 위험도 조정
    if any(word in text for word in critical_risk):
        return 3  # 매우 높음
    elif any(word in text for word in high_risk):
        return max(base_risk, 2)  # 높음
    elif any(word in text for word in medium_risk):
        return max(base_risk, 1)  # 보통
    else:
        return base_risk


def _classify_subject_type(author: str, text: str, site_name: str) -> str:
    """외식업 특화 주체 구분 자동 분류"""
    author_lower = author.lower()
    
    # 외식업 자영업자 키워드 (세분화)
    if any(word in author_lower for word in ["사장", "업주", "점주", "ceo", "대표"]) or \
       any(word in text for word in ["우리가게", "우리매장", "저희가게", "저희업소", "장사", "매출", "손님들", "가게운영", "자영업"]):
        # 추가 세분화
        if any(word in text for word in ["프랜차이즈", "가맹점", "본사"]):
            return "가맹점주"
        elif any(word in text for word in ["개인", "소상공인", "1인"]):
            return "개인자영업자"
        else:
            return "외식업자영업자"
    
    # 배달 라이더 키워드
    elif any(word in author_lower for word in ["라이더", "배달", "기사", "드라이버"]) or \
         any(word in text for word in ["배달하", "콜량", "배차", "픽업", "드롭", "배달일", "라이더일"]):
        return "배달라이더"
    
    # 배달앱 직원/관계자
    elif any(word in text for word in ["배민직원", "쿠팡직원", "요기요직원", "고객센터", "cs"]):
        return "플랫폼관계자"
    
    # 기자/언론
    elif any(word in text for word in ["기자", "뉴스", "보도", "취재"]) or "기자" in author_lower:
        return "언론관계자"
    
    # 배달 전문 업체
    elif any(word in text for word in ["배달전문", "배달만", "포장전문"]):
        return "배달전문업체"
    
    # 기본값은 일반소비자
    else:
        return "일반소비자"


def _classify_service_type(text: str, search_keyword: str) -> str:
    """외식업 특화 배달앱 서비스 구분 자동 분류"""
    # 검색 키워드 우선 확인
    keyword_lower = search_keyword.lower()
    if "쿠팡" in keyword_lower:
        return "쿠팡이츠"
    elif "요기요" in keyword_lower:
        return "요기요"
    elif "배민" in keyword_lower or "배달의민족" in keyword_lower:
        return "배달의민족"
    
    # 텍스트 내용 정밀 분석
    text_lower = text.lower()
    
    # 쿠팡이츠 관련
    if any(word in text_lower for word in ["쿠팡이츠", "쿠팡 이츠", "쿠팡배달", "쿠팡"]):
        return "쿠팡이츠"
    
    # 요기요 관련
    elif any(word in text_lower for word in ["요기요", "yogiyo"]):
        return "요기요"
    
    # 배달의민족 관련 (다양한 표현)
    elif any(word in text_lower for word in ["배달의민족", "배민", "baemin", "우아한형제들"]):
        return "배달의민족"
    
    # 기타 배달앱들
    elif any(word in text_lower for word in ["땡겨요", "딜리버리히어로"]):
        return "기타배달앱"
    
    # 여러 앱 언급 시
    elif len([app for app in ["쿠팡", "요기요", "배민"] if app in text_lower]) > 1:
        return "다중플랫폼"
    
    # 기본값 (외식업 모니터링이므로 배민이 기본)
    else:
        return "배달의민족"


def _classify_channel_type(site_name: str, url: str) -> str:
    """채널 구분 자동 분류"""
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
    """외식업 특화 리스크 분류 자동 분류"""
    if risk_level == 0:
        return "NO_RISK"
    
    # === 매출 직접 영향 리스크 ===
    if any(word in text for word in ["매출", "수익", "손해", "적자", "망한다", "폐업", "경영악화"]):
        return "REVENUE_IMPACT_RISK"
    
    # === 수수료 정책 리스크 ===
    elif any(word in text for word in ["수수료", "중개수수료", "광고비", "정산", "수익배분"]):
        if any(word in text for word in ["인상", "올라", "비싸", "부담", "과도"]):
            return "FEE_POLICY_RISK"
        else:
            return "FEE_RELATED_ISSUE"
    
    # === 경쟁 환경 변화 리스크 ===
    elif any(word in text for word in ["경쟁", "경쟁력", "밀려", "뒤처져", "시장점유율", "갈아타"]):
        return "COMPETITIVE_RISK"
    
    # === 컴플라이언스 리스크 (법적, 규제) ===
    elif any(word in text for word in ["파업", "노조", "시위", "고발", "신고", "법적", "소송", "규제"]):
        return "COMPLIANCE_RISK"
    
    # === 운영 서비스 리스크 ===
    elif any(word in text for word in ["배달", "라이더", "배차", "픽업", "콜량", "서비스품질"]):
        if subject_type == "배달라이더":
            return "OPERATIONAL_RISK"
        else:
            return "SERVICE_QUALITY_RISK"
    
    # === 플랫폼 정책 변화 리스크 ===
    elif any(word in text for word in ["정책", "변경", "업데이트", "새로운정책", "규정"]):
        return "PLATFORM_POLICY_RISK"
    
    # === 기술 시스템 리스크 ===
    elif any(word in text for word in ["앱", "시스템", "오류", "버그", "장애", "다운"]):
        return "TECHNICAL_RISK"
    
    # === 평판 리스크 ===
    elif any(word in text for word in ["언론", "기사", "뉴스", "보도", "이미지", "평판"]):
        return "REPUTATION_RISK"
    
    # === 기타 리스크 ===
    else:
        if risk_level >= 2:
            return "HIGH_RISK_UNCLASSIFIED"
        else:
            return "GENERAL_RISK"


def _classify_business_category(text: str, subject_type: str, sentiment: str) -> tuple:
    """외식업 특화 비즈니스 분류 체계 자동 분류 (대분류, 중분류, 소분류)"""
    
    # === 수수료 및 정산 이슈 (외식업 핵심) ===
    if any(word in text for word in ["수수료", "중개수수료", "광고비", "정산", "수익배분", "마케팅비"]):
        if any(word in text for word in ["인상", "올라", "비싸", "부담"]):
            return ("수수료이슈", "수수료인상", "수수료부담")
        elif any(word in text for word in ["광고", "마케팅", "노출"]):
            return ("수수료이슈", "광고비용", "광고정책")
        elif any(word in text for word in ["정산", "입금", "지연"]):
            return ("수수료이슈", "정산문제", "정산지연")
        else:
            return ("수수료이슈", "수수료정책", "수수료일반")
    
    # === 배달앱 정책 변화 ===
    elif any(word in text for word in ["정책", "변경", "업데이트", "새로운", "바뀐"]):
        if any(word in text for word in ["최소주문", "주문금액"]):
            return ("정책변화", "주문정책", "최소주문금액")
        elif any(word in text for word in ["배달료", "배달팁", "배송비"]):
            return ("정책변화", "배달정책", "배달료정책")
        elif any(word in text for word in ["할인", "쿠폰", "프로모션"]):
            return ("정책변화", "프로모션정책", "할인정책")
        else:
            return ("정책변화", "일반정책", "정책변경")
    
    # === 매출 및 경영 영향 ===
    elif any(word in text for word in ["매출", "수익", "손해", "적자", "흑자", "경영"]):
        if sentiment == "부정":
            return ("매출영향", "매출감소", "경영악화")
        elif sentiment == "긍정":
            return ("매출영향", "매출증가", "경영개선")
        else:
            return ("매출영향", "매출변화", "경영일반")
    
    # === 경쟁 및 플랫폼 비교 ===
    elif any(word in text for word in ["경쟁", "비교", "vs", "대비", "갈아타", "이동", "바꿔"]):
        return ("경쟁분석", "플랫폼비교", "플랫폼이동")
    
    # === 라이더 및 배달 서비스 ===
    elif any(word in text for word in ["라이더", "배달원", "배차", "픽업", "콜량", "배달시간"]):
        if subject_type == "배달라이더":
            return ("배달서비스", "라이더이슈", "라이더정책")
        elif any(word in text for word in ["늦어", "지연", "문제"]):
            return ("배달서비스", "배달지연", "서비스품질")
        else:
            return ("배달서비스", "배달일반", "배달경험")
    
    # === 고객 서비스 및 앱 이용 ===
    elif any(word in text for word in ["앱", "시스템", "오류", "버그", "업데이트", "고객센터"]):
        if any(word in text for word in ["오류", "버그", "문제", "안돼"]):
            return ("고객서비스", "앱오류", "기술문제")
        elif any(word in text for word in ["고객센터", "cs", "문의", "신고"]):
            return ("고객서비스", "고객지원", "CS문제")
        else:
            return ("고객서비스", "앱이용", "사용경험")
    
    # === 프로모션 및 마케팅 ===
    elif any(word in text for word in ["할인", "쿠폰", "이벤트", "프로모션", "혜택", "적립"]):
        return ("프로모션", "할인이벤트", "고객혜택")
    
    # === 중대 이슈 (파업, 사건사고) ===
    elif any(word in text for word in ["파업", "노조", "시위", "사고", "사건"]):
        if any(word in text for word in ["파업", "노조", "시위"]):
            return ("중대이슈", "노무이슈", "파업시위")
        else:
            return ("중대이슈", "사건사고", "안전문제")
    
    # === 기본 분류 (외식업 일반) ===
    else:
        if subject_type in ["외식업자영업자", "가맹점주", "개인자영업자"]:
            return ("외식업일반", "업주경험", "일반의견")
        elif subject_type == "일반소비자":
            return ("외식업일반", "소비자경험", "주문경험")
        else:
            return ("외식업일반", "기타의견", "일반")


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


# ── 세션 파일 관리 ──────────────────────────────────────────────────────────────


def has_saved_session() -> bool:
    """저장된 세션 파일이 존재하는지 확인"""
    return SESSION_FILE.exists()


# ── 세션 저장 ───────────────────────────────────────────────────────────────────
async def save_session():
    """현재 브라우저 쿠키를 JSON 파일로 저장"""
    if not _state["browser"] or not _state["context"]:
        return {"success": False, "message": "브라우저가 열려있지 않습니다."}
    
    try:
        if _state["page"] and _state["page"].is_closed():
            return {"success": False, "message": "페이지가 닫혔습니다. 브라우저를 다시 열어주세요."}
        
        cookies = await _state["context"].cookies()
        if not cookies:
            return {"success": False, "message": "저장할 쿠키가 없습니다. 먼저 로그인해주세요."}
        
        # 쿠키를 JSON 파일로 저장
        SESSION_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True, 
            "message": f"세션이 저장되었습니다. (쿠키 {len(cookies)}개) 다음부터 백그라운드 수집이 가능합니다.",
            "cookies_count": len(cookies)
        }
        
    except Exception as e:
        return {"success": False, "message": f"세션 저장 실패: {str(e)}"}


async def _cleanup():
    for key in ("page", "context", "browser", "pw"):
        obj = _state.get(key)
        if obj:
            try:
                await (obj.stop() if key == "pw" else obj.close())
            except Exception:
                pass
            _state[key] = None
