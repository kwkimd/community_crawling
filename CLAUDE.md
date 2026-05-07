# Community Crawling & Dashboard Project

## Project Overview
- 배달앱(배달의민족, 요기요, 쿠팡이츠 등) 관련 커뮤니티 여론·이슈 크롤링 및 트렌드 분석 프로젝트
- 경로: `C:\community_crawling`
- 목적: 각종 온라인 커뮤니티에서 배달앱 관련 게시글을 수집 → 이슈 탐지 → 트렌드 대시보드 시각화

## Tech Stack
- Language: Python 3.10+
- Crawling: Selenium, BeautifulSoup4, requests
- Data: pandas, SQLite 또는 PostgreSQL
- Dashboard: Streamlit 또는 Dash (Plotly)
- NLP/분석: KoNLPy, scikit-learn, wordcloud
- Scheduling: APScheduler 또는 cron

## Architecture
```
community_crawling/
├── CLAUDE.md                  # 이 파일 (프로젝트 규칙)
├── .claude/rules/             # 모듈별 세부 규칙
├── crawlers/                  # 커뮤니티별 크롤러 모듈
├── processors/                # 데이터 전처리·분석 모듈
├── dashboard/                 # 대시보드 UI
├── database/                  # DB 스키마·마이그레이션
├── config/                    # 설정 파일 (크롤링 대상, 키워드 등)
├── logs/                      # 크롤링 로그
├── data/                      # 수집 데이터 저장
├── tests/                     # 테스트 코드
└── docs/                      # 프로젝트 문서
```

## Coding Conventions
- 모든 Python 파일에 타입 힌트 사용
- docstring은 한국어로 작성
- 함수명·변수명은 snake_case, 클래스명은 PascalCase
- 크롤러 모듈은 `BaseCrawler` 추상 클래스를 상속하여 구현
- 에러 핸들링 시 반드시 logging 모듈 사용 (print 금지)
- 크롤링 결과는 항상 DataFrame으로 변환 후 저장

## Key Commands
- 크롤러 실행: `python -m crawlers.run --target [커뮤니티명]`
- 대시보드 실행: `streamlit run dashboard/app.py`
- 테스트: `pytest tests/ -v`
- 린트: `ruff check . --fix`

## Critical Rules
- 크롤링 시 반드시 rate limiting 적용 (최소 2초 간격)
- robots.txt 준수, 서버 부하 최소화
- 개인정보(닉네임, 연락처 등)는 수집 즉시 마스킹 처리
- API 키, 비밀번호 등은 절대 코드에 하드코딩 금지 → `.env` 파일 사용
- `.env` 파일은 반드시 `.gitignore`에 포함
- 크롤링 데이터에 날짜·시간·출처 메타데이터 필수 포함

## Git 원격 저장소

이 프로젝트는 원격 저장소가 2개입니다:
- `origin` → GitHub (`github.com/kwkimd/community_crawling`)
- `gitlab` → 사내 GitLab (`git.baemin.in/kwkimd/community_crawling`) ← **CI/CD 스케줄 파이프라인이 여기서 실행됨**

**아프니까 사장이다 모니터링 관련 변경사항은 반드시 두 곳 모두 푸시:**
```bash
git push origin main
git push gitlab main
```

GitLab에만 `.gitlab-ci.yml` 스케줄이 있으므로, GitLab에 푸시해야 다음 정각 실행에 반영됩니다.

## Workflow
1. 새 크롤러 추가 시: `crawlers/` 하위에 모듈 생성 → `BaseCrawler` 상속 → config에 대상 등록
2. 데이터 분석 추가 시: `processors/` 하위에 분석 모듈 생성 → 대시보드에 차트 연결
3. 커밋 메시지: `feat:`, `fix:`, `refactor:`, `docs:` 접두사 사용 (한국어 본문 가능)
