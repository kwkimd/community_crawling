#!/usr/bin/env python3
"""
구글 시트에 직접 복사-붙여넣기할 수 있는 CSV 파일 생성
"""
import csv
import json
import database as db
from datetime import datetime

def export_for_google_sheets():
    """구글 시트용 CSV 파일 생성"""
    
    # DB에서 모든 데이터 가져오기
    posts = db.get_all_posts()
    print(f"총 {len(posts)}개 데이터를 CSV로 내보냅니다...")
    
    # CSV 파일명 (현재 날짜 포함)
    today = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"구글시트용_커뮤니티데이터_{today}.csv"
    
    # CSV 헤더 (구글 시트와 동일)
    headers = [
        "번호", "년", "월", "일", "주차", "모니터링명", "위험도", "감성구분",
        "주체구분", "서비스구분", "검색어", "제목", "내용", "리스크분류",
        "분류_대분류", "분류_중분류", "분류_소분류", "사이트그룹", "사이트명",
        "작성자명", "조회수", "댓글수", "등록일", "게시글URL", "본문",
        "댓글", "요약", "컨텐츠키", "분석일시", "수집자"
    ]
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        
        # 헤더 쓰기
        writer.writerow(headers)
        
        # 데이터 쓰기
        for post in posts:
            # 댓글 JSON → 텍스트 변환
            try:
                comments_list = json.loads(post.get("comments", "[]") or "[]")
                comments_text = " | ".join(comments_list) if comments_list else ""
            except:
                comments_text = ""
            
            # 날짜 파싱
            post_date = post.get("post_date", "") or ""
            year, month, day = "", "", ""
            if post_date:
                try:
                    parts = post_date.split("-")
                    if len(parts) == 3:
                        year, month, day = parts
                except:
                    pass
            
            # 내용에서 줄바꿈 제거 (CSV 호환성)
            content = (post.get("content", "") or "").replace('\n', ' ').replace('\r', ' ')
            title = (post.get("title", "") or "").replace('\n', ' ').replace('\r', ' ')
            
            row = [
                post.get("id", ""),
                year,
                month, 
                day,
                post.get("week_info", "") or "",
                post.get("monitoring_name", "") or "",
                post.get("risk_level", 0) or 0,
                post.get("sentiment", "중립") or "중립",
                post.get("subject_type", "소비자") or "소비자",
                post.get("service_type", "배달의민족") or "배달의민족",
                post.get("keywords", "") or "",
                title,
                content,
                post.get("risk_classification", "NO RISK") or "NO RISK",
                post.get("main_category", "플랫폼 이용") or "플랫폼 이용",
                post.get("sub_category", "주문") or "주문",
                post.get("detail_category", "일반") or "일반",
                post.get("site_group", "네이버") or "네이버",
                post.get("cafe_name", "") or "",
                post.get("author", "") or "",
                post.get("view_count", 0) or 0,
                post.get("comment_count", 0) or 0,
                post_date,
                post.get("post_url", "") or "",
                content,  # 본문 (중복이지만 CSV 구조 맞춤)
                comments_text,
                post.get("summary", "") or "",
                post.get("content_key", "") or "",
                post.get("analysis_datetime", "") or "",
                post.get("collector", "SCA") or "SCA"
            ]
            
            writer.writerow(row)
    
    print(f"✅ CSV 파일이 생성되었습니다: {filename}")
    print(f"📋 사용 방법:")
    print(f"   1. 구글 시트 새 문서 생성")
    print(f"   2. 파일 → 가져오기 → 업로드")
    print(f"   3. '{filename}' 파일 선택")
    print(f"   4. 구분자: 쉼표, 인코딩: UTF-8")
    
    return filename

if __name__ == "__main__":
    export_for_google_sheets()