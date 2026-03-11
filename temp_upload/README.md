# 아프니까사장이다 대시보드

네이버 카페 게시글 분석 대시보드 - 클라우드 배포용

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/kwkimd/community_crawling)

## 빠른 시작

### 원클릭 배포 (추천)

위의 "Deploy to Render" 버튼을 클릭하면 자동으로 배포됩니다!

필요한 것:
- GitHub 계정
- Gemini API 키 ([여기서 발급](https://aistudio.google.com/app/apikey))

### 수동 배포

자세한 가이드는 [Render_배포_가이드.md](Render_배포_가이드.md)를 참고하세요.

## 주요 기능

- 게시글 데이터 조회 및 필터링
- AI 기반 감성 분석 (Gemini API)
- 키워드 추출 및 트렌드 분석
- Excel 내보내기
- 종합 리포트 생성

## 기술 스택

- FastAPI + Uvicorn
- SQLite
- Google Gemini API
- Jinja2 Templates
- Chart.js

## 로컬 실행

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일을 생성하고 Gemini API 키를 설정하세요:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
```

### 3. 서버 실행

```bash
python dashboard_server.py
```

브라우저에서 `http://localhost:8000` 접속

## 클라우드 배포

### Render 배포

1. GitHub 저장소 연결
2. 환경 변수 설정:
   - `GEMINI_API_KEY`: Gemini API 키
   - `GEMINI_MODEL`: gemini-2.0-flash
3. 빌드 명령: `pip install -r requirements.txt`
4. 시작 명령: `python dashboard_server.py`

### Railway 배포

1. GitHub 저장소 연결
2. 환경 변수 설정 (위와 동일)
3. 자동 배포 시작

## API 엔드포인트

- `GET /` - 대시보드 메인 페이지
- `GET /api/posts` - 게시글 목록 조회
- `GET /api/posts/export` - Excel 다운로드
- `POST /api/analyze` - AI 분석 실행
- `GET /api/stats` - 통계 조회
- `GET /health` - 헬스체크

## 주의사항

- `.env` 파일은 절대 커밋하지 마세요
- 데이터베이스 파일(`cafe_posts.db`)은 로컬에서만 사용됩니다
- 클라우드 배포 시 데이터는 휘발성입니다 (재시작 시 초기화)

## 라이선스

MIT
