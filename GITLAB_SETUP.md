# GitLab CI/CD 자동 모니터링 설정 가이드

## 개요

네이버 카페(아프니까사장이다) 자동 크롤링을 GitLab CI/CD Scheduled Pipeline으로 실행합니다.

- 실행 주기: 매 정각 (1시간마다)
- 수집 대상: 인기글 + 메뉴460
- 저장: Google Sheets 시트1
- 알림: Slack (키워드 매칭 시)

---

## 1. 사전 준비

### 로컬 환경에서 세션 생성

```bash
# 1. 크롤러 실행 → 네이버 로그인
통합_크롤러_런처.bat

# 2. 브라우저에서 네이버 로그인 후 "세션 저장" 클릭
# → naver_session.json 생성됨

# 3. base64 인코딩 값 확인
python update_naver_session.py
python update_naver_session.py --all  # 구글 인증 파일도 함께
```

---

## 2. GitLab CI/CD Variables 설정

**경로**: GitLab > 프로젝트 > Settings > CI/CD > Variables

| 변수명 | 값 | 옵션 |
|--------|-----|------|
| `NAVER_SESSION_B64` | `update_naver_session.py` 출력값 | Masked=Yes |
| `GOOGLE_CREDENTIALS_B64` | `update_naver_session.py --credentials` 출력값 | Masked=Yes |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/services/...` | Masked=Yes |
| `GOOGLE_SHEETS_URL` | `https://docs.google.com/spreadsheets/d/...` | Masked=No |

---

## 3. Pipeline Schedule 설정

**경로**: GitLab > 프로젝트 > CI/CD > Schedules > New schedule

- Description: `네이버 카페 자동 모니터링`
- Interval Pattern: `0 * * * *` (매 정각)
- Cron Timezone: `Asia/Seoul`
- Target branch: `main`
- Activated: Yes

---

## 4. 수동 실행

GitLab > CI/CD > Pipelines > Run pipeline

- Branch: `main`
- 변수 추가 없이 바로 실행 가능 (CI/CD Variables에서 자동 주입)

---

## 5. 세션 만료 시 대응

세션이 만료되면:
1. Slack에 "⚠️ 네이버 세션 만료" 알림 수신
2. GitLab Pipeline이 실패 상태로 표시

**갱신 절차:**

```bash
# 1. 로컬에서 크롤러 실행 → 네이버 재로그인
통합_크롤러_런처.bat
# 브라우저에서 로그인 → 세션 저장

# 2. base64 값 생성
python update_naver_session.py

# 3. GitLab 변수 업데이트
# Settings > CI/CD > Variables > NAVER_SESSION_B64 편집 → 새 값 붙여넣기
```

세션 유효 기간: 약 30~90일 (네이버 정책에 따라 변동)

---

## 6. 로컬 테스트

CI 환경 없이 로컬에서 직접 실행 가능:

```bash
python naver_cafe_monitor.py
```

- `.env` 파일의 `SLACK_WEBHOOK_URL` 사용
- `naver_session.json` 파일 직접 참조
- `sheets_config.json`의 URL 사용

---

## 7. 파일 구조

```
C:\community_crawling\
├── naver_cafe_monitor.py      # CI/CD 전용 독립 실행 스크립트
├── update_naver_session.py    # 세션 → base64 변환 헬퍼
├── .gitlab-ci.yml             # 파이프라인 정의
├── GITLAB_SETUP.md            # 이 문서
├── google_sheets_sync.py      # get_existing_urls() 추가됨
├── scraper.py                 # 기존 크롤링 엔진 (재사용)
├── slack_notifier.py          # 기존 Slack 알림 (재사용)
└── naver_session.json         # 네이버 세션 쿠키 (gitignore)
```

---

## 8. 트러블슈팅

### Pipeline 실패: "세션 만료"
→ 위 5번 절차 수행

### Pipeline 실패: "Google Sheets 연결 실패"
→ `GOOGLE_CREDENTIALS_B64` 변수 확인, 서비스 계정에 시트 공유 권한 확인

### Pipeline 실패: "모듈 import 오류"
→ `requirements.txt`에 필요한 패키지가 모두 포함되어 있는지 확인

### 신규 게시글이 0건
→ 정상 동작. 1시간 내 새 글이 없으면 0건으로 종료됨.
