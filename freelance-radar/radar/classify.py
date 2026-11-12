"""Обогащение заказа: категория, цена в рублях, сложность (1–5), пригодность для ИИ (0–100)."""
import re

# Примерные курсы к рублю, используются только для сортировки и фильтрации.
RATES = {"RUB": 1.0, "USD": 82.0, "EUR": 95.0, "GBP": 108.0, "UAH": 2.0,
         "KZT": 0.16, "BYN": 25.0, "INR": 0.95, "CAD": 59.0, "AUD": 54.0}

CATEGORIES = {
    "bot":    ["бот", "telegram", "телеграм", "chatbot", " bot", "discord", "whatsapp", "vk бот", "max бот"],
    "web":    ["сайт", "лендинг", "landing", "website", "web site", "wordpress", "tilda", "тильд", "html",
               "верстк", "frontend", "фронтенд", "shopify", "webflow", "интернет-магазин", "web app", "веб"],
    "app":    ["приложени", "mobile app", "android", "ios", "flutter", "react native", "desktop", "app "],
    "script": ["скрипт", "парс", "scrap", "автоматизац", "automation", "python", "api", "интеграц",
               "integration", "макрос", "macro", "google sheets", "selenium", "excel vba", "программ",
               "javascript", "php", "node", "backend", "бэкенд", "1с", "бд", "sql", "software"],
    "ai":     ["нейросет", "chatgpt", "gpt", " ai ", "ai-", "llm", "machine learning", "ml ",
               "искусственн", "openai", "claude", "midjourney", "stable diffusion"],
    "design": ["дизайн", "логотип", "баннер", "figma", "фигм", "logo", "ui/ux", "ux/ui", "иллюстрац",
               "illustrat", "graphic", "графич", "презентац", "presentation", "карточк", "инфографик"],
    "text":   ["текст", "стать", "копирайт", "рерайт", "перевод", "translat", "article", "content writ",
               "copywrit", "blog", "описани", "сценари", "редактур", "proofread"],
    "video":  ["видео", "монтаж", "video", "reels", "анимац", "animation", "motion", "youtube", "озвуч"],
    "data":   ["excel", "таблиц", "data entry", "данн", "dashboard", "дашборд", "анализ", "analys",
               "research", "исследован", "spreadsheet"],
}
CATEGORY_LABELS = {"bot": "Боты", "web": "Сайты", "app": "Приложения", "script": "Скрипты и автоматизация",
                   "ai": "AI / нейросети", "design": "Дизайн", "text": "Тексты и переводы",
                   "video": "Видео и анимация", "data": "Данные и таблицы", "other": "Другое"}
AI_FIT = {"bot": 95, "script": 92, "web": 90, "text": 90, "ai": 88, "data": 85,
          "design": 72, "app": 70, "video": 55, "other": 25}

# То, что нейросеть за вас не сделает: живые продажи, звонки, офлайн, юр. подпись и т.п.
NOT_AI = ["лидоген", "лидген", "холодн", "звонк", "обзвон", "продаж", "менеджер по", "курьер", "ремонт",
          "монтаж оборуд", "выезд", "на объект", "офис", "бухгалтер", "юрист", "нотари", "solicitor",
          "lawyer", "accountant", "cold call", "sales rep", "lead generation", "в штат", "вакансия",
          "full-time", "on-site", "отзыв", "накрут", "фотосесс", "фотограф", "грузчик", "водител",
          "telemarketing", "appointment setter", "recruit", "рекрут", "hr-менеджер", "team leader", "смм-менеджер", "таргетолог"]

HARD = ["маркетплейс", "marketplace", "crm", "erp", "saas", "платформ", "platform", "highload",
        "блокчейн", "blockchain", "смарт-контракт", "smart contract", "мультивендор", "multi-vendor",
        "android и ios", "ios и android", "ios and android", "кроссплатформ", "биллинг", "billing",
        "социальн сеть", "social network", "uber", "агрегатор", "machine learning", "обучение модели",
        "computer vision", "компьютерное зрение", "микросервис", "microservice", "мобильное приложение"]
