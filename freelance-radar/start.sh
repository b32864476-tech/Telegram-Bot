#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; }
( sleep 3; (xdg-open http://localhost:8000 || open http://localhost:8000) >/dev/null 2>&1 ) &
.venv/bin/python -m radar
