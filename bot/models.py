from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("chat_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(64))


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (UniqueConstraint("chat_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(8), default="open")  # open / done
    important: Mapped[bool] = mapped_column(Boolean, default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)  # local time, naive
    author_id: Mapped[int | None] = mapped_column(BigInteger)
    author_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(DateTime)
    done_by: Mapped[str | None] = mapped_column(String(128))
    assignee: Mapped[str | None] = mapped_column(String(256))  # "@ali,@vali"
    file_id: Mapped[str | None] = mapped_column(String(256))  # biriktirilgan media (Telegram file_id)
    file_type: Mapped[str | None] = mapped_column(String(16))  # photo / voice / video / document / ...
    file_name: Mapped[str | None] = mapped_column(String(256))
    # eski yozuvlar uchun True — yangilanishdan keyin eski muddatlar haqida birdan xabar yog'ilmasin
    due_notified: Mapped[bool] = mapped_column(Boolean, default=False, info={"migrate_default": True})

    category: Mapped[Category | None] = relationship(lazy="joined")


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("chat_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(256))
    phone: Mapped[str | None] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    assignee: Mapped[str | None] = mapped_column(String(256))  # "@vali"
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    remind_assignee: Mapped[bool] = mapped_column(Boolean, default=False)  # ishlanmaguncha har kuni eslatish
    import_batch: Mapped[str | None] = mapped_column(String(16), index=True)

    category: Mapped[Category | None] = relationship(lazy="joined")


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    author_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    client: Mapped[Client] = relationship(lazy="joined")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    text: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column(DateTime)  # UTC, naive
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    author_name: Mapped[str] = mapped_column(String(128), default="")


class Recurring(Base):
    """Takroriy vazifa: belgilangan vaqtda avtomatik zametka yaratadi."""

    __tablename__ = "recurring"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    text: Mapped[str] = mapped_column(Text)
    rule: Mapped[str] = mapped_column(String(32))  # daily / workdays / weekly:0 / monthly:5
    hour: Mapped[int] = mapped_column(Integer, default=9)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str | None] = mapped_column(String(64))
    assignee: Mapped[str | None] = mapped_column(String(256))
    author_name: Mapped[str] = mapped_column(String(128), default="")
    last_run: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD (mahalliy)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChatSettings(Base):
    __tablename__ = "chat_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    daily_summary: Mapped[bool] = mapped_column(Boolean, default=False)
    morning_summary: Mapped[bool] = mapped_column(Boolean, default=False)
    weekly_summary: Mapped[bool] = mapped_column(Boolean, default=False)
    due_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
