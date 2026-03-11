#!/usr/bin/env python3
"""
dashboard.html에서 불필요한 JavaScript 제거
"""
import re

with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 자동 수집 관련 JavaScript 제거
# "// ── 자동 수집" 부터 "// ── 게시글 저장" 또는 "// ── 게시글 목록" 전까지
pattern = r'// ── 자동 수집.*?(?=// ── 게시글)'
content = re.sub(pattern, '', content, flags=re.DOTALL)

# 2. 직접 입력 관련 JavaScript 제거  
# "// ── 게시글 저장" 부터 "// ── 게시글 목록" 전까지
pattern = r'// ── 게시글 저장.*?(?=// ── 게시글 목록)'
content = re.sub(pattern, '', content, flags=re.DOTALL)

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ dashboard.html 정리 완료!')
print('   - 자동 수집 JavaScript 제거')
print('   - 직접 입력 JavaScript 제거')
print('   - 게시글 목록, AI 분석 JavaScript 유지')