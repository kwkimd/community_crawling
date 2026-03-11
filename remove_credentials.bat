@echo off
echo Google 자격 증명 파일을 Git 히스토리에서 제거 중...
echo.

REM Git 히스토리에서 파일 제거
git rm --cached google_credentials.json

REM .gitignore 업데이트 커밋
git add .gitignore

REM 커밋
git commit -m "Remove google_credentials.json from repository and update .gitignore"

echo.
echo 완료! 이제 푸시하세요:
echo git push origin main
echo.
pause
