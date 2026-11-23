#!/usr/bin/env bash
# macOS: двойной клик по этому файлу откроет Терминал и запустит программу
cd "$(dirname "$0")"
exec ./start.sh "$@"
