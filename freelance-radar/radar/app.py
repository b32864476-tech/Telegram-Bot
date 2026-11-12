"""Веб-сервер: API + статика + фоновый сбор заказов."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import base64
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

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
PASSWORD = os.getenv("RADAR_PASSWORD", "")


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """Если задан RADAR_PASSWORD, сайт спросит логин/пароль (логин любой).
    Нужно, когда сайт открыт наружу через туннель."""
    if PASSWORD:
        ok = False
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, pwd = base64.b64decode(auth[6:]).decode().partition(":")
                ok = secrets.compare_digest(pwd, PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Radar"'})
    return await call_next(request)


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


STATIC_FILES = {"manifest.webmanifest": "application/manifest+json", "icon.svg": "image/svg+xml",
                "icon-192.png": "image/png", "icon-512.png": "image/png"}


@app.get("/{name}")
def static_file(name: str):
    if name not in STATIC_FILES:
        return Response(status_code=404)
    return FileResponse(STATIC / name, media_type=STATIC_FILES[name])


@app.get("/", response_class=HTMLResponse)
def index():
    # Файл написан без <html>/<head>, чтобы его же можно было опубликовать как статическую страницу.
    return '<!doctype html><html lang="ru">' + (STATIC / "index.html").read_text(encoding="utf-8")
