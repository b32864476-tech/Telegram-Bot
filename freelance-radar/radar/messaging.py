"""Переписка с заказчиками через официальные API бирж.

Поддерживаются только биржи с публичным API для откликов и сообщений:
  • Freelancehunt — https://apidocs.freelancehunt.com (личный токен: Настройки → API)
  • Freelancer.com — https://developers.freelancer.com (OAuth-токен со scope basic,
    fln:project_manage, fln:messaging)

Как устроен диалог:
  1. Первое сообщение уходит как ОТКЛИК на заказ (bid) — так его увидит заказчик
     под своим заказом. Нужны сумма и срок.
  2. Когда заказчик отвечает, на бирже появляется переписка (thread). Radar находит её
     и дальше сообщения ходят туда в обе стороны.
У остальных бирж (FL.ru, Kwork, Freelance.ru, Pchel, PeoplePerHour) API для сообщений нет.
"""
import html
import re
import time
from datetime import datetime

import httpx

TIMEOUT = 25


class ChatError(Exception):
    """Ошибка, текст которой можно показать пользователю как есть."""


def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _ts(iso: str | None) -> int:
    try:
        return int(datetime.fromisoformat(iso).timestamp())
    except Exception:
        return int(time.time())


# ------------------------------------------------------------ Freelancehunt
class Freelancehunt:
    source = "freelancehunt"
    name = "Freelancehunt"
    currency = "UAH"
    base = "https://api.freelancehunt.com/v2"

    def __init__(self, token: str, safe_type: str = "employer"):
        self.token = token
        self.safe_type = safe_type or None
        self._me = None

    async def _req(self, method: str, path: str, **kw):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.request(method, self.base + path,
                                headers={"Authorization": f"Bearer {self.token}"}, **kw)
        if r.status_code == 401:
            raise ChatError("Freelancehunt не принял токен. Проверьте его в настройках Radar.")
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
                detail = err.get("detail") or err.get("title") or r.text[:200]
            except Exception:
                detail = r.text[:200]
            raise ChatError(f"Freelancehunt: {detail}")
        return r.json() if r.content else {}

    async def me(self) -> dict:
        if not self._me:
            d = (await self._req("GET", "/my/profile"))["data"]
            a = d["attributes"]
            self._me = {"id": str(d["id"]), "name": a.get("login") or a.get("first_name")}
        return self._me

    async def employer_of(self, project_id: str) -> str | None:
        d = (await self._req("GET", f"/projects/{project_id}"))["data"]["attributes"]
        emp = d.get("employer")
        return str(emp["id"]) if emp else None

    async def bid(self, project_id: str, text: str, amount: float, days: int, currency: str | None) -> dict:
        body = {"days": max(1, int(days)), "safe_type": self.safe_type,
                "budget": {"amount": round(float(amount)), "currency": currency or self.currency},
                "comment": text, "is_hidden": False}
        d = (await self._req("POST", f"/projects/{project_id}/bids", json=body))["data"]
        return {"bid_id": str(d["id"]), "message": {"id": f"{self.source}:bid:{d['id']}", "from_me": True,
                                                     "text": d["attributes"].get("comment") or text,
                                                     "at": int(time.time())}}

    async def find_thread(self, employer_id: str | None, project_id: str, project_title: str = "") -> str | None:
        if not employer_id:
            return None
        threads = (await self._req("GET", "/threads"))["data"]
        best = None
        for t in threads:
            p = t["attributes"].get("participants") or {}
            ids = {str((p.get("from") or {}).get("id")), str((p.get("to") or {}).get("id"))}
            if employer_id in ids:
                # если с заказчиком несколько переписок — берём ту, где тема похожа на заказ
                if project_title and project_title[:25].lower() in (t["attributes"].get("subject") or "").lower():
                    return str(t["id"])
                best = best or str(t["id"])
        return best

    async def messages(self, thread_id: str) -> list[dict]:
        me = (await self.me())["id"]
        data = (await self._req("GET", f"/threads/{thread_id}"))["data"]
        out = []
        for m in data:
            a = m["attributes"]
            frm = str(((a.get("participants") or {}).get("from") or {}).get("id"))
            out.append({"id": f"{self.source}:{m['id']}", "from_me": frm == me,
                        "text": a.get("message") or _strip_html(a.get("message_html")), "at": _ts(a.get("posted_at"))})
        return out

    async def send(self, thread_id: str, text: str) -> dict:
        d = (await self._req("POST", f"/threads/{thread_id}", json={"message_html": html.escape(text)}))["data"]
        return {"id": f"{self.source}:{d['id']}", "from_me": True, "text": text, "at": _ts(d["attributes"].get("posted_at"))}

    async def new_thread(self, employer_id: str, project_id: str, subject: str, text: str) -> str:
        d = (await self._req("POST", "/threads", json={"subject": subject[:100], "message_html": html.escape(text),
                                                      "to_profile_id": int(employer_id)}))["data"]
        return str(d["id"])


