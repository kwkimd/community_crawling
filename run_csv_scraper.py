#!/usr/bin/env python3
"""
아프니까사장이다 카페 데이터를 CSV 형식으로 수집하는 스크립트

사용법:
    python run_csv_scraper.py
    
설정 가능한 옵션들:
- 모니터링명: 수집할 주제 (예: "1인분(한그릇)", "배달료", "수수료" 등)
- 검색 키워드: 검색할 키워드 (예: "배민", "쿠팡이츠", "배달의민족" 등)  
- 수집 개수: 최대 수집할 게시글 수 (0이면 전체)
- 날짜 범위: 수집할 날짜 범위
- 출력 파일: CSV 파일명
"""

import asyncio
import sys
from datetime import datetime, timedelta
import csv_scraper


async def main():
    print("=" * 60)
    print("🍕 아프니까사장이다 카페 CSV 데이터 수집기")
    print("=" * 60)
    
    # 설정값 입력받기
    print("\n📋 수집 설정을 입력해주세요:")
    
    monitoring_name = input("모니터링명 (기본값: 1인분(한그릇)): ").strip()
    if not monitoring_name:
        monitoring_name = "1인분(한그릇)"
    
    search_keyword = input("검색 키워드 (기본값: 배민): ").strip()
    if not search_keyword:
        search_keyword = "배민"
    
    max_posts_input = input("최대 수집 개수 (기본값: 50, 0=전체): ").strip()
    try:
        max_posts = int(max_posts_input) if max_posts_input else 50
    except ValueError:
        max_posts = 50
    
    # 날짜 범위 설정
    print("\n📅 날짜 범위 설정 (YYYY-MM-DD 형식, 엔터로 건너뛰기):")
    date_from = input("시작 날짜: ").strip()
    date_to = input("종료 날짜: ").strip()
    
    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_filename = f"아프니까사장이다_{monitoring_name}_{timestamp}.csv"
    output_file = input(f"출력 파일명 (기본값: {default_filename}): ").strip()
    if not output_file:
        output_file = default_filename
    
    print(f"\n🔧 수집 설정:")
    print(f"   모니터링명: {monitoring_name}")
    print(f"   검색 키워드: {search_keyword}")
    print(f"   최대 개수: {max_posts if max_posts > 0 else '전체'}")
    print(f"   날짜 범위: {date_from or '제한없음'} ~ {date_to or '제한없음'}")
    print(f"   출력 파일: {output_file}")
    
    confirm = input("\n계속하시겠습니까? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("수집을 취소했습니다.")
        return
    
    print("\n🚀 브라우저를 열고 있습니다...")
    
    try:
        # 브라우저 열기
        await csv_scraper.open_browser()
        
        print("✅ 브라우저가 열렸습니다.")
        print("📌 네이버에 로그인하고 아프니까사장이다 카페로 이동해주세요.")
        print("📌 수집할 게시판 페이지로 이동한 후 엔터를 눌러주세요.")
        
        input("준비가 완료되면 엔터를 눌러주세요...")
        
        print(f"\n📊 데이터 수집을 시작합니다...")
        
        # CSV 수집 시작
        await csv_scraper.start_csv_scraping(
            max_posts=max_posts,
            monitoring_name=monitoring_name,
            search_keyword=search_keyword,
            date_from=date_from,
            date_to=date_to,
            output_file=output_file
        )
        
        # 수집 상태 모니터링
        while True:
            status = csv_scraper.get_status()
            
            if status["status"] == "scraping":
                progress = status["progress"]
                total = status["total"]
                message = status["message"]
                
                if total > 0:
                    percent = (progress / total) * 100
                    print(f"\r진행률: {progress}/{total} ({percent:.1f}%) - {message}", end="", flush=True)
                else:
                    print(f"\r{message}", end="", flush=True)
                    
            elif status["status"] == "done":
                print(f"\n✅ {status['message']}")
                break
                
            elif status["status"] == "error":
                print(f"\n❌ 오류: {status['message']}")
                break
                
            await asyncio.sleep(1)
        
        print(f"\n📁 CSV 파일이 저장되었습니다: {output_file}")
        
        # 결과 미리보기
        try:
            with open(output_file, 'r', encoding='utf-8-sig') as f:
                reader = list(csv.reader(f))
                if len(reader) > 1:
                    print(f"\n📋 수집 결과 미리보기 (총 {len(reader)-1}개 게시글):")
                    print("-" * 80)
                    for i, row in enumerate(reader[1:6]):  # 헤더 제외하고 최대 5개
                        if len(row) >= 14:  # 제목 컬럼 확인
                            print(f"{i+1}. {row[13][:50]}...")  # 제목 컬럼
                    if len(reader) > 6:
                        print(f"... 외 {len(reader)-6}개")
        except Exception as e:
            print(f"미리보기 생성 실패: {e}")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  사용자가 수집을 중단했습니다.")
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
    finally:
        print("\n🔄 브라우저를 닫는 중...")
        await csv_scraper.close_browser()
        print("✅ 완료되었습니다.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램이 종료되었습니다.")
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(1)