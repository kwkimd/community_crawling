# Git 병합 충돌 해결 및 GitHub 푸시 가이드

## 🎯 목표
https://github.com/kwkimd/community_crawling 저장소에 배포 설정 파일들을 업로드

## ⚠️ 주의사항
- `.env` 파일은 절대 푸시하지 말 것 (`.gitignore`에 포함됨)
- `google_credentials.json`도 제외
- `--force` 옵션으로 기존 히스토리의 민감한 파일 문제 해결

## 📋 실행 방법

### 방법 1: PowerShell 스크립트 실행 (권장)
```powershell
.\fix_merge_and_push.ps1
```

### 방법 2: 배치 파일 실행
```cmd
fix_merge_and_push.bat
```

### 방법 3: 수동으로 명령어 실행
PowerShell 또는 Git Bash에서 다음 명령어를 순서대로 실행하세요:

```bash
# 1. 현재 Git 상태 확인
git status

# 2. 병합 중단
git merge --abort

# 3. google_credentials.json 파일을 Git 추적에서 제거
git rm --cached google_credentials.json

# 4. .gitignore 확인 (이미 추가되어 있음)
cat .gitignore | grep google_credentials.json

# 5. 모든 변경사항 추가
git add .

# 6. 커밋
git commit -m "Add deployment configuration for cloud hosting"

# 7. 강제 푸시
git push origin main --force
```

## ✅ 확인사항

푸시 후 GitHub 저장소에서 다음을 확인하세요:
- ✅ `.env` 파일이 없는지 확인
- ✅ `google_credentials.json` 파일이 없는지 확인
- ✅ `DEPLOYMENT.md`, `README.md` 등 배포 문서가 있는지 확인
- ✅ `requirements.txt`, `Dockerfile` 등 배포 설정 파일이 있는지 확인

## 🔧 문제 해결

### "fatal: not in a merge" 오류가 발생하는 경우
병합 상태가 아니므로 2번 단계를 건너뛰고 3번부터 진행하세요.

### "error: pathspec 'google_credentials.json' did not match any files" 오류
파일이 이미 추적에서 제거되었으므로 3번 단계를 건너뛰고 5번부터 진행하세요.

### 푸시가 거부되는 경우
`--force` 옵션을 사용하여 강제 푸시하세요. 이는 기존 히스토리의 민감한 파일을 제거하기 위해 필요합니다.
