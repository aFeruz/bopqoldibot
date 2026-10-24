"""Mas'ullar, o'zgartirishlar, takroriy vazifalar, muddat xabarlari, sozlamalar, migratsiya."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from bot import jobs
from bot.db import init_db
from bot.handlers.actions import execute
from bot.parser import parse
from bot.services import clients as clients_svc
from bot.services import notes as notes_svc
from bot.services import recurring as rec_svc
from bot.services import reminders as rem_svc
from bot.services.common import local_now
from tests.test_flow import CHAT, FakeMsg


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))


@pytest.fixture
async def maker():
    return await init_db("sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def session(maker):
    async with maker() as s:
        yield s


async def say(session, text, username="feruz_dev"):
    replies = await execute(parse(text, local_now()), FakeMsg("Feruz", username), session, "kimedibubot")
    return "\n".join(r.text for r in replies)


async def note(session, n):
    return (await notes_svc.get_notes(session, CHAT, [n]))[n]


async def test_assignees_and_my_tasks(session):
    out = await say(session, "@ali_karimov tovar sanash")
    assert "👤 @ali_karimov" in out
    await say(session, "@feruz_dev @ali_karimov hisobot tayyorlash")
    await say(session, "umumiy ish")

    out = await say(session, "@ali_karimov ishlari")
    assert "2 ta" in out and "umumiy" not in out
    out = await say(session, "mening ishlarim")
    assert "1 ta" in out and "hisobot" in out
    out = await say(session, "mening ishlarim", username=None)
    assert "username" in out

    await say(session, "3 ni @feruz_dev ga ber")
    assert (await note(session, 3)).assignee == "@feruz_dev"


async def test_note_updates(session):
    await say(session, "tovar sanash")
    await say(session, "1 ni #ombor ga o'tkaz")
    assert (await note(session, 1)).category.name == "ombor"
    await say(session, "1 muhim")
    assert (await note(session, 1)).important
    await say(session, "1 muhim emas")
    assert not (await note(session, 1)).important
    out = await say(session, "1 ni ertaga sur")
    due = (await note(session, 1)).due_at
    assert due.date() == local_now().date() + timedelta(days=1) and "⏰" in out
    out = await say(session, "99 muhim")
    assert "#99" in out


async def test_client_updates_and_followup(session):
    await say(session, "mijoz qo'sh: Alisher")
    await say(session, "Alisher telefoni +998 90 123 45 67")
    await say(session, "Alisher izoh: Chilonzorda do'koni bor")
    out = await say(session, "Alisher ni #vip ga o'tkaz")
    c = (await clients_svc.resolve(session, CHAT, "Alisher"))[0]
    assert c.phone == "+998901234567" and c.comment == "Chilonzorda do'koni bor" and c.category.name == "vip"
    assert "Chilonzorda" in out

    out = await say(session, "Alisher bilan gaplashdim, 3 kundan keyin qayta qo'ng'iroq qilaman")
    assert "eslatma #" in out
    pending = await rem_svc.pending(session, CHAT)
    assert len(pending) == 1 and "Alisher" in pending[0].text
    # izohda vaqt bo'lmasa eslatma qo'yilmaydi
    await say(session, "Alisher bilan ishladim narx kelishildi")
    assert len(await rem_svc.pending(session, CHAT)) == 1


async def test_recurring(session, maker):
    out = await say(session, "har kuni 9 da #kassa kassani tekshirish")
    assert "har kuni 09:00" in out
    await say(session, "har dushanba hisobot")
    out = await say(session, "takroriylar")
    assert "kassani tekshirish" in out and "har dushanba" in out

    r = (await rec_svc.list_active(session, CHAT))[0]
    morning = datetime(2026, 10, 26, 9, 5)  # dushanba
    assert {x.text for x in await rec_svc.due_now(session, morning)} == {"kassani tekshirish", "hisobot"}
    assert await rec_svc.due_now(session, datetime(2026, 10, 26, 8, 0)) == []
    assert [x.text for x in await rec_svc.due_now(session, datetime(2026, 10, 27, 9, 5))] == ["kassani tekshirish"]

    # ishga tushirish: zametka yaratadi, guruhga yozadi, bir kunda bir marta
    r.hour, r.minute, r.last_run = 0, 0, None
    await session.commit()
    bot = FakeBot()
    await jobs.run_recurring(bot, maker)
    await jobs.run_recurring(bot, maker)
    texts_sent = [t for _, t, _ in bot.sent]
    assert sum("kassani tekshirish" in t for t in texts_sent) == 1
    open_notes, _ = await notes_svc.list_notes(session, CHAT)
    assert any(n.text == "kassani tekshirish" and n.category.name == "kassa" for n in open_notes)

    assert await rec_svc.deactivate(session, CHAT, r.id)
    assert len(await rec_svc.list_active(session, CHAT)) == 1


async def test_due_alerts(session, maker):
    n = await notes_svc.add_note(session, CHAT, "yuk tushirish", 1, "F", due_at=local_now() + timedelta(hours=1))
    past = await notes_svc.add_note(session, CHAT, "eski", 1, "F", due_at=local_now() - timedelta(hours=1))
    assert past.due_notified  # yaratilganda muddati o'tgan — xabar yuborilmaydi
    bot = FakeBot()
    await jobs.send_due_alerts(bot, maker)
    assert bot.sent == []

    await notes_svc.update_note(session, CHAT, n.number, "due", local_now() - timedelta(minutes=1))
    n.due_notified = False
    await session.commit()
    await jobs.send_due_alerts(bot, maker)
    await jobs.send_due_alerts(bot, maker)
    assert len(bot.sent) == 1 and "yuk tushirish" in bot.sent[0][1]
    assert bot.sent[0][2].inline_keyboard[0][0].callback_data == f"nd:{n.number}"

    # sozlamada o'chirilsa xabar yo'q
    await rem_svc.set_flag(session, CHAT, "due_alerts", False)
    await notes_svc.add_note(session, CHAT, "yana", 1, "F", due_at=local_now() + timedelta(minutes=1))
    m = await notes_svc.latest(session, CHAT)
    m.due_at, m.due_notified = local_now() - timedelta(minutes=1), False
    await session.commit()
    await jobs.send_due_alerts(bot, maker)
    assert len(bot.sent) == 1


async def test_settings_and_summaries(session, maker):
    out = await say(session, "sozlamalar")
    assert "⬜️ ☀️ Ertalabki" in out and "✅ ⏰ Muddat" in out
    cs = await rem_svc.set_flag(session, CHAT, "morning_summary")
    assert cs.morning_summary
    await rem_svc.set_flag(session, CHAT, "weekly_summary", True)

    await say(session, "! muhim ish")
    await say(session, "bugun soat 23:59 hisobot")
    await say(session, "mijoz qo'sh: Sardor")
    bot = FakeBot()
    await jobs.send_morning(bot, maker)
    await jobs.send_weekly(bot, maker)
    morning, weekly = bot.sent[0][1], bot.sent[1][1]
    assert "muhim ish" in morning and "hisobot" in morning and "Sardor" in morning
    assert "Statistika" in weekly

    out = await say(session, "kun rejasi")
    assert "Jami ochiq ishlar: <b>2</b>" in out


def test_migration_adds_columns(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE notes (id INTEGER PRIMARY KEY, chat_id BIGINT, number INT, text TEXT, category_id INT,
            status VARCHAR(8), important BOOLEAN, due_at DATETIME, author_id BIGINT, author_name VARCHAR(128),
            created_at DATETIME, done_at DATETIME, done_by VARCHAR(128));
        INSERT INTO notes (chat_id, number, text, status, important, author_name, created_at)
            VALUES (1, 1, 'eski zametka', 'open', 0, 'F', '2026-01-01 00:00:00');
        CREATE TABLE chat_settings (chat_id BIGINT PRIMARY KEY, daily_summary BOOLEAN);
        INSERT INTO chat_settings VALUES (1, 1);
    """)
    con.commit()
    con.close()

    import asyncio
    asyncio.run(init_db(f"sqlite+aiosqlite:///{db}"))
    con = sqlite3.connect(db)
    assert con.execute("select text, due_notified, assignee from notes").fetchone() == ("eski zametka", 1, None)
    assert con.execute("select daily_summary, morning_summary, due_alerts from chat_settings").fetchone() == (1, 0, 1)
