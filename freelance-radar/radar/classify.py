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
          "telemarketing", "appointment setter", "смм-менеджер", "таргетолог"]

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
    return o
