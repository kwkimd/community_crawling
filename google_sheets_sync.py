#!/usr/bin/env python3
"""
구글 시트와 데이터 동기화 모듈
"""
import json
import database as db

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    print("⚠️  구글 시트 연동을 위해 라이브러리 설치가 필요합니다:")
    print("   pip install gspread google-auth")

HEADERS = [
    "번호", "년", "월", "일", "주차", "모니터링명", "위험도", "감성구분",
    "주체구분", "서비스구분", "검색어", "키워드", "제목", "내용", "리스크분류",
    "분류_대분류", "분류_중분류", "분류_소분류", "사이트그룹", "사이트명",
    "작성자명", "조회수", "댓글수", "등록일", "게시글URL", "본문",
    "댓글", "요약", "화자 관점", "핵심 비판 포인트", "쿠팡이츠 관련 언급",
    "주요 팩트/수치", "여론 방향성 요약", "컨텐츠키", "분석일시", "수집자"
]


def _post_to_row(post: dict) -> list:
    """post dict → 시트 행 변환"""
    try:
        comments_list = json.loads(post.get("comments", "[]") or "[]")
        comments_text = "\n".join(
            f"{i+1}. {c}" for i, c in enumerate(comments_list)
        ) if comments_list else ""
    except Exception:
        comments_text = ""

    post_date = post.get("post_date", "") or ""
    year, month, day = "", "", ""
    if post_date:
        parts = post_date.split("-")
        if len(parts) == 3:
            year, month, day = parts

    return [
        post.get("id", ""),
        year, month, day,
        post.get("week_info", "") or "",
        post.get("monitoring_name", "") or "",
        post.get("risk_level", 0) or 0,
        post.get("sentiment", "중립") or "중립",
        post.get("subject_type", "소비자") or "소비자",
        post.get("service_type", "배달의민족") or "배달의민족",
        post.get("search_keyword", "") or "",      # 검색어 (통합 모니터링 키워드)
        post.get("keywords", "") or "",             # 키워드 (본문 자동 추출)
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
        post.get("speaker_perspective", "") or "",
        post.get("criticism_point", "") or "",
        post.get("coupangeats_mention", "") or "",
        post.get("key_facts", "") or "",
        post.get("opinion_summary", "") or "",
        post.get("content_key", "") or "",
        post.get("analysis_datetime", "") or "",
        post.get("collector", "SCA") or "SCA",
    ]


