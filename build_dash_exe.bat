@echo off
setlocal

REM Dash EXE 빌드 스크립트 (Windows)
REM 사전 설치: pip install pyinstaller dash dash-ag-grid pandas openpyxl

pyinstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name MMIS_Compare_Tool_Dash ^
  --add-data "app_modules;app_modules" ^
  dash_app.py

if %errorlevel% neq 0 (
  echo 빌드 실패
  exit /b %errorlevel%
)

echo 빌드 성공: dist\MMIS_Compare_Tool_Dash.exe
endlocal
