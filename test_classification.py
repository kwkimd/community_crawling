import scraper

# Test auto-classification functions
test_post = {
    'title': '배민 한그릇할인기능 오픈 무슨ㅈㄹ',
    'content': '1인분배달 독려정책 미친거같네요 가뜩이나 1인분배달은 남기는거 없어서 그냥 광고비 쓰고 무료봉사한다 개념으로 하고있었는데',
    'author': '서울 블리짱',
    'post_date': '2025-04-15',
    'cafe_name': '아프니까사장이다'
}

enhanced = scraper._enhance_post_with_csv_structure(test_post, '1인분(한그릇)', '배민')

print('Auto-classification test results:')
print(f'Sentiment: {enhanced["sentiment"]}')
print(f'Risk Level: {enhanced["risk_level"]}')
print(f'Subject Type: {enhanced["subject_type"]}')
print(f'Service Type: {enhanced["service_type"]}')
print(f'Channel Type: {enhanced["channel_type"]}')
print(f'Risk Classification: {enhanced["risk_classification"]}')
print(f'Categories: {enhanced["main_category"]} > {enhanced["sub_category"]} > {enhanced["detail_category"]}')
print(f'Summary: {enhanced["summary"]}')
print(f'Week Info: {enhanced["week_info"]}')
print(f'Site Group: {enhanced["site_group"]}')