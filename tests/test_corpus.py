"""Real guruh yozishmalariga o'xshash gaplar to'plami va "bot jim qolmaydi" kafolati."""

from datetime import datetime
from unittest.mock import patch

import pytest
from aiogram.types import Chat, Message, User

from bot.db import init_db
from bot.handlers.context import apply_context, reply_context
from bot.handlers.files import on_media_message
from bot.handlers.mention import on_media, on_message
from bot.parser import parse

NOW = datetime(2026, 10, 24, 12, 0)

CASES = [
 # suhbat
 ("bormisan", "alive"), ("uxlab qoldingmi?", "alive"), ("hoy bot", "alive"), ("javob ber", "alive"),
 ("nega jimsan", "alive"), ("shu yerdamisan?", "alive"), ("alo", "alive"), ("tirikmisan", "alive"),
 ("ok", "ack"), ("xo'p", "ack"), ("mayli", "ack"), ("tushunarli", "ack"), ("ha", "ack"), ("ok rahmat", "thanks"),
 ("kelishdik", "ack"), ("bo'pti", "ack"), ("albatta", "ack"), ("ok ok", "ack"),
 ("yo'q", "no"), ("kerak emas", "no"), ("shart emas", "no"), ("hozircha yo'q", "no"),
 ("xaxaxa", "laugh"), ("hahaha", "laugh"), ("))))", "laugh"), ("kuldirding", "laugh"),
 ("😂", "emoji"), ("👍", "emoji"), ("❤️", "emoji"), ("🔥🔥", "emoji"), ("😢", "emoji"),
 ("zo'r bot ekansan", "compliment"), ("sen zo'rsan", "compliment"), ("aqlli bot", "compliment"),
 ("ahmoq bot", "insult"), ("hech narsa tushunmaysan", "insult"),
 ("kechirasiz", "sorry"), ("uzr", "sorry"),
 ("latifa ayt", "joke"), ("bitta hazil qil", "joke"), ("kuldir meni", "joke"),
 ("charchadim", "motivation"), ("motivatsiya ber", "motivation"), ("kayfiyatim yo'q", "motivation"),
 ("soat necha", "time_now"), ("hozir soat nechchi?", "time_now"),
 ("bugun nechanchi", "date_now"), ("bugun qaysi kun?", "date_now"),
 ("rahmat", "thanks"), ("katta rahmat", "thanks"), ("spasibo", "thanks"), ("barakalla", "thanks"),
 ("yaxshi", "fine"), ("alhamdulillah", "fine"), ("zo'r, o'zingiz-chi?", "howareyou"),
 ("qalaysan", "howareyou"), ("nima gap", "howareyou"), ("ishlar qalay?", "howareyou"),
 ("salom", "greet"), ("assalomu alaykum", "greet"), ("va alaykum assalom", "greet"), ("xayrli tong", "greet"),
 ("xayr", "bye"), ("xayrli tun", "bye"), ("sen kimsan", "about"), ("yordam", "help"),
 ("", "labbay"), ("?", "labbay"),
 # zametkalar
 ("tovar sanash kerak", "note"), ("ertaga bankka borish", "note"), ("@ali_k ombor kalitini olib kel", "note"),
 ("yozib qo'y: kassa", "note"), ("eslab qol: Ali qarzi 500", "note"),
 ("3 bo'ldi", "done"), ("3 ok", "done"), ("3 👍", "done"), ("bo'ldi", "done"), ("uchinchisi tayyor", "done"),
 ("hisobotni tugatdim", "done_text"), ("kassani yopdim", "done_text"),
 ("nechta ish qoldi", "list"), ("nechta ochiq vazifa bor?", "list"), ("ishlarni ko'rsat", "list"),
 ("nima qolgan", "list"), ("hamma ishlar", "list"), ("ro'yxat", "list"),
 ("bugun nima qilamiz", "agenda"), ("nima bor bugunga", "agenda"),
 ("ertaga yig'ilish bormi?", "question"), ("Ali to'lov qildimi?", "question"), ("kalit qayerda?", "question"),
 # mijozlar
 ("nechta mijoz bor", "clients"), ("mijozlar", "clients"),
 ("Ali bilan gaplashdim", "worked"), ("Aliga qo'ng'iroq qildim, ko'tarmadi", "worked"),
 ("kimga qo'ng'iroq qilish kerak", "not_worked"), ("kim qoldi", "not_worked"),
 ("Ali haqida", "client_card"),
 # boshqalar
 ("eslat 10 minutdan keyin choy", "remind"), ("statistika", "stats"), ("kundalik", "diary"),
 ("export", "export"), ("sozlamalar", "settings"), ("har kuni 9 da kassa", "recurring_add"),
]

