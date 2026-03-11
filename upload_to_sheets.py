#!/usr/bin/env python3
"""
특정 구글 시트에 데이터 업로드
"""
from google_sheets_sync import GoogleSheetsSync

def upload_to_specific_sheet():
    """지정된 구글 시트에 데이터 업로드"""
    
    # 구글 시트 URL
    sheet_url = "https://docs.google.com/spreadsheets/d/1qP37BDR68sqoegMI31FMZt74923JO8NklUY2-XVOk5A/edit?gid=0#gid=0"
    
    print("구글 시트에 데이터를 업로드합니다...")
    print(f"대상 시트: {sheet_url}")
    
    try:
        # 구글 시트 연결
        sync = GoogleSheetsSync(sheet_url=sheet_url)
        
        if sync.setup_connection():
            print("✅ 구글 시트 연결 성공!")
            
            # 데이터 업로드
            if sync.sync_all_data():
                print("🎉 데이터 업로드 완료!")
                print(f"🔗 구글 시트 확인: {sheet_url}")
            else:
                print("❌ 데이터 업로드 실패")
        else:
            print("❌ 구글 시트 연결 실패")
            
    except Exception as e:
        print(f"오류 발생: {e}")
        print("\n대안: CSV 파일로 수동 업로드")
        print("python export_to_csv_for_sheets.py")

if __name__ == "__main__":
    upload_to_specific_sheet()