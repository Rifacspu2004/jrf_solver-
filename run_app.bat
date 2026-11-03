@echo off
title UGC NET JRF PYQ AI Engine
echo ========================================================
echo   UGC NET Computer Science JRF PYQ AI Engine (2017-2026)
echo ========================================================
echo Starting Streamlit Application on http://localhost:8501 ...
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" -m streamlit run "%~dp0app.py"
pause
