"""Parser -> execute -> baza oqimi, soxta Telegram xabari bilan.

Javoblar tasodifiy iboralardan iborat, shuning uchun testlar ibora matniga emas,
mazmunga (raqamlar, nomlar, holat) va bazaga qaraydi.
"""

from types import SimpleNamespace

import pytest

from bot import phrases
from bot.db import init_db
from bot.handlers.actions import PENDING, execute
from bot.parser import parse
from bot.services import clients as clients_svc
from bot.services import notes as notes_svc
from bot.services.common import local_now

CHAT = -100123


class FakeMsg:
    def __init__(self, name="Feruz", username="feruz_dev"):
        self.chat = SimpleNamespace(id=CHAT, type="supergroup")
        self.from_user = SimpleNamespace(id=1, full_name=name, first_name=name, username=username)
        self.documents = []

    async def answer_document(self, doc):
        self.documents.append(doc)


@pytest.fixture
async def session():
    maker = await init_db("sqlite+aiosqlite:///:memory:")
    async with maker() as s:
        yield s


async def say(session, text, name="Feruz"):
    msg = FakeMsg(name)
    replies = await execute(parse(text, local_now()), msg, session, "kundalik_bot")
    return "\n".join(r.text for r in replies), replies, msg


async def status_of(session, number):
    return (await notes_svc.get_notes(session, CHAT, [number]))[number].status


def all_phrases(key):
    return {p.split("{")[0].strip(" ,") for p in phrases.POOL[key]}


async def test_notes_flow(session):
    out, *_ = await say(session, "tovar sanash kerak")
    assert "#1" in out and "tovar sanash kerak" in out
    out, *_ = await say(session, "! #ombor yuk tushirish ertaga soat 10")
    assert "#2" in out and "#ombor" in out and "⏰" in out
    await say(session, "iltimos kassa hisobotini tekshirish deb yozib qo'y")
    assert (await notes_svc.get_notes(session, CHAT, [3]))[3].text == "kassa hisobotini tekshirish"

    out, *_ = await say(session, "nima ishlar bor")
    assert "3 ta" in out and out.index("#2") < out.index("#1")  # muhim birinchi

    out, *_ = await say(session, "ro'yxat #ombor")
    assert "1 ta" in out and "yuk tushirish" in out

    out, *_ = await say(session, "1 bo'ldi", name="Ali")
    assert "<s>#1 tovar sanash kerak</s>" in out and "2 ta" in out  # qolganlar soni
    out, *_ = await say(session, "1 bo'ldi")
    assert "#1" in out and await status_of(session, 1) == "done"

    out, *_ = await say(session, "kassa hisobotini tekshirish bo'ldi")
    assert "#3" in out and await status_of(session, 3) == "done"

    out, *_ = await say(session, "bajarilganlar")
    assert "2 ta" in out and "Ali" in out

    out, *_ = await say(session, "1 ni qaytar")
    assert await status_of(session, 1) == "open"
    out, *_ = await say(session, "1 o'zgartir: tovarni qayta sanash")
    assert "tovarni qayta sanash" in out
    out, *_ = await say(session, "qidir qayta")
    assert "#1" in out
    await say(session, "1 o'chir")
    assert await notes_svc.get_notes(session, CHAT, [1]) == {}
    out, *_ = await say(session, "99 bo'ldi")
    assert "#99" in out

    out, *_ = await say(session, "kategoriyalar")
    assert "#ombor" in out
    out, *_ = await say(session, "statistika")
    assert "Ochiq zametkalar: <b>1</b>" in out
    out, *_ = await say(session, "bugun nima qildik")
    assert "Yozildi" in out and "Bajarildi" in out

    # oxirgi ochiq ishni yopamiz -> bayram xabari
    out, *_ = await say(session, "2 bajarildi")
    assert any(p in out for p in all_phrases("all_clear"))


async def test_latest_and_bare(session):
    await say(session, "birinchi ish")
    await say(session, "ikkinchi ish")
    await say(session, "uchinchi ish")
    out, *_ = await say(session, "oxirgisi bo'ldi")
    assert await status_of(session, 3) == "done"
    await say(session, "ikkinchisi bajarildi")
    assert await status_of(session, 2) == "done"
    await say(session, "oxirgisini qaytar")
    assert await status_of(session, 2) == "open"

    out, replies, _ = await say(session, "bo'ldi")
    buttons = [b.callback_data for row in replies[0].markup.inline_keyboard for b in row]
    assert buttons == ["nd:2", "nd:1"]


