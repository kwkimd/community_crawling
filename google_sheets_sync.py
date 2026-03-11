#!/usr/bin/env python3
"""
구글 시트와 데이터 동기화 모듈
"""
import json
import database as db
from datetime import datetime

# Google Sheets API 사용을 위한 라이브러리 (설치 필요)
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    print("⚠️  구글 시트 연동을 위해 라이브러리 설치가 필요합니다:")
    print("   pip install gspread google-auth")

class GoogleSheetsSync:
    def __init__(self, credentials_file=None, sheet_url=None):
        """
        구글 시트 동기화 클래스
        
        Args:
            credentials_file: 구글 서비스 계정 JSON 파일 경로
            sheet_url: 구글 시트 URL
        """
        self.credentials_file = credentials_file or "google_credentials.json"
        self.sheet_url = sheet_url
        self.gc = None
        self.sheet = None
        
    def setup_connection(self):
        """구글 시트 연결 설정"""
        if not GSPREAD_AVAILABLE:
            raise Exception("gspread 라이브러리가 설치되지 않았습니다.")
            
        try:
            # 서비스 계정 인증
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = Credentials.from_service_account_file(
                self.credentials_file, scopes=scope
            )
            self.gc = gspread.authorize(creds)
            
            if self.sheet_url:
                self.sheet = self.gc.open_by_url(self.sheet_url).sheet1
            else:
                print("❌ 구글 시트 URL이 필요합니다.")
                print("   1. 구글 시트에서 새 문서를 직접 만드세요")
                print("   2. 시트 URL을 복사하세요")
                print("   3. GoogleSheetsSync(sheet_url='복사한URL')로 실행하세요")
                return False
                
            return True
            
        except Exception as e:
            print(f"구글 시트 연결 실패: {e}")
            return False
    
    def create_headers(self):
        """시트에 헤더 생성"""
        headers = [
            "번호", "년", "월", "일", "주차", "모니터링명", "위험도", "감성구분",
            "주체구분", "서비스구분", "검색어", "제목", "내용", "리스크분류",
            "분류_대분류", "분류_중분류", "분류_소분류", "사이트그룹", "사이트명",
            "작성자명", "조회수", "댓글수", "등록일", "게시글URL", "본문",
            "댓글", "요약", "컨텐츠키", "분석일시", "수집자"
        ]
        
        try:
            # 첫 번째 행에 헤더 추가
            self.sheet.insert_row(headers, 1)
            
            # 헤더 스타일링 (굵게, 배경색)
            self.sheet.format('A1:AD1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.9, 'blue': 1.0}
            })
            
            print("✅ 구글 시트 헤더가 생성되었습니다.")
            return True
            
        except Exception as e:
            print(f"헤더 생성 실패: {e}")
            return False
    
    def sync_all_data(self):
        """DB의 모든 데이터를 구글 시트에 동기화"""
        if not self.sheet:
            print("구글 시트 연결이 필요합니다.")
            return False
            
        try:
            # 기존 데이터 삭제 (헤더 제외)
            self.sheet.clear()
            
            # 헤더 생성
            self.create_headers()
            
            # DB에서 모든 데이터 가져오기
            posts = db.get_all_posts()
            print(f"총 {len(posts)}개 데이터를 구글 시트에 업로드합니다...")
            
            # 데이터 변환
            rows = []
            for post in posts:
                # 댓글 JSON → 텍스트 변환
                try:
                    comments_list = json.loads(post.get("comments", "[]") or "[]")
                    comments_text = "\n".join(
                        f"{i+1}. {c}" for i, c in enumerate(comments_list)
                    ) if comments_list else ""
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
                    post.get("title", "") or "",
                    post.get("content", "") or "",
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
                    post.get("content", "") or "",
                    comments_text,
                    post.get("summary", "") or "",
                    post.get("content_key", "") or "",
                    post.get("analysis_datetime", "") or "",
                    post.get("collector", "SCA") or "SCA"
                ]
                rows.append(row)
            
            # 배치로 데이터 업로드 (속도 향상)
            if rows:
                self.sheet.insert_rows(rows, 2)  # 헤더 다음부터 삽입
                
            print(f"✅ {len(rows)}개 데이터가 구글 시트에 업로드되었습니다.")
            print(f"🔗 구글 시트 URL: {self.sheet.spreadsheet.url}")
            
            return True
            
        except Exception as e:
            print(f"데이터 동기화 실패: {e}")
            return False
    
    def add_new_posts(self, posts):
        """새로운 게시글들만 구글 시트에 추가"""
        if not self.sheet or not posts:
            return False
            
        try:
            # 새 데이터 변환 및 추가
            rows = []
            for post in posts:
                # 위의 sync_all_data와 동일한 변환 로직
                # ... (생략)
                pass
            
            if rows:
                self.sheet.insert_rows(rows, 2)  # 맨 위에 삽입
                print(f"✅ {len(rows)}개 새 데이터가 추가되었습니다.")
                
            return True
            
        except Exception as e:
            print(f"새 데이터 추가 실패: {e}")
            return False


def setup_google_sheets():
    """구글 시트 설정 가이드"""
    print("📋 구글 시트 연동 설정 가이드")
    print("=" * 50)
    print()
    print("1. 구글 클라우드 콘솔에서 서비스 계정 생성")
    print("   https://console.cloud.google.com/")
    print()
    print("2. Google Sheets API 활성화")
    print()
    print("3. 서비스 계정 키 다운로드 (JSON 파일)")
    print("   → 파일명을 'google_credentials.json'으로 변경")
    print()
    print("4. 라이브러리 설치:")
    print("   pip install gspread google-auth")
    print()
    print("5. 사용 예시:")
    print("   sync = GoogleSheetsSync()")
    print("   sync.setup_connection()")
    print("   sync.sync_all_data()")


if __name__ == "__main__":
    if not GSPREAD_AVAILABLE:
        setup_google_sheets()
    else:
        # 테스트 실행
        sync = GoogleSheetsSync()
        if sync.setup_connection():
            sync.sync_all_data()