@echo off
chcp 65001 >nul
cd /d "%~dp0"
python\python.exe app\oberflaeche.py
if errorlevel 1 (
  echo.
  echo Das Programm wurde unerwartet beendet.
  pause
)
