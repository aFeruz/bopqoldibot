from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import ChatSettings, Reminder, utcnow
from bot.services.common import to_utc


async def add(session: AsyncSession, chat_id: int, text: str, when_local: datetime, author: str) -> Reminder:
    r = Reminder(chat_id=chat_id, text=text, remind_at=to_utc(when_local), author_name=author)
    session.add(r)
    await session.commit()
    return r


async def pending(session: AsyncSession, chat_id: int | None = None) -> list[Reminder]:
    q = select(Reminder).where(Reminder.sent.is_(False))
    if chat_id is not None:
        q = q.where(Reminder.chat_id == chat_id)
    return list(await session.scalars(q.order_by(Reminder.remind_at)))


async def due(session: AsyncSession) -> list[Reminder]:
    q = select(Reminder).where(Reminder.sent.is_(False), Reminder.remind_at <= utcnow())
    return list(await session.scalars(q))


async def cancel(session: AsyncSession, chat_id: int, reminder_id: int) -> bool:
    r = await session.get(Reminder, reminder_id)
    if not r or r.chat_id != chat_id or r.sent:
        return False
    r.sent = True
    await session.commit()
    return True


SETTINGS_FIELDS = ("morning_summary", "daily_summary", "weekly_summary", "due_alerts")


async def get_settings(session: AsyncSession, chat_id: int) -> ChatSettings:
    cs = await session.get(ChatSettings, chat_id)
    if cs is None:
        cs = ChatSettings(chat_id=chat_id, daily_summary=False, morning_summary=False, weekly_summary=False,
                          due_alerts=True)
        session.add(cs)
        await session.flush()
    return cs


async def set_flag(session: AsyncSession, chat_id: int, field: str, value: bool | None = None) -> ChatSettings:
    """Sozlamani o'rnatadi; value=None — teskarisiga almashtiradi."""
    if field not in SETTINGS_FIELDS:
        raise ValueError(field)
    cs = await get_settings(session, chat_id)
    setattr(cs, field, (not getattr(cs, field)) if value is None else value)
    await session.commit()
    return cs


async def set_daily(session: AsyncSession, chat_id: int, value: bool) -> None:
    await set_flag(session, chat_id, "daily_summary", value)


async def chats_with(session: AsyncSession, field: str) -> list[int]:
    col = getattr(ChatSettings, field)
    return list(await session.scalars(select(ChatSettings.chat_id).where(col.is_(True))))


async def daily_chats(session: AsyncSession) -> list[int]:
    return await chats_with(session, "daily_summary")


async def alerts_disabled(session: AsyncSession) -> set[int]:
    return set(await session.scalars(select(ChatSettings.chat_id).where(ChatSettings.due_alerts.is_(False))))
