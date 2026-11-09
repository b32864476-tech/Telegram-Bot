# Джарвис — Telegram-бот для управления компьютером

Запускается **на вашем компьютере** и принимает команды из Telegram, пока вы не дома.

## Установка
1. Создайте бота у [@BotFather](https://t.me/BotFather), получите токен.
2. Узнайте свой ID у [@userinfobot](https://t.me/userinfobot).
3. ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env   # впишите BOT_TOKEN и ALLOWED_USER_IDS
   python -m jarvis
   ```
4. Для автозапуска: Планировщик задач (Windows), systemd user-unit (Linux) или launchd (macOS).

## Команды
`/status /screenshot /ps /kill /sh /open /get /ls /volume /lock /sleep /reboot /shutdown /cancel`,
а присланные боту файлы сохраняются в `~/JarvisUploads`.

## Безопасность
- Бот отвечает **только** ID из `ALLOWED_USER_IDS`; остальные игнорируются.
- `/sh` даёт полный доступ к системе — никому не передавайте токен и включите двухфакторку в Telegram.
- Выключение/перезагрузка/сон требуют подтверждения кнопкой.
- Бот использует long polling: открывать порты на роутере не нужно.
- Если токен утёк — сразу `/revoke` у BotFather.
