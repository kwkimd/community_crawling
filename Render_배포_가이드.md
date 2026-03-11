# 🚀 Render 자동 배포 가이드

GitHub에서 직접 Render로 자동 배포하는 방법입니다.

## 1단계: Render 계정 연결 (1회만)

### 1. Render 접속
https://render.com 접속

### 2. GitHub 계정으로 로그인
- "Get Started" 또는 "Sign Up" 클릭
- "Continue with GitHub" 선택
- GitHub 계정 인증

### 3. GitHub 저장소 권한 부여
- Render가 GitHub 저장소에 접근할 수 있도록 권한 부여
- `kwkimd/community_crawling` 저장소 선택

---

## 2단계: Web Service 생성

### 1. 새 서비스 생성
- Render 대시보드에서 "New +" 클릭
- "Web Service" 선택

### 2. 저장소 연결
- GitHub 탭에서 `kwkimd/community_crawling` 검색
- "Connect" 클릭

### 3. 서비스 설정

**Name (이름):**
```
community-dashboard
```

**Region (지역):**
```
Singapore (가장 가까운 지역)
```

**Branch (브랜치):**
```
main
```

**Root Directory (루트 디렉토리):**
```
(비워두기)
```

**Runtime (런타임):**
```
Python 3
```

**Build Command (빌드 명령):**
```
pip install -r requirements.txt
```

**Start Command (시작 명령):**
```
python dashboard_server.py
```

**Instance Type (인스턴스 타입):**
```
Free (무료)
```

### 4. 환경 변수 설정

"Advanced" 섹션에서 "Add Environment Variable" 클릭:

**변수 1:**
- Key: `GEMINI_API_KEY`
- Value: `AIzaSyAMXC6IEPC7YGEiuRlGgEXo2P6-wxKipRY`

**변수 2:**
- Key: `GEMINI_MODEL`
- Value: `gemini-3-flash-preview`

**변수 3 (자동 설정됨):**
- Key: `PORT`
- Value: (Render가 자동으로 설정)

### 5. 배포 시작
- "Create Web Service" 클릭
- 자동으로 빌드 및 배포 시작

---

## 3단계: 배포 확인

### 빌드 로그 확인
- 배포 진행 상황을 실시간으로 확인
- 예상 소요 시간: 2-3분

### 배포 완료
빌드가 성공하면:
```
==> Your service is live 🎉
```

### URL 확인
Render가 자동으로 생성한 URL:
```
https://community-dashboard-xxxx.onrender.com
```

---

## 4단계: 자동 배포 설정 완료!

이제부터는:
1. GitHub에 코드를 푸시하면
2. Render가 자동으로 감지하고
3. 자동으로 재배포됩니다!

```bash
git add .
git commit -m "Update dashboard"
git push origin main
```

→ Render가 자동으로 배포 시작!

---

## 배포된 대시보드 접속

### 메인 페이지
```
https://your-app-name.onrender.com/
```

### API 문서
```
https://your-app-name.onrender.com/docs
```

### 헬스체크
```
https://your-app-name.onrender.com/health
```

---

## 주의사항

### 무료 플랜 제한
- ✅ 월 750시간 무료 (충분함)
- ⚠️ 15분 비활성 시 슬립 모드
- ⚠️ 슬립 모드에서 깨어나는데 30초 소요
- ✅ 자동 HTTPS 제공
- ✅ 무제한 배포

### 슬립 모드 방지 (선택사항)
외부 모니터링 서비스로 주기적으로 접속:
- UptimeRobot (무료): https://uptimerobot.com
- 5분마다 헬스체크 요청

### 데이터베이스
- ⚠️ SQLite는 휘발성 (재배포 시 초기화)
- 영구 저장 필요 시 PostgreSQL 사용 권장

---

## 트러블슈팅

### 빌드 실패
**증상:** Build failed
**해결:**
1. Render 로그 확인
2. `requirements.txt` 확인
3. Python 버전 확인

### 서버 시작 실패
**증상:** Service failed to start
**해결:**
1. 환경 변수 확인
2. Start Command 확인: `python dashboard_server.py`
3. 로그에서 오류 확인

### 환경 변수 수정
1. Render 대시보드 → 서비스 선택
2. "Environment" 탭
3. 변수 수정 후 자동 재배포

---

## 배포 상태 확인

### Render 대시보드
https://dashboard.render.com

### 배포 로그
- "Events" 탭: 배포 이력
- "Logs" 탭: 실시간 서버 로그
- "Metrics" 탭: CPU, 메모리 사용량

---

## 완료! 🎉

이제 GitHub에 푸시만 하면 자동으로 배포됩니다!

**배포 URL을 팀원들과 공유하세요.**
