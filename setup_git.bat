@echo off
SET GIT="C:\Program Files\Git\cmd\git.exe"

echo [1] git init...
%GIT% init

echo [2] git user config...
%GIT% config user.name "kwkimd"
%GIT% config user.email "kwkimd@woowahan.com"

echo [3] git add...
%GIT% add .

echo [4] git commit...
%GIT% commit -m "Initial commit: 네이버 카페 크롤러 + AI 분석 도구"

echo [5] git branch -M main...
%GIT% branch -M main

echo [6] git remote add...
%GIT% remote add origin https://github.com/kwkimd/community_crawling.git

echo [7] git push...
%GIT% push -u origin main

echo Done!
pause
