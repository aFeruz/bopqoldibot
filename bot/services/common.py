from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import Category


def local_now() -> datetime:
    return datetime.now(settings.zone).replace(tzinfo=None)


def to_local(utc: datetime) -> datetime:
    return utc.replace(tzinfo=timezone.utc).astimezone(settings.zone).replace(tzinfo=None)


def to_utc(local: datetime) -> datetime:
    return local.replace(tzinfo=settings.zone).astimezone(timezone.utc).replace(tzinfo=None)


def period_start(period: str | None) -> datetime | None:
    """Davr boshini UTC da qaytaradi (None — butun vaqt)."""
    now = local_now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period in (None, "all"):
        return None
    if period == "today":
        start = midnight
    elif period == "yesterday":
        start = midnight - timedelta(days=1)
    elif period == "week":
        start = midnight - timedelta(days=now.weekday())
    elif period == "month":
        start = midnight.replace(day=1)
    elif period.endswith("d"):
        start = midnight - timedelta(days=int(period[:-1]) - 1)
    else:
        return None
    return to_utc(start)


def period_end(period: str | None) -> datetime | None:
    if period == "yesterday":
        return period_start("today")
    return None


PERIOD_TITLES = {
    "today": "bugun", "yesterday": "kecha", "week": "shu hafta", "month": "shu oy", "all": "butun vaqt",
}


def period_title(period: str | None) -> str:
    if period and period.endswith("d") and period[:-1].isdigit():
        return f"oxirgi {period[:-1]} kun"
    return PERIOD_TITLES.get(period or "all", "butun vaqt")


async def get_category(session: AsyncSession, chat_id: int, name: str | None, create: bool = True) -> Category | None:
    if not name:
        return None
    name = name.lower().strip()
    cat = await session.scalar(select(Category).where(Category.chat_id == chat_id, Category.name == name))
    if cat is None and create:
        cat = Category(chat_id=chat_id, name=name)
        session.add(cat)
        await session.flush()
    return cat


async def next_number(session: AsyncSession, model, chat_id: int) -> int:
    current = await session.scalar(select(func.max(model.number)).where(model.chat_id == chat_id))
    return (current or 0) + 1
