@echo off
cd /d "%~dp0backend"
if not exist .env copy .env.example .env
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
pause
