from datetime import datetime

import pytest

from bot.parser import parse, parse_client_list, parse_when

NOW = datetime(2026, 10, 24, 12, 0)  # shanba


def p(text):
    return parse(text, NOW)


@pytest.mark.parametrize(
    "text,kind",
    [
        ("", "help"),
        ("yordam", "help"),
        ("tovar sanash kerak", "note"),
        ("#ombor tovar sanash", "note"),
        ("3 bo'ldi", "done"),
        ("3, 5 va 7 bajarildi", "done"),
        ("#4 tayyor", "done"),
        ("done 4", "done"),
        ("tovar sanash bo'ldi", "done_text"),
        ("3 ni qaytar", "undo"),
        ("3 o'chir", "delete"),
        ("3 o'zgartir: yangi matn", "edit"),
        ("zametkalar", "list"),
        ("ro'yxat #ombor", "list"),
        ("#ombor", "list"),
        ("bajarilganlar", "list"),
        ("qidir tovar", "search"),
        ("mijoz qo'sh: Ali, Vali", "client_add"),
        ("yangi mijoz Ali +998901234567", "client_add"),
        ("Ali bilan ishladim", "worked"),
        ("Aliga qo'ng'iroq qildim", "worked"),
        ("Ali va Vali bilan gaplashdik narx kelishildi", "worked"),
        ("ishlanmaganlar", "not_worked"),
        ("kim bilan ishlamadik bu hafta #vip", "not_worked"),
        ("ishlanganlar", "worked_list"),
        ("mijozlar", "clients"),
        ("mijozlar #vip", "clients"),
        ("mijoz 5", "client_card"),
        ("Ali haqida", "client_card"),
        ("mijoz 5 o'chir", "client_archive"),
        ("statistika", "stats"),
        ("kundalik", "diary"),
        ("bugun nima qildik", "diary"),
        ("kategoriyalar", "categories"),
        ("eslat ertaga 10:00 hisobot topshirish", "remind"),
        ("export", "export"),
        ("3 бўлди", "done"),
        ("мижозлар", "clients"),
        ("3 boʻldi", "done"),
    ],
)
def test_kinds(text, kind):
    assert p(text).kind == kind


def test_note_details():
    i = p("! #ombor tovar sanash ertaga")
    assert i.category == "ombor"
    assert i.important
    assert i.text == "tovar sanash ertaga"
    assert i.when == datetime(2026, 10, 25, 9, 0)


def test_done_numbers():
    assert p("3, 5 va 7 bajarildi").numbers == [3, 5, 7]


def test_worked_details():
    i = p("Ali va Vali bilan gaplashdik narx kelishildi")
    assert i.names == ["Ali", "Vali"]
    assert i.text == "narx kelishildi"
    assert p("Aliga qo'ng'iroq qildim").names == ["Ali"]
    assert p("mijoz 5 bilan ishladim").names == ["5"]


def test_not_worked_filters():
    i = p("kim bilan ishlamadik bu hafta #vip")
    assert i.period == "week" and i.category == "vip"


def test_list_status():
    assert p("bajarilganlar").status == "done"
    assert p("bajarilmaganlar").status == "open"
    assert p("ro'yxat #ombor").category == "ombor"
    assert p("bugungi ishlar").filter == "today"


def test_remind():
    i = p("eslat ertaga 10:00 hisobot topshirish")
    assert i.when == datetime(2026, 10, 25, 10, 0)
    assert i.text == "hisobot topshirish"
    i = p("eslat 30 minutdan keyin qo'ng'iroq")
    assert i.when == datetime(2026, 10, 24, 12, 30)
    assert i.text == "qo'ng'iroq"


def test_when_variants():
    assert parse_when("dushanba soat 15", NOW)[0] == datetime(2026, 10, 26, 15, 0)
    assert parse_when("25.12 uchrashuv", NOW)[0] == datetime(2026, 12, 25, 9, 0)
    assert parse_when("soat 9:30", NOW)[0] == datetime(2026, 10, 25, 9, 30)
    assert parse_when("oddiy matn", NOW)[0] is None


def test_client_list():
    cs = parse_client_list("Ali, Vali va Sardor #vip")
    assert [c.name for c in cs] == ["Ali", "Vali", "Sardor"]
    assert all(c.category == "vip" for c in cs)
    cs = parse_client_list("Ali Valiyev +998 90 123 45 67 #ulgurji | Chilonzor\nSardor 901112233")
    assert cs[0].name == "Ali Valiyev" and cs[0].phone == "+998901234567"
    assert cs[0].category == "ulgurji" and cs[0].comment == "Chilonzor"
    assert cs[1].name == "Sardor" and cs[1].phone == "901112233"


