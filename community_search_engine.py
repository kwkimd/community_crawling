#!/usr/bin/env python3
"""
범용 커뮤니티 자동 검색 엔진
- 다양한 커뮤니티 사이트의 검색 URL 패턴 지원
- 메인 URL + 키워드 → 자동 검색 URL 생성
"""
import re
import urllib.parse
from typing import Dict, Tuple, Optional

class CommunitySearchEngine:
    """커뮤니티 사이트별 검색 URL 생성기"""
    
    def __init__(self):
        # 사이트별 검색 URL 패턴 정의
        self.search_patterns = {
            # 네이버 카페
            "cafe.naver.com": {
                "name": "네이버 카페",
                "patterns": [
                    {
                        "main_pattern": r"cafe\.naver\.com/f-e/cafes/(\d+)",
                        "search_template": "https://cafe.naver.com/f-e/cafes/{cafe_id}/menus/0?q={keyword}&ta=SUBJECT",
                        "type": "new_format"
                    },
                    {
                        "main_pattern": r"cafe\.naver\.com/([^/?#]+)",
                        "search_template": "https://cafe.naver.com/{cafe_name}/ArticleSearchList.nhn?search.query={keyword}",
                        "type": "old_format"
                    }
                ],
                "search_indicators": ["search", "query=", "q=", "ArticleSearchList", "menus/0?q="]
            },
            
            # 에펨코리아
            "fmkorea.com": {
                "name": "에펨코리아",
                "patterns": [
                    {
                        "main_pattern": r"(www\.)?fmkorea\.com",
                        "search_template": "https://www.fmkorea.com/search.php?act=IS&is_keyword={keyword}",
                        "type": "main_site"
                    }
                ],
                "search_indicators": ["search.php", "is_keyword="]
            },
            
            # 디시인사이드
            "dcinside.com": {
                "name": "디시인사이드",
                "patterns": [
                    {
                        "main_pattern": r"gall\.dcinside\.com/board/lists/\?id=([^&]+)",
                        "search_template": "https://gall.dcinside.com/board/lists/?id={gallery_id}&s_type=search_subject_memo&s_keyword={keyword}",
                        "type": "gallery"
                    },
                    {
                        "main_pattern": r"(www\.)?dcinside\.com/?$",
                        "search_template": "https://gall.dcinside.com/board/lists/?id=programming&s_type=search_subject_memo&s_keyword={keyword}",
                        "type": "main_site"
                    },
                    {
                        "main_pattern": r"gall\.dcinside\.com/?$",
                        "search_template": "https://gall.dcinside.com/board/lists/?id=programming&s_type=search_subject_memo&s_keyword={keyword}",
                        "type": "gallery_main"
                    }
                ],
                "search_indicators": ["s_keyword=", "search.dcinside.com"]
            },
            
            # 클리앙
            "clien.net": {
                "name": "클리앙",
                "patterns": [
                    {
                        "main_pattern": r"clien\.net",
                        "search_template": "https://www.clien.net/service/search?q={keyword}&sort=recency",
                        "type": "main_site"
                    }
                ],
                "search_indicators": ["service/search?q="]
            },
            
            # 루리웹
            "ruliweb.com": {
                "name": "루리웹",
                "patterns": [
                    {
                        "main_pattern": r"(bbs\.)?ruliweb\.com/?$",
                        "search_template": "https://bbs.ruliweb.com/community/board/300143?search_type=subject_content&search_key={keyword}",
                        "type": "main_site"
                    }
                ],
                "search_indicators": ["search_key="]
            },
            
            # 보배드림
            "bobaedream.co.kr": {
                "name": "보배드림",
                "patterns": [
                    {
                        "main_pattern": r"(www\.)?bobaedream\.co\.kr/?$",
                        "search_template": "https://www.bobaedream.co.kr/cyber/CyberCommunity.php?search_type=1&search_keyword={keyword}",
                        "type": "main_site"
                    }
                ],
                "search_indicators": ["search_keyword="]
            },
            
            # 82cook
            "82cook.com": {
                "name": "82cook",
                "patterns": [
                    {
                        "main_pattern": r"(www\.)?82cook\.com/?$",
                        "search_template": "https://www.82cook.com/entiz/enti.php?bn=15&search_type=subject&search_keyword={keyword}",
                        "type": "main_site"
                    }
                ],
                "search_indicators": ["search_keyword="]
            },
            
            # 네이트판
            "pann.nate.com": {
                "name": "네이트판",
                "patterns": [
                    {
                        "main_pattern": r"pann\.nate\.com/?$",
                        "search_template": "https://pann.nate.com/search/total?q={keyword}",
                        "type": "main_site"
                    },
                    {
                        "main_pattern": r"pann\.nate\.com/(talk|news|photo|vote|knowhow|qna)/?$",
                        "search_template": "https://pann.nate.com/search/total?q={keyword}",
                        "type": "category_page"
                    }
                ],
                "search_indicators": ["search/total?q=", "search?q="]
            },
            
            # 네이버 검색
            "search.naver.com": {
                "name": "네이버 검색",
                "patterns": [
                    {
                        "main_pattern": r"search\.naver\.com",
                        "search_template": "https://search.naver.com/search.naver?where=view&query={keyword}&sm=tab_opt&nso=so%3Add%2Cp%3A1w",
                        "type": "main_site"
                    }
                ],
                "search_indicators": ["query=", "where="]
            }
        }
    
    def detect_site_type(self, url: str) -> Tuple[str, str]:
        """URL에서 사이트 타입 감지"""
        if not url:
            return "unknown", "알 수 없는 사이트"
        
        for domain, config in self.search_patterns.items():
            if domain in url:
                # 검색 URL인지 확인
                if any(indicator in url for indicator in config["search_indicators"]):
                    return "search_result", f"{config['name']} 검색 결과"
                
                # 메인 URL인지 확인
                for pattern_config in config["patterns"]:
                    if re.search(pattern_config["main_pattern"], url):
                        return "main_site", f"{config['name']} 메인"
        
        return "unknown", "지원하지 않는 사이트"
    
    def build_search_url(self, url: str, keyword: str) -> Tuple[str, str]:
        """메인 URL + 키워드 → 검색 URL 생성 (다중 키워드 지원)"""
        if not keyword.strip():
            return url, "키워드가 없어서 원본 URL 사용"
        
        # 다중 키워드 처리
        processed_keyword, keyword_info = self._process_multiple_keywords(url, keyword.strip())
        
        for domain, config in self.search_patterns.items():
            if domain in url:
                for pattern_config in config["patterns"]:
                    match = re.search(pattern_config["main_pattern"], url)
                    if match:
                        template = pattern_config["search_template"]
                        
                        # 템플릿에 따라 URL 생성
                        if pattern_config["type"] == "new_format":  # 네이버 카페 새 형식
                            cafe_id = match.group(1)
                            search_url = template.format(cafe_id=cafe_id, keyword=processed_keyword)
                        elif pattern_config["type"] == "old_format":  # 네이버 카페 구 형식
                            cafe_name = match.group(1)
                            search_url = template.format(cafe_name=cafe_name, keyword=processed_keyword)
                        elif pattern_config["type"] == "gallery":  # 디시 갤러리
                            gallery_id = match.group(1)
                            search_url = template.format(gallery_id=gallery_id, keyword=processed_keyword)
                        else:  # 일반 사이트
                            search_url = template.format(keyword=processed_keyword)
                        
                        return search_url, f"{config['name']}에서 {keyword_info} 검색 URL 생성"
        
        return url, "지원하지 않는 사이트 - 원본 URL 사용"
    
    def _process_multiple_keywords(self, url: str, keywords: str) -> Tuple[str, str]:
        """다중 키워드 처리 - 사이트별로 다른 방식 적용"""
        
        # 키워드 분리 (쉼표, 공백, 세미콜론으로 구분)
        keyword_list = []
        for separator in [',', ';', '|']:
            if separator in keywords:
                keyword_list = [k.strip() for k in keywords.split(separator) if k.strip()]
                break
        
        # 구분자가 없으면 공백으로 분리 시도
        if not keyword_list:
            parts = keywords.split()
            if len(parts) > 1:
                keyword_list = parts
            else:
                keyword_list = [keywords]
        
        # 단일 키워드인 경우
        if len(keyword_list) == 1:
            return urllib.parse.quote(keyword_list[0]), f"'{keyword_list[0]}'"
        
        # 다중 키워드 처리 - 사이트별 방식
        domain = self._extract_domain(url)
        
        if "clien.net" in domain:
            # 클리앙: OR 검색 (공백으로 구분)
            combined = " ".join(keyword_list)
            return urllib.parse.quote(combined), f"'{' OR '.join(keyword_list)}' (OR 검색)"
            
        elif "fmkorea.com" in domain:
            # 에펨코리아: 첫 번째 키워드만 사용 (다중 키워드 미지원)
            return urllib.parse.quote(keyword_list[0]), f"'{keyword_list[0]}' (첫 번째 키워드만, 총 {len(keyword_list)}개 중)"
            
        elif "dcinside.com" in domain:
            # 디시인사이드: OR 검색 (첫 번째 키워드만 사용)
            # 디시인사이드는 다중 키워드 OR 검색 미지원
            encoded = urllib.parse.quote(keyword_list[0], safe='')
            return encoded, f"'{keyword_list[0]}' (대표 키워드, 총 {len(keyword_list)}개)"
            
        elif "ruliweb.com" in domain:
            # 루리웹: 첫 번째 키워드만 사용
            return urllib.parse.quote(keyword_list[0]), f"'{keyword_list[0]}' (첫 번째 키워드만, 총 {len(keyword_list)}개 중)"
            
        elif "bobaedream.co.kr" in domain:
            # 보배드림: 공백으로 구분하여 OR 검색
            combined = " ".join(keyword_list)
            return urllib.parse.quote(combined), f"'{' OR '.join(keyword_list)}' (OR 검색)"
            
        elif "82cook.com" in domain:
            # 82cook: 첫 번째 키워드만 사용
            return urllib.parse.quote(keyword_list[0]), f"'{keyword_list[0]}' (첫 번째 키워드만, 총 {len(keyword_list)}개 중)"
            
        elif "pann.nate.com" in domain:
            # 네이트판: 첫 번째 키워드만 사용 (다중 키워드 미지원)
            return urllib.parse.quote(keyword_list[0]), f"'{keyword_list[0]}' (첫 번째 키워드만, 총 {len(keyword_list)}개 중)"
            
        elif "cafe.naver.com" in domain:
            # 네이버 카페: OR 검색 (첫 번째 키워드만 사용, 네이버 카페는 다중 키워드 OR 검색 미지원)
            # 대신 첫 번째 키워드로 검색 후 클라이언트 측에서 필터링
            return urllib.parse.quote(keyword_list[0]), f"'{keyword_list[0]}' (대표 키워드, 총 {len(keyword_list)}개)"
            
        else:
            # 기본값: 첫 번째 키워드만 사용
            return urllib.parse.quote(keyword_list[0]), f"'{keyword_list[0]}' (첫 번째 키워드만, 총 {len(keyword_list)}개 중)"
    
    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        return url.lower()
    
    def process_url(self, url: str, keyword: str) -> Dict[str, str]:
        """URL 처리 및 결과 반환"""
        if not url.strip():
            return {
                "final_url": "",
                "message": "URL이 입력되지 않았습니다",
                "site_type": "empty",
                "site_name": "",
                "action": "none"
            }
        
        site_type, site_name = self.detect_site_type(url)
        
        if site_type == "search_result":
            return {
                "final_url": url,
                "message": f"검색 결과 URL 감지 - 바로 크롤링 ({site_name})",
                "site_type": site_type,
                "site_name": site_name,
                "action": "direct_crawl"
            }
        
        elif site_type == "main_site" and keyword.strip():
            search_url, message = self.build_search_url(url, keyword)
            return {
                "final_url": search_url,
                "message": message,
                "site_type": site_type,
                "site_name": site_name,
                "action": "auto_search"
            }
        
        elif site_type == "main_site":
            return {
                "final_url": url,
                "message": f"{site_name} 메인 URL - 최신 게시글 수집",
                "site_type": site_type,
                "site_name": site_name,
                "action": "latest_posts"
            }
        
        else:
            return {
                "final_url": url,
                "message": "지원하지 않는 사이트 - 원본 URL로 시도",
                "site_type": site_type,
                "site_name": site_name,
                "action": "fallback"
            }
    
    def get_supported_sites(self) -> Dict[str, str]:
        """지원하는 사이트 목록 반환"""
        return {domain: config["name"] for domain, config in self.search_patterns.items()}
    
    def add_site_pattern(self, domain: str, name: str, patterns: list, search_indicators: list):
        """새로운 사이트 패턴 추가"""
        self.search_patterns[domain] = {
            "name": name,
            "patterns": patterns,
            "search_indicators": search_indicators
        }