# ------------------------------------------------------------ Freelancer.com
class FreelancerCom:
    source = "freelancer.com"
    name = "Freelancer.com"
    currency = None   # отклик всегда в валюте заказа
    base = "https://www.freelancer.com/api"

    def __init__(self, token: str):
        self.token = token
        self._me = None

    async def _req(self, method: str, path: str, **kw):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.request(method, self.base + path, headers={"freelancer-oauth-v1": self.token}, **kw)
        try:
            j = r.json()
        except Exception:
            j = {}
        if r.status_code == 401 or j.get("error_code") == "RestExceptionCodes.NOT_AUTHENTICATED":
            raise ChatError("Freelancer.com не принял токен. Проверьте его в настройках Radar.")
        if r.status_code >= 400 or j.get("status") == "error":
            raise ChatError(f"Freelancer.com: {j.get('message') or r.text[:200]}")
        return j.get("result", {})

    async def me(self) -> dict:
        if not self._me:
            r = await self._req("GET", "/users/0.1/self/")
            self._me = {"id": str(r["id"]), "name": r.get("username") or r.get("display_name")}
        return self._me

    async def employer_of(self, project_id: str) -> str | None:
        r = await self._req("GET", f"/projects/0.1/projects/{project_id}/")
        return str(r["owner_id"]) if r.get("owner_id") else None

    async def bid(self, project_id: str, text: str, amount: float, days: int, currency: str | None) -> dict:
        me = (await self.me())["id"]
        body = {"project_id": int(project_id), "bidder_id": int(me), "amount": float(amount),
                "period": max(1, int(days)), "milestone_percentage": 100, "description": text}
        r = await self._req("POST", "/projects/0.1/bids/", json=body)
        return {"bid_id": str(r.get("id")), "message": {"id": f"{self.source}:bid:{r.get('id')}", "from_me": True,
                                                         "text": r.get("description") or text, "at": int(time.time())}}

    async def find_thread(self, employer_id: str | None, project_id: str, project_title: str = "") -> str | None:
        r = await self._req("GET", "/messages/0.1/threads/",
                            params={"contexts[]": project_id, "context_type": "project", "limit": 20})
        threads = r.get("threads") or []
        return str(threads[0]["id"]) if threads else None

    async def messages(self, thread_id: str) -> list[dict]:
        me = (await self.me())["id"]
        r = await self._req("GET", "/messages/0.1/messages/", params={"threads[]": thread_id, "limit": 100})
        return [{"id": f"{self.source}:{m['id']}", "from_me": str(m.get("from_user")) == me,
                 "text": m.get("message") or "", "at": int(m.get("time_created") or time.time())}
                for m in r.get("messages") or []]

    async def send(self, thread_id: str, text: str) -> dict:
        r = await self._req("POST", f"/messages/0.1/threads/{thread_id}/messages/", data={"message": text})
        return {"id": f"{self.source}:{r.get('id')}", "from_me": True, "text": text,
                "at": int(r.get("time_created") or time.time())}

    async def new_thread(self, employer_id: str, project_id: str, subject: str, text: str) -> str:
        me = (await self.me())["id"]
        r = await self._req("POST", "/messages/0.1/threads/",
                            data={"members[]": [int(employer_id), int(me)], "context_type": "project",
                                  "context": int(project_id), "message": text})
        return str((r.get("thread") or r).get("id"))


# ------------------------------------------------------------------ фабрика
SUPPORTED = {"freelancehunt": "Freelancehunt", "freelancer.com": "Freelancer.com"}
WHY_NOT = ("У этой биржи нет открытого API для сообщений. Отправка через браузер с вашим логином "
           "нарушает её правила и может привести к бану, поэтому Radar так не делает. "
           "Скопируйте отклик и отправьте его на сайте биржи.")


def provider(source: str, settings: dict):
    if source == "freelancehunt" and settings.get("freelancehunt_token"):
        return Freelancehunt(settings["freelancehunt_token"], settings.get("freelancehunt_safe_type", "employer"))
    if source == "freelancer.com" and settings.get("freelancer_token"):
        return FreelancerCom(settings["freelancer_token"])
    return None


def project_id_of(order_id: str) -> str:
    return order_id.split(":", 1)[1]
