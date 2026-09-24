@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please create the Python virtual environment using README.md first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -c "import fastapi, uvicorn, foundry" >nul 2>&1
if errorlevel 1 (
  echo Please install dependencies: .venv\Scripts\python.exe -m pip install -e ".[dev,server]"
  pause
  exit /b 1
)
if not exist ".local\local-user-token.txt" (
  .venv\Scripts\python.exe -m foundry.service add-user local-user --token-file .local/local-user-token.txt
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
echo Open http://127.0.0.1:8000 in your browser.
echo Your personal token is in .local\local-user-token.txt
echo Keep this window open. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m foundry.service serve --port 8000
pause
