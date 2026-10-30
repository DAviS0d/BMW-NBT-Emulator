@echo off
cd /d "%~dp0"
start "" /b pyw.exe -3 "%~dp0webui.py"
start "" http://127.0.0.1:8877
