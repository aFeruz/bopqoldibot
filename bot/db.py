import os

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.models import Base

engine = None
Session: async_sessionmaker[AsyncSession] | None = None


def _add_missing_columns(conn) -> None:
    """Yangi versiyada qo'shilgan ustunlarni eski bazaga qo'shadi (create_all buni qilmaydi)."""
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(conn.dialect)}"
            default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
            default = col.info.get("migrate_default", default)
            if isinstance(default, bool):
                ddl += f" DEFAULT {int(default)}"
            elif isinstance(default, (int, str)):
                ddl += f" DEFAULT {default!r}"
            conn.execute(text(ddl))


async def init_db(url: str) -> async_sessionmaker[AsyncSession]:
    global engine, Session
    if url.startswith("sqlite+aiosqlite:///") and ":memory:" not in url:
        path = url.removeprefix("sqlite+aiosqlite:///")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return Session
