"""Телеграм-бот Джарвис: удалённое управление компьютером."""
import io
import logging
import os
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from . import system

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("jarvis")

TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
SHELL_TIMEOUT = int(os.getenv("SHELL_TIMEOUT", "60"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", Path.home() / "JarvisUploads"))
MAX_MSG = 3900

HELP = """🤖 Джарвис к вашим услугам, сэр.

/status — состояние ПК
/screenshot — скриншот экрана
/ps — топ процессов
/kill <pid|имя> — завершить процесс
/sh <команда> — выполнить shell-команду
/open <приложение|файл|URL> — открыть
/get <путь> — прислать файл с ПК
/ls [путь] — список файлов
/volume <0-100> — громкость
/lock — заблокировать экран
/sleep — спящий режим
/reboot — перезагрузка
/shutdown — выключение
/cancel — отменить выключение (Windows/Linux)

Файл, отправленный боту, сохранится в папку загрузок на ПК."""


def authorized(func):
    """Пускает только пользователей из ALLOWED_USER_IDS, остальным — тишина."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id not in ALLOWED:
            log.warning("Отказ в доступе: id=%s", user.id if user else None)
            return
        try:
            return await func(update, ctx)
        except Exception as e:  # noqa: BLE001
            log.exception("Ошибка в %s", func.__name__)
            msg = update.effective_message
            if msg:
                await msg.reply_text(f"⚠️ Ошибка: {e}")
    return wrapper


async def reply_long(update: Update, text: str):
    if len(text) <= MAX_MSG:
        await update.effective_message.reply_text(f"<pre>{escape(text)}</pre>", parse_mode="HTML")
    else:
        bio = io.BytesIO(text.encode())
        bio.name = "output.txt"
        await update.effective_message.reply_document(bio)


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@authorized
async def start(update, ctx):
    await update.message.reply_text(HELP)


@authorized
async def status(update, ctx):
    await update.message.reply_text(system.status_text())


@authorized
async def screenshot(update, ctx):
    png = system.screenshot_png()
    await update.message.reply_document(io.BytesIO(png), filename="screenshot.png")


@authorized
async def ps(update, ctx):
    await reply_long(update, system.top_processes())


@authorized
async def kill(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Использование: /kill <pid|имя>")
    await update.message.reply_text(system.kill_process(" ".join(ctx.args)))


@authorized
async def sh(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Использование: /sh <команда>")
    cmd = update.message.text.split(maxsplit=1)[1]
    await reply_long(update, await system.run_shell(cmd, SHELL_TIMEOUT))


@authorized
async def open_cmd(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Использование: /open <приложение|файл|URL>")
    target = update.message.text.split(maxsplit=1)[1]
    system.open_target(target)
    await update.message.reply_text(f"✅ Открываю: {target}")


@authorized
async def get_file(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Использование: /get <путь>")
    path = Path(update.message.text.split(maxsplit=1)[1]).expanduser()
    if not path.is_file():
        return await update.message.reply_text("Файл не найден")
    if path.stat().st_size > 50 * 1024 * 1024:
        return await update.message.reply_text("Файл больше 50 МБ — лимит Telegram для ботов")
    with path.open("rb") as f:
        await update.message.reply_document(f, filename=path.name)


@authorized
async def ls(update, ctx):
    arg = update.message.text.split(maxsplit=1)
    path = Path(arg[1] if len(arg) > 1 else ".").expanduser()
    if not path.is_dir():
        return await update.message.reply_text("Папка не найдена")
    rows = []
    for p in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            rows.append(f"{'📁' if p.is_dir() else '📄'} {p.name}"
                        + ("" if p.is_dir() else f"  ({system.human(p.stat().st_size)})"))
        except OSError:
            rows.append(f"❓ {p.name}")
    await reply_long(update, f"{path.resolve()}\n" + "\n".join(rows or ["(пусто)"]))


@authorized
async def volume(update, ctx):
    if not ctx.args or not ctx.args[0].isdigit():
        return await update.message.reply_text("Использование: /volume <0-100>")
    await update.message.reply_text(system.set_volume(int(ctx.args[0])))


@authorized
async def lock(update, ctx):
    system.lock()
    await update.message.reply_text("🔒 Экран заблокирован")


@authorized
async def cancel(update, ctx):
    system.power("cancel")
    await update.message.reply_text("↩️ Отмена выключения отправлена")


def confirm_cmd(action: str, title: str):
    @authorized
    async def handler(update, ctx):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Да", callback_data=f"confirm:{action}"),
            InlineKeyboardButton("❌ Нет", callback_data="confirm:no"),
        ]])
        await update.message.reply_text(f"{title} Подтвердите, сэр.", reply_markup=kb)
    return handler


@authorized
async def on_confirm(update, ctx):
    q = update.callback_query
    await q.answer()
    action = q.data.split(":", 1)[1]
    if action == "no":
        return await q.edit_message_text("Отменено.")
    system.power(action)
    await q.edit_message_text(f"✅ Выполняю: {action}")


@authorized
async def on_upload(update, ctx):
    msg = update.message
    att = msg.document or (msg.photo[-1] if msg.photo else None)
    if not att:
        return
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = getattr(att, "file_name", None) or f"{att.file_unique_id}.jpg"
    dest = UPLOAD_DIR / Path(name).name  # защита от path traversal
    f = await att.get_file()
    await f.download_to_drive(dest)
    await msg.reply_text(f"📥 Сохранено: {dest}")


def main():
    if not TOKEN or not ALLOWED:
        raise SystemExit("Задайте BOT_TOKEN и ALLOWED_USER_IDS в .env (см. .env.example)")
    app = Application.builder().token(TOKEN).build()
    for name, fn in [("start", start), ("help", start), ("status", status),
                     ("screenshot", screenshot), ("ps", ps), ("kill", kill), ("sh", sh),
                     ("open", open_cmd), ("get", get_file), ("ls", ls),
                     ("volume", volume), ("lock", lock), ("cancel", cancel)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CommandHandler("shutdown", confirm_cmd("shutdown", "⚠️ Выключить компьютер?")))
    app.add_handler(CommandHandler("reboot", confirm_cmd("reboot", "⚠️ Перезагрузить компьютер?")))
    app.add_handler(CommandHandler("sleep", confirm_cmd("sleep", "😴 Перевести ПК в сон?")))
    app.add_handler(CallbackQueryHandler(on_confirm, pattern=r"^confirm:"))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, on_upload))
    log.info("Джарвис запущен. Разрешённые пользователи: %s", sorted(ALLOWED))
    app.run_polling()


if __name__ == "__main__":
    main()
