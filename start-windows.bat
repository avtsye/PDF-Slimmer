@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python app_win11.py
if errorlevel 1 pause
