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
    last_seen   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pub ON orders(published DESC);
CREATE INDEX IF NOT EXISTS ix_price ON orders(price_rub);
CREATE INDEX IF NOT EXISTS ix_cx ON orders(complexity);
CREATE TABLE IF NOT EXISTS runs (
    source TEXT PRIMARY KEY, ok INTEGER, count INTEGER, error TEXT, at INTEGER
);
"""

FIELDS = ["id", "source", "url", "title", "description", "tags", "price", "price_min", "currency",
          "price_rub", "category", "complexity", "ai_fit", "bids", "published"]


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
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
