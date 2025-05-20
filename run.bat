@echo off
call .\venv\Scripts\activate
cd .\diplom\
uvicorn app.main:app --reload