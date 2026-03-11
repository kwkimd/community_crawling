@echo off
chcp 65001 >nul
echo 🚀 GitHub 배포 준비 중...
echo.

REM Git 상태 확인
if not exist .git (
    echo ❌ Git 저장소가 초기화되지 않았습니다.
    echo 다음 명령어를 실행하세요:
    echo   git init
    echo   git remote add origin https://github.com/kwkimd/community_crawling.git
    exit /b 1
)

REM 변경사항 확인
echo 📝 변경된 파일 확인 중...
git status
echo.

REM 스테이징
echo ➕ 파일 추가 중...
git add .
echo.

REM 커밋
set /p commit_message="💾 커밋 메시지를 입력하세요 (Enter = 기본 메시지): "
if "%commit_message%"=="" set commit_message=Deploy dashboard to GitHub
git commit -m "%commit_message%"
echo.

REM 푸시
echo 🌐 GitHub에 푸시 중...
git push origin main
echo.

echo ✅ 배포 완료!
echo.
echo 다음 단계:
echo 1. https://render.com 또는 https://railway.app 접속
echo 2. GitHub 저장소 연결
echo 3. 환경 변수 설정 (GEMINI_API_KEY)
echo 4. 배포 시작
echo.
pause
