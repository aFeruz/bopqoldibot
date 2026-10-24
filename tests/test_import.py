"""Excel/CSV import, mijozlarni mas'ulga biriktirish va mas'ulga ertalabki eslatma."""

import io
from datetime import timedelta

import openpyxl
import pytest

from bot import jobs
from bot.db import init_db
from bot.handlers.actions import execute
from bot.handlers.files import import_document
from bot.models import Interaction
from bot.parser import parse
from bot.services import clients as clients_svc
from bot.services import reminders as rem_svc
from bot.services.common import local_now
from bot.services.importer import clean_name, clean_phone, parse_table
from tests.test_features import FakeBot
from tests.test_flow import CHAT, FakeMsg

META_HEADER = [
    "id", "created_time", "ad_id", "ad_name", "adset_id", "adset_name", "campaign_id", "campaign_name", "form_id",
    "form_name", "is_organic", "platform", "nimani_ijaraga_berasiz?_(masalan:_qurilish_uskunalari)",
    "полное_имя", "номер_телефона", "lead_status",
]


def meta_row(name, phone, interest="Qurilish uskunalari", status="CREATED", note=None):
    row = ["l:1", "2026-10-20T02:36:58-05:00", "ag:1", "Видео А | UZ", "as:1", "Видео А", "c:1", "Rangor | Лиды",
           "f:1", "Rangor — test 1", "false", "ig", interest, name, phone, status]
    return row + ([note] if note else [])


def xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


META_FILE = xlsx([
    META_HEADER,
    meta_row("<test lead: dummy data for полное_имя>", "p:<test lead: dummy data>"),
    meta_row("Karim Xasanov", "p:+998997990049", note="oylab"),
    meta_row("Shuxrat 974066030", "p:+998907437173", interest="Опалубка ижарв", status="adashgan"),
    meta_row("Mamurjon 5323", "p:991717373"),
    meta_row("Karim Xasanov", "p:+998997990049"),  # dublikat
    meta_row("Обидхон Каримов", "p:+998905971097"),
])


def test_helpers():
    assert clean_phone("p:+998901234567") == "+998901234567"
    assert clean_phone("p:991717373") == "+998991717373"
    assert clean_phone(998901234567.0) == "+998901234567"
    assert clean_phone("90 123 45 67") == "+998901234567"
    assert clean_phone("abc") is None
    assert clean_name("Shuxrat 974066030", "+998") == "Shuxrat"
    assert clean_name("Mamurjon 5323", "+998") == "Mamurjon"
    assert clean_name("BAXT SAROYI | URGUT", None) == "BAXT SAROYI | URGUT"


def test_parse_meta_export():
    items, report = parse_table(META_FILE, "Rangor lid.xlsx")
    assert report.rows == 6 and report.skipped_test == 1 and report.duplicates_in_file == 1
    assert report.columns["name"] == "полное_имя" and report.columns["phone"] == "номер_телефона"
    assert [c.name for c in items] == ["Karim Xasanov", "Shuxrat", "Mamurjon", "Обидхон Каримов"]
    karim, shuxrat, mamur, _ = items
    assert karim.phone == "+998997990049" and "oylab" in karim.comment and "Qiziqish: Qurilish" in karim.comment
    assert "Holat: adashgan" in shuxrat.comment and "Holat" not in mamur.comment  # CREATED yozilmaydi
    assert mamur.phone == "+998991717373"
    assert karim.created_at.hour == 7  # -05:00 -> UTC


@pytest.mark.parametrize("sep", [",", ";"])
def test_parse_csv(sep):
    text = sep.join(["Ism", "Telefon", "Kategoriya", "Izoh", "Mas'ul"]) + "\n"
    text += sep.join(["Ali Valiyev", "+998 90 111 22 33", "VIP", "Chilonzor", "@vali_x"]) + "\n"
    text += sep.join(["Sardor", "901112244", "", "", ""]) + "\n"
    items, report = parse_table(text.encode("utf-8"), "mijozlar.csv")
    assert [(c.name, c.phone) for c in items] == [("Ali Valiyev", "+998901112233"), ("Sardor", "+998901112244")]
    assert items[0].category == "vip" and items[0].comment == "Chilonzor" and items[0].assignee == "@vali_x"


