@echo off
rem © 2026 davisod & JEtsKi
setlocal
for %%I in ("%~dp0..\..") do set "NBT_WORKSPACE=%%~fI"
set "NBT_VIEWER=%NBT_WORKSPACE%\work\graphics-port\hmi-runner\viewer.py"
if not exist "%NBT_VIEWER%" (
    echo Nu gasesc aplicatia: "%NBT_VIEWER%"
    echo Pastreaza acest dosar in outputs\NBT_live_viewer din proiectul NBT.
    pause
    exit /b 2
)
cd /d "%NBT_WORKSPACE%"
if "%~1"=="" (
    where pyw.exe >nul 2>nul
    if not errorlevel 1 (
        start "" /b pyw.exe -3 "%NBT_VIEWER%"
        exit /b 0
    )
)
where py.exe >nul 2>nul
if errorlevel 1 (
    echo Nu gasesc Python 3 prin lansatorul py. Aplicatia necesita Python cu Tkinter.
    pause
    exit /b 2
)
py.exe -3 "%NBT_VIEWER%" %*
set "NBT_VIEWER_EXIT=%ERRORLEVEL%"
if not "%NBT_VIEWER_EXIT%"=="0" (
    echo Aplicatia s-a oprit cu eroarea %NBT_VIEWER_EXIT%. Vezi jurnalele viewer-runs.
    if "%~1"=="" pause
)
exit /b %NBT_VIEWER_EXIT%
