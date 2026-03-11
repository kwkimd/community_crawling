@echo off
echo GitHub 강제 푸시 스크립트
echo ================================
echo.

REM google_credentials.json 제거
echo 1. 민감한 파일 제거 중...
git rm --cached google_credentials.json 2>nul
git rm --cached .env 2>nul

REM 모든 변경사항 추가
echo 2. 파일 추가 중...
git add .

REM 커밋
echo 3. 커밋 생성 중...
git commit -m "Add deployment configuration for cloud hosting"

REM 강제 푸시
echo 4. GitHub에 강제 푸시 중...
git push origin main --force

echo.
echo ================================
echo 완료!
echo GitHub 저장소를 확인하세요:
echo https://github.com/kwkimd/community_crawling
echo.
pause