TRICKY = [
 ("hazil emas, ertaga 9 da yig'ilish", "note"),
 ("hujjatning ikkinchi qismi", "note"),
 ("shartnoma rasmi", "note"),
 ("Ali bilan ertaga gaplashish kerak", "note"),
 ("ok, 3 bo'ldi", "done"),
 ("ha, 3 bo'ldi", "done"),
 ("yo'q, 4 bo'ldi", "done"),
 ("mayli rahmat", "thanks"),
 ("xo'p bo'ladi", "ack"),
 ("aqlli bot, 3 bo'ldi", "done"),
 ("charchadim lekin 3 bo'ldi", "done"),
 ("soat 3 da yig'ilish", "note"),
 ("Ali bilan gaplashdimi?", "question"),
 ("hisobot tayyormi?", "question"),
 ("kassa yopildimi", "question"),
 ("ertaga bayram bo'ladimi", "question"),
 ("yangi mijoz qo'sh: Salimi", "client_add"),
 ("latifa", "joke"),
 ("bugun kayfiyat zo'r, 2 bo'ldi", "done"),
]



@pytest.mark.parametrize("text,kind", CASES + TRICKY)
def test_corpus(text, kind):
    assert parse(text, NOW).kind == kind


NOTE_CARD = "Yozib qo'ydim, shef! ✍️\n\n📌 #12 · tovar sanash\n🏷 #ombor"
CLIENT_CARD = "Mijoz ma'lumoti yangilandi\n\n👤 #5 Alisher\n📞 +998901112233"
REMINDER = "⏰ Esingizdami, Feruz?\n\n🔔 hisobot topshirish\n— Feruz"
NOTE_LIST = "Mana 👇\n\n📋 Ochiq zametkalar — 2 ta\n\n❗ #2 a\n▫️ #1 b"
ACTIVITY = "Navbatdagilar 👇\n\n⏳ Ishlanmagan mijozlar — 1 ta\n\n⏳ 👤 #3 Sardor — oxirgi: hech qachon"


@pytest.mark.parametrize(
    "bot_text,expected",
    [(NOTE_CARD, ("note", 12)), (CLIENT_CARD, ("client", 5)), (REMINDER, ("reminder", None)),
     (NOTE_LIST, None), (ACTIVITY, ("client", 3)), ("Va alaykum assalom! 🤝", None)],
)
def test_reply_context(bot_text, expected):
    ctx = reply_context(bot_text)
    assert (ctx and (ctx.kind, ctx.number)) == expected or (ctx is None and expected is None)


