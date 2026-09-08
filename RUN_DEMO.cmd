@echo off
REM Launches the Fab Yield & Capacity Decision Intelligence workspace locally.
REM First run may take ~30-60s while the server pre-warms the real-data
REM pipeline (SECOM model + all 4 scenarios) in the background.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python environment...
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)

if not exist "frontend\dist\index.html" (
    echo Building React frontend...
    pushd frontend
    call npm ci --no-fund --no-audit
    call npm run build
    popd
)

echo Starting server at http://127.0.0.1:8020 ...
start "" http://127.0.0.1:8020
".venv\Scripts\python.exe" -m uvicorn api.main:app --host 127.0.0.1 --port 8020
