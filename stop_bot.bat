@echo off
echo Остановка бота Avito Analytics...
echo.

REM Поиск процесса Python, который запускает main.py
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV ^| findstr /V "INFO"') do (
    set PID=%%i
    set PID=!PID:"=!
    
    REM Проверяем командную строку процесса
    wmic process where "ProcessId=!PID!" get CommandLine 2>nul | findstr /C:"main.py" >nul
    if !errorlevel! equ 0 (
        echo Найден процесс бота с PID: !PID!
        taskkill /PID !PID! /F >nul 2>&1
        if !errorlevel! equ 0 (
            echo Бот успешно остановлен.
        ) else (
            echo Ошибка при остановке процесса !PID!
        )
        goto :found
    )
)

echo Процесс бота не найден. Возможно, бот уже остановлен.
:found
pause
