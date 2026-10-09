@echo off
cd /d "%~dp0frontend"
if not exist .env.local copy .env.local.example .env.local
if not exist node_modules npm install
npm run dev
pause
