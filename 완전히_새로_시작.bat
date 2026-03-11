@echo off
echo ========================================
echo   Git 히스토리 완전 초기화
echo ========================================
echo.
echo 이 스크립트는 .git 폴더를 삭제하고
echo 완전히 새로운 Git 저장소로 시작합니다.
echo.
pause

REM .git 폴더 삭제
echo 1. 기존 Git 히스토리 삭제 중...
rmdir /s /q .git

REM 새로운 Git 저장소 초기화
echo 2. 새 Git 저장소 초기화...
git init

REM 기본 브랜치를 main으로 설정
echo 3. 기본 브랜치 설정...
git branch -M main

REM 모든 파일 추가 (.gitignore가 자동으로 제외)
echo 4. 파일 추가 중...
git add .

REM 커밋
echo 5. 첫 커밋 생성...
git commit -m "Initial commit: Deploy dashboard to GitHub"

REM 원격 저장소 연결
echo 6. GitHub 저장소 연결...
git remote add origin https://github.com/kwkimd/community_crawling.git

REM 강제 푸시
echo 7. GitHub에 푸시...
git push -u origin main --force

echo.
echo ========================================
echo 완료!
echo https://github.com/kwkimd/community_crawling
echo ========================================
pause
