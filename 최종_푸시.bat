@echo off
chcp 65001 >nul
echo ========================================
echo   GitHub 푸시 (사용자 정보 포함)
echo ========================================
echo.

REM Git 사용자 정보 설정
echo 1. Git 사용자 정보 설정...
git config user.email "kwkimd@woowahan.com"
git config user.name "kwkimd"

REM 파일 추가
echo 2. 파일 추가...
git add .

REM 커밋
echo 3. 커밋 생성...
git commit -m "Initial commit: Deploy dashboard to GitHub"

REM 푸시
echo 4. GitHub에 푸시...
git push -u origin main --force

echo.
echo ========================================
echo 완료!
echo https://github.com/kwkimd/community_crawling
echo ========================================
pause
