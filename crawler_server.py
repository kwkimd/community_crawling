#!/usr/bin/env python3
"""
크롤러 전용 서버 (로컬 실행용)
- 브라우저 제어 및 데이터 수집
- 로컬 DB 저장
- 구글 시트 자동 업로드
"""
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

import database as db
import scraper

app = FastAPI(title="아프니까사장이다 크롤러")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db()


# ── 페이지 ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("crawler.html", {
        "request": request,
        "cafe_url": scraper.CAFE_URL,
        "board_url": scraper.BOARD_URL,
    })


# ── 크롤링 API ──────────────────────────────────────────────────────────────────

@app.post("/api/scrape/open")
async def scrape_open():
    """브라우저를 열고 카페로 이동"""
    try:
        await scraper.open_browser(scraper.CAFE_URL)
        return {"success": True, "message": scraper.get_status()["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scrape/goto")
async def scrape_goto(request: Request):
    """열린 브라우저에서 특정 URL로 이동"""
    body = await request.json()
    url = body.get("url", scraper.BOARD_URL)
    page = scraper._state.get("page")
    if not page:
        raise HTTPException(status_code=400, detail="브라우저가 열려있지 않습니다.")
    try:
        await page.goto(url, wait_until="domcontentloaded")
        return {"success": True, "message": f"이동 완료: {url}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scrape/start")
async def scrape_start(request: Request):
    """현재 브라우저에서 게시글 수집 시작"""
    body = await request.json()
    max_posts = int(body.get("max_posts") or 0)
    category = body.get("category", "")
    date_from = body.get("date_from", "")
    date_to = body.get("date_to", "")
    board_url = body.get("board_url", "")
    cafe_name = body.get("cafe_name", "")
    monitoring_name = body.get("monitoring_name", "")
    search_keyword = body.get("search_keyword", "")
    
    try:
        await scraper.start_scraping(
            max_posts=max_posts, category=category,
            date_from=date_from, date_to=date_to,
            board_url=board_url, cafe_name=cafe_name,
            monitoring_name=monitoring_name, 
            search_keyword=search_keyword
        )
        return {"success": True, "message": "수집을 시작했습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scrape/status")
async def scrape_status():
    """현재 수집 상태 조회"""
    return scraper.get_status()


@app.post("/api/scrape/close")
async def scrape_close():
    """브라우저 닫기"""
    await scraper.close_browser()
    return {"success": True, "message": "브라우저를 닫았습니다."}


# ── 직접 입력 API ──────────────────────────────────────────────────────────────

@app.post("/api/posts")
async def create_post(
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form("일반"),
    post_date: str = Form(""),
    author: str = Form(""),
    view_count: int = Form(0),
    comment_count: int = Form(0),
):
    """직접 입력으로 게시글 추가"""
    post_id = db.create_post(
        title=title, content=content, category=category,
        post_date=post_date, author=author,
        view_count=view_count, comment_count=comment_count,
    )
    return {"success": True, "id": post_id, "message": "게시글이 저장되었습니다."}


# ── 헬스체크 ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "service": "crawler",
        "scraper_status": scraper.get_status()["status"]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("crawler_server:app", host="0.0.0.0", port=8001, reload=False)