@echo off
setlocal
title BMW NBT Emulator
cd /d "%~dp0"
set "NBT_RUNNER=%~dp0work\graphics-port\hmi-runner"

if /i "%~1"=="/check" goto check
where py.exe >nul 2>nul
if errorlevel 1 (
    echo Python launcher not found. Install Python 3 with Tkinter and the py launcher.
    pause
    exit /b 1
)
if /i "%~1"=="emulator" goto emulator
if /i "%~1"=="web" goto web
if /i "%~1"=="simulator" goto simulator
if /i "%~1"=="hypervisor" goto hypervisor
if not "%~1"=="" goto usage

:menu
cls
echo ============================================================
echo                      BMW NBT Emulator
echo ============================================================
echo.
echo   1. Start original BMW NBT emulator
echo   2. Open web interface
echo   3. Run vehicle-data simulator demo
echo   4. Check hypervisor and QEMU acceleration
echo   5. Exit
echo.
echo Integrated phone entries, sport gauges and OSM maps use the
echo native profile when it is available.
echo.
choice /c 12345 /n /m "Choose [1-5]: "
if errorlevel 5 exit /b 0
if errorlevel 4 goto hypervisor
if errorlevel 3 goto simulator
if errorlevel 2 goto web
if errorlevel 1 goto emulator
exit /b 1

:emulator
echo Starting BMW NBT. Software CPU mode takes about 25 seconds.
py -3 "%NBT_RUNNER%\viewer.py"
if errorlevel 1 (
    echo.
    echo Startup failed. See work\graphics-port\hmi-runner\viewer-runs.
    pause
    exit /b 1
)
exit /b 0

:web
call "%NBT_RUNNER%\RUN_WEBUI.cmd"
exit /b %errorlevel%

:simulator
echo Running a 60-second vehicle-data demo. Press Ctrl+C to stop.
call "%~dp0tools\RUN_CAR_SIM.cmd"
echo.
echo Latest data: work\graphics-port\hmi-runner\vehicle-state.json
pause
exit /b 0

:hypervisor
call "%~dp0tools\CHECK_HYPERVISOR.cmd"
exit /b %errorlevel%

:check
for %%F in ("%NBT_RUNNER%\viewer.py" "%NBT_RUNNER%\RUN_WEBUI.cmd" "%~dp0tools\RUN_CAR_SIM.cmd" "%~dp0tools\CHECK_HYPERVISOR.cmd") do (
    if not exist "%%~F" (
        echo Missing: %%~F
        exit /b 1
    )
)
where py.exe >nul 2>nul
if errorlevel 1 exit /b 1
echo Launcher paths and Python launcher verified.
exit /b 0

:usage
echo Usage: RUN_NBT.cmd [emulator^|web^|simulator^|hypervisor^|/check]
exit /b 2
