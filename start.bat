@echo off
title Banet - Live Internet Statistics & Speed Tester
echo ===================================================
echo     Banet - Live Internet Statistics & Speed Tester
echo ===================================================
echo Starting Banet local server...
echo.

python run.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] An error occurred while starting Banet.
    echo Press any key to exit...
    pause >nul
)
