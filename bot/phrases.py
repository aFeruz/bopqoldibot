"""Botning "jonli" javoblari: har safar tasodifiy ibora va murojaat.

Shablonda `{a}` — murojaat (shef, xo'jayin, ism...). Ba'zan murojaatsiz chiqadi,
shunda `, {a}` qismi olib tashlanadi. Bir xil ibora ketma-ket takrorlanmaydi.
"""

import random
import re
from html import escape


ADDRESSES = [
    "shef", "xo'jayin", "boss", "do'stim", "rahbar", "azizim", "jigar", "hamkasb", "ustoz", "chempion",
]

_last: dict[str, str] = {}


def address(name: str | None = None) -> str:
    pool = ADDRESSES + ([escape(name)] * 3 if name else [])
    return random.choice(pool)


def say(key: str, user: str | None = None, **kw) -> str:
    """POOL[key] dan tasodifiy ibora: murojaat bilan yoki usiz, oldingisidan farqli."""
    options = POOL[key]
    choices = [o for o in options if o != _last.get(key)] or options
    tpl = random.choice(choices)
    _last[key] = tpl
    if random.random() < 0.75:
        kw["a"] = address(user)
    else:
        tpl = re.sub(r",?\s*\{a\}", "", tpl)
    return tpl.format(**kw)


def greet(kind: str | None, user: str | None = None) -> str:
    """Salomga alik: salom -> "Va alaykum assalom", alik -> hol-ahvol, xayrli tong -> xayrli tong."""
    if kind == "alik":
        return say("greet_after_alik", user)
    if kind in ("tong", "kun", "kech"):
        word = {"tong": "Xayrli tong", "kun": "Xayrli kun", "kech": "Xayrli kech"}[kind]
        return say("greet_time", user, g=word)
    return say("greet_alik", user)


def greet_prefix(kind: str | None, user: str | None = None) -> str:
    """Gap salom bilan boshlansa, javob oldiga qo'shiladigan qisqa alik."""
    if kind == "alik":
        return random.choice(["Rahmat", "Barakalla"]) + "! 😊"
    if kind in ("tong", "kun", "kech"):
        return {"tong": "Xayrli tong", "kun": "Xayrli kun", "kech": "Xayrli kech"}[kind] + "! ☀️"
    return say("alik_short", user)


