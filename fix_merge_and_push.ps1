Write-Host "===== Git 병합 충돌 해결 및 푸시 =====" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/7] 현재 Git 상태 확인..." -ForegroundColor Yellow
git status
Write-Host ""

Write-Host "[2/7] 병합 중단..." -ForegroundColor Yellow
git merge --abort 2>&1
Write-Host ""

Write-Host "[3/7] google_credentials.json 파일을 Git 추적에서 제거..." -ForegroundColor Yellow
git rm --cached google_credentials.json 2>&1
Write-Host ""

Write-Host "[4/7] .gitignore 확인 (이미 추가되어 있음)" -ForegroundColor Yellow
Get-Content .gitignore | Select-String "google_credentials.json"
Write-Host ""

Write-Host "[5/7] 모든 변경사항 추가..." -ForegroundColor Yellow
git add .
Write-Host ""

Write-Host "[6/7] 커밋..." -ForegroundColor Yellow
git commit -m "Add deployment configuration for cloud hosting"
Write-Host ""

Write-Host "[7/7] 강제 푸시..." -ForegroundColor Yellow
git push origin main --force
Write-Host ""

Write-Host "===== 완료 =====" -ForegroundColor Green