@pytest.mark.parametrize(
    "text,kind",
    [
        # zametka qo'shish turli shakllarda
        ("iltimos yozib qo'y: kassa tekshirish", "note"),
        ("kassa tekshirish deb yozib qo'y", "note"),
        ("shef, tovar keldi", "note"),
        # done sinonimlari
        ("3 bo'pti", "done"),
        ("3 bitirdim", "done"),
        ("3 yakunlandi", "done"),
        ("3 tamom", "done"),
        ("3 ✅", "done"),
        ("3 +", "done"),
        ("#3 ni hal qildim", "done"),
        ("uchinchisi bo'ldi", "done"),
        ("oxirgisi bo'ldi", "done"),
        ("bo'ldi", "done"),
        ("shu bajarildi", "done"),
        ("готово 3", "done"),
        ("hisobotni tugatdim", "done_text"),
        # undo / delete / edit
        ("3 xato bosdim", "undo"),
        ("3 bo'lmabdi", "undo"),
        ("3 kerak emas", "delete"),
        ("oxirgisini o'chir", "delete"),
        ("3 tuzat: yangi matn", "edit"),
        # ro'yxatlar
        ("nima ishlar bor", "list"),
        ("nima qoldi", "list"),
        ("ro'yxatni ko'rsat", "list"),
        ("zametkalarni ber", "list"),
        ("bugungi reja", "agenda"),
        ("kun rejasi", "agenda"),
        ("qilingan ishlar", "list"),
        ("qani ro'yxat", "list"),
        # mijozlar
        ("Ali, Vali ni mijozlarga qo'sh", "client_add"),
        ("bazaga qo'sh: Ali", "client_add"),
        ("ishladim Ali bilan", "worked"),
        ("Aliga taklif yubordim", "worked"),
        ("Ali bilan shartnoma tuzdik", "worked"),
        ("Ali — gaplashildi", "worked"),
        ("kimlar qoldi", "not_worked"),
        ("kimga qo'ng'iroq qilish kerak", "not_worked"),
        ("kim bilan ishladik", "worked_list"),
        ("mijozlarni ko'rsat", "clients"),
        ("bazadagi mijozlar", "clients"),
        ("Ali haqida ma'lumot ber", "client_card"),
        # boshqalar
        ("hisobotni ertaga 9 da eslat", "remind"),
        ("esimga sol 1 soatdan keyin choy", "remind"),
        ("qalay ketyapmiz", "stats"),
        ("kun yakuni", "diary"),
        ("tovarni qidir", "search"),
        ("excel qilib ber", "export"),
        # suhbat
        ("salom", "greet"),
        ("assalomu alaykum", "greet"),
        ("va alaykum assalom", "greet"),
        ("xayrli kech", "greet"),
        ("rahmat", "thanks"),
        ("katta rahmat shef", "thanks"),
        ("zo'r", "thanks"),
        ("qalaysan", "howareyou"),
        ("xayr", "bye"),
        ("sen kimsan", "about"),
        ("nima qila olasan", "help"),
    ],
)
def test_vocabulary(text, kind):
    assert p(text).kind == kind, p(text)


def test_vocabulary_details():
    assert p("uchinchisi bo'ldi").numbers == [3]
    assert p("oxirgisi bo'ldi").numbers == [0]
    assert p("bo'ldi").numbers == []
    assert p("kassa tekshirish deb yozib qo'y").text == "kassa tekshirish"
    assert p("iltimos yozib qo'y: kassa tekshirish").text == "kassa tekshirish"
    assert p("hisobotni tugatdim").text == "hisobot"
    assert p("ishladim Ali bilan").names == ["Ali"]
    assert p("salom, ro'yxatni ko'rsat").kind == "list"
    assert p("salom, ro'yxatni ko'rsat").greeting == "salam"
    assert p("Assalomu alaykum").greeting == "salam"
    assert p("va alaykum assalom").greeting == "alik"
    assert p("assalomu alaykum, 3 bo'ldi").numbers == [3]
    i = p("hisobotni ertaga 9 da eslat")
    assert i.text == "hisobot" and i.when == datetime(2026, 10, 25, 9, 0)


def test_when_rich():
    assert parse_when("yarim soatdan keyin", NOW)[0] == datetime(2026, 10, 24, 12, 30)
    assert parse_when("ikki soatdan keyin", NOW)[0] == datetime(2026, 10, 24, 14, 0)
    assert parse_when("ertaga kechqurun", NOW)[0] == datetime(2026, 10, 25, 19, 0)
    assert parse_when("kechqurun 8 da", NOW)[0] == datetime(2026, 10, 24, 20, 0)
    assert parse_when("ertaga ertalab", NOW)[0] == datetime(2026, 10, 25, 9, 0)
    assert parse_when("soat 3 da", NOW)[0] == datetime(2026, 10, 24, 15, 0)
    assert parse_when("keyingi hafta", NOW)[0] == datetime(2026, 10, 26, 9, 0)
    assert parse_when("oy oxirida", NOW)[0] == datetime(2026, 10, 31, 9, 0)
    assert parse_when("tushdan keyin", NOW)[0] == datetime(2026, 10, 24, 14, 0)
    # oddiy matnda vaqt yo'q
    assert parse_when("2 soat ishladim", NOW)[0] is None
