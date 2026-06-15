@echo off
cd /d "%~dp0"
if exist "%~dp0EncutSetup.exe" (
    "%~dp0EncutSetup.exe" %*
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
)
echo.
pause
