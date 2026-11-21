@echo off
chcp 65001 >nul
title Build Kavir Tire Bot
echo ============================================
echo ساخت فایل اجرایی ربات کویر تایر
echo ============================================
py -m pip install --upgrade pip
py -m pip install playwright pyinstaller
if errorlevel 1 (
  echo خطا در نصب ابزارهای ساخت. اتصال اينترنت و Python را بررسی کنيد.
  pause
  exit /b 1
)
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "KavirTireBot" --collect-all playwright --collect-all greenlet --collect-all pyee kavir_tire_bot.py
if errorlevel 1 (
  echo ساخت فايل اجرايی ناموفق بود.
  pause
  exit /b 1
)
echo.
echo فايل اجرايی در پوشه dist ساخته شد:
echo dist\KavirTireBot.exe
pause
