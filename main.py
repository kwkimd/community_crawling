import asyncio
import io
from urllib.parse import quote
from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json
import xlwt

import database as db
import gemini_analyzer as gemini
import scraper
import csv_scraper

app = FastAPI(title="아프니까사장이다 분석 도구")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db()


# ── 페이지 ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = db.get_stats()
    categories = db.get_categories()
    recent = db.get_all_posts()[:5]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": stats,
        "categories": categories,
        "recent_posts": recent,
        "cafe_url": scraper.CAFE_URL,
        "board_url": scraper.BOARD_URL,
    })


# ── 게시글 API ─────────────────────────────────────────────────────────────────

@app.get("/api/posts")
async def list_posts(
    category: str = Query(None),
    keyword: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    cafe_name: str = Query(None),
):
    posts = db.get_all_posts(category=category, keyword=keyword,
                             date_from=date_from, date_to=date_to,
                             cafe_name=cafe_name)
    return {"posts": posts, "total": len(posts)}


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
    post_id = db.create_post(
        title=title, content=content, category=category,
        post_date=post_date, author=author,
        view_count=view_count, comment_count=comment_count,
    )
    return {"success": True, "id": post_id, "message": "게시글이 저장되었습니다."}


@app.get("/api/posts/export")
async def export_posts(
    date_from: str = Query(None),
    date_to: str = Query(None),
    category: str = Query(None),
    keyword: str = Query(None),
    cafe_name: str = Query(None),
):
    """게시글 Excel(.xls) 다운로드"""
    posts = db.get_all_posts(
        category=category, keyword=keyword,
        date_from=date_from, date_to=date_to,
        cafe_name=cafe_name,
    )

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("게시글")

    # 헤더 스타일
    header_style = xlwt.easyxf(
        "font: bold true; "
        "pattern: pattern solid, fore_colour light_blue; "
        "alignment: horizontal centre;"
    )
    # 본문 줄바꿈 스타일
    wrap_style = xlwt.easyxf("alignment: wrap true, vertical top;")
    normal_style = xlwt.easyxf("alignment: vertical top;")

    headers = ["번호", "년", "월", "일", "주차", "모니터링명", "위험도", "감성구분", 
               "주체구분", "서비스구분", "검색어", "제목", "내용", "리스크분류", 
               "분류_대분류", "분류_중분류", "분류_소분류", "사이트그룹", "사이트명", 
               "작성자명", "조회수", "댓글수", "등록일", "게시글URL", "본문", "댓글", 
               "요약", "컨텐츠키", "분석일시", "수집자"]
    col_widths = [6, 6, 6, 6, 12, 18, 8, 10, 10, 12, 12, 48, 80, 16, 16, 16, 16, 
                  14, 18, 14, 8, 8, 14, 50, 80, 60, 60, 20, 20, 10]

    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, header_style)
        ws.col(col).width = w * 256  # 1단위 = 1/256 문자폭

    for row, p in enumerate(posts, 1):
        # 댓글 JSON → "1. 댓글내용\n2. 댓글내용" 형식 텍스트
        try:
            comments_list = json.loads(p.get("comments", "[]") or "[]")
            comments_text = "\n".join(
                f"{i+1}. {c}" for i, c in enumerate(comments_list)
            ) if comments_list else ""
        except Exception:
            comments_text = ""

        # 날짜 파싱
        post_date = p.get("post_date", "") or ""
        year, month, day = "", "", ""
        if post_date:
            try:
                parts = post_date.split("-")
                if len(parts) == 3:
                    year, month, day = parts
            except:
                pass

        ws.write(row, 0,  p.get("id", ""),            normal_style)
        ws.write(row, 1,  year,                       normal_style)
        ws.write(row, 2,  month,                      normal_style)
        ws.write(row, 3,  day,                        normal_style)
        ws.write(row, 4,  p.get("week_info", "") or "", normal_style)
        ws.write(row, 5,  p.get("monitoring_name", "") or "", normal_style)
        ws.write(row, 6,  p.get("risk_level", 0) or 0, normal_style)
        ws.write(row, 7,  p.get("sentiment", "중립") or "중립", normal_style)
        ws.write(row, 8,  p.get("subject_type", "소비자") or "소비자", normal_style)
        ws.write(row, 9,  p.get("service_type", "배달의민족") or "배달의민족", normal_style)
        ws.write(row, 10, p.get("keywords", "") or "", normal_style)
        ws.write(row, 11, p.get("title", "") or "",    normal_style)
        ws.write(row, 12, p.get("content", "") or "",  wrap_style)
        ws.write(row, 13, p.get("risk_classification", "NO RISK") or "NO RISK", normal_style)
        ws.write(row, 14, p.get("main_category", "플랫폼 이용") or "플랫폼 이용", normal_style)
        ws.write(row, 15, p.get("sub_category", "주문") or "주문", normal_style)
        ws.write(row, 16, p.get("detail_category", "일반") or "일반", normal_style)
        ws.write(row, 17, p.get("site", "네이버") or "네이버", normal_style)
        ws.write(row, 18, p.get("cafe_name", "") or "", normal_style)
        ws.write(row, 19, p.get("author", "") or "",   normal_style)
        ws.write(row, 20, p.get("view_count", 0) or 0, normal_style)
        ws.write(row, 21, p.get("comment_count", 0) or 0, normal_style)
        ws.write(row, 22, post_date,                   normal_style)
        ws.write(row, 23, p.get("post_url", "") or "", normal_style)
        ws.write(row, 24, p.get("content", "") or "",  wrap_style)
        ws.write(row, 25, comments_text,               wrap_style)
        ws.write(row, 26, p.get("summary", "") or "",  wrap_style)
        ws.write(row, 27, p.get("content_key", "") or "", normal_style)
        ws.write(row, 28, p.get("analysis_datetime", "") or "", normal_style)
        ws.write(row, 29, p.get("collector", "SCA") or "SCA", normal_style)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # 파일명: 아프니까사장이다_20260301_20260308.xls
    parts = []
    if date_from:
        parts.append(date_from.replace("-", ""))
    if date_to:
        parts.append(date_to.replace("-", ""))
    suffix = "_".join(parts) if parts else "all"
    filename = f"아프니까사장이다_{suffix}.xls"

    return StreamingResponse(
        buf,
        media_type="application/vnd.ms-excel",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@app.get("/api/posts/{post_id}")
async def get_post(post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    return post


@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: int):
    ok = db.delete_post(post_id)
    if not ok:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    return {"success": True, "message": "삭제되었습니다."}


@app.get("/api/stats")
async def get_stats():
    return db.get_stats()


# ── 자동 수집 API ──────────────────────────────────────────────────────────────

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


@app.post("/api/scrape/csv/start")
async def scrape_csv_start(request: Request):
    """CSV 형식으로 데이터 수집 시작"""
    body = await request.json()
    max_posts = int(body.get("max_posts") or 0)
    monitoring_name = body.get("monitoring_name", "1인분(한그릇)")
    search_keyword = body.get("search_keyword", "배민")
    date_from = body.get("date_from", "")
    date_to = body.get("date_to", "")
    board_url = body.get("board_url", "")
    output_file = body.get("output_file", "")
    
    try:
        await csv_scraper.start_csv_scraping(
            max_posts=max_posts,
            monitoring_name=monitoring_name,
            search_keyword=search_keyword,
            date_from=date_from,
            date_to=date_to,
            board_url=board_url,
            output_file=output_file
        )
        return {"success": True, "message": "CSV 수집을 시작했습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scrape/csv/status")
async def scrape_csv_status():
    """CSV 수집 상태 조회"""
    return csv_scraper.get_status()


@app.post("/api/scrape/csv/open")
async def scrape_csv_open():
    """CSV 수집용 브라우저 열기"""
    try:
        await csv_scraper.open_browser(csv_scraper.CAFE_URL)
        return {"success": True, "message": csv_scraper.get_status()["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scrape/csv/close")
async def scrape_csv_close():
    """CSV 수집용 브라우저 닫기"""
    await csv_scraper.close_browser()
    return {"success": True, "message": "브라우저를 닫았습니다."}


@app.post("/api/scrape/start")
async def scrape_start(request: Request):
    """현재 브라우저에서 게시글 수집 시작"""
    body = await request.json()
    max_posts = int(body.get("max_posts") or 0)  # 0 = 제한 없음
    category = body.get("category", "")
    date_from = body.get("date_from", "")
    date_to = body.get("date_to", "")
    board_url = body.get("board_url", "")
    cafe_name = body.get("cafe_name", "")
    # CSV 구조 추가 파라미터
    monitoring_name = body.get("monitoring_name", "")
    search_keyword = body.get("search_keyword", "")
    
    try:
        await scraper.start_scraping(max_posts=max_posts, category=category,
                                     date_from=date_from, date_to=date_to,
                                     board_url=board_url, cafe_name=cafe_name,
                                     monitoring_name=monitoring_name, 
                                     search_keyword=search_keyword)
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


# ── 분석 API ───────────────────────────────────────────────────────────────────

@app.post("/api/analyze/comprehensive")
async def save_comprehensive_analysis(request: Request):
    """종합 분석 결과 저장"""
    body = await request.json()
    analyses = body.get("analyses", {})
    post_ids = body.get("post_ids", [])
    period = body.get("period", "all")
    post_count = body.get("post_count", 0)
    
    # 종합 분석 결과 구조화
    comprehensive_result = {
        "sentiment": analyses.get("sentiment", {}),
        "keywords": analyses.get("keywords", {}),
        "trends": analyses.get("trends", {}),
        "report": analyses.get("report", {}),
        "metadata": {
            "period": period,
            "post_count": post_count,
            "analysis_type": "comprehensive"
        }
    }
    
    analysis_id = db.save_analysis(
        analysis_type="comprehensive",
        post_ids=post_ids,
        result=json.dumps(comprehensive_result, ensure_ascii=False),
    )
    
    return {"success": True, "analysis_id": analysis_id, "message": "종합 분석 결과가 저장되었습니다."}


@app.get("/api/analyses/{analysis_id}")
async def get_analysis_by_id(analysis_id: int):
    """특정 분석 결과 조회"""
    analysis = db.get_analysis_by_id(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    
    try:
        result = json.loads(analysis["result"])
        return {
            "id": analysis["id"],
            "created_at": analysis["created_at"],
            "analysis_type": analysis["analysis_type"],
            "post_ids": json.loads(analysis["post_ids"]) if analysis["post_ids"] else [],
            "result": result,
            "post_count": result.get("metadata", {}).get("post_count", 0)
        }
    except Exception:
        raise HTTPException(status_code=500, detail="분석 결과 파싱 오류")


@app.post("/api/analyze")
async def analyze(request: Request):
    body = await request.json()
    analysis_type = body.get("type", "report")
    post_ids = body.get("post_ids", [])

    if post_ids:
        posts = [db.get_post(pid) for pid in post_ids]
        posts = [p for p in posts if p]
    else:
        posts = db.get_all_posts()

    if not posts:
        raise HTTPException(status_code=400, detail="분석할 게시글이 없습니다.")

    if analysis_type == "sentiment":
        result = gemini.analyze_sentiment(posts)
    elif analysis_type == "keywords":
        result = gemini.extract_keywords(posts)
    elif analysis_type == "trends":
        result = gemini.analyze_trends(posts)
    elif analysis_type == "report":
        result = gemini.generate_report(posts)
    else:
        raise HTTPException(status_code=400, detail="알 수 없는 분석 유형입니다.")

    if "error" in result:
        raise HTTPException(status_code=500, detail=f"Gemini 분석 오류: {result['error']}")

    db.save_analysis(
        analysis_type=analysis_type,
        post_ids=[p["id"] for p in posts],
        result=json.dumps(result, ensure_ascii=False),
    )

    return {"success": True, "type": analysis_type, "result": result, "post_count": len(posts)}


@app.get("/api/analyses")
async def list_analyses(limit: int = Query(10)):
    analyses = db.get_recent_analyses(limit)
    for a in analyses:
        try:
            a["result"] = json.loads(a["result"])
        except Exception:
            pass
    return {"analyses": analyses}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
