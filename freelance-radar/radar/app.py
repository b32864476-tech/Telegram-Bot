"""Веб-сервер: API + статика + фоновый сбор заказов."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import base64
import secrets
import time

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

import math

from fastapi import Body
from fastapi.responses import JSONResponse

from . import db
from .classify import CATEGORY_LABELS, enrich
from .messaging import SUPPORTED, WHY_NOT, ChatError, project_id_of, provider
from .scrapers import collect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("radar")
logging.getLogger("httpx").setLevel(logging.WARNING)
STATIC = Path(__file__).resolve().parent.parent / "static"
INTERVAL = int(os.getenv("RADAR_INTERVAL_MIN", "15")) * 60
CHAT_INTERVAL = int(os.getenv("RADAR_CHAT_INTERVAL_SEC", "60"))
TOKEN_KEYS = ["freelancehunt_token", "freelancer_token", "freelancehunt_safe_type"]
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


def settings() -> dict:
    con = db.connect()
    try:
        out = {k: db.get_setting(con, k) for k in TOKEN_KEYS}
    finally:
        con.close()
    # переменные окружения — запасной вариант
    out["freelancehunt_token"] = out["freelancehunt_token"] or os.getenv("FREELANCEHUNT_TOKEN", "")
    out["freelancer_token"] = out["freelancer_token"] or os.getenv("FREELANCER_TOKEN", "")
    return out


async def sync_chat(con, chat: dict, p) -> list[dict]:
    """Подтянуть переписку по заказу с биржи. Возвращает новые входящие сообщения."""
    pid = chat["project_id"]
    if not chat.get("employer_id"):
        try:
            chat["employer_id"] = await p.employer_of(pid)
        except ChatError:
            pass
    if not chat.get("thread_id"):
        title = (con.execute("SELECT title FROM orders WHERE id=?", (chat["order_id"],)).fetchone() or [""])[0]
        chat["thread_id"] = await p.find_thread(chat.get("employer_id"), pid, title)
    fresh = []
    if chat.get("thread_id"):
        fresh = db.add_messages(con, chat["order_id"], await p.messages(chat["thread_id"]))
    chat["error"] = None
    db.save_chat(con, chat)
    return fresh


async def chat_loop():
    """Раз в минуту проверяет ответы заказчиков по всем перепискам."""
    while True:
        await asyncio.sleep(CHAT_INTERVAL)
        try:
            st = settings()
            con = db.connect()
            for chat in [dict(r) for r in con.execute("SELECT * FROM chats")]:
                p = provider(chat["source"], st)
                if not p:
                    continue
                try:
                    fresh = await sync_chat(con, chat, p)
                    if fresh:
                        log.info("Новых сообщений по %s: %d", chat["order_id"], len(fresh))
                except ChatError as e:
                    chat["error"] = str(e)
                    db.save_chat(con, chat)
            con.close()
        except Exception:
            log.exception("Проверка сообщений упала")


@asynccontextmanager
async def lifespan(app):
    tasks = [asyncio.create_task(loop()), asyncio.create_task(chat_loop())]
    yield
    for t in tasks:
        t.cancel()


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
    elif request.url.path.startswith(("/api/chat", "/api/settings", "/api/inbox")) and (
            "cf-connecting-ip" in request.headers or "x-forwarded-for" in request.headers):
        # Сайт открыт через туннель без пароля: отправку сообщений от вашего имени не даём.
        return JSONResponse({"error": "Задайте RADAR_PASSWORD, чтобы пользоваться чатом через интернет."},
                            status_code=403)
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


def _err(msg: str, code: int = 400):
    return JSONResponse({"error": msg}, status_code=code)


@app.get("/api/settings")
def get_settings():
    st = settings()
    return {"freelancehunt": {"configured": bool(st["freelancehunt_token"]),
                              "safe_type": st["freelancehunt_safe_type"] or "employer"},
            "freelancer": {"configured": bool(st["freelancer_token"])}}


@app.post("/api/settings")
async def save_settings(body: dict = Body(...)):
    con = db.connect()
    for k in TOKEN_KEYS:
        if k in body and body[k] is not None:
            db.set_setting(con, k, str(body[k]).strip())
    con.close()
    st, check = settings(), {}
    for src in SUPPORTED:
        p = provider(src, st)
        if not p:
            continue
        try:
            check[src] = {"ok": True, "name": (await p.me())["name"]}
        except ChatError as e:
            check[src] = {"ok": False, "error": str(e)}
        except Exception as e:
            check[src] = {"ok": False, "error": f"Нет связи с биржей: {e}"}
    return {**get_settings(), "check": check}


@app.get("/api/inbox")
def inbox():
    con = db.connect()
    try:
        chats = db.inbox(con)
        latest = [dict(r) for r in con.execute(
            "SELECT m.*, o.title FROM messages m LEFT JOIN orders o ON o.id=m.order_id "
            "WHERE m.unread=1 ORDER BY m.at DESC LIMIT 20")]
        return {"unread": sum(c["unread"] for c in chats), "chats": chats, "latest": latest}
    finally:
        con.close()


@app.get("/api/chat/{order_id:path}")
async def get_chat(order_id: str):
    source = order_id.split(":", 1)[0]
    con = db.connect()
    try:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        order = dict(order) if order else {}
        p = provider(source, settings())
        chat = db.get_chat(con, order_id)
        error = None
        if chat and p:
            try:
                await sync_chat(con, chat, p)
            except ChatError as e:
                error = str(e)
        db.mark_read(con, order_id)
        days = math.ceil((order.get("ai_hours_hi") or 6) / 6)
        if order.get("deadline_days"):
            days = min(days, max(1, int(order["deadline_days"])))
        return {
            "supported": source in SUPPORTED,
            "configured": bool(p),
            "why_not": None if source in SUPPORTED else WHY_NOT,
            "source_name": SUPPORTED.get(source, source),
            "chat": db.get_chat(con, order_id),
            "messages": db.chat_messages(con, order_id),
            "error": error,
            "defaults": {"amount": order.get("price"), "currency": order.get("currency") or (p.currency if p else None),
                         "days": days},
        }
    finally:
        con.close()


@app.post("/api/chat/{order_id:path}")
async def send_chat(order_id: str, body: dict = Body(...)):
    text = (body.get("text") or "").strip()
    if not text:
        return _err("Напишите сообщение.")
    source = order_id.split(":", 1)[0]
    if source not in SUPPORTED:
        return _err(WHY_NOT)
    p = provider(source, settings())
    if not p:
        return _err(f"Добавьте токен {SUPPORTED[source]} в настройках Radar (шестерёнка вверху).")
    con = db.connect()
    try:
        chat = db.get_chat(con, order_id) or {"order_id": order_id, "source": source,
                                              "project_id": project_id_of(order_id)}
        if not chat.get("bid_id") and not chat.get("thread_id"):
            # первое сообщение = отклик под заказом
            try:
                amount = float(body.get("amount") or 0)
                days = int(body.get("days") or 0)
            except (TypeError, ValueError):
                return _err("Сумма и срок должны быть числами.")
            if amount <= 0 or days <= 0:
                return _err("Первое сообщение уходит откликом: укажите сумму и срок в днях.")
            res = await p.bid(chat["project_id"], text, amount, days, body.get("currency"))
            chat["bid_id"] = res["bid_id"]
            db.add_messages(con, order_id, [res["message"]])
            db.save_chat(con, chat)
            try:
                await sync_chat(con, chat, p)
            except ChatError:
                pass
        else:
            await sync_chat(con, chat, p)
            if chat.get("thread_id"):
                msg = await p.send(chat["thread_id"], text)
            else:
                if not chat.get("employer_id"):
                    return _err("Заказчик ещё не открыл переписку. Ваш отклик он видит, "
                                "а когда ответит, сообщения появятся здесь.")
                title = (con.execute("SELECT title FROM orders WHERE id=?", (order_id,)).fetchone() or [""])[0]
                try:
                    chat["thread_id"] = await p.new_thread(chat["employer_id"], chat["project_id"], title or "Заказ", text)
                except ChatError as e:
                    return _err(f"Заказчик ещё не открыл переписку, а биржа не даёт написать первым ({e}). "
                                "Ваш отклик он видит; когда ответит, сообщения появятся здесь.")
                db.save_chat(con, chat)
                await sync_chat(con, chat, p)   # подтянет и наше первое сообщение
                msg = None
            if msg:
                db.add_messages(con, order_id, [msg])
        return {"chat": db.get_chat(con, order_id), "messages": db.chat_messages(con, order_id)}
    except ChatError as e:
        return _err(str(e), 502)
    finally:
        con.close()


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