def test_headerless_table():
    items, _ = parse_table(xlsx([["Ali", "901112233"], ["Vali", "+998901112244"]]), "x.xlsx")
    assert [(c.name, c.phone) for c in items] == [("Ali", "+998901112233"), ("Vali", "+998901112244")]


class DownloadBot(FakeBot):
    def __init__(self, data):
        super().__init__()
        self.data = data

    async def download(self, file_id):
        return io.BytesIO(self.data)


@pytest.fixture
async def maker():
    return await init_db("sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def session(maker):
    async with maker() as s:
        yield s


async def test_import_document_and_undo(session):
    bot = DownloadBot(META_FILE)
    reply = await import_document(bot, session, CHAT, "f1", "Rangor lid.xlsx", "#rangor @vali_x ga o'tkaz, eslatib tur",
                                  "Feruz", "Feruz")
    assert "Yangi mijozlar: <b>4</b>" in reply.text and "#rangor" in reply.text and "@vali_x" in reply.text
    clients, total = await clients_svc.list_clients(session, CHAT, limit=100)
    assert total == 4 and all(c.category.name == "rangor" and c.assignee == "@vali_x" and c.remind_assignee
                              for c in clients)

    # qayta import — dublikatlar telefon bo'yicha aniqlanadi
    reply2 = await import_document(bot, session, CHAT, "f1", "Rangor lid.xlsx", "", "Feruz", "Feruz")
    assert "Yangi mijozlar: <b>0</b>" in reply2.text and "Bazada bor edi: 4" in reply2.text

    # bekor qilish: aloqa yozilgan mijoz qoladi
    batch = reply.markup.inline_keyboard[0][0].callback_data.split(":")[1]
    session.add(Interaction(client_id=clients[0].id, chat_id=CHAT, text="", author_name="F"))
    await session.commit()
    removed, kept = await clients_svc.undo_import(session, CHAT, batch)
    assert (removed, kept) == (3, 1)


async def say(session, text):
    replies = await execute(parse(text, local_now()), FakeMsg("Feruz", "feruz_dev"), session, "bopqoldibot")
    return "\n".join(r.text for r in replies)


async def test_assign_and_digest(session, maker):
    await say(session, "mijoz qo'sh: Alisher, Karim, Sardor #vip")
    out = await say(session, "Alisher, Karim ni @vali_x ga o'tkaz, eslatib tur")
    assert "@vali_x" in out and "2 ta" in out
    out = await say(session, "@vali_x mijozlari")
    assert "2 ta" in out and "Sardor" not in out

    await say(session, "Sardor ni @feruz_dev ga ber")
    out = await say(session, "mening mijozlarim")
    assert "1 ta" in out and "Sardor" in out

    bot = FakeBot()
    await jobs.send_assignee_digests(bot, maker)
    assert len(bot.sent) == 1 and "@vali_x" in bot.sent[0][1] and "Alisher" in bot.sent[0][1]

    # Alisher bilan ishlandi — ertangi eslatmada faqat Karim qoladi
    await say(session, "Alisher bilan gaplashdim")
    bot = FakeBot()
    await jobs.send_assignee_digests(bot, maker)
    assert "Karim" in bot.sent[0][1] and "Alisher" not in bot.sent[0][1]

    out = await say(session, "@vali_x ishlanmaganlari")
    assert "1 ta" in out and "Karim" in out

    # kategoriya bo'yicha va vaqtli eslatma
    out = await say(session, "#vip mijozlarini @sardor_x ga ber, ertaga 10 da eslat")
    assert "3 ta" in out and "eslatma #" in out
    reminders = await rem_svc.pending(session, CHAT)
    assert reminders[-1].text.startswith("@sardor_x") and reminders[-1].remind_at > local_now() - timedelta(hours=6)


async def test_add_with_assignee_and_fallback(session):
    out = await say(session, "mijoz qo'sh: Ali, Vali, @vali_x ga o'tkaz")
    assert "2 ta mijoz" in out and "@vali_x, sizga" in out or "@vali_x" in out
    clients, _ = await clients_svc.list_clients(session, CHAT)
    assert {c.assignee for c in clients} == {"@vali_x"}
    # mijoz emas — topshiriq sifatida zametka bo'ladi
    out = await say(session, "hisobotni @vali_x ga ber")
    assert "📌" in out and "hisobot" in out and "@vali_x" in out
