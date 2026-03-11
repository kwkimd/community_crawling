FROM python:3.11-slim

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY dashboard_server.py .
COPY database.py .
COPY gemini_analyzer.py .
COPY templates/ templates/

# 포트 노출
EXPOSE 8000

# 환경 변수 기본값
ENV PORT=8000
ENV GEMINI_MODEL=gemini-2.0-flash

# 서버 실행
CMD ["python", "dashboard_server.py"]
