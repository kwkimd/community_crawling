import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

def _get_client():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    genai.configure(api_key=api_key)
    return genai

MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def _chat(prompt: str) -> str:
    _get_client()
    model = genai.GenerativeModel(MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.rstrip("`").strip()
    return json.loads(text)


def _posts_to_text(posts: list[dict]) -> str:
    import json as _json
    lines = []
    for i, p in enumerate(posts, 1):
        # 댓글 파싱 (JSON 문자열 or list)
        raw_comments = p.get("comments", [])
        if isinstance(raw_comments, str):
            try:
                raw_comments = _json.loads(raw_comments)
            except Exception:
                raw_comments = []
        comments_text = ""
        if raw_comments:
            comment_lines = "\n".join(f"  - {c}" for c in raw_comments[:20])
            comments_text = f"\n댓글({len(raw_comments)}개):\n{comment_lines}"

        lines.append(
            f"[게시글 {i}]\n"
            f"제목: {p['title']}\n"
            f"카테고리: {p.get('category', '')}\n"
            f"작성일: {p.get('post_date', '')}\n"
            f"조회수: {p.get('view_count', 0)} | 댓글수: {p.get('comment_count', 0)}\n"
            f"내용:\n{p['content']}"
            f"{comments_text}\n"
        )
    return "\n---\n".join(lines)


ROLE_CONTEXT = """당신은 배달플랫폼 회사의 서비스 모니터링 담당자입니다.
회사의 목표는 두 가지입니다:
1. 우리 플랫폼을 이용하는 자영업자(입점 사장님)들의 매출을 실질적으로 높여주는 것
2. 이를 통해 플랫폼의 거래액과 회사 이윤을 함께 성장시키는 것

분석 시 반드시 지켜야 할 관점:
- 정부 정책이나 법·제도 변경에 의존하는 해결책은 제안하지 않습니다 (우리가 통제할 수 없음)
- 모든 인사이트와 개선안은 '플랫폼이 직접 실행할 수 있는 것'에 초점을 맞춥니다
- 자영업자의 불만·고충은 곧 플랫폼 이탈 위험 신호로 해석하고, 리텐션 관점에서 접근합니다
- 자영업자의 매출 증대 = 플랫폼 수익 증대라는 구조를 항상 염두에 둡니다"""


def analyze_sentiment(posts: list[dict]) -> dict:
    """게시글 감성 분석 (긍정/부정/중립 비율 + 설명)"""
    text = _posts_to_text(posts)
    prompt = f"""{ROLE_CONTEXT}

아래 '아프니까 사장이다' 카페 게시글들의 감성을 분석해주세요.
특히 배달플랫폼(수수료, UI, 정산, 광고, 고객응대 등)에 대한 감성에 집중하고,
자영업자들이 플랫폼에 느끼는 불만과 기대를 파악하세요.

{text}

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "positive_ratio": 30,
  "negative_ratio": 50,
  "neutral_ratio": 20,
  "overall_sentiment": "부정적",
  "summary": "플랫폼 이용 자영업자들의 전반적인 감성과 주요 감정 흐름 요약 (3-4문장)",
  "key_emotions": ["불만", "기대", "피로감", "불안"],
  "platform_sentiment": "배달플랫폼에 대한 감성만 별도 서술 (수수료·정산·광고·UI 등)",
  "churn_risk": "플랫폼 이탈 위험 수준 (낮음/중간/높음) 및 이유",
  "notable_patterns": "감성 패턴에서 발견된 특이사항"
}}"""
    try:
        return _parse_json(_chat(prompt))
    except Exception as e:
        return {"error": str(e)}


def extract_keywords(posts: list[dict]) -> dict:
    """핵심 키워드 및 이슈 추출"""
    text = _posts_to_text(posts)
    prompt = f"""{ROLE_CONTEXT}

아래 '아프니까 사장이다' 카페 게시글들에서 핵심 키워드와 주요 이슈를 추출해주세요.
배달플랫폼이 직접 개선·활용할 수 있는 키워드와 이슈에 집중하세요.

{text}

다음 JSON 형식으로만 응답하세요:
{{
  "top_keywords": [
    {{"keyword": "환불", "count": 15, "context": "부당 환불 요청으로 인한 사장님 피해", "platform_action": "플랫폼 차원의 환불 중재 정책 강화 가능"}},
    {{"keyword": "수수료", "count": 12, "context": "높은 수수료 부담", "platform_action": "성과 기반 수수료 구조 검토"}}
  ],
  "platform_pain_points": [
    {{"issue": "부당 환불", "frequency": "높음", "impact": "매출 직접 감소", "possible_fix": "플랫폼에서 할 수 있는 구체적 개선안"}}
  ],
  "sales_opportunity_keywords": ["매출 상승 기회와 연결되는 키워드들"],
  "retention_risk_keywords": ["사장님 이탈 위험과 연결되는 키워드들"],
  "competitor_mentions": "경쟁 플랫폼 언급 여부 및 맥락"
}}"""
    try:
        return _parse_json(_chat(prompt))
    except Exception as e:
        return {"error": str(e)}


def analyze_trends(posts: list[dict]) -> dict:
    """기간별 주제 트렌드 및 동향 분석"""
    text = _posts_to_text(posts)
    prompt = f"""{ROLE_CONTEXT}

아래 '아프니까 사장이다' 카페 게시글들의 시간적 흐름과 트렌드를 분석해주세요.
배달플랫폼 관련 이슈가 시간이 지남에 따라 어떻게 변화하는지,
사장님들의 니즈가 무엇인지 플랫폼 비즈니스 관점에서 파악하세요.

{text}

다음 JSON 형식으로만 응답하세요:
{{
  "trend_summary": "분석 기간 내 자영업자들의 주요 관심사 변화 요약 (3-4문장, 플랫폼 관점)",
  "topic_trends": [
    {{"topic": "부당 환불 이슈", "direction": "증가", "description": "트렌드 설명", "platform_implication": "플랫폼에 주는 시사점"}}
  ],
  "platform_usage_signals": "플랫폼 이용 행태 변화 신호 (주문량 증감 추정, 광고 활용도 등)",
  "emerging_needs": [
    {{"need": "사장님들의 신규 니즈", "urgency": "높음/중간/낮음", "monetization_opportunity": "플랫폼 수익화 연결 가능성"}}
  ],
  "competitive_landscape": "경쟁 플랫폼 이동 징후나 비교 언급 트렌드",
  "forecast": "향후 1-2개월 내 주요 이슈 예측 및 플랫폼이 선제적으로 대응해야 할 사항"
}}"""
    try:
        return _parse_json(_chat(prompt))
    except Exception as e:
        return {"error": str(e)}


def generate_report(posts: list[dict]) -> dict:
    """종합 인사이트 리포트 생성"""
    text = _posts_to_text(posts)
    prompt = f"""{ROLE_CONTEXT}

아래 '아프니까 사장이다' 카페 게시글 {len(posts)}개를 종합 분석하여
배달플랫폼 내부 보고용 인사이트 리포트를 작성해주세요.
모든 개선 제안은 플랫폼이 자체적으로 실행 가능한 것이어야 하며,
자영업자 매출 증대와 플랫폼 수익 성장을 동시에 달성하는 방향으로 작성하세요.

{text}

다음 JSON 형식으로만 응답하세요:
{{
  "executive_summary": "플랫폼 모니터링 관점의 핵심 현황 요약 (3-4문장)",
  "key_findings": [
    "발견 1: 자영업자들이 플랫폼에 가장 강하게 느끼는 불만은...",
    "발견 2: 플랫폼 기능 중 긍정적으로 언급되는 것은...",
    "발견 3: 매출 증대에 성공한 사례에서 공통적으로 활용한 것은..."
  ],
  "platform_pain_points": [
    {{"issue": "부당 환불 처리", "severity": "높음", "detail": "구체적 설명", "actionable_fix": "플랫폼이 실행할 수 있는 개선안"}}
  ],
  "revenue_opportunities": [
    {{"opportunity": "신규 수익 기회", "potential": "높음/중간/낮음", "implementation": "구체적 실행 방안"}}
  ],
  "retention_actions": [
    "사장님 이탈 방지를 위해 플랫폼이 즉시 할 수 있는 액션 1",
    "사장님 이탈 방지를 위해 플랫폼이 즉시 할 수 있는 액션 2"
  ],
  "priority_improvements": [
    {{"priority": 1, "improvement": "최우선 개선 사항", "expected_effect": "예상 효과 (사장님 매출 및 플랫폼 수익 관점)"}},
    {{"priority": 2, "improvement": "차순위 개선 사항", "expected_effect": "예상 효과"}}
  ],
  "data_summary": {{
    "total_posts_analyzed": {len(posts)},
    "date_range": "분석된 게시글의 날짜 범위",
    "main_issues": ["이슈1", "이슈2", "이슈3"]
  }}
}}"""
    try:
        return _parse_json(_chat(prompt))
    except Exception as e:
        return {"error": str(e)}
