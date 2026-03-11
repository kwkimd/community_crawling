@echo off
echo ========================================
echo   새로운 방식으로 GitHub에 푸시
echo ========================================
echo.

REM 1. 임시 폴더 생성
echo 1. 임시 폴더 생성 중...
mkdir temp_upload 2>nul

REM 2. 필요한 파일만 복사 (민감한 파일 제외)
echo 2. 필요한 파일 복사 중...
copy dashboard_server.py temp_upload\
copy database.py temp_upload\
copy gemini_analyzer.py temp_upload\
copy requirements.txt temp_upload\
copy runtime.txt temp_upload\
copy Procfile temp_upload\
copy render.yaml temp_upload\
copy Dockerfile temp_upload\
copy .dockerignore temp_upload\
copy .gitignore temp_upload\
copy README.md temp_upload\
copy DEPLOYMENT.md temp_upload\
copy Render_배포_가이드.md temp_upload\

REM 3. templates 폴더 복사
echo 3. templates 폴더 복사 중...
xcopy templates temp_upload\templates\ /E /I /Y

REM 4. .github 폴더 복사
echo 4. .github 폴더 복사 중...
xcopy .github temp_upload\.github\ /E /I /Y

echo.
echo ========================================
echo 완료!
echo.
echo temp_upload 폴더가 생성되었습니다.
echo 이제 다음 단계를 진행하세요:
echo.
echo 1. temp_upload 폴더로 이동
echo 2. git init
echo 3. git add .
echo 4. git commit -m "Initial commit"
echo 5. git remote add origin https://github.com/kwkimd/community_crawling.git
echo 6. git push -u origin main --force
echo.
pause
