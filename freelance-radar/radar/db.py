"""Хранилище заказов: SQLite (один файл, без отдельного сервера)."""
import json
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.getenv("RADAR_DB", Path(__file__).resolve().parent.parent / "orders.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          TEXT PRIMARY KEY,          -- source:external_id
    source      TEXT NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    tags        TEXT,
    price       REAL,                      -- сумма в валюте заказа (максимум диапазона)
    price_min   REAL,
    currency    TEXT,
    price_rub   INTEGER,                   -- для сортировки
    category    TEXT,
    complexity  INTEGER,
    ai_fit      INTEGER,
    bids        INTEGER,
    published   INTEGER,                   -- unix time
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL,
    ai_hours_lo REAL,                      -- оценка часов работы с ИИ
    ai_hours_hi REAL,
    manual_hours REAL,                     -- то же без ИИ
    rate_rub    INTEGER,                   -- бюджет / часы с ИИ
    deadline_days REAL,                    -- срок заказчика, дней
    fits        TEXT                       -- ok | tight | no | NULL
);
CREATE INDEX IF NOT EXISTS ix_pub ON orders(published DESC);
CREATE INDEX IF NOT EXISTS ix_price ON orders(price_rub);
CREATE INDEX IF NOT EXISTS ix_cx ON orders(complexity);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS chats (
    order_id    TEXT PRIMARY KEY,          -- id заказа (source:external_id)
    source      TEXT NOT NULL,
    project_id  TEXT NOT NULL,             -- id заказа на бирже
    employer_id TEXT,                      -- id заказчика на бирже
    bid_id      TEXT,                      -- наш отклик
    thread_id   TEXT,                      -- переписка с заказчиком
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    error       TEXT                       -- последняя ошибка опроса
);
CREATE TABLE IF NOT EXISTS messages (
    id        TEXT PRIMARY KEY,            -- source:message_id (или bid:<id> для отклика)
    order_id  TEXT NOT NULL,
    from_me   INTEGER NOT NULL,
    text      TEXT NOT NULL,
    at        INTEGER NOT NULL,
    unread    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_msg_order ON messages(order_id, at);
CREATE TABLE IF NOT EXISTS runs (
    source TEXT PRIMARY KEY, ok INTEGER, count INTEGER, error TEXT, at INTEGER
);
"""

FIELDS = ["id", "source", "url", "title", "description", "tags", "price", "price_min", "currency",
          "price_rub", "category", "complexity", "ai_fit", "bids", "published",
          "ai_hours_lo", "ai_hours_hi", "manual_hours", "rate_rub", "deadline_days", "fits"]
NEW_COLUMNS = {"ai_hours_lo": "REAL", "ai_hours_hi": "REAL", "manual_hours": "REAL",
               "rate_rub": "INTEGER", "deadline_days": "REAL", "fits": "TEXT"}


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(orders)")}
    for col, typ in NEW_COLUMNS.items():       # миграция старых баз
        if col not in have:
            con.execute(f"ALTER TABLE orders ADD COLUMN {col} {typ}")
    return con


def upsert(con, orders: list[dict]) -> int:
    now = int(time.time())
    new = 0
    for o in orders:
        row = {f: o.get(f) for f in FIELDS}
        row["published"] = row["published"] or now
        cur = con.execute("SELECT 1 FROM orders WHERE id=?", (row["id"],)).fetchone()
        if cur:
            sets = ", ".join(f"{f}=:{f}" for f in FIELDS if f != "id")
            con.execute(f"UPDATE orders SET {sets}, last_seen=:now WHERE id=:id", {**row, "now": now})
        else:
            new += 1
            cols = ", ".join(FIELDS)
            con.execute(f"INSERT INTO orders ({cols}, first_seen, last_seen) VALUES "
                        f"({', '.join(':' + f for f in FIELDS)}, :now, :now)", {**row, "now": now})
    con.commit()
    return new


def log_run(con, source: str, ok: bool, count: int, error: str | None):
    con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
                (source, int(ok), count, error, int(time.time())))
    con.commit()


def recent(con, days: int = 30, limit: int = 8000, q: str | None = None) -> list[dict]:
    sql = "SELECT * FROM orders WHERE published >= ?"
    args: list = [int(time.time()) - days * 86400]
    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY published DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in con.execute(sql, args)]


def stats(con) -> dict:
    total = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    day = con.execute("SELECT COUNT(*) FROM orders WHERE first_seen >= ?",
                      (int(time.time()) - 86400,)).fetchone()[0]
    runs = [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY source")]
    return {"total": total, "last24h": day, "sources": runs}


def export_json(con, path: Path, days: int = 30, desc_limit: int = 1500):
    rows = recent(con, days)
    for r in rows:
        r["description"] = (r["description"] or "")[:desc_limit]
        r.pop("last_seen", None)
    path.write_text(json.dumps({"generated": int(time.time()), "orders": rows, "stats": stats(con)},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ------------------------------------------------------------- настройки и чаты
def get_setting(con, key: str, default: str = "") -> str:
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r and r[0] is not None else default


def set_setting(con, key: str, value: str):
    con.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
    con.commit()


def get_chat(con, order_id: str):
    r = con.execute("SELECT * FROM chats WHERE order_id=?", (order_id,)).fetchone()
    return dict(r) if r else None


def save_chat(con, chat: dict):
    now = int(time.time())
    chat.setdefault("created_at", now)
    chat["updated_at"] = now
    cols = ["order_id", "source", "project_id", "employer_id", "bid_id", "thread_id",
            "created_at", "updated_at", "error"]
    con.execute(f"INSERT OR REPLACE INTO chats ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [chat.get(c) for c in cols])
    con.commit()


def add_messages(con, order_id: str, msgs: list[dict]) -> list[dict]:
    """Сохраняет сообщения, возвращает новые входящие (для уведомлений)."""
    fresh = []
    for m in msgs:
        if con.execute("SELECT 1 FROM messages WHERE id=?", (m["id"],)).fetchone():
            continue
        unread = 0 if m["from_me"] else 1
        con.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)",
                    (m["id"], order_id, int(m["from_me"]), m["text"], m["at"], unread))
        if unread:
            fresh.append({**m, "order_id": order_id})
    con.commit()
    return fresh


def chat_messages(con, order_id: str) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT * FROM messages WHERE order_id=? ORDER BY at, rowid", (order_id,))]


def mark_read(con, order_id: str):
    con.execute("UPDATE messages SET unread=0 WHERE order_id=?", (order_id,))
    con.commit()


def inbox(con) -> list[dict]:
    """Все переписки: последнее сообщение, число непрочитанных, данные заказа."""
    rows = con.execute("""
        SELECT c.order_id, c.source, c.error, o.title, o.url,
               (SELECT COUNT(*) FROM messages m WHERE m.order_id=c.order_id AND m.unread=1) AS unread,
               (SELECT text FROM messages m WHERE m.order_id=c.order_id ORDER BY at DESC, rowid DESC LIMIT 1) AS last_text,
               (SELECT from_me FROM messages m WHERE m.order_id=c.order_id ORDER BY at DESC, rowid DESC LIMIT 1) AS last_from_me,
               COALESCE((SELECT MAX(at) FROM messages m WHERE m.order_id=c.order_id), c.updated_at) AS last_at
        FROM chats c LEFT JOIN orders o ON o.id=c.order_id
        ORDER BY unread > 0 DESC, last_at DESC""")
    return [dict(r) for r in rows]
