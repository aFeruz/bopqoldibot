"""Rasm, ovoz, video va fayllarni zametka sifatida saqlash va qayta yuborish."""

from datetime import datetime
from unittest.mock import patch

import pytest
from aiogram.types import Chat, Message, MessageEntity, User

from bot.db import init_db
from bot.handlers.actions import execute
from bot.handlers.context import apply_context, reply_context
from bot.handlers.files import on_media_message
from bot.handlers.mention import on_message
from bot.media import describe, extract_media
from bot.parser import parse
from bot.services import notes as notes_svc
from bot.services.common import local_now
from tests.test_flow import FakeMsg

NOW = datetime(2026, 10, 24, 12, 0)
BOT = User(id=42, is_bot=True, first_name="Kim bu ?", username="kimedibubot")
ME = User(id=1, is_bot=False, first_name="Feruz", username="feruz_dev")
ALI = User(id=2, is_bot=False, first_name="Ali")
CHAT_ID = -100123
CHAT = Chat(id=CHAT_ID, type="supergroup")
PHOTO = [{"file_id": "small", "file_unique_id": "s", "width": 90, "height": 90},
         {"file_id": "big-photo", "file_unique_id": "b", "width": 1280, "height": 960}]
VOICE = {"file_id": "voice-1", "file_unique_id": "v", "duration": 83}
DOC = {"file_id": "doc-1", "file_unique_id": "d", "file_name": "shartnoma.pdf"}
XLSX = {"file_id": "xlsx-1", "file_unique_id": "x", "file_name": "lidlar.xlsx"}


class MediaBot:
    def __init__(self):
        self.sent = []

    def __getattr__(self, name):
        if not name.startswith("send_"):
            raise AttributeError(name)

        async def send(chat_id, **kw):
            self.sent.append((name.removeprefix("send_"), kw))
        return send


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


def mention(text):
    return [MessageEntity(type="mention", offset=0, length=len("@kimedibubot"))] if text.startswith("@") else None


def test_extract_and_describe():
    m = extract_media(Message(message_id=1, date=NOW, chat=CHAT, from_user=ME, photo=PHOTO))
    assert (m.file_id, m.type) == ("big-photo", "photo")  # eng katta o'lcham
    m = extract_media(Message(message_id=1, date=NOW, chat=CHAT, from_user=ME, voice=VOICE))
    assert describe(m.type, m.name, m.duration) == "🎤 Ovozli xabar · 1:23"
    m = extract_media(Message(message_id=1, date=NOW, chat=CHAT, from_user=ME, document=DOC))
    assert describe(m.type, m.name) == "📄 shartnoma.pdf"
    assert extract_media(Message(message_id=1, date=NOW, chat=CHAT, from_user=ME, text="salom")) is None


async def test_photo_with_caption_saved(session, replies):
    cap = "@kimedibubot eslab qol #shartnoma Ali bilan imzolangan nusxa"
    msg = Message(message_id=5, date=NOW, chat=CHAT, from_user=ME, photo=PHOTO, caption=cap,
                  caption_entities=mention(cap))
    await on_media_message(msg, session, None, "kimedibubot", 42)
    note = await notes_svc.latest(session, CHAT_ID)
    assert note.file_id == "big-photo" and note.file_type == "photo"
    assert note.category.name == "shartnoma" and note.text == "Ali bilan imzolangan nusxa"
    assert "📎" in replies[0]


async def test_reply_to_voice_saves_it(session, replies):
    voice_msg = Message(message_id=7, date=NOW, chat=CHAT, from_user=ALI, voice=VOICE)
    text = "@kimedibubot eslab qol #yigilish"
    msg = Message(message_id=8, date=NOW, chat=CHAT, from_user=ME, text=text, entities=mention(text),
                  reply_to_message=voice_msg)
    await on_message(msg, session, "kimedibubot", 42)
    note = await notes_svc.latest(session, CHAT_ID)
    assert note.file_type == "voice" and note.category.name == "yigilish"
    assert note.text == "🎤 Ovozli xabar · 1:23"

    # faqat "@bot" — ham saqlanadi
    text = "@kimedibubot"
    msg = Message(message_id=9, date=NOW, chat=CHAT, from_user=ME, text=text, entities=mention(text),
                  reply_to_message=Message(message_id=6, date=NOW, chat=CHAT, from_user=ALI, document=DOC))
    await on_message(msg, session, "kimedibubot", 42)
    assert (await notes_svc.latest(session, CHAT_ID)).file_name == "shartnoma.pdf"


async def test_table_saved_as_file_when_asked(session, replies):
    cap = "@kimedibubot saqlab qo'y #hisobot"
    msg = Message(message_id=5, date=NOW, chat=CHAT, from_user=ME, document=XLSX, caption=cap,
                  caption_entities=mention(cap))
    await on_media_message(msg, session, None, "kimedibubot", 42)
    note = await notes_svc.latest(session, CHAT_ID)
    assert note.file_name == "lidlar.xlsx" and note.category.name == "hisobot"


async def test_untagged_group_media_ignored(session, replies):
    msg = Message(message_id=5, date=NOW, chat=CHAT, from_user=ME, photo=PHOTO)
    await on_media_message(msg, session, None, "kimedibubot", 42)
    assert replies == [] and await notes_svc.latest(session, CHAT_ID) is None


async def test_list_and_send_files(session):
    await notes_svc.add_note(session, CHAT_ID, "shartnoma", 1, "F", "shartnoma", file_id="d1", file_type="document",
                             file_name="a.pdf")
    await notes_svc.add_note(session, CHAT_ID, "majlis", 1, "F", "yigilish", file_id="v1", file_type="voice")
    await notes_svc.add_note(session, CHAT_ID, "oddiy zametka", 1, "F")
    msg = FakeMsg()
    msg.bot = MediaBot()

    async def run(text):
        return "\n".join(r.text for r in await execute(parse(text, local_now()), msg, session, "kimedibubot"))

    out = await run("fayllar")
    assert "2 ta" in out and "oddiy" not in out
    out = await run("ovozli xabarlar")
    assert "1 ta" in out and "majlis" in out
    out = await run("fayllarni tashla #shartnoma")
    assert "1 ta" in out and msg.bot.sent[-1][0] == "document" and msg.bot.sent[-1][1]["document"] == "d1"
    assert "📌" in msg.bot.sent[-1][1]["caption"]

    await run("2 ni tashla")
    assert msg.bot.sent[-1][0] == "voice"
    out = await run("3 ni tashla")
    assert "oddiy zametka" in out  # fayli yo'q — kartochkasi

    ctx = reply_context("📌 #2 · majlis #yigilish")
    i = apply_context("tashla", parse("tashla", NOW), ctx, NOW)
    assert i.kind == "send_file" and i.numbers == [2]
