@echo off
py -3 "%~dp0check_hypervisor.py" %*
if "%~1"=="" pause
