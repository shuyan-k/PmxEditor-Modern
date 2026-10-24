@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0build\python\pythonw.exe"
if not exist "%PY%" set "PY=pythonw.exe"
start "" "%PY%" "%~dp0main.py" %*