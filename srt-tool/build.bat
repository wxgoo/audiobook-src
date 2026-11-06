@echo off
setlocal
cd /d "%~dp0"

set VENV=venv
set PY=%VENV%\Scripts\python.exe

:: 1. Create venv if missing
if not exist "%PY%" (
    echo [build] Virtual environment not found. Creating...
    python -m venv %VENV%
    if errorlevel 1 (
        echo [build] Failed to create venv. Make sure Python 3.10+ is installed and in PATH.
        exit /b 1
    )
)

:: 2. Install dependencies
echo [build] Installing dependencies...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install faster-whisper ctranslate2==4.8.5 pyinstaller
if errorlevel 1 (
    echo [build] Dependency installation failed.
    exit /b 1
)

:: 3. Run build.py
echo [build] Starting packaging...
"%PY%" build.py %*
set RC=%ERRORLEVEL%

if %RC% neq 0 (
    echo [build] Build failed. Exit code: %RC%
) else (
    echo [build] Success. Output is in dist\make_srt\
)
pause
exit /b %RC%