# 배포 가이드

## GitHub 저장소 설정

### 1. 저장소 푸시

```bash
git add .
git commit -m "Add deployment configuration"
git push origin main
```

## Render 배포 (추천)

### 1. Render 계정 생성
- https://render.com 접속 후 GitHub 계정으로 로그인

### 2. 새 Web Service 생성
1. Dashboard → "New +" → "Web Service"
2. GitHub 저장소 연결: `kwkimd/community_crawling`
3. 설정:
   - Name: `community-dashboard`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python dashboard_server.py`

### 3. 환경 변수 설정
Environment 탭에서 추가:
- `GEMINI_API_KEY`: (Gemini API 키 입력)
- `GEMINI_MODEL`: `gemini-2.0-flash`

### 4. 배포
- "Create Web Service" 클릭
- 자동으로 빌드 및 배포 시작
- 완료 후 제공되는 URL로 접속

## Railway 배포

### 1. Railway 계정 생성
- https://railway.app 접속 후 GitHub 계정으로 로그인

### 2. 새 프로젝트 생성
1. "New Project" → "Deploy from GitHub repo"
2. 저장소 선택: `kwkimd/community_crawling`

### 3. 환경 변수 설정
Variables 탭에서 추가:
- `GEMINI_API_KEY`: (Gemini API 키 입력)
- `GEMINI_MODEL`: `gemini-2.0-flash`

### 4. 배포
- 자동으로 배포 시작
- Settings → Networking에서 도메인 생성

## Heroku 배포

### 1. Heroku CLI 설치
```bash
# Windows
winget install Heroku.HerokuCLI
```

### 2. 로그인 및 앱 생성
```bash
heroku login
heroku create community-dashboard
```

### 3. 환경 변수 설정
```bash
heroku config:set GEMINI_API_KEY=your_api_key_here
heroku config:set GEMINI_MODEL=gemini-2.0-flash
```

### 4. 배포
```bash
git push heroku main
```

## 로컬 테스트

배포 전 로컬에서 테스트:

```bash
# 환경 변수 설정
export GEMINI_API_KEY=your_api_key_here
export GEMINI_MODEL=gemini-2.0-flash
export PORT=8000

# 서버 실행
python dashboard_server.py
```

브라우저에서 `http://localhost:8000` 접속

## 주의사항

### 데이터베이스
- 클라우드 배포 시 SQLite는 휘발성입니다
- 서버 재시작 시 데이터가 초기화됩니다
- 영구 저장이 필요하면 PostgreSQL 등 외부 DB 사용 권장

### API 키 보안
- `.env` 파일은 절대 커밋하지 마세요
- 환경 변수로만 API 키를 설정하세요
- `.gitignore`에 `.env`가 포함되어 있는지 확인하세요

### 포트 설정
- 클라우드 플랫폼은 자동으로 `PORT` 환경 변수를 설정합니다
- `dashboard_server.py`는 이를 자동으로 감지합니다

## 트러블슈팅

### 빌드 실패
```bash
# requirements.txt 확인
pip install -r requirements.txt

# Python 버전 확인 (3.11 권장)
python --version
```

### 서버 시작 실패
- 환경 변수가 올바르게 설정되었는지 확인
- 로그에서 오류 메시지 확인

### 데이터베이스 오류
- `database.py`의 `init_db()` 함수가 정상 실행되는지 확인
- SQLite 파일 권한 확인

## 모니터링

### 헬스체크
```bash
curl https://your-app-url.com/health
```

응답 예시:
```json
{
  "status": "healthy",
  "service": "dashboard",
  "total_posts": 0
}
```

### 로그 확인
- Render: Dashboard → Logs
- Railway: Deployments → View Logs
- Heroku: `heroku logs --tail`