@pytest.mark.parametrize(
    "bot_text,text,kind,check",
    [
        (NOTE_CARD, "bo'ldi", "done", lambda i: i.numbers == [12]),
        (NOTE_CARD, "👍", "done", lambda i: i.numbers == [12]),
        (NOTE_CARD, "ok", "done", lambda i: i.numbers == [12]),
        (NOTE_CARD, "muhim", "note_update", lambda i: i.field == "important"),
        (NOTE_CARD, "ertaga sur", "note_update", lambda i: i.field == "due"),
        (NOTE_CARD, "@vali_x ga ber", "note_update", lambda i: i.value == "@vali_x"),
        (NOTE_CARD, "#kassa ga o'tkaz", "note_update", lambda i: i.value == "kassa"),
        (NOTE_CARD, "tuzat: yangi matn", "edit", lambda i: i.text == "yangi matn"),
        (NOTE_CARD, "o'chir", "delete", lambda i: i.numbers == [12]),
        (NOTE_CARD, "rahmat", "thanks", lambda i: True),
        (CLIENT_CARD, "gaplashdim narx kelishildi", "worked", lambda i: i.names == ["5"] and i.text == "narx kelishildi"),
        (CLIENT_CARD, "qo'ng'iroq qildim", "worked", lambda i: i.names == ["5"]),
        (CLIENT_CARD, "telefoni +998901112244", "client_update", lambda i: i.field == "phone"),
        (CLIENT_CARD, "izoh: Chilonzor", "client_update", lambda i: i.value == "Chilonzor"),
        (CLIENT_CARD, "@vali_x ga o'tkaz", "client_assign", lambda i: i.assignee == "@vali_x"),
        (CLIENT_CARD, "arxivla", "client_archive", lambda i: i.numbers == [5]),
        (REMINDER, "bo'ldi", "reminder_done", lambda i: i.text == "hisobot topshirish"),
        (REMINDER, "10 minutdan keyin yana eslat", "remind", lambda i: i.when == datetime(2026, 10, 24, 12, 10)),
        (REMINDER, "keyinroq", "remind", lambda i: i.when == datetime(2026, 10, 24, 12, 30)),
    ],
)
def test_apply_context(bot_text, text, kind, check):
    i = apply_context(text, parse(text, NOW), reply_context(bot_text), NOW)
    assert i.kind == kind and check(i), i


BOT = User(id=42, is_bot=True, first_name="Kim bu ?", username="kimedibubot")
ME = User(id=1, is_bot=False, first_name="Feruz", username="feruz_dev")
CHAT = Chat(id=-100, type="supergroup")


@pytest.fixture
async def session():
    maker = await init_db("sqlite+aiosqlite:///:memory:")
    async with maker() as s:
        yield s


def reply_msg(text, bot_text, **extra):
    bot_msg = Message(message_id=1, date=NOW, chat=CHAT, from_user=BOT, text=bot_text)
    return Message(message_id=2, date=NOW, chat=CHAT, from_user=ME, text=text, reply_to_message=bot_msg, **extra)


@pytest.mark.parametrize("bot_text", [NOTE_CARD, CLIENT_CARD, REMINDER, NOTE_LIST, "Zo'r! O'zingiz yaxshimisiz?"])
async def test_never_silent_on_reply(session, bot_text):
    """Botning har qanday xabariga tag qilinmagan reply — har doim javob bor."""
    sent = []

    async def fake_reply(self, text, **kw):
        sent.append(text)

    async def fake_doc(self, *a, **kw):
        sent.append("doc")

    with patch.object(Message, "reply", fake_reply), patch.object(Message, "answer_document", fake_doc):
        for text, _ in CASES + TRICKY:
            if not text:
                continue
            before = len(sent)
            await on_message(reply_msg(text, bot_text), session, "kimedibubot", 42)
            assert len(sent) > before, f"jim qoldi: {text!r} -> {bot_text[:20]!r}"


async def test_sticker_and_voice_reply():
    sent = []

    async def fake_reply(self, text, **kw):
        sent.append(text)

    bot_msg = Message(message_id=1, date=NOW, chat=CHAT, from_user=BOT, text="Zo'r!")
    sticker = {"file_id": "s", "file_unique_id": "s", "type": "regular", "width": 1, "height": 1,
               "is_animated": False, "is_video": False}
    voice = {"file_id": "v", "file_unique_id": "v", "duration": 1}
    with patch.object(Message, "reply", fake_reply):
        m = Message(message_id=2, date=NOW, chat=CHAT, from_user=ME, reply_to_message=bot_msg, sticker=sticker)
        await on_media(m, 42)
        # ovoz bilan botga javob — saqlash taklifi (files.py)
        m = Message(message_id=4, date=NOW, chat=CHAT, from_user=ME, reply_to_message=bot_msg, voice=voice)
        await on_media_message(m, None, None, "kimedibubot", 42)
        # botga emas — jim
        m = Message(message_id=3, date=NOW, chat=CHAT, from_user=ME, sticker=sticker)
        await on_media(m, 42)
    assert len(sent) == 2
