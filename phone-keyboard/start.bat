@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv (
  echo Первый запуск: устанавливаю зависимости...
  python -m venv .venv || (echo Не найден Python. Установите его с python.org и отметьте "Add to PATH". & pause & exit /b 1)
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python -m keyboard %*
pause
