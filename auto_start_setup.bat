@echo off
chcp 65001 >nul
cd /d "%~dp0"

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
copy "%~dp0start_bot_only.bat" "%STARTUP%\LiAI_Bot.bat"

echo Done! Bot will auto-start on next boot.
pause
