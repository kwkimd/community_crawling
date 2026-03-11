#!/usr/bin/env python3
"""
기존 데이터를 지능형 분류 시스템으로 업그레이드
"""
import database as db
from intelligent_classifier import classify_post_intelligent

def upgrade_existing_data():
    """기존 데이터를 지능형 분류로 업그레이드"""
    print("🧠 지능형 분류 시스템으로 업그레이드를 시작합니다...")
    
    # 모든 기존 게시글 조회
    conn = db.get_connection()
    posts = conn.execute("SELECT * FROM posts ORDER BY id").fetchall()
    total_posts = len(posts)
    
    print(f"총 {total_posts}개의 게시글을 업그레이드합니다.")
    
    updated_count = 0
    
    for i, post in enumerate(posts, 1):
        post_dict = dict(post)
        post_id = post_dict['id']
        
        print(f"[{i}/{total_posts}] ID {post_id}: 지능형 분류 적용 중...")
        
        try:
            # 지능형 분류 적용
            enhanced_post = classify_post_intelligent(
                post_dict, 
                monitoring_name=post_dict.get('monitoring_name', '일반모니터링'),
                search_keyword=post_dict.get('keywords', '배달')
            )
            
            # DB 업데이트 (새로운 분류 결과만)
            conn.execute("""
                UPDATE posts SET
                    risk_classification = ?,
                    main_category = ?,
                    sub_category = ?,
                    detail_category = ?,
                    keywords = ?,
                    summary = ?,
                    risk_level = ?
                WHERE id = ?
            """, (
                enhanced_post.get("risk_classification", "NO RISK"),
                enhanced_post.get("main_category", "플랫폼 이용"),
                enhanced_post.get("sub_category", "주문"),
                enhanced_post.get("detail_category", "일반"),
                enhanced_post.get("keywords", ""),
                enhanced_post.get("summary", ""),
                enhanced_post.get("risk_level", 0),
                post_id
            ))
            
            updated_count += 1
            
            # 진행상황 표시
            if i % 20 == 0:
                print(f"  → 진행률: {i}/{total_posts} ({i/total_posts*100:.1f}%)")
                conn.commit()  # 중간 저장
                
        except Exception as e:
            print(f"  ❌ ID {post_id} 처리 중 오류: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 지능형 분류 업그레이드 완료!")
    print(f"   - 업그레이드됨: {updated_count}개")
    print(f"   - 총 처리: {total_posts}개")

def show_upgrade_results():
    """업그레이드 결과 샘플 확인"""
    print("\n=== 지능형 분류 결과 샘플 ===")
    conn = db.get_connection()
    
    # 최근 5개 게시글의 새 분류 결과 확인
    posts = conn.execute("""
        SELECT id, title, risk_classification, main_category, sub_category, 
               detail_category, keywords, summary
        FROM posts 
        ORDER BY id DESC 
        LIMIT 5
    """).fetchall()
    
    for post in posts:
        print(f"\nID {post[0]}: {post[1][:40]}...")
        print(f"  리스크: {post[2]}")
        print(f"  분류: {post[3]} > {post[4]} > {post[5]}")
        print(f"  키워드: {post[6][:50]}...")
        print(f"  요약: {post[7][:60]}...")
    
    # 분류별 통계
    print(f"\n=== 분류별 통계 ===")
    
    risk_stats = conn.execute("""
        SELECT risk_classification, COUNT(*) as cnt 
        FROM posts 
        GROUP BY risk_classification 
        ORDER BY cnt DESC
    """).fetchall()
    
    print("리스크 분류:")
    for risk, cnt in risk_stats:
        print(f"  {risk}: {cnt}개")
    
    category_stats = conn.execute("""
        SELECT main_category, COUNT(*) as cnt 
        FROM posts 
        GROUP BY main_category 
        ORDER BY cnt DESC
    """).fetchall()
    
    print("\n대분류:")
    for cat, cnt in category_stats:
        print(f"  {cat}: {cnt}개")
    
    conn.close()

if __name__ == "__main__":
    try:
        # 기존 데이터 업그레이드
        upgrade_existing_data()
        
        # 결과 확인
        show_upgrade_results()
        
    except KeyboardInterrupt:
        print("\n중단되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()