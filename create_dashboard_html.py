#!/usr/bin/env python3
"""
dashboard.html 생성 스크립트
index.html에서 자동 수집 탭만 제거
"""
import re

with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 탭 메뉴에서 '자동 수집' 제거
content = content.replace(
    "[('dashboard','대시보드'),('collect','자동 수집'),('input','직접 입력'),('list','게시글 목록'),('analyze','AI 분석')]",
    "[('dashboard','대시보드'),('input','직접 입력'),('list','게시글 목록'),('analyze','AI 분석')]"
)

# 2. 자동 수집 탭 내용 전체 제거
# <!-- ── 자동 수집 탭 부터 다음 탭 시작 전까지
pattern = r'<!-- ── 자동 수집 탭.*?(?=<!-- ── 직접 입력 탭)'
content = re.sub(pattern, '', content, flags=re.DOTALL)

# 3. 자동 수집 관련 JavaScript 함수 제거
# collectAction 함수와 관련 코드 제거
pattern = r'// ── 자동 수집.*?(?=// ──|<\/script>)'
content = re.sub(pattern, '', content, flags=re.DOTALL)

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ dashboard.html 생성 완료!')
print('   - 자동 수집 탭 제거됨')
print('   - 대시보드, 직접 입력, 게시글 목록, AI 분석 탭 유지')