MEDIUM = ["админк", "admin panel", "api", "интеграц", "integration", "база данных", "database",
          "авторизац", "личный кабинет", "оплат", "payment", "stripe", "backend", "бэкенд", "react",
          "vue", "django", "laravel", "fastapi", "dashboard", "дашборд", "парсер", "scraper", "1с",
          "битрикс", "bitrix", "интернет-магазин", "e-commerce", "ecommerce", "чат-бот с оплат", "webapp"]
EASY = ["лендинг", "landing", "правк", "исправ", "fix ", "bug", "небольш", "простой", "простая", "простого",
        "small", "simple", "quick", "логотип", "logo", "баннер", "banner", "статья", "article", "перевод",
        "translat", "одностранич", "one page", "визитк", "обложк", "аватар", "рерайт", "описание товар",
        "доработ", "tweak", "минор"]


_cache: dict = {}


def _rx(words):
    """Ключевые слова совпадают только с начала слова: «бот» не найдётся в «работа»."""
    key = id(words)
    if key not in _cache:
        _cache[key] = [re.compile(r"(?<![\w])" + re.escape(w.strip())) for w in words]
    return _cache[key]


def _has(text: str, words) -> int:
    return sum(1 for r in _rx(words) if r.search(text))


def to_rub(amount, currency: str | None):
    if amount is None:
        return None
    return round(float(amount) * RATES.get((currency or "RUB").upper(), 1.0))


_num = re.compile(r"(\d[\d\s  ]*(?:[.,]\d+)?)")


def parse_money(text: str):
    """'Бюджет: 20 000 ₽' / '$665' / '100USD' -> (amount, currency) или (None, None)."""
    if not text:
        return None, None
    t = text.replace("&#8381;", "₽")
    cur = None
    if "₽" in t or "руб" in t.lower() or "rub" in t.lower():
        cur = "RUB"
    elif "$" in t or "usd" in t.lower():
        cur = "USD"
    elif "€" in t or "eur" in t.lower():
        cur = "EUR"
    elif "£" in t or "gbp" in t.lower():
        cur = "GBP"
    elif "₴" in t or "uah" in t.lower() or "грн" in t.lower():
        cur = "UAH"
    elif "₸" in t or "kzt" in t.lower():
        cur = "KZT"
    m = _num.search(t)
    if not m or not cur:
        return None, None
    try:
        val = float(re.sub(r"[\s  ]", "", m.group(1)).replace(",", "."))
    except ValueError:
        return None, None
    return (val, cur) if val > 0 else (None, None)


