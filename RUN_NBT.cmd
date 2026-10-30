@echo off
setlocal
cd /d "%~dp0"
if not "%~1"=="" (
    call "%~dp0RUN_NBT_MENU.cmd" %*
    exit /b
)
where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" /b pyw.exe -3 "%~dp0launcher.py"
    exit /b 0
)
where py.exe >nul 2>nul
if errorlevel 1 (
    echo Python launcher not found. Install Python 3 with Tkinter.
    pause
    exit /b 1
)
py.exe -3 "%~dp0launcher.py"
if errorlevel 1 pause
