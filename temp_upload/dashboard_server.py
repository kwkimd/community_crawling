#!/usr/bin/env python3
"""
대시보드 전용 서버 (클라우드 배포용)
- 데이터 조회 및 분석
- AI 분석 기능
- Excel 내보내기
- 크롤링 기능 제외
"""
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

app = FastAPI(title="아프니까사장이다 대시보드")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db()


# ── 페이지 ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = db.get_stats()
    categories = db.get_categories()
    recent = db.get_all_posts()[:5]
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "categories": categories,
        "recent_posts": recent,
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
        ws.col(col).width = w * 256

    for row, p in enumerate(posts, 1):
        try:
            comments_list = json.loads(p.get("comments", "[]") or "[]")
            comments_text = "\n".join(
                f"{i+1}. {c}" for i, c in enumerate(comments_list)
            ) if comments_list else ""
        except Exception:
            comments_text = ""

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
        ws.write(row, 17, p.get("site_group", "네이버") or "네이버", normal_style)
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


# ── 분석 API ───────────────────────────────────────────────────────────────────

@app.post("/api/analyze/comprehensive")
async def save_comprehensive_analysis(request: Request):
    """종합 분석 결과 저장"""
    body = await request.json()
    analyses = body.get("analyses", {})
    post_ids = body.get("post_ids", [])
    period = body.get("period", "all")
    post_count = body.get("post_count", 0)
    
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


# ── 헬스체크 ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "service": "dashboard",
        "total_posts": db.get_stats()["total"]
    }


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("dashboard_server:app", host="0.0.0.0", port=port, reload=False)