def enrich(o: dict) -> dict:
    text = f" {o.get('title', '')} {o.get('description', '')} {o.get('tags', '')} ".lower()

    scores = {cat: _has(text, words) for cat, words in CATEGORIES.items()}
    # Заголовок важнее описания.
    title = f" {o.get('title', '')} ".lower()
    for cat, words in CATEGORIES.items():
        scores[cat] += 2 * _has(title, words)
    best = max(scores, key=scores.get)
    category = best if scores[best] > 0 else "other"

    fit = AI_FIT[category]
    if _has(text, NOT_AI):
        fit = max(5, fit - 55)

    rub = o.get("price_rub")
    cx = 2 + 2 * min(1, _has(text, HARD)) + min(1, _has(text, MEDIUM)) - min(1, _has(title, EASY) + _has(text, EASY) // 2)
    if category == "app":
        cx += 1
    if len(o.get("description", "")) > 2500:
        cx += 1
    if rub is not None:
        if rub < 3000:
            cx -= 1
        elif rub > 60000:
            cx += 1
        if rub > 250000:
            cx += 1
    o["complexity"] = max(1, min(5, cx))
    o["category"] = category
    o["ai_fit"] = fit
    return estimate(o)


# ------------------------------------------------------------------ сроки
# Часы работы С ИИ для задачи средней «ширины» по уровню сложности (диапазон).
CX_HOURS = {1: (0.5, 2), 2: (2, 5), 3: (5, 14), 4: (14, 36), 5: (36, 90)}
# Поправка по направлению: тексты ИИ пишет быстро, приложения дольше собирать и тестировать.
CAT_MULT = {"text": .5, "data": .6, "design": .75, "script": .9, "bot": 1.0, "web": 1.0,
            "ai": 1.1, "video": 1.2, "app": 1.4, "other": 1.2}
# Во сколько раз дольше то же самое без ИИ.
SPEEDUP = {"text": 4, "script": 3.2, "bot": 3, "data": 3, "web": 2.6, "ai": 2.2,
           "design": 2, "app": 2.2, "video": 1.6, "other": 1.5}
# Какие этапы входят в работу и какая доля времени на них уходит.
PLAN = {
    "bot":    [("Разобрать ТЗ, сценарии и команды бота", .1), ("Код бота с ИИ (aiogram / python-telegram-bot)", .4),
               ("Тест в Telegram и правки", .3), ("Деплой на сервер и сдача", .2)],
    "web":    [("Структура и тексты страниц", .15), ("Вёрстка и логика с ИИ", .45),
               ("Адаптив, проверка в браузерах", .25), ("Домен, хостинг, сдача", .15)],
    "script": [("Разобрать задачу и данные", .15), ("Код с ИИ", .4), ("Тест на реальных данных и правки", .3),
               ("Инструкция по запуску и сдача", .15)],
    "app":    [("Экраны и архитектура", .15), ("Код с ИИ", .4), ("Тест на устройствах и правки", .3),
               ("Сборка, публикация, сдача", .15)],
    "ai":     [("Разобрать задачу, выбрать модель", .15), ("Промпты, интеграция, код с ИИ", .45),
               ("Проверка качества ответов", .25), ("Сдача и инструкция", .15)],
    "text":   [("Бриф и структура", .15), ("Черновик с ИИ", .3), ("Редактура и проверка фактов", .4),
               ("Сдача и правки", .15)],
    "design": [("Референсы и концепция", .2), ("Генерация и сборка макета", .4), ("Доработка вручную", .3),
               ("Исходники и сдача", .1)],
    "data":   [("Разобрать источник данных", .15), ("Формулы / скрипт с ИИ", .4), ("Проверка результата", .3),
               ("Сдача", .15)],
    "video":  [("Сценарий и материалы", .2), ("Генерация / монтаж с ИИ", .45), ("Цвет, звук, правки", .25),
               ("Рендер и сдача", .1)],
    "other":  [("Разобраться в задаче", .25), ("Основная работа с ИИ", .45), ("Проверка и правки", .3)],
}
MARKET_RATE = 1500     # ₽/ч, средняя ставка фрилансера без ИИ — для сверки с бюджетом
HOURLY_HOURS = 20      # столько часов закладывает парсер Freelancer.com в бюджет почасовых заказов
EXTRA_WORK = ["оплат", "payment", "админк", "admin panel", "личный кабинет", "авторизац", "регистрац",
              "база данных", "database", "интеграц", "integration", "api", "crm", "1с", "уведомлен",
              "notification", "рассылк", "мультиязыч", "multilingual", "парсинг", "scrap", "дизайн с нуля"]

_deadline = [
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:-|–|до)?\s*(?:\d+\s*)?(час|ч\b|hour|hr)"), 1 / 8),
    (re.compile(r"(\d+)\s*(?:-|–)?\s*(?:\d+\s*)?(дн|день|дня|сут|day)"), 1),
    (re.compile(r"(\d+)\s*(?:-|–)?\s*(?:\d+\s*)?(недел|week)"), 7),
    (re.compile(r"(\d+)\s*(?:-|–)?\s*(?:\d+\s*)?(месяц|мес\b|month)"), 30),
]
_deadline_ctx = re.compile(r"(срок|deadline|within|за\s+\d|в течени|выполнить за|сделать за|turnaround|deliver)")
_volume = [
    (re.compile(r"(\d[\d\s]{0,6})\s*(?:слов|words)"), "words"),
    (re.compile(r"(\d[\d\s]{0,7})\s*(?:знак|символ|characters|chars)"), "chars"),
    (re.compile(r"(\d{1,3})\s*(?:стат|articles|posts|постов|текст)"), "articles"),
    (re.compile(r"(\d{1,3})\s*(?:баннер|логотип|иллюстрац|картин|изображен|images|banners|slides|слайд)"), "pics"),
    (re.compile(r"(\d{1,3})\s*(?:видео|ролик|videos|reels)"), "videos"),
]


