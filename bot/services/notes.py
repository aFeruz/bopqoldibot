from datetime import datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Category, Note, utcnow
from bot.services.common import get_category, local_now, next_number


async def add_note(
    session: AsyncSession, chat_id: int, text: str, author_id: int | None, author_name: str,
    category: str | None = None, important: bool = False, due_at: datetime | None = None,
    assignee: str | None = None,
) -> Note:
    cat = await get_category(session, chat_id, category)
    note = Note(
        chat_id=chat_id, number=await next_number(session, Note, chat_id), text=text,
        category_id=cat.id if cat else None, category=cat, important=important, due_at=due_at,
        author_id=author_id, author_name=author_name, assignee=assignee,
        # muddat allaqachon o'tgan bo'lsa ("bugun" 9:00 dan keyin yozilgan) — darhol xabar yubormaymiz
        due_notified=bool(due_at and due_at <= local_now()),
    )
    session.add(note)
    await session.commit()
    return note


async def get_notes(session: AsyncSession, chat_id: int, numbers: list[int]) -> dict[int, Note]:
    rows = await session.scalars(select(Note).where(Note.chat_id == chat_id, Note.number.in_(numbers)))
    return {n.number: n for n in rows}


async def list_notes(
    session: AsyncSession, chat_id: int, status: str = "open", category: str | None = None,
    flt: str | None = None, offset: int = 0, limit: int = 10, assignee: str | None = None,
) -> tuple[list[Note], int]:
    q = select(Note).where(Note.chat_id == chat_id)
    if assignee:
        q = q.where(func.lower(Note.assignee).contains(assignee.lower()))
    if status in ("open", "done"):
        q = q.where(Note.status == status)
    if category:
        q = q.join(Category, Note.category_id == Category.id).where(Category.name == category.lower())
    now = local_now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if flt == "today":
        q = q.where(Note.due_at >= midnight, Note.due_at < midnight + timedelta(days=1))
    elif flt == "tomorrow":
        q = q.where(Note.due_at >= midnight + timedelta(days=1), Note.due_at < midnight + timedelta(days=2))
    elif flt == "important":
        q = q.where(Note.important.is_(True))
    elif flt == "overdue":
        q = q.where(Note.due_at < now, Note.status == "open")
    total = await session.scalar(select(func.count()).select_from(q.subquery()))
    order = (Note.important.desc(), Note.number.asc()) if status != "done" else (Note.done_at.desc(),)
    rows = await session.scalars(q.order_by(*order).offset(offset).limit(limit))
    return list(rows), total or 0


async def set_status(
    session: AsyncSession, chat_id: int, numbers: list[int], status: str, by: str,
) -> tuple[list[Note], list[int]]:
    notes = await get_notes(session, chat_id, numbers)
    changed = []
    for num in numbers:
        note = notes.get(num)
        if note is None or note.status == status:
            continue
        note.status = status
        note.done_at = utcnow() if status == "done" else None
        note.done_by = by if status == "done" else None
        changed.append(note)
    await session.commit()
    missing = [n for n in numbers if n not in notes]
    return changed, missing


async def delete_notes(session: AsyncSession, chat_id: int, numbers: list[int]) -> list[int]:
    notes = await get_notes(session, chat_id, numbers)
    for note in notes.values():
        await session.delete(note)
    await session.commit()
    return sorted(notes)


async def edit_note(session: AsyncSession, chat_id: int, number: int, text: str) -> Note | None:
    note = (await get_notes(session, chat_id, [number])).get(number)
    if note:
        note.text = text
        await session.commit()
    return note


async def search_notes(session: AsyncSession, chat_id: int, query: str, limit: int = 20) -> list[Note]:
    words = [w for w in query.lower().split() if w]
    q = select(Note).where(Note.chat_id == chat_id)
    for w in words:
        q = q.where(func.lower(Note.text).contains(w))
    return list(await session.scalars(q.order_by(Note.number.desc()).limit(limit)))


def _similarity(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    if a in b or b in a:
        return 0.9 + 0.1 * min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


async def find_open_by_text(session: AsyncSession, chat_id: int, text: str) -> list[Note]:
    """Matn bo'yicha eng mos ochiq zametkalar (eng yaxshisi birinchi)."""
    rows = await session.scalars(select(Note).where(Note.chat_id == chat_id, Note.status == "open"))
    scored = sorted(((_similarity(text, n.text), n) for n in rows), key=lambda x: -x[0])
    good = [n for s, n in scored if s >= 0.55]
    if good and _similarity(text, good[0].text) >= 0.9 and (len(good) == 1 or _similarity(text, good[1].text) < 0.9):
        return good[:1]
    return good[:5]


async def latest(session: AsyncSession, chat_id: int, status: str | None = None) -> Note | None:
    """Eng so'nggi zametka: ochiq — oxirgi yozilgani, done — oxirgi bajarilgani."""
    q = select(Note).where(Note.chat_id == chat_id)
    if status:
        q = q.where(Note.status == status)
    order = Note.done_at.desc() if status == "done" else Note.number.desc()
    return await session.scalar(q.order_by(order).limit(1))


async def recent(session: AsyncSession, chat_id: int, status: str | None, limit: int = 6) -> list[Note]:
    q = select(Note).where(Note.chat_id == chat_id)
    if status:
        q = q.where(Note.status == status)
    order = Note.done_at.desc() if status == "done" else Note.number.desc()
    return list(await session.scalars(q.order_by(order).limit(limit)))


async def count_open(session: AsyncSession, chat_id: int) -> int:
    return await session.scalar(
        select(func.count()).select_from(Note).where(Note.chat_id == chat_id, Note.status == "open")
    ) or 0


async def count_done_since(session: AsyncSession, chat_id: int, since) -> int:
    q = select(func.count()).select_from(Note).where(Note.chat_id == chat_id, Note.status == "done")
    if since:
        q = q.where(Note.done_at >= since)
    return await session.scalar(q) or 0


async def update_note(session: AsyncSession, chat_id: int, number: int, field: str, value) -> Note | None:
    note = (await get_notes(session, chat_id, [number])).get(number)
    if note is None:
        return None
    if field == "category":
        cat = await get_category(session, chat_id, value)
        note.category_id, note.category = cat.id, cat
    elif field == "important":
        note.important = bool(value)
    elif field == "assignee":
        note.assignee = value
    elif field == "due":
        note.due_at = value
        note.due_notified = value <= local_now()
    await session.commit()
    return note


async def due_for_alert(session: AsyncSession) -> list[Note]:
    """Muddati kelgan, hali xabar berilmagan ochiq zametkalar."""
    q = select(Note).where(
        Note.status == "open", Note.due_notified.is_(False), Note.due_at.is_not(None), Note.due_at <= local_now()
    )
    return list(await session.scalars(q))


async def agenda(session: AsyncSession, chat_id: int) -> tuple[list[Note], list[Note], list[Note], int]:
    """Ertalabki reja: (bugungi, muddati o'tgan, muhim, jami ochiq)."""
    now = local_now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    base = select(Note).where(Note.chat_id == chat_id, Note.status == "open")
    today = await session.scalars(base.where(Note.due_at >= midnight, Note.due_at < midnight + timedelta(days=1))
                                  .order_by(Note.due_at))
    overdue = await session.scalars(base.where(Note.due_at < midnight).order_by(Note.due_at))
    important = await session.scalars(base.where(Note.important.is_(True), Note.due_at.is_(None)).order_by(Note.number))
    return list(today), list(overdue), list(important), await count_open(session, chat_id)
