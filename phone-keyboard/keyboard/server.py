"""Веб-сервер: отдаёт приложение для iPhone и принимает нажатия по WebSocket."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import secrets
import socket
from pathlib import Path

from aiohttp import WSMsgType, web

from .backend import LAYOUT_SWITCH, OS, Backend, os_label

log = logging.getLogger("keyboard")
STATIC = Path(__file__).parent / "static"
TOKEN_FILE = Path.home() / ".phone_keyboard_token"


def load_token(reset: bool = False) -> str:
    """Ключ доступа хранится на диске, чтобы ярлык на iPhone работал после перезапуска."""
    if not reset:
        try:
            token = TOKEN_FILE.read_text().strip()
            if len(token) >= 8:
                return token
        except OSError:
            pass
    token = secrets.token_urlsafe(9)
    try:
        TOKEN_FILE.write_text(token)
    except OSError:
        log.warning("не удалось сохранить ключ в %s", TOKEN_FILE)
    return token


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # пакеты не отправляются, только выбор интерфейса
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def print_qr(url: str):
    try:
        import qrcode
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


class Session:
    """Одно подключение телефона. Помнит зажатые клавиши, чтобы отпустить их при обрыве."""

    def __init__(self, backend: Backend):
        self.b = backend
        self.keys: set[str] = set()
        self.buttons: set[str] = set()

    def handle(self, m: dict):
        t = m.get("t")
        b = self.b
        if t == "down":
            k = str(m["k"])
            if b.down(k):
                self.keys.add(k)
        elif t == "up":
            k = str(m["k"])
            b.up(k)
            self.keys.discard(k)
        elif t == "tap":
            b.tap(str(m["k"]))
        elif t == "combo":
            b.combo([str(k) for k in m.get("keys", [])][:6])
        elif t == "text":
            b.type_text(str(m.get("s", ""))[:5000])
        elif t == "layout":
            b.combo(LAYOUT_SWITCH)
        elif t == "move":
            b.move(float(m.get("dx", 0)), float(m.get("dy", 0)))
        elif t == "click":
            b.click(str(m.get("b", "left")), int(m.get("n", 1)))
        elif t == "mdown":
            btn = str(m.get("b", "left"))
            b.mouse_down(btn)
            self.buttons.add(btn)
        elif t == "mup":
            btn = str(m.get("b", "left"))
            b.mouse_up(btn)
            self.buttons.discard(btn)
        elif t == "scroll":
            b.scroll(int(m.get("dx", 0)), int(m.get("dy", 0)))
        elif t == "release":
            self.release_all()

    def release_all(self):
        for k in list(self.keys):
            try:
                self.b.up(k)
            except Exception:  # noqa: BLE001
                pass
        for btn in list(self.buttons):
            try:
                self.b.mouse_up(btn)
            except Exception:  # noqa: BLE001
                pass
        self.keys.clear()
        self.buttons.clear()


def make_app(backend: Backend, token: str) -> web.Application:
    async def index(_req):
        resp = web.FileResponse(STATIC / "index.html")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    async def ws_handler(req: web.Request):
        if not secrets.compare_digest(req.query.get("k", ""), token):
            return web.Response(status=403, text="bad key")
        ws = web.WebSocketResponse(heartbeat=15, max_msg_size=64 * 1024)
        await ws.prepare(req)
        peer = req.remote
        log.info("📱 подключился %s", peer)
        session = Session(backend)
        await ws.send_json({"t": "hello", "os": OS})
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    batch = data if isinstance(data, list) else [data]
                    for m in batch[:64]:
                        if m.get("t") == "ping":
                            await ws.send_json({"t": "pong", "id": m.get("id")})
                        else:
                            session.handle(m)
                except Exception as e:  # noqa: BLE001
                    log.warning("ошибка обработки %r: %s", msg.data[:200], e)
        finally:
            session.release_all()
            log.info("📴 отключился %s", peer)
        return ws

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", STATIC)
    return app


def main():
    p = argparse.ArgumentParser(description="Клавиатура и тачпад для компьютера с iPhone")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--new-key", action="store_true", help="сгенерировать новый ключ доступа")
    p.add_argument("--dry-run", action="store_true", help="не нажимать клавиши, только печатать")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for name in ("aiohttp.access",):
        logging.getLogger(name).setLevel(logging.WARNING)

    backend = Backend(dry_run=args.dry_run)
    token = load_token(args.new_key)
    url = f"http://{lan_ip()}:{args.port}/?k={token}"

    print()
    print("=" * 60)
    print(f"  Клавиатура для iPhone запущена · {os_label()}")
    print("  Телефон и компьютер должны быть в одной сети Wi-Fi.")
    print("  Наведите камеру iPhone на QR-код или откройте в Safari:")
    print(f"\n  {url}\n")
    print_qr(url)
    print("  Затем в Safari: «Поделиться» → «На экран Домой».")
    print("  Остановить: Ctrl+C")
    print("=" * 60)

    try:
        web.run_app(make_app(backend, token), host=args.host, port=args.port, print=None)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    main()
