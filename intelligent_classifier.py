#!/usr/bin/env python3
"""
지능형 자동 분류 시스템
- AI 기반 분류 (Gemini API)
- 고도화된 키워드 분석
- 문맥 기반 분류
"""
import re
import json
from typing import Dict, Tuple, List
import database as db

# Gemini API 사용 (선택적)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

class IntelligentClassifier:
    def __init__(self):
        self.risk_keywords = self._load_risk_keywords()
        self.category_patterns = self._load_category_patterns()
        
    def _load_risk_keywords(self) -> Dict:
        """위험도별 키워드 패턴"""
        return {
            "COMPLIANCE_RISK": {
                "keywords": ["파업", "노조", "시위", "고발", "신고", "법적", "소송", "고용노동부", "근로감독관"],
                "patterns": [r"법적.*조치", r"고발.*하겠", r"신고.*할", r"노조.*결성"]
            },
            "OPERATIONAL_RISK": {
                "keywords": ["배차", "픽업", "콜량", "라이더", "배달원", "사고", "안전"],
                "patterns": [r"배차.*문제", r"콜.*없어", r"라이더.*부족", r"사고.*발생"]
            },
            "OPERATIONAL_EXCELLENCE": {
                "keywords": ["수수료", "정책", "할인", "프로모션", "서비스", "시스템", "개선"],
                "patterns": [r"수수료.*인상", r"정책.*변경", r"시스템.*개선"]
            },
            "REPUTATION_RISK": {
                "keywords": ["언론", "기사", "뉴스", "보도", "이미지", "평판"],
                "patterns": [r"언론.*보도", r"기사.*나", r"이미지.*실추"]
            }
        }
    
    def _load_category_patterns(self) -> Dict:
        """분류 체계 패턴"""
        return {
            "프로모션": {
                "keywords": ["할인", "쿠폰", "이벤트", "프로모션", "혜택", "적립", "포인트"],
                "sub_categories": {
                    "쿠폰/이벤트": ["쿠폰", "이벤트", "할인"],
                    "적립/포인트": ["적립", "포인트", "리워드"],
                    "멤버십": ["멤버십", "등급", "VIP"]
                }
            },
            "배달/라이더": {
                "keywords": ["라이더", "배달원", "배차", "픽업", "콜량", "배달"],
                "sub_categories": {
                    "라이더": ["라이더", "배달원", "기사"],
                    "배달": ["배차", "픽업", "배송"],
                    "배달비": ["배달료", "배달팁", "배송비"]
                }
            },
            "서비스": {
                "keywords": ["가게", "매장", "업주", "사장", "서비스", "품질"],
                "sub_categories": {
                    "가게": ["가게", "매장", "업체"],
                    "서비스": ["서비스", "품질", "만족도"],
                    "음식": ["음식", "맛", "품질"]
                }
            },
            "시스템": {
                "keywords": ["앱", "시스템", "오류", "버그", "업데이트", "기능"],
                "sub_categories": {
                    "앱 이용": ["앱", "어플", "애플리케이션"],
                    "시스템": ["시스템", "서버", "네트워크"],
                    "기능": ["기능", "업데이트", "개선"]
                }
            },
            "중대이슈": {
                "keywords": ["파업", "노조", "시위", "사고", "사건"],
                "sub_categories": {
                    "노무": ["파업", "노조", "시위"],
                    "사고": ["사고", "안전", "위험"],
                    "법적": ["소송", "고발", "신고"]
                }
            }
        }
    
    def classify_risk_intelligent(self, text: str, title: str, subject_type: str, sentiment: str) -> str:
        """지능형 리스크 분류"""
        full_text = f"{title} {text}".lower()
        
        # 1. 패턴 매칭 점수 계산
        risk_scores = {}
        
        for risk_type, data in self.risk_keywords.items():
            score = 0
            
            # 키워드 매칭
            for keyword in data["keywords"]:
                if keyword in full_text:
                    score += 1
            
            # 정규식 패턴 매칭 (가중치 높음)
            for pattern in data["patterns"]:
                if re.search(pattern, full_text):
                    score += 3
            
            risk_scores[risk_type] = score
        
        # 2. 감성과 주체 고려
        if sentiment == "부정":
            # 부정적 감성일 때 리스크 점수 증가
            for risk_type in risk_scores:
                risk_scores[risk_type] *= 1.5
        
        if subject_type == "업주":
            # 업주 발언은 운영 관련 리스크 가중치 증가
            risk_scores["OPERATIONAL_RISK"] *= 1.3
        elif subject_type == "라이더":
            # 라이더 발언은 컴플라이언스 리스크 가중치 증가
            risk_scores["COMPLIANCE_RISK"] *= 1.3
        
        # 3. 최고 점수 리스크 반환
        if max(risk_scores.values()) > 0:
            return max(risk_scores, key=risk_scores.get)
        else:
            return "NO RISK"
    
    def classify_business_intelligent(self, text: str, title: str, subject_type: str, sentiment: str) -> Tuple[str, str, str]:
        """지능형 비즈니스 분류"""
        full_text = f"{title} {text}".lower()
        
        # 1. 카테고리별 점수 계산
        category_scores = {}
        
        for main_cat, data in self.category_patterns.items():
            score = 0
            
            # 메인 키워드 매칭
            for keyword in data["keywords"]:
                if keyword in full_text:
                    score += 1
            
            category_scores[main_cat] = score
        
        # 2. 주체별 가중치 적용
        if subject_type == "업주":
            category_scores["서비스"] *= 1.5
        elif subject_type == "라이더":
            category_scores["배달/라이더"] *= 1.5
        elif subject_type == "소비자":
            category_scores["프로모션"] *= 1.2
            category_scores["시스템"] *= 1.2
        
        # 3. 최고 점수 카테고리 선택
        if max(category_scores.values()) > 0:
            main_category = max(category_scores, key=category_scores.get)
        else:
            main_category = "플랫폼 이용"
        
        # 4. 서브 카테고리 결정
        sub_category, detail_category = self._determine_sub_category(
            main_category, full_text, subject_type
        )
        
        return main_category, sub_category, detail_category
    
    def _determine_sub_category(self, main_category: str, text: str, subject_type: str) -> Tuple[str, str]:
        """서브 카테고리 결정"""
        if main_category not in self.category_patterns:
            return "일반", "일반"
        
        sub_cats = self.category_patterns[main_category]["sub_categories"]
        sub_scores = {}
        
        for sub_cat, keywords in sub_cats.items():
            score = sum(1 for keyword in keywords if keyword in text)
            sub_scores[sub_cat] = score
        
        if max(sub_scores.values()) > 0:
            sub_category = max(sub_scores, key=sub_scores.get)
        else:
            sub_category = list(sub_cats.keys())[0]  # 첫 번째를 기본값으로
        
        # 디테일 카테고리는 서브와 동일하거나 더 구체적으로
        detail_category = self._get_detail_category(main_category, sub_category, text)
        
        return sub_category, detail_category
    
    def _get_detail_category(self, main_cat: str, sub_cat: str, text: str) -> str:
        """디테일 카테고리 결정"""
        detail_patterns = {
            ("플랫폼 이용", "주문"): {
                "최소 주문 금액": ["최소주문", "주문금액", "최소금액"],
                "배달팁": ["배달료", "배달팁", "배송비"],
                "주문 취소": ["취소", "환불"],
                "일반": []
            },
            ("프로모션", "쿠폰/이벤트"): {
                "할인 쿠폰": ["할인", "쿠폰"],
                "이벤트": ["이벤트", "프로모션"],
                "일반": []
            }
        }
        
        key = (main_cat, sub_cat)
        if key in detail_patterns:
            for detail, keywords in detail_patterns[key].items():
                if any(keyword in text for keyword in keywords):
                    return detail
        
        return "일반"
    
    def extract_smart_keywords(self, text: str, title: str) -> str:
        """스마트 키워드 추출"""
        full_text = f"{title} {text}"
        
        # 1. 중요 키워드 패턴
        important_patterns = [
            r"배달의민족|배민",
            r"쿠팡이츠|쿠팡",
            r"요기요",
            r"라이더|배달원",
            r"업주|사장",
            r"할인|쿠폰|이벤트",
            r"수수료|정책",
            r"앱|시스템|오류"
        ]
        
        keywords = []
        for pattern in important_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            keywords.extend(matches)
        
        # 2. 빈도 기반 키워드 (2글자 이상, 3회 이상 등장)
        words = re.findall(r'[가-힣]{2,}', full_text)
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
        
        frequent_words = [word for word, freq in word_freq.items() if freq >= 2]
        keywords.extend(frequent_words[:5])  # 상위 5개만
        
        return ", ".join(list(set(keywords))[:10])  # 중복 제거, 최대 10개
    
    def generate_smart_summary(self, text: str, title: str) -> str:
        """스마트 요약 생성"""
        # 1. 제목 우선 사용
        if title and len(title.strip()) > 5:
            return title.strip()[:100]
        
        # 2. 첫 문장 추출
        sentences = re.split(r'[.!?]', text)
        if sentences and len(sentences[0].strip()) > 10:
            return sentences[0].strip()[:100]
        
        # 3. 중요 키워드 포함 문장 찾기
        important_keywords = ["배달", "라이더", "업주", "할인", "문제", "불만"]
        for sentence in sentences:
            if any(keyword in sentence for keyword in important_keywords):
                return sentence.strip()[:100]
        
        # 4. 기본 요약
        return text[:100] + ("..." if len(text) > 100 else "")

