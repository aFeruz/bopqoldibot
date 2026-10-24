"""Boshqa xabarlarni (matn, kontakt, lokatsiya, forward) reply orqali eslab qolish."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from aiogram.types import Chat, Contact, Location, Message, MessageEntity, MessageOriginUser, User

from bot.db import init_db
from bot.handlers.files import on_shared_item
from bot.handlers.mention import on_message
from bot.handlers.saving import is_save_instruction, message_content
from bot.services import clients as clients_svc
from bot.services import notes as notes_svc
from bot.services import reminders as rem_svc

NOW = datetime(2026, 10, 24, 12, 0)
ME = User(id=1, is_bot=False, first_name="Feruz", username="feruz_dev")
ALI = User(id=2, is_bot=False, first_name="Ali", last_name="Valiyev")
GROUP_ID = -100777
GROUP = Chat(id=GROUP_ID, type="supergroup")
PRIVATE = Chat(id=1, type="private")
TAG = "@kimedibubot"


@pytest.fixture
async def session():
    maker = await init_db("sqlite+aiosqlite:///:memory:")
    async with maker() as s:
        yield s


@pytest.fixture
def replies():
    sent = []

    async def fake_reply(self, text, **kw):
        sent.append(text)
    with patch.object(Message, "reply", fake_reply):
        yield sent


def ali_says(text=None, **extra):
    return Message(message_id=10, date=NOW, chat=GROUP, from_user=ALI, text=text, **extra)


async def tag_reply(session, original, text):
    full = f"{TAG} {text}".strip()
    msg = Message(message_id=11, date=NOW, chat=GROUP, from_user=ME, text=full, reply_to_message=original,
                  entities=[MessageEntity(type="mention", offset=0, length=len(TAG))])
    await on_message(msg, session, "kimedibubot", 42)


async def latest(session, chat_id=GROUP_ID):
    return await notes_svc.latest(session, chat_id)


@pytest.mark.parametrize(
    "text,expected",
    [("", True), ("eslab qol", True), ("eslab qol #narx", True), ("#narx", True), ("@vali_x", True),
     ("! ertaga", True), ("saqlab qo'y, juda muhim", True), ("3 bo'ldi", False), ("mijozlar qo'sh", False),
     ("ertaga 9 da eslat", False), ("statistika", False)],
)
def test_is_save_instruction(text, expected):
    assert is_save_instruction(text) is expected


async def test_save_reply_text_with_category(session, replies):
    await tag_reply(session, ali_says("Narxlar: plita 50 000, g'isht 1 200"), "eslab qol #narx")
    note = await latest(session)
    assert note.text == "Narxlar: plita 50 000, g'isht 1 200" and note.category.name == "narx"
    assert "Ali Valiyev" in replies[-1]


async def test_save_reply_plain_mention_keeps_text_verbatim(session, replies):
    await tag_reply(session, ali_says("Ertaga omborga 3 ta mashina keladi! #ombor"), "")
    note = await latest(session)
    assert note.text == "Ertaga omborga 3 ta mashina keladi! #ombor" and note.category.name == "ombor"


async def test_save_reply_assign_and_due(session, replies):
    await tag_reply(session, ali_says("Shartnomani tekshirish kerak"), "@vali_x ertaga")
    note = await latest(session)
    assert note.assignee == "@vali_x" and note.due_at.date() == (datetime.now() + timedelta(days=1)).date()
    assert note.text == "Shartnomani tekshirish kerak"


async def test_save_reply_with_comment(session, replies):
    await tag_reply(session, ali_says("Yangi narxlar ro'yxati"), "eslab qol, oy oxirigacha amal qiladi")
    assert (await latest(session)).text == "Yangi narxlar ro'yxati\n💬 oy oxirigacha amal qiladi"


async def test_reply_with_command_is_not_saved(session, replies):
    await notes_svc.add_note(session, GROUP_ID, "birinchi", 1, "F")
    await tag_reply(session, ali_says("biror gap"), "1 bo'ldi")
    note = await latest(session)
    assert note.text == "birinchi" and note.status == "done"


async def test_reply_remind_uses_message_text(session, replies):
    await tag_reply(session, ali_says("Soliq hisobotini topshirish"), "ertaga 9 da eslat")
    r = (await rem_svc.pending(session, GROUP_ID))[0]
    assert r.text == "Soliq hisobotini topshirish"


async def test_reply_client_list_still_imports(session, replies):
    await tag_reply(session, ali_says("Sardor 901112233\nMadina 901112244"), "mijozlar qo'sh")
    clients, total = await clients_svc.list_clients(session, GROUP_ID)
    assert total == 2


async def test_save_contact_and_location(session, replies):
    contact = Contact(phone_number="+998901234567", first_name="Bobur", last_name="Karimov")
    await tag_reply(session, ali_says(contact=contact), "eslab qol #yetkazuvchi")
    note = await latest(session)
    assert note.text == "📇 Bobur Karimov +998901234567" and note.category.name == "yetkazuvchi"

    loc = Message(message_id=20, date=NOW, chat=PRIVATE, from_user=ME, location=Location(latitude=41.31, longitude=69.27))
    await on_shared_item(loc, session, 42)
    assert "maps.google.com/?q=41.31,69.27" in (await latest(session, 1)).text


async def test_private_forward_saved_not_executed(session, replies):
    await notes_svc.add_note(session, 1, "eski ish", 1, "F")
    fwd = Message(message_id=30, date=NOW, chat=PRIVATE, from_user=ME, text="1 bo'ldi",
                  forward_origin=MessageOriginUser(date=NOW, sender_user=ALI))
    await on_message(fwd, session, "kimedibubot", 42)
    note = await latest(session, 1)
    assert note.text == "1 bo'ldi" and note.number == 2  # buyruq emas, yangi zametka
    assert (await notes_svc.get_notes(session, 1, [1]))[1].status == "open"
    assert "Ali Valiyev" in replies[-1]


def test_message_content_poll():
    from aiogram.types import Poll, PollOption
    poll = Poll(id="p", question="Qachon yig'ilamiz?", options=[PollOption(text="Dushanba", voter_count=0),
                PollOption(text="Juma", voter_count=0)], total_voter_count=0, is_closed=False, is_anonymous=True,
                type="regular", allows_multiple_answers=False)
    assert message_content(ali_says(poll=poll)) == "📊 Qachon yig'ilamiz?: Dushanba / Juma"
