@echo off
echo ========================================
echo   GitHub에 푸시
echo ========================================
echo.

REM Git 초기화
echo 1. Git 초기화...
git init

REM 모든 파일 추가
echo 2. 파일 추가...
git add .

REM 커밋
echo 3. 커밋 생성...
git commit -m "Deploy dashboard to GitHub"

REM 원격 저장소 추가
echo 4. 원격 저장소 연결...
git remote add origin https://github.com/kwkimd/community_crawling.git

REM 강제 푸시
echo 5. GitHub에 푸시...
git push -u origin main --force

echo.
echo ========================================
echo 완료!
echo https://github.com/kwkimd/community_crawling
echo ========================================
echo.
pause
