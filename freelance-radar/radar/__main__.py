"""python -m radar            — запустить сайт на http://localhost:8000
   python -m radar scrape     — один раз собрать заказы и выйти
   python -m radar export F   — выгрузить базу в JSON (для статической версии)"""
import asyncio
import os
import sys
from pathlib import Path

if len(sys.argv) > 1 and sys.argv[1] == "scrape":
    from .app import refresh
    for k, v in asyncio.run(refresh()).items():
        print(f"{k:16} {v}")
elif len(sys.argv) > 1 and sys.argv[1] == "export":
    from . import db
    db.export_json(db.connect(), Path(sys.argv[2] if len(sys.argv) > 2 else "orders.json"))
else:
    import socket

    import uvicorn
    host, port = os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8000"))
    try:  # адрес компьютера в домашней сети, чтобы открыть сайт с телефона
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
        s.close()
    except OSError:
        lan = None
    print(f"\n  Radar запущен:\n    на этом компьютере:  http://localhost:{port}")
    if lan and host == "0.0.0.0":
        print(f"    с телефона (та же Wi-Fi сеть):  http://{lan}:{port}")
    if not os.getenv("RADAR_PASSWORD"):
        print("    пароль не задан — для доступа из интернета задайте RADAR_PASSWORD")
    print()
    uvicorn.run("radar.app:app", host=host, port=port, log_level="warning")
