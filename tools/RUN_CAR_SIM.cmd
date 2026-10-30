@echo off
cd /d "%~dp0.."
py -3 work\graphics-port\hmi-runner\vehicle_sim_cli.py --demo --seconds 60 --hz 10 --output work\graphics-port\hmi-runner\vehicle-state.json %*
if errorlevel 1 pause
