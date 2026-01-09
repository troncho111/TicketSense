@echo off
REM Setup auto-push to GitHub after every commit (Windows)

echo Setting up auto-push to GitHub...

REM Create post-commit hook
echo #!/bin/sh > .git\hooks\post-commit
echo echo "🚀 Auto-pushing to GitHub..." >> .git\hooks\post-commit
echo git push origin main >> .git\hooks\post-commit

REM Make it executable (if Git Bash is available)
where bash >nul 2>&1
if %errorlevel% == 0 (
    bash -c "chmod +x .git/hooks/post-commit"
)

echo.
echo ✅ Auto-push configured!
echo.
echo Now every time you commit, it will automatically push to GitHub.
echo To test: git commit --allow-empty -m "Test auto-push"
