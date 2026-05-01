@echo off
chcp 65001 >nul
cd /d "%~dp0"
start /min "LiAI Bot" python telegram_bot.py