async def test_smalltalk(session):
    for text, key in [("rahmat shef", "thanks"), ("qalaysan", "howareyou"), ("xayr", "bye")]:
        out, *_ = await say(session, text)
        assert any(p in out for p in all_phrases(key)), text
    for text in ["salom", "Assalomu alaykum", "assalomu aleykum shef", "Ассалому алайкум", "assalom"]:
        out, *_ = await say(session, text)
        assert out.startswith("Va alaykum assalom"), (text, out)
    for text in ["va alaykum assalom", "Va aleykum assalom!", "alaykum assalom"]:
        out, *_ = await say(session, text)
        assert "alaykum" not in out.lower() and any(p in out for p in all_phrases("greet_after_alik")), (text, out)
    out, *_ = await say(session, "xayrli tong")
    assert out.startswith("Xayrli tong")
    out, *_ = await say(session, "Assalomu alaykum, ro'yxatni ko'rsat")
    assert out.startswith("Va alaykum assalom") and "Ochiq zametkalar" in out


async def test_clients_flow(session):
    out, *_ = await say(session, "mijoz qo'sh: Alisher, Valijon va Sardor #vip")
    assert "3 ta mijoz" in out
    out, *_ = await say(session, "mijozlar qo'sh:\nMadina +998 90 111 22 33 #ulgurji | Chilonzor\nAlisher")
    assert "1 ta mijoz" in out and "#1 Alisher" in out

    out, *_ = await say(session, "kimlar qoldi")
    assert "4 ta" in out

    out, *_ = await say(session, "Alisher bilan ishladim narx kelishildi")
    assert "Alisher" in out and "narx kelishildi" in out
    out, *_ = await say(session, "Valijonga qo'ng'iroq qildim")
    assert "Valijon" in out

    out, *_ = await say(session, "ishlanmaganlar #vip")
    assert "1 ta" in out and "Sardor" in out and "Alisher" not in out
    out, *_ = await say(session, "bugun kimlar bilan ishladik")
    assert "2 ta" in out

    out, *_ = await say(session, "Alisher haqida ma'lumot ber")
    assert "narx kelishildi" in out and "(1 ta)" in out
    out, *_ = await say(session, "mijoz 4")
    assert "Madina" in out and "Chilonzor" in out

    out, *_ = await say(session, "Alishr bilan gaplashdim")  # xato yozilgan ism
    assert "Alisher" in out and "#1" in out

    out, replies, _ = await say(session, "Bobur bilan uchrashdim")
    assert "Bobur" in out
    assert replies[0].markup.inline_keyboard[-1][0].callback_data.startswith("ca:")
    assert len(PENDING) >= 1

    out, *_ = await say(session, "mijoz 3 o'chir")
    assert "#3 Sardor" in out
    out, *_ = await say(session, "mijozlarni ko'rsat")
    assert "3 ta" in out and "Sardor" not in out

    out, *_ = await say(session, "statistika")
    assert "Ishlangan mijozlar: <b>2</b>" in out


async def test_fuzzy_resolve_ambiguous(session):
    await say(session, "mijoz qo'sh: Ali Karimov, Ali Valiyev")
    found = await clients_svc.resolve(session, CHAT, "Ali")
    assert len(found) == 2


async def test_reminder_and_export(session):
    out, *_ = await say(session, "eslat ertaga 10:00 hisobot topshirish")
    assert "Eslatma qo'yildi" in out
    out, *_ = await say(session, "eslatmalar")
    assert "hisobot topshirish" in out
    out, *_ = await say(session, "eslat hisobot")
    assert "<code>eslat" in out  # vaqtni so'raydi

    await say(session, "test zametka")
    await say(session, "mijoz qo'sh: Ali")
    out, _, msg = await say(session, "export")
    assert len(msg.documents) == 3


def test_say_formats_without_braces():
    for key in phrases.POOL:
        for _ in range(20):
            text = phrases.say(key, "Feruz", n=3, what="x", client="Ali", name="Ali", g="Salom", when="ertaga", who="@vali")
            assert "{" not in text and "}" not in text, (key, text)


async def test_smalltalk_prefix(session):
    await say(session, "tovar sanash")
    out, *_ = await say(session, "rahmat yaxshi , Assalomu alaykum, nima bor bugunga ?")
    first_line = out.split("\n")[0]
    assert first_line.startswith("Va alaykum assalom") and any(p in first_line for p in all_phrases("fine_short"))
    assert "Jami ochiq ishlar: <b>1</b>" in out
    out, *_ = await say(session, "yaxshi")
    assert any(p in out for p in all_phrases("fine"))
