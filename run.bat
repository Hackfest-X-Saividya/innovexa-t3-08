@echo off
title Green Pulse - Carbon Footprint Tracking & Reduction Platform
echo ======================================================================
echo Starting Green Pulse Web Application...
echo Tagline: "Track Your Impact. Make Every Action Count."
echo ======================================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not found in PATH!
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

echo Checking dependencies...
pip install -r requirements.txt --quiet

echo.
echo Launching local Flask server...
echo Access the application in your browser at: http://127.0.0.1:5000
echo (Press CTRL+C in this terminal window to stop the server)
echo ======================================================================
echo.

python app.py
pause
