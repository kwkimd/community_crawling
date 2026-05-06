#!/usr/bin/env python3
"""
네이버 세션 → base64 변환 헬퍼
로컬에서 세션 갱신 후 GitLab CI/CD 변수 업데이트를 위한 도구

사용법:
  1. 로컬에서 크롤러 실행하여 네이버 로그인 (세션 저장)
  2. python update_naver_session.py 실행
  3. 출력된 base64 문자열을 GitLab 변수에 붙여넣기
"""
import base64
import sys
from pathlib import Path

SESSION_FILE = Path(__file__).parent / "naver_session.json"
CREDENTIALS_FILE = Path(__file__).parent / "google_credentials.json"


def encode_file(filepath: Path, var_name: str):
    """파일을 base64로 인코딩하여 출력"""
    if not filepath.exists():
        print(f"[오류] {filepath} 파일이 없습니다.")
        return False

    content = filepath.read_bytes()
    encoded = base64.b64encode(content).decode("utf-8")

    print(f"\n{'='*60}")
    print(f"  {var_name}")
    print(f"  파일: {filepath.name} ({len(content):,} bytes)")
    print(f"{'='*60}")
    print(f"\n{encoded}\n")
    print(f"{'='*60}")
    print(f"위 값을 GitLab > Settings > CI/CD > Variables에 붙여넣으세요.")
    print(f"변수명: {var_name}")
    print(f"옵션: Masked=Yes, Protected=No, Expand=No")
    print()
    return True


def main():
    print("=" * 60)
    print("  GitLab CI/CD 변수 업데이트 헬퍼")
    print("=" * 60)

    if "--all" in sys.argv:
        # 모든 인증 파일 변환
        encode_file(SESSION_FILE, "NAVER_SESSION_B64")
        encode_file(CREDENTIALS_FILE, "GOOGLE_CREDENTIALS_B64")
    elif "--credentials" in sys.argv:
        encode_file(CREDENTIALS_FILE, "GOOGLE_CREDENTIALS_B64")
    else:
        # 기본: 세션 파일만
        if not encode_file(SESSION_FILE, "NAVER_SESSION_B64"):
            print("\n세션 파일이 없습니다. 먼저 크롤러를 실행하여 네이버에 로그인하세요:")
            print("  1. 통합_크롤러_런처.bat 실행")
            print("  2. 브라우저 열기 → 네이버 로그인")
            print("  3. 세션 저장 버튼 클릭")
            print("  4. 이 스크립트 다시 실행")
            sys.exit(1)

    print("\n[안내] GitLab 변수 설정 경로:")
    print("  GitLab > 프로젝트 > Settings > CI/CD > Variables > Add variable")
    print()
    print("  필요한 변수 목록:")
    print("  - NAVER_SESSION_B64    : 네이버 세션 (위 출력값)")
    print("  - GOOGLE_CREDENTIALS_B64 : 구글 서비스 계정 키")
    print("  - SLACK_WEBHOOK_URL    : Slack Webhook URL")
    print("  - GOOGLE_SHEETS_URL    : 스프레드시트 URL")


if __name__ == "__main__":
    main()
