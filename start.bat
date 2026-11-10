@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  Equipment Fault Consultation Agent - Windows launcher
REM  Usage:
REM    start.bat            launch the desktop client
REM    start.bat test       run the unit test suite
REM    start.bat selftest   build the GUI and exit (quick check)
REM ============================================================

title Equipment Fault Agent
set "MODE=%~1"
set "PYEXE="

echo [1/3] Looking for a Python interpreter with Tkinter...
for %%V in ("py -3.15" "py -3.14" "py -3.13" "py -3.12" "py -3" "python") do (
    if not defined PYEXE (
        %%~V -c "import tkinter" >nul 2>&1
        if not errorlevel 1 set "PYEXE=%%~V"
    )
)

if not defined PYEXE (
    echo.
    echo [ERROR] No Python 3 with Tkinter was found on this machine.
    echo         Install Python 3.10+ from https://www.python.org/downloads/windows/
    echo         and make sure the "tcl/tk and IDLE" component is checked.
    echo.
    echo Press any key to close this window...
    pause >nul
    exit /b 1
)
echo       using: %PYEXE%

if /i "%MODE%"=="test" (
    echo [2/3] Running unit tests...
    %PYEXE% run_tests.py
    echo.
    echo Press any key to close this window...
    pause >nul
    exit /b 0
)

if /i "%MODE%"=="selftest" (
    echo [2/3] Running GUI self-test...
    %PYEXE% app.py --selftest
    echo.
    echo Press any key to close this window...
    pause >nul
    exit /b 0
)

echo [2/3] Resolving windowed interpreter...
for /f "delims=" %%P in ('%PYEXE% -c "import sys,os;print(os.path.dirname(sys.executable))"') do set "PYDIR=%%P"
set "PYW=%PYDIR%\pythonw.exe"

echo [3/3] Starting the desktop client...
if exist "%PYW%" (
    start "" "%PYW%" "%~dp0app.py"
) else (
    start "" %PYEXE% "%~dp0app.py"
)

timeout /t 2 >nul
exit /b 0
