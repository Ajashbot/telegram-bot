@echo off
REM start.bat — تشغيل البوت على Windows
if exist .env (
    for /f "tokens=*" %%i in (.env) do set %%i
)
python installer.py
pause
