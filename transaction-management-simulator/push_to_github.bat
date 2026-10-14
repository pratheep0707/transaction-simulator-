@echo off
echo ========================================================
echo Pushing Transaction Simulator to GitHub
echo Target Repo: https://github.com/pratheep0707/transaction-simulator-.git
echo ========================================================

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git is not recognized in your current PATH.
    echo If you have Git installed, please run these commands inside Git Bash or add Git to your PATH.
    pause
    exit /b 1
)

echo [1/5] Initializing Git repository...
if not exist ".git" (
    git init
    git branch -M main
)

echo [2/5] Configuring remote repository...
git remote remove origin 2>nul
git remote add origin https://github.com/pratheep0707/transaction-simulator-.git

echo [3/5] Staging files (respecting .gitignore to protect secrets)...
git add .

echo [4/5] Creating commit...
git commit -m "Complete DBMS Transaction Management & Concurrency Control Simulator"

echo [5/5] Pushing to main branch...
git push -u origin main

echo ========================================================
echo Successfully pushed to https://github.com/pratheep0707/transaction-simulator-
echo ========================================================
pause
