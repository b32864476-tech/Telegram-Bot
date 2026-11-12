"""Веб-сервер: API + статика + фоновый сбор заказов."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import db
from .classify import CATEGORY_LABELS, enrich
from .scrapers import collect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("radar")
logging.getLogger("httpx").setLevel(logging.WARNING)
STATIC = Path(__file__).resolve().parent.parent / "static"
INTERVAL = int(os.getenv("RADAR_INTERVAL_MIN", "15")) * 60
_lock = asyncio.Lock()


async def refresh(only=None) -> dict:
    async with _lock:
        results = await collect(only)
        con = db.connect()
        summary = {}
        for src, res in results.items():
            if isinstance(res, Exception):
                log.warning("%s: %s", src, res)
                db.log_run(con, src, False, 0, str(res)[:300])
                summary[src] = {"ok": False, "error": str(res)[:300]}
                continue
            new = db.upsert(con, [enrich(o) for o in res])
            db.log_run(con, src, True, len(res), None)
            summary[src] = {"ok": True, "fetched": len(res), "new": new}
            log.info("%s: получено %d, новых %d", src, len(res), new)
        con.close()
        return summary


async def loop():
    while True:
        try:
            await refresh()
        except Exception:
            log.exception("Сбор упал")
        await asyncio.sleep(INTERVAL)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(loop())
    yield
    task.cancel()


app = FastAPI(title="Freelance Radar", lifespan=lifespan)


@app.get("/api/orders")
def orders(days: int = 30, limit: int = 8000, q: str | None = None):
    con = db.connect()
    try:
        return {"orders": db.recent(con, days, limit, q), "stats": db.stats(con),
                "categories": CATEGORY_LABELS}
    finally:
        con.close()


@app.post("/api/refresh")
async def manual_refresh():
    return await refresh()


@app.get("/", response_class=HTMLResponse)
def index():
    # Файл написан без <html>/<head>, чтобы его же можно было опубликовать как статическую страницу.
    return '<!doctype html><html lang="ru">' + (STATIC / "index.html").read_text(encoding="utf-8")
