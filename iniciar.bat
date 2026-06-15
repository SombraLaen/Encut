@echo off
cd /d "%~dp0"
if exist "%~dp0runtime\ffmpeg\bin" set "PATH=%~dp0runtime\ffmpeg\bin;%PATH%"
if exist "%~dp0runtime\python\pythonw.exe" (
    start "" "%~dp0runtime\python\pythonw.exe" "%~dp0silence_cutter.py" --gui
    exit /b
)
if exist "%~dp0runtime\python\python.exe" (
    start "" "%~dp0runtime\python\python.exe" "%~dp0silence_cutter.py" --gui
    exit /b
)
where pythonw >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" pythonw "%~dp0silence_cutter.py" --gui
) else (
    start "" python "%~dp0silence_cutter.py" --gui
)
exit /b
