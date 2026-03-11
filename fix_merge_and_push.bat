@echo off
echo ===== Git 병합 충돌 해결 및 푸시 =====
echo.

echo [1/7] 현재 Git 상태 확인...
git status
echo.

echo [2/7] 병합 중단...
git merge --abort
echo.

echo [3/7] google_credentials.json 파일을 Git 추적에서 제거...
git rm --cached google_credentials.json
echo.

echo [4/7] .gitignore 확인 (이미 추가되어 있음)
type .gitignore | findstr google_credentials.json
echo.

echo [5/7] 모든 변경사항 추가...
git add .
echo.

echo [6/7] 커밋...
git commit -m "Add deployment configuration for cloud hosting"
echo.

echo [7/7] 강제 푸시...
git push origin main --force
echo.

echo ===== 완료 =====
pause
