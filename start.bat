@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ====================================
echo  FiveM Dev Lab - Server Starting
echo ====================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org
    pause
    exit /b 1
)

echo [OK] Python found
echo.

REM Check if requirements are installed
echo Checking dependencies...
pip list | find "Flask" >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)

echo [OK] All dependencies installed
echo.
echo ====================================
echo  Starting FiveM Dev Lab...
echo  Open browser: http://localhost:5000
echo  Login: admin / admin123
echo ====================================
echo.

REM Run the Flask app
python app.py

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Application failed to start
    pause
    exit /b 1
)

pause
