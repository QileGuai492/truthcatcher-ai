@echo off
title TruthCatcher

echo ========================================
echo   TruthCatcher Launcher
echo ========================================
echo.

REM -- check Python --
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo Python: %PYVER%

REM -- check .env --
if not exist ".env" (
    echo [ERROR] .env not found
    pause
    exit /b 1
)
echo .env: found

REM -- setup venv --
if not exist "venv\Scripts\python.exe" (
    echo Creating venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] venv creation failed
        pause
        exit /b 1
    )
    echo venv: created
) else (
    echo venv: found
)

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] venv activate failed
    pause
    exit /b 1
)

REM -- install deps --
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. See above for details.
    pause
    exit /b 1
)
echo Dependencies: OK
echo.

REM -- check API keys --
python -c "from app.config import settings; missing=settings.missing_keys(); exit(1 if missing else 0)"
if errorlevel 1 (
    echo [ERROR] Missing API keys. Check your .env file.
    python -c "from app.config import settings; print('Missing:', settings.missing_keys())"
    pause
    exit /b 1
)
echo API config: OK
echo.

echo ========================================
echo   Starting Gradio Web UI...
echo   Open http://127.0.0.1:7860 in browser
echo   Press Ctrl+C to stop
echo ========================================
echo.

python run.py 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] App crashed. Check the traceback above.
)
pause
