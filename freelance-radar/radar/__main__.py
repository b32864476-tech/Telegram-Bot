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
    import uvicorn
    uvicorn.run("radar.app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
