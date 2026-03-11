# GitHub 푸시 스크립트
Write-Host "🚀 GitHub 배포 시작..." -ForegroundColor Green
Write-Host ""

# Git 상태 확인
Write-Host "📝 Git 상태 확인 중..." -ForegroundColor Yellow
git status

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Git이 설치되지 않았거나 저장소가 초기화되지 않았습니다." -ForegroundColor Red
    Write-Host "Git을 설치하거나 'git init' 명령을 실행하세요." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "➕ 파일 추가 중..." -ForegroundColor Yellow
git add .

Write-Host ""
Write-Host "💾 커밋 생성 중..." -ForegroundColor Yellow
git commit -m "Add deployment configuration for GitHub hosting"

Write-Host ""
Write-Host "🌐 GitHub에 푸시 중..." -ForegroundColor Yellow
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ GitHub 푸시 완료!" -ForegroundColor Green
    Write-Host ""
    Write-Host "다음 단계:" -ForegroundColor Cyan
    Write-Host "1. https://render.com 또는 https://railway.app 접속"
    Write-Host "2. GitHub 저장소 연결: kwkimd/community_crawling"
    Write-Host "3. 환경 변수 설정:"
    Write-Host "   - GEMINI_API_KEY: (API 키 입력)"
    Write-Host "   - GEMINI_MODEL: gemini-2.0-flash"
    Write-Host "4. 배포 시작"
    Write-Host ""
    Write-Host "📖 자세한 내용은 DEPLOYMENT.md 참고" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "❌ 푸시 실패" -ForegroundColor Red
    Write-Host "원격 저장소가 설정되지 않았을 수 있습니다." -ForegroundColor Yellow
    Write-Host "다음 명령을 실행하세요:" -ForegroundColor Yellow
    Write-Host "git remote add origin https://github.com/kwkimd/community_crawling.git" -ForegroundColor White
}

Write-Host ""
Read-Host "계속하려면 Enter를 누르세요"