# 전역 인스턴스
search_engine = CommunitySearchEngine()

# 편의 함수들
def detect_url_type(url: str) -> Tuple[str, str]:
    """URL 타입 감지"""
    return search_engine.detect_site_type(url)

def build_search_url(url: str, keyword: str) -> Tuple[str, str]:
    """검색 URL 생성"""
    return search_engine.build_search_url(url, keyword)

def process_community_url(url: str, keyword: str) -> Dict[str, str]:
    """커뮤니티 URL 처리 (등록된 URL만 허용)"""
    # 등록된 URL인지 확인
    if not is_registered_url(url):
        return {
            "final_url": "",
            "message": f"❌ 등록되지 않은 URL입니다.\n\n🔗 크롤링 URL 관리 탭에서 다음 정보로 먼저 등록해주세요:\n• 사이트명: (예: 새로운 커뮤니티)\n• URL: {url}\n• 검색 키워드: {keyword}\n• 타입: community",
            "site_type": "unregistered",
            "site_name": "미등록 사이트",
            "action": "reject"
        }
    
    return search_engine.process_url(url, keyword)

def is_registered_url(url: str) -> bool:
    """URL이 등록된 URL 목록에 있는지 확인"""
    try:
        import json
        from pathlib import Path
        
        urls_file = Path("crawler_urls.json")
        if not urls_file.exists():
            return False
        
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls_data = json.load(f)
        
        registered_urls = urls_data.get("urls", [])
        
        # 입력된 URL이 등록된 URL 목록에 있는지 확인
        for registered_url_info in registered_urls:
            registered_url = registered_url_info.get("url", "")
            backup_urls = registered_url_info.get("backup_urls", [])
            
            # 메인 URL 또는 백업 URL과 일치하는지 확인
            if url.strip() == registered_url.strip():
                return True
            
            # 백업 URL들과 일치하는지 확인
            for backup_url in backup_urls:
                if url.strip() == backup_url.strip():
                    return True
            
            # 도메인 기반 부분 일치 확인 (같은 사이트의 다른 페이지)
            from urllib.parse import urlparse
            input_domain = urlparse(url).netloc.lower()
            registered_domain = urlparse(registered_url).netloc.lower()
            
            if input_domain and registered_domain and input_domain == registered_domain:
                return True
        
        return False
        
    except Exception as e:
        print(f"[URL 확인 오류] {e}")
        return False

def get_supported_communities() -> Dict[str, str]:
    """지원하는 커뮤니티 목록"""
    return search_engine.get_supported_sites()

if __name__ == "__main__":
    # 테스트
    test_cases = [
        ("https://www.fmkorea.com/", "배민"),
        ("https://cafe.naver.com/jihosoccer123", "배달"),
        ("https://cafe.naver.com/f-e/cafes/23611966", "배달"),
        ("https://gall.dcinside.com/board/lists/?id=food", "배민"),
        ("https://www.clien.net/", "배달앱"),
    ]
    
    print("🔍 커뮤니티 자동 검색 테스트")
    print("=" * 60)
    
    for url, keyword in test_cases:
        result = process_community_url(url, keyword)
        print(f"\n입력: {url}")
        print(f"키워드: {keyword}")
        print(f"결과: {result['final_url']}")
        print(f"메시지: {result['message']}")
        print(f"액션: {result['action']}")