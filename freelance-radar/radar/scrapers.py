"""Парсеры фриланс-бирж. Каждый возвращает список «сырых» заказов (dict)."""
import asyncio
import html
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

from .classify import parse_money, to_rub

log = logging.getLogger("radar")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}


def clean(s: str | None, limit: int = 4000) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s[:limit]


def rss_ts(s: str | None):
    try:
        return int(parsedate_to_datetime(s).timestamp()) if s else None
    except Exception:
        return None


def mk(source, ext_id, url, title, desc="", tags="", amount=None, currency=None,
       amount_min=None, published=None, bids=None) -> dict:
    return {
        "id": f"{source}:{ext_id}", "source": source, "url": url,
        "title": clean(title, 300), "description": clean(desc), "tags": tags,
        "price": amount, "price_min": amount_min, "currency": currency,
        "price_rub": to_rub(amount, currency), "published": published, "bids": bids,
    }


# ---------------------------------------------------------------- FL.ru (RSS)
FL_CATEGORIES = [None, 2, 3, 5, 6, 8, 11]   # все, сайты, дизайн, программирование, SEO, тексты, аудио/видео


async def fl_ru(c: httpx.AsyncClient) -> list[dict]:
    out = {}
    for cat in FL_CATEGORIES:
        url = "https://www.fl.ru/rss/all.xml" + (f"?category={cat}" if cat else "")
        r = await c.get(url)
        r.raise_for_status()
        for it in ET.fromstring(r.content).iter("item"):
            title = it.findtext("title") or ""
            link = it.findtext("link") or ""
            m = re.search(r"/projects/(\d+)", link)
            if not m:
                continue
            amount, cur = None, None
            b = re.search(r"\(Бюджет:([^)]*)\)\s*$", title)
            if b:
                amount, cur = parse_money(html.unescape(b.group(1)))
                title = title[: b.start()].strip()
            out[m.group(1)] = mk("fl.ru", m.group(1), link, title, it.findtext("description"),
                                 it.findtext("category") or "", amount, cur,
                                 published=rss_ts(it.findtext("pubDate")))
    return list(out.values())


# ---------------------------------------------------------- Freelance.ru (HTML)
async def freelance_ru(c: httpx.AsyncClient, pages: int = 8) -> list[dict]:
    out = []
    for p in range(1, pages + 1):
        r = await c.get("https://freelance.ru/task", params={"page": p})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("article.task-card")
        if not cards:
            break
        for card in cards:
            a = card.select_one("a.task-card__title-link")
            if not a:
                continue
            m = re.search(r"/task/view/(\d+)", a["href"])
            if not m:
                continue
            budget = card.select_one(".task-card__budget .bold")
            amount, cur = parse_money(budget.get_text(" ") if budget else "")
            desc = card.select_one(".task-card__desc")
            tags = ", ".join(t.get_text(strip=True) for t in card.select(".task-chip"))
            meta = card.select_one(".task-card__meta-rows")
            o = mk("freelance.ru", m.group(1), "https://freelance.ru" + a["href"],
                   a.get("title") or a.get_text(), desc.decode_contents() if desc else "",
                   tags, amount, cur)
            o["deadline_text"] = clean(meta.get_text(" ")) if meta else ""
            out.append(o)
        await asyncio.sleep(0.5)
    return out


# --------------------------------------------------------- Freelancehunt (RSS)
async def freelancehunt(c: httpx.AsyncClient) -> list[dict]:
    r = await c.get("https://freelancehunt.com/projects.rss")
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).iter("item"):
        title = it.findtext("title") or ""
        link = (it.findtext("link") or "").split("?")[0]
        m = re.search(r"/(\d+)\.html", link)
        if not m:
            continue
        amount, cur = None, None
        b = re.search(r"\s-\s([\d\s]+)\s?(USD|UAH|EUR|PLN|RUB)\s*$", title)
        if b:
            amount, cur = float(b.group(1).replace(" ", "")), b.group(2)
            title = title[: b.start()]
        tags = ", ".join(x.text or "" for x in it.findall("category"))
        out.append(mk("freelancehunt", m.group(1), link, title, it.findtext("description"), tags,
                      amount, cur, published=rss_ts(it.findtext("pubDate"))))
    return out