def parse_deadline(text: str):
    """Срок, который назвал заказчик, в днях (None, если не указан)."""
    if text.startswith("срок:"):          # freelance.ru отдаёт поле «Срок: 3 дня»
        window = text
    else:
        m = _deadline_ctx.search(text)
        if not m:
            return None
        window = text[m.start(): m.start() + 60]
    for rx, mult in _deadline:
        d = rx.search(window)
        if d:
            val = float(d.group(1).replace(",", ".")) * mult
            if 0 < val <= 365:
                return round(val, 2)
    if "сегодня" in window or "срочно" in window or "today" in window:
        return 1.0
    return None


def estimate(o: dict) -> dict:
    """Сколько часов займёт заказ с ИИ (диапазон) и без ИИ, ставка ₽/час, успеваете ли к сроку."""
    text = f" {o.get('title', '')} {o.get('description', '')} ".lower()
    cat, cx = o["category"], o["complexity"]
    lo, hi = CX_HOURS[cx]
    m = CAT_MULT[cat]
    lo, hi = lo * m, hi * m

    hourly = "почасовая" in (o.get("tags") or "")
    volume_known = False
    # Объём в тексте ТЗ точнее общей оценки: «5 статей», «3000 слов», «10 баннеров».
    for rx, kind in _volume:
        v = rx.search(text)
        if not v:
            continue
        n = int(re.sub(r"\s", "", v.group(1)) or 0)
        if not n:
            continue
        per = {"words": n / 2500, "chars": n / 15000, "articles": n * .6, "pics": n * .4, "videos": n * 1.5}[kind]
        if per > 0:
            lo, hi = max(.3, per * .7), max(.6, per * 1.4)
            volume_known = True
            break

    # Бюджет тоже подсказывает объём: за 60 000 ₽ вряд ли просят 15-минутную задачу.
    # Сводим оценку по ТЗ с оценкой «по деньгам» (рынок ≈ 1500 ₽/ч вручную).
    # Для диапазона «от–до» берём середину: «до $750» обычно значит меньше.
    budget = o.get("price_rub")
    if budget and o.get("price_min") and o.get("price"):
        budget = budget * (o["price_min"] + o["price"]) / (2 * o["price"])
    if budget and not hourly:
        mid0 = (lo + hi) / 2
        implied = budget / MARKET_RATE / SPEEDUP[cat]
        lim = (.8, 2) if volume_known else (.6, 3.5)
        k = max(lim[0], min(lim[1], (mid0 * implied) ** .5 / mid0))
        lo, hi = lo * k, hi * k

    extra = min(4, _has(text, EXTRA_WORK))
    lo, hi = lo * (1 + .12 * extra), hi * (1 + .15 * extra)
    lo, hi = round(lo, 1), round(max(hi, lo + .5), 1)
    mid = (lo + hi) / 2

    o["ai_hours_lo"], o["ai_hours_hi"] = lo, hi
    o["manual_hours"] = round(mid * SPEEDUP[cat], 1)
    if hourly:   # почасовой заказ: ставка — это и есть оплата за час
        o["rate_rub"] = round(o["price_rub"] / HOURLY_HOURS) if o.get("price_rub") else None
    else:
        o["rate_rub"] = round(budget / mid) if budget else None

    dl = parse_deadline((o.get("deadline_text") or "").lower()) or parse_deadline(text)
    o["deadline_days"] = dl
    if dl:
        work_days = hi / 6               # ~6 продуктивных часов в день
        o["fits"] = "ok" if work_days <= dl * .6 else "tight" if work_days <= dl else "no"
    else:
        o["fits"] = None
    return o
