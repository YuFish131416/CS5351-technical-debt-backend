@echo off
REM start.cmd - Windows batch helper to create venv, install deps and run the app

IF NOT EXIST .venv (
    echo Creating virtual environment .venv...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

IF NOT EXIST .env (
    echo .env not found. Please create a .env file with DATABASE_URL, REDIS_URL and SECRET_KEY.
) ELSE (
    echo Using .env
)

uvicorn main:app --reload --host 0.0.0.0 --port 8000