# ----------------------------------------------------- Freelancer.com (API)
async def freelancer_com(c: httpx.AsyncClient, pages: int = 10) -> list[dict]:
    out = []
    usd_rub = to_rub(1, "USD")
    for p in range(pages):
        r = await c.get("https://www.freelancer.com/api/projects/0.1/projects/active/",
                        params={"limit": 100, "offset": p * 100, "job_details": "true",
                                "full_description": "true", "sort_field": "time_updated"})
        r.raise_for_status()
        projects = r.json().get("result", {}).get("projects", [])
        if not projects:
            break
        for pr in projects:
            b = pr.get("budget") or {}
            cur = pr.get("currency") or {}
            rate = cur.get("exchange_rate") or 1  # к доллару
            hi = b.get("maximum") or b.get("minimum")
            o = mk("freelancer.com", pr["id"], f"https://www.freelancer.com/projects/{pr.get('seo_url')}",
                   pr.get("title", ""), pr.get("description") or pr.get("preview_description", ""),
                   ", ".join(j.get("name", "") for j in pr.get("jobs") or []),
                   hi, cur.get("code"), b.get("minimum"), pr.get("time_submitted"),
                   (pr.get("bid_stats") or {}).get("bid_count"))
            o["price_rub"] = round(hi * rate * usd_rub) if hi else None
            if pr.get("type") == "hourly" and hi:
                o["tags"] += ", почасовая"
                o["price_rub"] *= 20   # оценка: ~20 часов работы
            out.append(o)
        await asyncio.sleep(0.4)
    return out


# --------------------------------------------------------------- Pchel.net
async def pchel(c: httpx.AsyncClient, pages: int = 6) -> list[dict]:
    out = []
    for p in range(1, pages + 1):
        url = "https://pchel.net/jobs/" + (f"page-{p}/" if p > 1 else "")
        r = await c.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.select("div.project-block")
        if not blocks:
            break
        for bl in blocks:
            a = bl.select_one(".project-title a")
            pid = bl.select_one("input[name=project_id]")
            if not a or not pid:
                continue
            price = bl.select_one(".project-block-cont .price")
            amount, cur = parse_money(price.get_text(" ") if price else "")
            desc = bl.select_one(".project-text")
            tags = ", ".join(x.get_text(strip=True) for x in bl.select(".project-tags a"))
            bids = bl.select_one(".p-user")
            out.append(mk("pchel.net", pid["value"], "https://pchel.net" + a["href"], a.get_text(),
                          desc.decode_contents() if desc else "", tags, amount, cur,
                          bids=int(bids.get_text(strip=True)) if bids and bids.get_text(strip=True).isdigit() else None))
        await asyncio.sleep(0.5)
    return out


# --------------------------------------------------------- PeoplePerHour
async def peopleperhour(c: httpx.AsyncClient, pages: int = 5) -> list[dict]:
    out = []
    for p in range(1, pages + 1):
        r = await c.get("https://www.peopleperhour.com/freelance-jobs", params={"page": p})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("li[class*='list__item']")
        if not items:
            break
        for li in items:
            a = li.select_one("a[class*='item__url']")
            if not a:
                continue
            m = re.search(r"-(\d+)$", a["href"].rstrip("/"))
            if not m:
                continue
            price = li.select_one("[class*='card__price']")
            amount, cur = parse_money(price.get_text(" ") if price else "")
            desc = li.select_one("p[class*='item__desc']")
            out.append(mk("peopleperhour", m.group(1), a["href"], a.get_text(),
                          desc.get_text("\n") if desc else "", "", amount, cur))
        await asyncio.sleep(0.6)
    return out


# ------------------------------------------------------------------ Kwork
async def kwork(c: httpx.AsyncClient, pages: int = 5) -> list[dict]:
    """Kwork блокирует IP дата-центров; с домашнего интернета обычно работает."""
    out = []
    for p in range(1, pages + 1):
        r = await c.post("https://kwork.ru/projects", data={"c": "all", "page": p},
                         headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
        if "not_access" in str(r.url) or r.status_code >= 400:
            raise RuntimeError(f"Kwork закрыл доступ (HTTP {r.status_code}) — запустите с домашнего IP")
        data = r.json().get("data", {})
        wants = data.get("wants") or data.get("pagination", {}).get("data") or []
        if not wants:
            break
        for w in wants:
            amount = float(w.get("possiblePriceLimit") or w.get("priceLimit") or 0) or None
            out.append(mk("kwork", w["id"], f"https://kwork.ru/projects/{w['id']}", w.get("name", ""),
                          w.get("description", ""), "", amount, "RUB",
                          float(w.get("priceLimit") or 0) or None, bids=w.get("kwork_count")))
        await asyncio.sleep(0.6)
    return out


SOURCES = {
    "fl.ru": fl_ru,
    "freelance.ru": freelance_ru,
    "freelancehunt": freelancehunt,
    "freelancer.com": freelancer_com,
    "pchel.net": pchel,
    "peopleperhour": peopleperhour,
    "kwork": kwork,
}


async def collect(only: list[str] | None = None):
    """Запускает все парсеры параллельно. Возвращает {source: (orders | Exception)}."""
    async with httpx.AsyncClient(headers=HEADERS, timeout=25, follow_redirects=True) as c:
        names = [n for n in SOURCES if not only or n in only]
        res = await asyncio.gather(*(SOURCES[n](c) for n in names), return_exceptions=True)
    return dict(zip(names, res))