# 전역 분류기 인스턴스
_classifier = IntelligentClassifier()

def classify_post_intelligent(post: dict, monitoring_name: str, search_keyword: str) -> dict:
    """게시글 지능형 분류 (기존 함수 대체)"""
    enhanced = post.copy()
    
    title = post.get("title", "")
    content = post.get("content", "")
    author = post.get("author", "")
    
    # 기존 분류 (감성, 주체 등)는 유지
    from scraper import _analyze_sentiment, _classify_subject_type, _classify_service_type, _classify_channel_type, _classify_site_group
    
    sentiment = _analyze_sentiment(f"{title} {content}".lower())
    subject_type = _classify_subject_type(author, f"{title} {content}".lower(), post.get("cafe_name", ""))
    service_type = _classify_service_type(f"{title} {content}".lower(), search_keyword)
    channel_type = _classify_channel_type(post.get("cafe_name", ""), post.get("post_url", ""))
    site_group = _classify_site_group(post.get("cafe_name", ""), post.get("post_url", ""))
    
    # 새로운 지능형 분류
    risk_classification = _classifier.classify_risk_intelligent(content, title, subject_type, sentiment)
    main_cat, sub_cat, detail_cat = _classifier.classify_business_intelligent(content, title, subject_type, sentiment)
    smart_keywords = _classifier.extract_smart_keywords(content, title)
    smart_summary = _classifier.generate_smart_summary(content, title)
    
    # 위험도 계산 (기존 로직 유지하되 새 분류 반영)
    risk_level = 0
    if sentiment == "부정":
        if risk_classification in ["COMPLIANCE_RISK", "REPUTATION_RISK"]:
            risk_level = 2
        elif risk_classification in ["OPERATIONAL_RISK"]:
            risk_level = 1
        else:
            risk_level = 1
    
    # 결과 업데이트
    enhanced.update({
        "monitoring_name": monitoring_name,
        "risk_level": risk_level,
        "sentiment": sentiment,
        "subject_type": subject_type,
        "service_type": service_type,
        "channel_type": channel_type,
        "risk_classification": risk_classification,
        "main_category": main_cat,
        "sub_category": sub_cat,
        "detail_category": detail_cat,
        "site_group": site_group,
        "keywords": smart_keywords,
        "summary": smart_summary,
        # 기존 필드들
        "week_info": post.get("week_info", ""),
        "content_key": post.get("content_key", ""),
        "analysis_datetime": post.get("analysis_datetime", ""),
        "collector": "SCA"
    })
    
    return enhanced