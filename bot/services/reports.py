import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Category, Client, Interaction, Note
from bot.services.common import period_end, period_start, to_local


@dataclass
class Stats:
    open: int = 0
    done: int = 0
    important_open: int = 0
    created: int = 0
    closed: int = 0
    clients: int = 0
    clients_worked: int = 0
    interactions: int = 0
    top_doers: list[tuple[str, int]] = field(default_factory=list)
    top_workers: list[tuple[str, int]] = field(default_factory=list)


def _in(col, since, until):
    conds = []
    if since:
        conds.append(col >= since)
    if until:
        conds.append(col < until)
    return conds


async def stats(session: AsyncSession, chat_id: int, period: str | None) -> Stats:
    since, until = period_start(period), period_end(period)
    s = Stats()
    count = lambda *w: session.scalar(select(func.count()).select_from(Note).where(Note.chat_id == chat_id, *w))
    s.open = await count(Note.status == "open")
    s.done = await count(Note.status == "done")
    s.important_open = await count(Note.status == "open", Note.important.is_(True))
    s.created = await count(*_in(Note.created_at, since, until))
    s.closed = await count(Note.status == "done", *_in(Note.done_at, since, until))
    s.clients = await session.scalar(
        select(func.count()).select_from(Client).where(Client.chat_id == chat_id, Client.archived.is_(False))
    )
    iw = [Interaction.chat_id == chat_id, *_in(Interaction.created_at, since, until)]
    s.interactions = await session.scalar(select(func.count()).select_from(Interaction).where(*iw))
    s.clients_worked = await session.scalar(select(func.count(func.distinct(Interaction.client_id))).where(*iw))
    s.top_doers = list((await session.execute(
        select(Note.done_by, func.count()).where(Note.chat_id == chat_id, Note.status == "done",
                                                 *_in(Note.done_at, since, until))
        .group_by(Note.done_by).order_by(func.count().desc()).limit(5)
    )).all())
    s.top_workers = list((await session.execute(
        select(Interaction.author_name, func.count()).where(*iw)
        .group_by(Interaction.author_name).order_by(func.count().desc()).limit(5)
    )).all())
    return s


@dataclass
class Diary:
    created: list[Note]
    closed: list[Note]
    interactions: list[Interaction]


async def diary(session: AsyncSession, chat_id: int, period: str | None) -> Diary:
    since, until = period_start(period), period_end(period)
    created = await session.scalars(
        select(Note).where(Note.chat_id == chat_id, *_in(Note.created_at, since, until)).order_by(Note.created_at)
    )
    closed = await session.scalars(
        select(Note).where(Note.chat_id == chat_id, Note.status == "done", *_in(Note.done_at, since, until))
        .order_by(Note.done_at)
    )
    inter = await session.scalars(
        select(Interaction).where(Interaction.chat_id == chat_id, *_in(Interaction.created_at, since, until))
        .order_by(Interaction.created_at)
    )
    return Diary(list(created), list(closed), list(inter))


async def categories(session: AsyncSession, chat_id: int) -> list[tuple[str, int, int, int]]:
    """(nom, ochiq zametkalar, bajarilgan, mijozlar)."""
    cats = list(await session.scalars(select(Category).where(Category.chat_id == chat_id).order_by(Category.name)))
    result = []
    for c in cats:
        o = await session.scalar(select(func.count()).where(Note.category_id == c.id, Note.status == "open"))
        d = await session.scalar(select(func.count()).where(Note.category_id == c.id, Note.status == "done"))
        k = await session.scalar(select(func.count()).where(Client.category_id == c.id, Client.archived.is_(False)))
        result.append((c.name, o, d, k))
    return result


def _fmt(dt):
    return to_local(dt).strftime("%Y-%m-%d %H:%M") if dt else ""


async def export_csv(session: AsyncSession, chat_id: int) -> dict[str, bytes]:
    files = {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "Matn", "Kategoriya", "Holat", "Muhim", "Muddat", "Muallif", "Yaratilgan", "Bajarilgan", "Kim bajardi",
                "Mas'ul", "Fayl"])
    for n in await session.scalars(select(Note).where(Note.chat_id == chat_id).order_by(Note.number)):
        w.writerow([
            n.number, n.text, n.category.name if n.category else "", n.status, "ha" if n.important else "",
            n.due_at.strftime("%Y-%m-%d %H:%M") if n.due_at else "", n.author_name, _fmt(n.created_at),
            _fmt(n.done_at), n.done_by or "", n.assignee or "",
            f"{n.file_type}: {n.file_name}" if n.file_name else (n.file_type or ""),
        ])
    files["zametkalar.csv"] = buf.getvalue().encode("utf-8-sig")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "Ism", "Telefon", "Kategoriya", "Izoh", "Arxiv", "Qo'shilgan"])
    for c in await session.scalars(select(Client).where(Client.chat_id == chat_id).order_by(Client.number)):
        w.writerow([c.number, c.name, c.phone or "", c.category.name if c.category else "", c.comment or "",
                    "ha" if c.archived else "", _fmt(c.created_at)])
    files["mijozlar.csv"] = buf.getvalue().encode("utf-8-sig")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Sana", "Mijoz #", "Mijoz", "Izoh", "Kim"])
    for i in await session.scalars(
        select(Interaction).where(Interaction.chat_id == chat_id).order_by(Interaction.created_at)
    ):
        w.writerow([_fmt(i.created_at), i.client.number, i.client.name, i.text, i.author_name])
    files["aloqalar.csv"] = buf.getvalue().encode("utf-8-sig")
    return files
