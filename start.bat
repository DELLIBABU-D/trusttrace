@echo off
REM TrustTrace one-click start (Windows). First run installs the Python packages.
cd /d "%~dp0"
python --version >nul 2>&1 || (echo Python 3.11+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist backend\data\.installed (
  echo Installing Python packages (first run only)...
  python -m pip install -r backend\requirements.txt || (echo pip install failed. See PROJECT_STATUS.md, Troubleshooting. & pause & exit /b 1)
  if not exist backend\data mkdir backend\data
  echo ok> backend\data\.installed
)
python backend\manage.py doctor
python serve.py
pause
