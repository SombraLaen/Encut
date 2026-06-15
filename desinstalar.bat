@echo off
cd /d "%~dp0"
if exist "%~dp0EncutSetup.exe" (
    "%~dp0EncutSetup.exe" /uninstall %*
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar.ps1" %*
)
echo.
pause
