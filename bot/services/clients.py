from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Category, Client, Interaction
from bot.parser import ClientInput
from bot.services.common import get_category, next_number


async def add_clients(session: AsyncSession, chat_id: int, items: list[ClientInput]) -> tuple[list[Client], list[Client]]:
    """(qo'shilganlar, allaqachon bor bo'lganlar)."""
    existing = {c.name.lower(): c for c in await session.scalars(select(Client).where(Client.chat_id == chat_id))}
    added, dupes = [], []
    number = await next_number(session, Client, chat_id)
    for item in items:
        old = existing.get(item.name.lower())
        if old:
            if old.archived:
                old.archived = False
            if item.phone and not old.phone:
                old.phone = item.phone
            dupes.append(old)
            continue
        cat = await get_category(session, chat_id, item.category)
        client = Client(
            chat_id=chat_id, number=number, name=item.name, phone=item.phone, comment=item.comment,
            category_id=cat.id if cat else None, category=cat,
        )
        number += 1
        session.add(client)
        existing[item.name.lower()] = client
        added.append(client)
    await session.commit()
    return added, dupes


async def resolve(session: AsyncSession, chat_id: int, name: str) -> list[Client]:
    """Ism yoki raqam bo'yicha mijozni topadi. Bitta aniq mos bo'lsa — [client], aks holda variantlar."""
    name = name.strip().lstrip("#")
    q = select(Client).where(Client.chat_id == chat_id, Client.archived.is_(False))
    if name.isdigit():
        c = await session.scalar(q.where(Client.number == int(name)))
        return [c] if c else []
    clients = list(await session.scalars(q))
    low = name.lower()
    exact = [c for c in clients if c.name.lower() == low]
    if exact:
        return exact[:1]
    contains = [c for c in clients if low in c.name.lower() or c.name.lower() in low]
    if len(contains) == 1:
        return contains
    pool = contains or clients
    scored = sorted(((SequenceMatcher(None, low, c.name.lower()).ratio(), c) for c in pool), key=lambda x: -x[0])
    good = [c for s, c in scored if s >= 0.6]
    if not contains and len(good) >= 1 and scored[0][0] >= 0.8 and (len(scored) == 1 or scored[1][0] < 0.8):
        return good[:1]
    return (contains or good)[:6]


async def add_interaction(session: AsyncSession, client: Client, text: str, author: str) -> Interaction:
    it = Interaction(client_id=client.id, chat_id=client.chat_id, text=text, author_name=author)
    session.add(it)
    await session.commit()
    return it


def _base(chat_id: int, category: str | None):
    q = select(Client).where(Client.chat_id == chat_id, Client.archived.is_(False))
    if category:
        q = q.join(Category, Client.category_id == Category.id).where(Category.name == category.lower())
    return q


async def list_clients(
    session: AsyncSession, chat_id: int, category: str | None = None, archived: bool = False,
    offset: int = 0, limit: int = 20,
) -> tuple[list[Client], int]:
    q = select(Client).where(Client.chat_id == chat_id, Client.archived.is_(archived))
    if category:
        q = q.join(Category, Client.category_id == Category.id).where(Category.name == category.lower())
    total = await session.scalar(select(func.count()).select_from(q.subquery()))
    rows = await session.scalars(q.order_by(Client.number).offset(offset).limit(limit))
    return list(rows), total or 0


@dataclass
class ClientActivity:
    client: Client
    last_at: datetime | None
    count: int


async def activity(
    session: AsyncSession, chat_id: int, since: datetime | None, until: datetime | None = None,
    category: str | None = None,
) -> tuple[list[ClientActivity], list[ClientActivity]]:
    """(ishlanganlar, ishlanmaganlar) davr bo'yicha. last_at — oxirgi aloqa (umuman)."""
    clients = list(await session.scalars(_base(chat_id, category).order_by(Client.number)))
    last_q = (
        select(Interaction.client_id, func.max(Interaction.created_at))
        .where(Interaction.chat_id == chat_id)
        .group_by(Interaction.client_id)
    )
    last = dict((await session.execute(last_q)).all())
    cnt_q = select(Interaction.client_id, func.count()).where(Interaction.chat_id == chat_id)
    if since:
        cnt_q = cnt_q.where(Interaction.created_at >= since)
    if until:
        cnt_q = cnt_q.where(Interaction.created_at < until)
    counts = dict((await session.execute(cnt_q.group_by(Interaction.client_id))).all())
    worked, not_worked = [], []
    for c in clients:
        a = ClientActivity(c, last.get(c.id), counts.get(c.id, 0))
        (worked if a.count else not_worked).append(a)
    worked.sort(key=lambda a: a.last_at or datetime.min, reverse=True)
    not_worked.sort(key=lambda a: a.last_at or datetime.min)
    return worked, not_worked


async def history(session: AsyncSession, client: Client, limit: int = 10) -> tuple[list[Interaction], int]:
    q = select(Interaction).where(Interaction.client_id == client.id)
    total = await session.scalar(select(func.count()).select_from(q.subquery()))
    rows = await session.scalars(q.order_by(Interaction.created_at.desc()).limit(limit))
    return list(rows), total or 0


async def archive(session: AsyncSession, chat_id: int, numbers: list[int], value: bool = True) -> list[Client]:
    rows = list(await session.scalars(select(Client).where(Client.chat_id == chat_id, Client.number.in_(numbers))))
    for c in rows:
        c.archived = value
    await session.commit()
    return rows


async def get_by_number(session: AsyncSession, chat_id: int, number: int) -> Client | None:
    return await session.scalar(select(Client).where(Client.chat_id == chat_id, Client.number == number))


async def update_client(session: AsyncSession, client: Client, field: str, value: str) -> Client:
    if field == "phone":
        client.phone = value
    elif field == "comment":
        client.comment = value
    elif field == "category":
        cat = await get_category(session, client.chat_id, value)
        client.category_id, client.category = cat.id, cat
    await session.commit()
    return client
