# ⚡ 빠른 시작 가이드

## 3분 안에 배포하기

### 1️⃣ GitHub 푸시 (1분)

```bash
# Windows 사용자
deploy.bat

# 또는 수동으로
git add .
git commit -m "Deploy dashboard"
git push origin main
```

### 2️⃣ Render 배포 (2분)

1. https://render.com 접속 → GitHub 로그인
2. "New +" → "Web Service" → 저장소 선택
3. 환경 변수 추가:
   - `GEMINI_API_KEY`: [여기서 발급](https://aistudio.google.com/app/apikey)
   - `GEMINI_MODEL`: `gemini-2.0-flash`
4. "Create Web Service" 클릭

### 3️⃣ 완료! ✅

배포된 URL로 접속하세요.

---

## 더 자세한 가이드

- 📖 [시작하기.md](시작하기.md) - 전체 과정 설명
- 📋 [배포_체크리스트.md](배포_체크리스트.md) - 단계별 체크리스트
- 🔧 [DEPLOYMENT.md](DEPLOYMENT.md) - 상세 배포 가이드
