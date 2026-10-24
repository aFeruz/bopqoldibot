from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Recurring
from bot.services.common import local_now

WEEKDAY_NAMES = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]


def describe(rule: str, hour: int, minute: int) -> str:
    t = f"{hour:02d}:{minute:02d}"
    if rule == "daily":
        return f"har kuni {t}"
    if rule == "workdays":
        return f"ish kunlari {t}"
    kind, _, arg = rule.partition(":")
    if kind == "weekly":
        return f"har {WEEKDAY_NAMES[int(arg)]} {t}"
    return f"har oyning {arg}-sanasi {t}"


def matches_today(rule: str, now: datetime) -> bool:
    if rule == "daily":
        return True
    if rule == "workdays":
        return now.weekday() < 5
    kind, _, arg = rule.partition(":")
    if kind == "weekly":
        return now.weekday() == int(arg)
    return now.day == int(arg)


async def add(
    session: AsyncSession, chat_id: int, text: str, rule: str, hour: int, minute: int,
    category: str | None, assignee: str | None, author: str,
) -> Recurring:
    now = local_now()
    # bugungi vaqti o'tib ketgan bo'lsa, birinchi marta keyingi safar ishlaydi
    passed = matches_today(rule, now) and (now.hour, now.minute) >= (hour, minute)
    r = Recurring(chat_id=chat_id, text=text, rule=rule, hour=hour, minute=minute, category=category,
                  assignee=assignee, author_name=author, last_run=now.date().isoformat() if passed else None)
    session.add(r)
    await session.commit()
    return r


async def list_active(session: AsyncSession, chat_id: int) -> list[Recurring]:
    q = select(Recurring).where(Recurring.chat_id == chat_id, Recurring.active.is_(True)).order_by(Recurring.id)
    return list(await session.scalars(q))


async def deactivate(session: AsyncSession, chat_id: int, rid: int) -> bool:
    r = await session.get(Recurring, rid)
    if not r or r.chat_id != chat_id or not r.active:
        return False
    r.active = False
    await session.commit()
    return True


async def due_now(session: AsyncSession, now: datetime) -> list[Recurring]:
    """Bugun ishga tushishi kerak bo'lgan va vaqti kelganlar (bot o'chiq turgan bo'lsa ham shu kuni yetkaziladi)."""
    today = now.date().isoformat()
    rows = await session.scalars(select(Recurring).where(Recurring.active.is_(True)))
    return [
        r for r in rows
        if r.last_run != today and matches_today(r.rule, now) and (now.hour, now.minute) >= (r.hour, r.minute)
    ]
