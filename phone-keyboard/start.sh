#!/usr/bin/env bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  echo "Нужен Python 3.9 или новее. Скачайте его с https://www.python.org/downloads/ и запустите снова."
  read -r -p "Нажмите Enter для выхода..." _
  exit 1
fi
if [ ! -f .venv/.installed ]; then
  echo "Первый запуск: устанавливаю зависимости (1–2 минуты)..."
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -r requirements.txt \
    && touch .venv/.installed || { echo "Не удалось установить зависимости."; read -r -p "Enter для выхода..." _; exit 1; }
fi
exec .venv/bin/python -m keyboard "$@"