POOL: dict[str, list[str]] = {
    # --- zametkalar ---
    "note_saved": [
        "Yozib qo'ydim, {a}! ✍️",
        "Qo'shdim, {a} 👌",
        "Qayd etildi, {a} 📌",
        "Esimda, {a}! 🧠",
        "Tushundim, {a}, yozib oldim 📝",
        "Daftarga tushdi, {a} 📓",
        "Saqladim, {a}. Unutmaymiz! 💾",
        "Xo'p bo'ladi, {a}! Ro'yxatga qo'shildi 📋",
        "Jonim bilan, {a}! 📝",
        "Qabul qilindi, {a} 🫡",
        "Yozdim-qo'ydim, {a} ✍️",
        "Kundalikka kiritdim, {a} 📔",
        "Mana, {a}, muhrlab qo'ydim 🔖",
        "Eslab qoldim, {a}, xotirjam bo'ling 😌",
        "Bo'pti, {a}, ro'yxatda turibdi 📋",
        "Ko'z ostida, {a} 👀",
        "Yozildi, {a}! Vaqti kelganda eslatib turaman 😉",
        "Hammasi joyida, {a} — saqlandi 🗂",
    ],
    "note_important": [
        "Muhim deb belgiladim, {a}! 🔥 Ro'yxat boshida turadi",
        "Shoshilinch! ❗ Eng tepaga qo'ydim, {a}",
        "Bu jiddiy ekan — birinchi o'ringa chiqardim, {a} 🚨",
        "Muhim ish qabul qilindi, {a}! Ko'zdan qochirmaymiz 🎯",
        "Qizil chiroq yondi 🔴 Tepada turadi, {a}",
    ],
    "note_empty": [
        "Nima yozib qo'yay, {a}? 🙂",
        "Matnni unutdingiz, {a} 😄 Nima yozay?",
        "Qulog'im sizda, {a} 👂 Nima qayd etamiz?",
    ],
    "done": [
        "Zo'r, {a}! ✅",
        "Barakalla, {a}! 💪",
        "Ofarin, {a}! Yana bitta ish bitdi 🎯",
        "Qoyil, {a}! 👏",
        "Mana bu ish! 🔥",
        "Bitdi-ketdi ✅",
        "Gap yo'q, {a}! 🏆",
        "Uddasidan chiqdingiz, {a} 💯",
        "Ana endi bo'ldi! 🙌",
        "Klass, {a}! ✔️",
        "Yana bir g'alaba, {a}! 🥇",
        "Bajarildi, {a}! Charchamang 😊",
        "Ishning ko'zini bilasiz, {a} 😎",
        "Tamom! Bir yuk yengillashdi, {a} 🪶",
        "Qoyilmaqom, {a}! ⭐",
        "Shunaqa ishlash kerak, {a}! 🚀",
        "Yopdik, {a}! Keyingisiga o'tamiz ➡️",
        "Molodes, {a}! 👍",
    ],
    "done_many": [
        "Voy-bo', {n} ta ish birdaniga, {a}! 🚀",
        "{n} tasi bitdi, {a}! Rekord! 🏆",
        "Bir zarbada {n} ta, {a}! 💥",
        "{n} ta ishni yopdingiz — tezlik zo'r, {a}! ⚡",
        "Ishlar qaynayapti, {a}! {n} tasi tayyor 🔥",
    ],
    "all_clear": [
        "🎉 Ochiq ish qolmadi, {a}! Endi choy ichsa bo'ladi ☕",
        "🏁 Ro'yxat bo'm-bo'sh! Dam oling, {a} 🌴",
        "🌟 Hammasi bajarildi! Siz zo'rsiz, {a}",
        "🎊 Nol qarz, nol ochiq ish! Mukammal, {a}",
        "🥳 Ro'yxat toza! Bugun bayram, {a}",
    ],
    "remaining": [
        "📋 Yana {n} ta qoldi 💪",
        "📋 Qolgani: {n} ta",
        "📋 Oldinda yana {n} ta ish",
        "📋 {n} ta ish navbatda turibdi",
    ],
    "milestone": [
        "🏅 Bugun {n}-ish yopildi! Jamoa zo'r ishlayapti",
        "🔥 Bugungi hisob: {n} ta bajarilgan ish! Davom etamiz",
        "📈 {n} ta! Bugun samarali kun bo'lyapti",
    ],
    "already_done": [
        "Bu allaqachon bajarilgan-ku, {a} 😄",
        "Bu oldinroq yopilgan edi, {a} 👀",
        "Bu ish allaqachon tayyor, {a} ✅",
    ],
    "already_open": [
        "Bu hali ham ochiq, {a} 🙂",
        "U baribir ro'yxatda turibdi, {a}",
    ],
    "undo": [
        "Qayta ochdim, {a} ↩️",
        "Mayli, ro'yxatga qaytardim, {a} 🔄",
        "Xo'p, hali bo'lmagan ekan — qaytardim ↩️",
        "Qaytdi! Davom ettiramiz, {a} 💪",
        "Ortga oldim, {a} ↩️",
    ],
    "delete": [
        "O'chirib tashladim, {a} 🗑",
        "Yo'q qildim, {a} 🧹",
        "Ketdi! 🗑",
        "Tozaladim, {a} ✨",
        "Ro'yxatdan olib tashladim, {a} 🧽",
    ],
    "edit": [
        "Tuzatdim, {a} ✏️",
        "Yangiladim, {a} ✏️",
        "O'zgartirdim, {a} 🖊",
        "Mana, yangi ko'rinishda, {a} ✍️",
    ],
    "not_found": [
        "Hmm, {what} topolmadim, {a} 🤔",
        "Afsus, {a}, {what} yo'q ekan 🤷",
        "Qidirdim-qidirdim, {what} topilmadi 🔍",
        "{what} bazada yo'q, {a} 🤷",
    ],
    "which_one": [
        "Qaysi birini aytyapsiz, {a}? 👇",
        "Bir nechtasi o'xshash ekan, {a}. Qaysi biri? 🤔",
        "Aniqlashtirib bering, {a} 👇",
    ],
    "which_number": [
        "Qaysi biri, {a}? Tanlang yoki raqamini yozing 👇",
        "Qaysi ishni aytyapsiz, {a}? 👇",
    ],
    "search_head": [
        "Mana nima topdim, {a} 🔎",
        "Topildi, {a} 👇",
        "Qidiruv natijalari, {a} 🔍",
    ],
    # --- ro'yxatlar ---
    "list_head": [
        "Mana, {a} 👇",
        "Qolgan ishlar, {a} 👇",
        "Ro'yxat tayyor, {a} 📋",
        "Marhamat, {a} 📋",
        "Bugungi front, {a} 🎯",
        "Ko'z yugurtirib chiqing, {a} 👀",
    ],
    "list_empty": [
        "Ochiq ish yo'q, {a}! 🎉",
        "Ro'yxat toza ✨ Yangi vazifa bormi, {a}?",
        "Hech narsa qolmagan, {a} 😎",
        "Bo'm-bo'sh! Hammasi bajarilgan, {a} 🏖",
    ],
    "done_head": [
        "Mana qilingan ishlar, {a} 💪",
        "Faxrlanadigan ro'yxat, {a} 🏆",
        "Bajarilganlar, {a} ✅",
    ],
    # --- mijozlar ---
    "client_added": [
        "Bazaga qo'shdim, {a}! 👥",
        "Yangi mijozlar kirdi, {a} 🤝",
        "Mijozlar safi kengaydi, {a} 📈",
        "Qo'shildi, {a}! Endi ular bilan ishlaymiz 💼",
        "Ro'yxatga kiritdim, {a} 👥",
    ],
    "client_dupe": [
        "Bular bazada bor ekan, {a}",
        "Bularni oldin qo'shgan edik, {a}",
    ],
    "client_empty": [
        "Kimni qo'shay, {a}? Masalan: <code>mijoz qo'sh: Ali, Vali #vip</code>",
    ],
    "worked": [
        "Yozib qo'ydim, {a}: {client} bilan ishlandi 🤝",
        "Zo'r! {client} bilan aloqa qayd etildi, {a} 📞",
        "{client} — belgilandi ✔️ Mijoz — oltin, {a} 💰",
        "Ajoyib, {a}! {client} bilan ish bo'ldi 🤝",
        "{client} bilan aloqa — ✅. Barakalla, {a}!",
        "Mijoz e'tiborsiz qolmadi 👌 {client} — yozildi",
        "Qo'l berib ko'rishdik 🤝 {client} — tarixga yozildi",
    ],
    "worked_ask_new": [
        "«{name}» degan mijozni topolmadim, {a} 🤔 Yangi mijoz qilib qo'shib, ishlandi deb belgilaymi?",
        "Bazada «{name}» yo'q ekan, {a}. Qo'shib qo'yaymi? 👇",
    ],
    "worked_ask_which": [
        "«{name}» — qaysi biri, {a}? 👇",
        "«{name}» ismli bir nechta mijoz bor, {a}. Qaysi biri? 👇",
    ],
    "not_worked_head": [
        "Bular hali kutib turibdi, {a} ⏳",
        "Bu mijozlarga e'tibor kerak, {a} 👀",
        "Qo'ng'iroq qilish vaqti, {a}! 📞",
        "Navbatdagilar, {a} 👇",
    ],
    "not_worked_empty": [
        "Hamma mijoz bilan ishlangan, {a}! 🏆",
        "Bironta ham mijoz e'tiborsiz qolmagan, {a} 💪",
        "Hammasi qamrab olingan, {a}! 🎯",
    ],
    "worked_head": [
        "Mana kimlar bilan ishladik, {a} 🤝",
        "Faol mijozlar, {a} 💼",
    ],
    "clients_head": [
        "Mijozlar bazasi, {a} 👥",
        "Mana mijozlarimiz, {a} 💼",
    ],
    "archived": [
        "Arxivga oldim, {a} 🗄",
        "Arxivlandi, {a}. Kerak bo'lsa qaytaramiz 🗄",
    ],
    # --- eslatmalar ---
    "remind_set": [
        "Eslataman, {a}! ⏰",
        "Xotirjam bo'ling, vaqtida aytaman, {a} 🔔",
        "Belgiladim, {a}, unutmayman ⏰",
        "Budilnik qo'ydim, {a} ⏰",
    ],
    "remind_fire": [
        "⏰ {a}, eslatma!",
        "🔔 Vaqt bo'ldi, {a}!",
        "⏰ Esingizdami, {a}?",
        "🔔 Diqqat, {a}!",
    ],
    "remind_when": [
        "Qachon eslatay, {a}? Masalan: <code>eslat ertaga 9:00 hisobot</code> yoki <code>eslat yarim soatdan keyin qo'ng'iroq</code>",
    ],
    "remind_past": [
        "Bu vaqt o'tib ketgan-ku, {a} 😅",
        "Vaqt mashinasi yo'q, {a} 😄 Kelajakdagi vaqtni yozing",
    ],
    # --- hisobotlar ---
    "stats_head": ["Raqamlar gapiradi, {a} 📊", "Mana natijalar, {a} 📊", "Hisobot tayyor, {a} 📈"],
    "diary_head": ["Kundalikni varaqlaymiz, {a} 📔", "Mana nima qildik, {a} 📔", "Kun sarhisobi, {a} 📔"],
    "export_done": ["Fayllar tayyor, {a}! Excel'da ochiladi 📦", "Mana, {a}, hammasi CSV'da 📦"],
    # --- o'zgartirishlar, mas'ullar ---
    "note_updated": [
        "Yangiladim, {a} ✏️",
        "Tayyor, {a}! O'zgartirdim 👌",
        "Bo'ldi, {a}, joyiga qo'ydim 🗂",
        "Xo'p, {a}! Mana yangi ko'rinishi 👇",
    ],
    "assigned": [
        "Topshiriq berildi, {a}! 🎯",
        "Mas'ul belgilandi, {a} 👤",
        "Yukladim, {a}. Endi bu ish egasi bor 💪",
    ],
    "no_username": [
        "Telegram'da username'ingiz yo'q ekan, {a} 🤷 Sozlamalardan @username qo'ysangiz, ishlaringizni ajratib beraman",
    ],
    "my_empty": [
        "Sizga biriktirilgan ochiq ish yo'q, {a} 😎",
        "Sizda hozircha topshiriq yo'q, {a} 🏖",
    ],
    "client_updated": [
        "Mijoz ma'lumoti yangilandi, {a} 👤",
        "Kartochkaga yozib qo'ydim, {a} 📇",
        "Yangiladim, {a} ✏️",
    ],
    "followup_set": [
        "📞 Qayta bog'lanishni eslataman: {when}",
        "🔔 {when} da eslatib qo'yaman",
        "⏰ Unutmaymiz: {when}",
    ],
    "assigned_clients": [
        "👤 {who}, sizga {n} ta mijoz biriktirildi. Omad! 💪",
        "👤 {who}, {n} ta mijoz endi sizning qo'lingizda 🤝",
        "👤 {who}, yangi topshiriq: {n} ta mijoz bilan bog'lanish 📞",
    ],
    "digest_on": [
        "🔔 Ular bilan ishlanmaguncha {who} ga har kuni ertalab eslatib turaman",
        "🔔 Nazoratga oldim: {who} ishlamaguncha har tong eslataman",
    ],
    "digest_head": [
        "☀️ {who}, xayrli tong! Sizni kutayotgan mijozlar ({n} ta):",
        "📞 {who}, bugun bu mijozlar bilan bog'laning ({n} ta):",
        "🔔 {who}, eslatma: {n} ta mijoz hali kutmoqda",
    ],
    "import_done": [
        "Fayl qabul qilindi, {a}! 📥",
        "Hammasini bazaga kiritdim, {a} 📥",
        "Import tugadi, {a}! 📊",
    ],
    "import_offer": [
        "Bu jadvalni mijozlar bazasiga kiritaymi, {a}? 📥",
        "Fayl ko'rindi 👀 Mijozlarni import qilaymi, {a}?",
    ],
    "import_empty": [
        "Fayldan mijoz topolmadim, {a} 🤔 Ism yoki telefon ustuni borligini tekshiring",
    ],
    "import_undone": ["Importni bekor qildim, {a} ↩️", "Import ortga qaytarildi, {a} ↩️"],
    # --- takroriy / avtomatik ---
    "recurring_set": [
        "Jadvalga qo'ydim, {a}! 🔁",
        "Endi o'zim eslatib turaman, {a} 🔁",
        "Har safar vaqtida yozib qo'yaman, {a} 📅",
    ],
    "recurring_fire": [
        "🔁 Vaqti keldi!",
        "🔁 Navbatdagi takroriy ish",
        "🔁 Esingizdami? Odatdagi vazifa",
    ],
    "recurring_deleted": ["Jadvaldan olib tashladim, {a} 🗑", "To'xtatdim, {a} ✋"],
    "due_alert": [
        "⏰ Muddat keldi, {a}!",
        "🔔 Vaqt bo'ldi, {a}!",
        "⏰ Diqqat, {a}! Bu ishning vaqti keldi",
        "🔥 Muddat yetib keldi, {a}!",
    ],
    "snoozed": ["Mayli, {when} ga surdim ⏰", "Xo'p, {when} da yana eslataman 🔔"],
    "morning_head": [
        "☀️ Xayrli tong, {a}! Bugungi reja:",
        "☀️ Xayrli tong! Yangi kun — yangi g'alabalar, {a} 💪",
        "🌅 Tong muborak, {a}! Mana bugungi front:",
    ],
    "agenda_head": ["Mana kun rejasi, {a} 🗓", "Bugungi reja, {a} 📅", "Rejamiz shunday, {a} 👇"],
    "weekly_head": [
        "📊 Hafta yakuni, {a}! Natijalar:",
        "📊 Haftani sarhisob qilamiz, {a}:",
        "🏁 Hafta tugadi! Mana raqamlar, {a}:",
    ],
    "settings_saved": ["Saqladim ✅", "Bo'ldi 👌", "O'zgartirildi ⚙️"],
    # --- suhbat ---
    "greet_alik": [
        "Va alaykum assalom, {a}! 🤝 Bugun nima ishlarimiz bor? 📋",
        "Va alaykum assalom, {a}! 😊 Xizmatingizga tayyorman 🫡",
        "Va alaykum assalom! Ishlaringiz yaxshimi, {a}? 💪",
        "Va alaykum assalom, {a}! 🌟 Qanday yordam kerak?",
        "Va alaykum assalom va rahmatullohi va barokatuh, {a}! 🤲 Qani, ishga kirishamizmi?",
        "Va alaykum assalom! Kelganingiz yaxshi bo'ldi, {a} 😊 Nima qilamiz?",
    ],
    "greet_after_alik": [
        "Ishlaringiz yaxshimi, {a}? 😊 Bugun nima qilamiz?",
        "Rahmat, {a}! 🤝 Qanday yordam bera olaman?",
        "Xursandman, {a}! 😊 Yozing, men tayyorman ✍️",
        "Tinchlikmi, {a}? 💪 Ro'yxatni ko'ramizmi?",
    ],
    "greet_time": [
        "{g}, {a}! ☀️ Bugun nima ishlarimiz bor?",
        "{g}! 😊 Xizmatingizga tayyorman, {a}",
        "{g}, {a}! 🌟 Qani, ishga kirishamiz",
    ],
    "alik_short": [
        "Va alaykum assalom, {a}! 🤝",
        "Va alaykum assalom! 😊",
    ],
    "thanks": [
        "Arzimaydi, {a}! 😊",
        "Doim xizmatingizda, {a} 🫡",
        "Sizga ham rahmat, {a}! 🙏",
        "Xursandman, {a} 😊",
        "Hech gap emas, {a}! 🤝",
        "Biz jamoamiz, {a}! 💪",
    ],
    "fine": [
        "Xursandman, {a}! 😊 Qanday yordam kerak?",
        "Shukr, {a}! 🙌 Bugun nima qilamiz?",
        "Ajoyib, {a}! 😊 Yozing, men tayyorman",
        "Yaxshi eshitib xursand bo'ldim, {a} 😊",
    ],
    "fine_short": ["Xursandman! 😊", "Shukr! 🙌", "Ajoyib! 😊"],
    "thanks_short": ["Arzimaydi! 😊", "Doim xizmatda! 🫡", "Hech gap emas! 🤝"],
    "how_short": ["Men ham zo'rman, rahmat! 💪", "Ishlar joyida! 💪", "Yaxshi, rahmat! 😊"],
    "save_offer": [
        "Buni zametka qilib yozib qo'yaymi, {a}? 📝",
        "Tushunmadim 🤔 Zametka sifatida saqlab qo'yaymi, {a}?",
        "Bu yangi ishmi, {a}? Yozib qo'yaymi? 📝",
    ],
    "bye": [
        "Xayr, {a}! Yaxshi dam oling 👋",
        "Ko'rishguncha, {a}! 🌙",
        "Sog' bo'ling, {a}! Ertaga davom etamiz 👋",
    ],
    "howareyou": [
        "Zo'r, {a}! Ishlayapmiz 💪 O'zingiz yaxshimisiz?",
        "Bir zum ham dam olmayapman, {a} 😄 Sizda ishlar qalay?",
        "Ajoyib! Ro'yxatlar tartibda, {a} 📋",
    ],
    "about": [
        "Men jamoaning kundaligiman, {a} 📔 Zametka, mijozlar, eslatmalar — hammasi menda. <code>yordam</code> deb yozing",
    ],
}