class GoogleSheetsSync:
    def __init__(self, credentials_file=None, sheet_url=None, sheet_name=None):
        self.credentials_file = credentials_file or "google_credentials.json"
        self.sheet_url = sheet_url
        self.sheet_name = sheet_name  # None이면 첫 번째 시트 사용
        self.gc = None
        self.spreadsheet = None
        self.sheet = None

    def setup_connection(self):
        """구글 시트 연결 설정"""
        if not GSPREAD_AVAILABLE:
            raise Exception("gspread 라이브러리가 설치되지 않았습니다.")

        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(
                self.credentials_file, scopes=scope
            )
            if hasattr(gspread, 'authorize'):
                self.gc = gspread.authorize(creds)
            else:
                self.gc = gspread.Client(auth=creds)

            if not self.sheet_url:
                print("❌ 구글 시트 URL이 필요합니다.")
                return False

            self.spreadsheet = self.gc.open_by_url(self.sheet_url)

            if self.sheet_name:
                self.sheet = self._get_or_create_worksheet(self.sheet_name)
            else:
                self.sheet = self.spreadsheet.sheet1
            return True

        except Exception as e:
            print(f"구글 시트 연결 실패: {e}")
            return False

    def _get_or_create_worksheet(self, name: str):
        """시트명으로 워크시트 가져오기, 없으면 자동 생성"""
        try:
            return self.spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            print(f"[시트] '{name}' 시트가 없어 새로 생성합니다.")
            ws = self.spreadsheet.add_worksheet(title=name, rows=1000, cols=30)
            # 새 시트에 헤더 추가
            ws.insert_row(HEADERS, 1)
            try:
                ws.format('A1:AJ1', {
                    'textFormat': {'bold': True},
                    'backgroundColor': {'red': 0.8, 'green': 0.9, 'blue': 1.0}
                })
            except Exception:
                pass
            return ws

    def create_headers(self):
        """시트에 헤더 생성"""
        try:
            self.sheet.insert_row(HEADERS, 1)
            self.sheet.format('A1:AJ1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.9, 'blue': 1.0}
            })
            print("✅ 구글 시트 헤더가 생성되었습니다.")
            return True
        except Exception as e:
            print(f"헤더 생성 실패: {e}")
            return False

    def sync_all_data(self, site_filter=None):
        """DB의 모든 데이터를 구글 시트에 동기화 (전체 덮어쓰기)
        
        site_filter: None=전체, "youtube"=유튜브만, "community"=유튜브+카카오톡 제외,
                     "community_no_kakao"=유튜브+카카오톡 제외, "kakao_recent"=카카오톡 최근 30일
        """
        if not self.sheet:
            print("구글 시트 연결이 필요합니다.")
            return False

        try:
            self.sheet.clear()
            self.create_headers()

            posts = db.get_all_posts()
            
            # 사이트 필터 적용
            if site_filter == "youtube":
                posts = [p for p in posts if (p.get("site") or "").strip() == "유튜브"
                         or (p.get("channel_type") or "").strip() == "유튜브"]
            elif site_filter in ("community", "community_no_kakao"):
                posts = [p for p in posts if (p.get("site") or "").strip() != "유튜브"
                         and (p.get("channel_type") or "").strip() != "유튜브"
                         and (p.get("site") or "").strip() != "카카오톡"]
            elif site_filter == "kakao_recent":
                from datetime import datetime, timedelta
                cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                posts = [p for p in posts if (p.get("site") or "").strip() == "카카오톡"
                         and (p.get("post_date") or "") >= cutoff]
            
            print(f"총 {len(posts)}개 데이터를 구글 시트에 업로드합니다...")

            rows = [_post_to_row(p) for p in posts]
            if rows:
                self.sheet.insert_rows(rows, 2)

            print(f"✅ {len(rows)}개 데이터가 구글 시트에 업로드되었습니다.")
            print(f"🔗 구글 시트 URL: {self.spreadsheet.url}")
            return True

        except Exception as e:
            print(f"데이터 동기화 실패: {e}")
            return False

    def add_new_posts(self, posts):
        """새로운 게시글들만 구글 시트 맨 위에 추가"""
        if not self.sheet or not posts:
            return False

        try:
            rows = [_post_to_row(p) for p in posts]
            if rows:
                self.sheet.insert_rows(rows, 2)
                print(f"✅ {len(rows)}개 새 데이터가 추가되었습니다.")
            return True

        except Exception as e:
            print(f"새 데이터 추가 실패: {e}")
            return False

    def get_existing_urls(self) -> set:
        """시트의 '게시글URL' 컬럼(25번째)에서 기존 URL 집합 반환 (중복 확인용)

        쿼리 파라미터를 제거한 정규화 URL로 반환해 진입 경로가 달라도 중복 처리.
        """
        import re

        def _norm(url: str) -> str:
            m = re.search(r"(cafe\.naver\.com/(?:f-e/cafes/\d+/articles|[^/?#]+)/\d+)", url)
            path = m.group(1) if m else url.split("?")[0]
            if not path.startswith("http"):
                path = "https://" + path
            return path

        if not self.sheet:
            return set()
        try:
            records = self.sheet.col_values(25)  # 1-indexed, 헤더 포함
            return set(_norm(v) for v in records[1:] if v)  # 헤더 및 빈 셀 제외
        except Exception as e:
            print(f"[시트] URL 목록 조회 실패: {e}")
            return set()


def setup_google_sheets():
    """구글 시트 설정 가이드"""
    print("📋 구글 시트 연동 설정 가이드")
    print("=" * 50)
    print("1. 구글 클라우드 콘솔에서 서비스 계정 생성")
    print("   https://console.cloud.google.com/")
    print("2. Google Sheets API 활성화")
    print("3. 서비스 계정 키 다운로드 → 'google_credentials.json'으로 저장")
    print("4. pip install gspread google-auth")


if __name__ == "__main__":
    if not GSPREAD_AVAILABLE:
        setup_google_sheets()
    else:
        sync = GoogleSheetsSync()
        if sync.setup_connection():
            sync.sync_all_data()
