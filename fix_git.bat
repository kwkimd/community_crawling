@echo off
echo 병합 충돌 해결 중...

REM 병합 중단
git merge --abort

REM 현재 상태 확인
git status

echo.
echo 병합이 중단되었습니다.
echo 이제 다시 커밋하고 푸시하세요:
echo.
echo git add .
echo git commit -m "Add deployment configuration"
echo git push origin main
echo.
pause
