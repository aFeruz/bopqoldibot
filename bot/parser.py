"""Erkin matnni (o'zbekcha, lotin yoki kirill) buyruqqa (Intent) aylantiradi.

Sof funksiyalar: bazaga ham, Telegramga ham bog'liq emas, shuning uchun to'liq testlanadi.
"""

import re
from dataclasses import dataclass, field
from dataclasses import field as dc_field  # Intent ichida "field" maydoni bor
from datetime import date, datetime, timedelta

# --- normalizatsiya -------------------------------------------------------

_APOSTROPHES = str.maketrans({c: "'" for c in "ʻʼ‘’`´ʹ"})

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'",
    "ҳ": "h",
}


def _translit(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in _CYR:
            lat = _CYR[low]
            out.append(lat.capitalize() if ch != low and lat else lat)
        else:
            out.append(ch)
    return "".join(out)


def normalize(text: str) -> str:
    """Apostroflarni bir xil qiladi, kirillni lotinga o'giradi, ortiqcha bo'shliqlarni olib tashlaydi."""
    text = text.translate(_APOSTROPHES)
    if re.search(r"[а-яёўқғҳ]", text, re.IGNORECASE):
        text = _translit(text)
    return re.sub(r"[ \t]+", " ", text).strip()


# --- Intent ---------------------------------------------------------------


@dataclass
class Intent:
    kind: str
    text: str = ""
    numbers: list[int] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    category: str | None = None
    important: bool = False
    when: datetime | None = None  # mahalliy vaqt
    period: str | None = None  # today / yesterday / week / month / all / "Nd"
    status: str | None = None  # open / done / all
    filter: str | None = None  # today / important / overdue
    greeting: str | None = None  # salam / alik / tong / kun / kech — gap boshidagi salomlashish
    assignee: str | None = None  # "@ali,@vali" yoki "me"
    field: str | None = None  # note_update/client_update: qaysi maydon
    value: object = None
    rule: str | None = None  # takroriy: daily / workdays / weekly:N / monthly:N
    remind: bool = False  # mas'ulga eslatib turish
    smalltalk: list[str] = dc_field(default_factory=list)  # gap boshidagi: greet / thanks / fine / how


# --- yordamchi parserlar ----------------------------------------------------

TAG_RE = re.compile(r"(?<![\w#])#([^\W\d][\w\-]*)", re.UNICODE)
NUM_TAG_RE = re.compile(r"#(\d+)\b")
PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{6,}\d")

WEEKDAYS = {
    "dushanba": 0, "seshanba": 1, "chorshanba": 2, "payshanba": 3,
    "juma": 4, "shanba": 5, "yakshanba": 6,
}

IMPORTANT_RE = re.compile(r"^!+\s*|\b(muhim|srochno|shoshilinch|tezda|zudlik bilan)\b", re.IGNORECASE)


def extract_tags(text: str) -> tuple[str, list[str]]:
    tags = [t.lower() for t in TAG_RE.findall(text)]
    clean = TAG_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", clean).strip(), tags


def extract_important(text: str) -> tuple[str, bool]:
    found = bool(IMPORTANT_RE.search(text))
    if text.startswith("!"):
        text = text.lstrip("!").strip()
    return text, found


NUM_WORDS = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4, "besh": 5, "olti": 6, "yetti": 7, "sakkiz": 8,
    "to'qqiz": 9, "toqqiz": 9, "o'n": 10, "o'n besh": 15, "yigirma": 20, "o'ttiz": 30, "qirq": 40, "ellik": 50,
    "yarim": 0.5,
}
_NUMW = "|".join(sorted(map(re.escape, NUM_WORDS), key=len, reverse=True))

_TIME_RE = re.compile(r"\b(?:soat\s*)?([01]?\d|2[0-3])[:.]([0-5]\d)\b(?:\s*(?:da|ga)\b)?|\bsoat\s*([01]?\d|2[0-3])\b(?:\s*(?:da|ga|larda))?")
_BARE_HOUR_RE = re.compile(r"\b([01]?\d|2[0-3])\s*(?:da|ga|larda)\b")
_DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b")
_REL_RE = re.compile(
    rf"\b(\d+|{_NUMW})\s*(minut\w*|daqiqa\w*|min|soat\w*|kun\w*|hafta\w*|oy\w*)\s*(?:dan|da)?\s*(keyin|so'ng|o'tib)?\b"
)
_DAYWORD_RE = re.compile(
    r"\b(bugun|ertaga|ertasiga|indinga|keyingi hafta|kelasi hafta|hafta oxiri|oy oxiri|" + "|".join(WEEKDAYS) + r")\w*"
)
# kun qismi -> (standart soat, tushdan keyinmi)
DAY_PARTS = [
    (r"ertalab|tongda|erta bilan", 9, False),
    (r"tushdan keyin|obeddan keyin|abeddan keyin", 14, True),
    (r"tushda|tushlikda|peshinda|obedda|abedda", 13, True),
    (r"kechqurun|kechki payt|kechga|kechda|oqshom\w*", 19, True),
    (r"kechasi|tunda|yarim tunda", 22, True),
]
_PART_RE = re.compile(r"\b(" + "|".join(p for p, _, _ in DAY_PARTS) + r")\b")


def parse_when(text: str, now: datetime) -> tuple[datetime | None, str]:
    """Matndan sana/vaqtni topadi. (datetime yoki None, sana iboralari olib tashlangan matn)."""
    low = text.lower()
    spans: list[tuple[int, int]] = []

    rel = _REL_RE.search(low)
    if rel:
        raw_n, unit, after = rel.group(1), rel.group(2), rel.group(3)
        n = float(raw_n) if raw_n.isdigit() else NUM_WORDS[raw_n]
        is_min = unit.startswith(("minut", "daqiqa", "min"))
        if after or (is_min and raw_n.isdigit()):
            if is_min:
                delta = timedelta(minutes=n)
            elif unit.startswith("soat"):
                delta = timedelta(hours=n)
            elif unit.startswith("kun"):
                delta = timedelta(days=n)
            elif unit.startswith("hafta"):
                delta = timedelta(weeks=n)
            else:
                delta = timedelta(days=30 * n)
            spans.append(rel.span())
            return (now + delta).replace(second=0, microsecond=0), _cut(text, spans)

    day: date | None = None
    m = _DAYWORD_RE.search(low)
    if m:
        word = m.group(1)
        if word == "bugun":
            day = now.date()
        elif word in ("ertaga", "ertasiga"):
            day = now.date() + timedelta(days=1)
        elif word == "indinga":
            day = now.date() + timedelta(days=2)
        elif word in ("keyingi hafta", "kelasi hafta"):
            day = now.date() + timedelta(days=7 - now.weekday())
        elif word == "hafta oxiri":
            day = now.date() + timedelta(days=(5 - now.weekday()) % 7)
        elif word == "oy oxiri":
            nxt = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
            day = (nxt - timedelta(days=1)).date()
        else:
            ahead = (WEEKDAYS[word] - now.weekday()) % 7 or 7
            day = now.date() + timedelta(days=ahead)
        spans.append(m.span())
    else:
        d = _DATE_RE.search(low)
        if d:
            dd, mm, yy = int(d.group(1)), int(d.group(2)), d.group(3)
            year = int(yy) + (2000 if yy and len(yy) == 2 else 0) if yy else now.year
            try:
                day = date(year, mm, dd)
                if not yy and day < now.date():
                    day = date(year + 1, mm, dd)
                spans.append(d.span())
            except ValueError:
                day = None

    part_hour, pm = None, False
    pt = _PART_RE.search(low)
    if pt:
        for pattern, h, is_pm in DAY_PARTS:
            if re.fullmatch(pattern, pt.group(1)):
                part_hour, pm = h, is_pm
                break
        spans.append(pt.span())

    hour = minute = None
    t = _TIME_RE.search(low)
    if t:
        if t.group(1) is not None:
            hour, minute = int(t.group(1)), int(t.group(2))
        else:
            hour, minute = int(t.group(3)), 0
        spans.append(t.span())
    elif day is not None or part_hour is not None:
        b = _BARE_HOUR_RE.search(low)  # "ertaga 10 da"
        if b:
            hour, minute = int(b.group(1)), 0
            spans.append(b.span())

    if hour is not None and hour < 12 and (pm or (part_hour is None and 1 <= hour <= 6)):
        hour += 12  # "kechqurun 7 da" -> 19:00, "soat 3 da" -> 15:00
    if hour is None and part_hour is not None:
        hour, minute = part_hour, 0

    if day is None and hour is None:
        return None, text
    if day is None:
        day = now.date()
        if (hour, minute) <= (now.hour, now.minute):
            day += timedelta(days=1)
    if hour is None:
        hour, minute = 9, 0
    return datetime(day.year, day.month, day.day, hour, minute), _cut(text, spans)


def _cut(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + text[end:]
    return re.sub(r"\s{2,}", " ", text).strip(" ,.-:")


def parse_period(text: str) -> str | None:
    low = text.lower()
    if re.search(r"\bbugun", low):
        return "today"
    if re.search(r"\bkecha", low):
        return "yesterday"
    m = re.search(r"\b(\d+)\s*kun", low)
    if m:
        return f"{m.group(1)}d"
    if re.search(r"\bhafta", low):
        return "week"
    if re.search(r"\boy\b|\boyda\b|\boylik|\bshu oy", low):
        return "month"
    if re.search(r"\b(hammasi|umuman|barcha vaqt)", low):
        return "all"
    return None


def parse_numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]


def split_names(text: str) -> list[str]:
    parts = re.split(r"\s*(?:,|;|\n|\bva\b|\bhamda\b)\s*", text)
    return [p.strip(" .-:") for p in parts if p.strip(" .-:")]


@dataclass
class ClientInput:
    name: str
    phone: str | None = None
    comment: str | None = None
    category: str | None = None
    assignee: str | None = None
    created_at: datetime | None = None  # importda: lid kelgan vaqt (UTC)


def parse_client_line(line: str) -> ClientInput | None:
    line, assignee = extract_assignees(line.strip(" -•*\t"))
    line, tags = extract_tags(line)
    comment = None
    if "|" in line:
        line, comment = (s.strip() for s in line.split("|", 1))
    phone = None
    pm = PHONE_RE.search(line)
    if pm:
        phone = re.sub(r"[\s\-()]", "", pm.group(0))
        line = line[: pm.start()] + line[pm.end():]
    name = re.sub(r"\s{2,}", " ", line).strip(" ,-:—")
    if not name:
        return None
    return ClientInput(name=name, phone=phone, comment=comment or None, category=tags[0] if tags else None,
                       assignee=assignee)


def parse_client_list(text: str) -> list[ClientInput]:
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) == 1 and not PHONE_RE.search(lines[0]) and "|" not in lines[0]:
        # "Ali, Vali va Sardor #vip" — umumiy teg hammasiga
        body, assignee = extract_assignees(lines[0])
        body, tags = extract_tags(body)
        cat = tags[0] if tags else None
        return [ClientInput(name=n, category=cat, assignee=assignee) for n in split_names(body)]
    result = []
    for line in lines:
        c = parse_client_line(line)
        if c:
            result.append(c)
    return result


# --- asosiy dispatcher ------------------------------------------------------

DONE_WORDS = (
    r"(?:bo'ldi|boldi|bo'pti|bopti|bo'p qoldi|bo'lib qoldi|bo'ldi-ku|bajarildi|bajardim|bajardik|bajarib qo'ydim|"
    r"bajarib bo'ldim|bajarib bo'ldik|bajarilgan|tayyor|tayyorladim|done|qilindi|qildim|qildik|qilib qo'ydim|"
    r"qilib bo'ldim|qilib bo'ldik|tugadi|tugatdim|tugatdik|tugatildi|tugallandi|yopildi|yopdim|yopdik|yop|"
    r"bitdi|bitirdim|bitirdik|bitirildi|hal bo'ldi|hal qilindi|hal qildim|hal qildik|yakunlandi|yakunladim|"
    r"yakunladik|tamom|tamom bo'ldi|uddaladim|uddaladik|gotovo|sdelano|sdelal|zakryto|complete|completed|"
    r"finished|fixed|ok|okey|✅|✔️|✔|👍|\+)"
)
UNDO_WORDS = (
    r"(?:qaytar\w*|ochiq qil|qayta och\w*|undo|bo'lmadi|bo'lmabdi|bo'lmagan ekan|bajarilmadi|hali bo'lmagan|"
    r"ortga qaytar\w*|otmena|xato bosdim|xato bo'ldi|adashibman|adashdim)"
)
DEL_WORDS = (
    r"(?:o'chir\w*|ochir\w*|delete|del|olib tashla\w*|kerak emas|keraksiz|bekor qil\w*|bekor|udali\w*|"
    r"yo'q qil\w*|tozala\w*)"
)
EDIT_WORDS = r"(?:o'zgartir\w*|ozgartir\w*|tahrirla\w*|tahrir|edit|almashtir\w*|to'g'rila\w*|tuzat\w*|yangila\w*)"
WORKED_WORDS = (
    r"(?:ishladim|ishladik|ishlandi|ishlashdik|gaplashdim|gaplashdik|gaplashildi|suhbatlashdim|suhbatlashdik|"
    r"suhbat qildim|suhbat qildik|muloqot qildim|muloqot qildik|uchrashdim|uchrashdik|uchrashuv bo'ldi|"
    r"uchrashuv o'tkazdim|uchrashuv o'tkazdik|qo'ng'iroq qildim|qo'ng'iroq qildik|qo'ng'iroq qilindi|"
    r"qo'ng'iroqlashdim|qo'ng'iroqlashdik|telefon qildim|telefon qildik|tel qildim|zvon qildim|zvonit qildim|"
    r"obzvon qildim|bog'landim|bog'landik|bog'lanildi|yozishdim|yozishdik|yozdim|xabar yubordim|sms yubordim|"
    r"xabarlashdim|xabarlashdik|aloqaga chiqdim|aloqaga chiqdik|aloqa qildim|aloqa qildik|ko'rishdim|ko'rishdik|"
    r"sotdim|sotdik|kelishdim|kelishdik|kelishib oldim|kelishib oldik|shartnoma tuzdim|shartnoma tuzdik|"
    r"taklif berdim|taklif yubordim|kp yubordim|tashrif buyurdim|tashrif buyurdik|bordim|bordik|"
    r"prezentatsiya qildim|taqdimot qildim|ko'rsatdim|ko'rsatdik)"
)
CLIENT_WORD = r"(?:mijoz|mijozlar|mijozni|mijozlarni|klient|klientlar|client|clients)"
CLIENTS_PLURAL = r"(?:mijozlar\w*|klientlar\w*|clients)"
NUMS = r"#?(\d+(?:\s*(?:,|va|\s)\s*#?\d+)*)"
ADD_VERB = r"(?:qo'sh|qosh|kirit|yoz|qayd et|ro'yxatga ol|add)\w*"

ORDINALS = {
    "birinchi": 1, "ikkinchi": 2, "uchinchi": 3, "to'rtinchi": 4, "beshinchi": 5, "oltinchi": 6,
    "yettinchi": 7, "sakkizinchi": 8, "to'qqizinchi": 9, "o'ninchi": 10,
}
_ORD_RE = re.compile(r"\b(" + "|".join(ORDINALS) + r")(?:si|sini|ni|zametka\w*)?\b")
_LAST_RE = re.compile(r"\b(?:eng\s+)?(?:oxirgi|oxirgisi|oxirgisini|so'nggi|songgi)(?:\s+(?:zametka|vazifa|ish)\w*)?\b")

FILLER = (
    r"(?:iltimos|marhamat|pls|plz|please|shef|xo'jayin|xojayin|boss|aka|opa|brat|bratan|bro|do'stim|dostim|"
    r"jigar(?:im)?|botjon|bot|azizim|ukam|qani|xo'sh|xullas|endi|hozir|tezroq)"
)
_ALAYKUM = r"(?:alaykum|aleykum|alaykim|alekum|alaykom)"
GREETINGS = [
    # (tur, regex) — tartib muhim: alik salomdan oldin tekshiriladi
    ("alik", rf"(?:va\s*)?{_ALAYKUM}\s*(?:as+alom|as+alam|salom)\w*|va\s+{_ALAYKUM}"),
    ("salam", rf"(?:as-?|a)?s+al[oa]mu?\s*{_ALAYKUM}|as+al[oa]m\w*|salom\w*|salam\w*|privet|hello|hi|"
              r"zdravstvuyte|qales\w*"),
    ("tong", r"[xh]ayrli tong|tong muborak"),
    ("kun", r"[xh]ayrli kun"),
    ("kech", r"[xh]ayrli kech\w*|[xh]ayrli oqshom"),
]
GREET_RE = re.compile(r"^(?:" + "|".join(f"(?P<{k}>{rx})" for k, rx in GREETINGS) + r")\b[\s,!.]*")
THANKS_RE = re.compile(
    r"^(?:katta |ko'p |juda )?(?:rahmat|raxmat|rahmet|spasibo|tashakkur|sag' bo'l\w*|sog' bo'l\w*|barakalla|"
    r"baraka toping|ofarin|molodes|malades|molodets|zo'r|zor|klass|super|thanks|thank you|qoyil|gap yo'q|"
    r"yashavor|yashang|charchamang)\b"
)
HOW_RE = re.compile(
    r"^(?:qalaysan\w*|qalaysiz|qalesan|yaxshimisan\w*|yaxshimisiz|ishlar qalay|ahvol\w*|nima gap|kak dela|"
    r"qandaysan|qandaysiz|charchamadingmi|tinchmisan|tinchmi|o'zingiz\w*(?:-?chi)?|o'zing\w*(?:-?chi)?|siz-?chi|"
    r"sen-?chi|sizda nima gap|o'zingda nima gap)"
)
FINE_RE = re.compile(
    r"^(?:men ham |o'zim ham |hammasi |ishlar |biz ham )?(?:yaxshi|yaxshiman|yaxshimiz|zo'r|zor|a'lo|joyida|"
    r"yomon emas|chakki emas|alhamdulillah\w*|shukr\w*|normalno|norm|xorosho|otlichno|tinch|tinchlik)\b"
)
def _whole(alts: str) -> re.Pattern:
    """Butun xabar shu so'z(lar)dan iborat bo'lsa (bir nechtasi ketma-ket ham bo'lishi mumkin)."""
    return re.compile(rf"^(?:{alts})(?:[\s,!.]+(?:{alts}))*[\s!.)]*$")


ACK_ALTS = (
    r"ok|okey|okay|oke|xo'p|xop|mayli|tushunarli|tushundim|tushundik|bo'pti|bopti|ha|xa|haa|albatta|kelishdik|"
    r"kelishildi|aniq|to'g'ri|togri|shunday|bo'ladi|boladi|yaxshi bo'ladi|ponyatno|ladno|davay|ok rahmat|"
    r"qabul qilindi|qabul|zo'r bo'ldi|ajoyib|super|norm"
)
NO_ALTS = r"yo'q|yoq|kerak emas|shart emas|yo'q rahmat|net|hojati yo'q|hozircha yo'q|keyin|keyinroq|boshqa safar"
ACK_RE = _whole(ACK_ALTS)
NO_RE = _whole(NO_ALTS)
ACK_HEAD_RE = re.compile(rf"^(?:{ACK_ALTS})\b")
NO_HEAD_RE = re.compile(rf"^(?:{NO_ALTS})\b")
LAUGH_RE = re.compile(
    r"^(?:(?:x+a+){2,}\w*|(?:h+a+){2,}\w*|(?:x+i+){2,}|(?:h+e+){2,}|ha-?ha\w*|xa-?xa\w*|kulgili\w*|kuldim|"
    r"kuldirding\w*|kuldirdingiz|lol|rofl|\)\)+)[\s!.)]*$"
)
ALIVE_RE = re.compile(
    r"^(?:bormisan|bormisiz|bormi|shu yerdamisan|shu yerdamisiz|tirikmisan|tirikmisiz|uxladingmi|uxlab qolding\w*|"
    r"uxlama\w*|uyg'on\w*|uyqudamisan|ishlayapsanmi|ishlayapsizmi|ishlayapti\w*mi|javob ber\w*|nega jim\w*|"
    r"nega javob bermay\w*|eshityapsanmi|eshityapsizmi|alo+|allo+|hoy|ey|qayerdasan|qayerdasiz|labbay)\b"
)
COMPLIMENT_RE = re.compile(
    r"(?:aqlli|zo'r|zor|ajoyib|yaxshi|super|klass|eng zo'r|molodes|malades|qoyil|zo'r ekan)\w*\s+"
    r"(?:bot|botsan|botsiz|ekansan|ekansiz|yordamchi|kotib)\w*|^(?:sen|siz)\s+(?:zo'r|aqlli|ajoyib|eng zo'r|super|"
    r"daxshat|zo'r ekan)\w*|^(?:seni |sizni )?(?:sevaman|yaxshi ko'raman)|^(?:sendan|sizdan) xursandman"
)
INSULT_RE = re.compile(
    r"\b(?:ahmoq|axmoq|tentak|jinni|yomon bot|bekorchi|foydasiz|tupoy|durak|lox|eshak|befoyda|ishlamaysan|"
    r"hech narsa bilmaysan|tushunmaysan|tushunmaysiz)\b"
)
SORRY_RE = re.compile(r"^(?:kechir\w*|uzr\w*|izvini\w*|sorry|afsus\w*|xafa bo'lma\w*)\b")
JOKE_RE = re.compile(
    r"\b(?:latifa|hazil|anekdot|qiziq gap|qiziqarli gap)\w*\s+(?:ayt|aytib|gapir|qil|bormi|top|ber|eshit)\w*|"
    r"^(?:bitta |bir |yana )?(?:latifa|hazil|anekdot)\w*$|\bkuldir\w*"
)
MOTIV_RE = re.compile(
    r"\b(?:motivatsiya|motivat|ruhlantir|ilhom|dalda|kuch ber|charchadim|charchadik|zerikdim|zerikarli|"
    r"ishlagim kelmayapti|kayfiyat yo'q|kayfiyatim yo'q|kayfiyat\w* yomon|qiynaldim|holdan toydim)\w*"
)
TIME_ASK_RE = re.compile(r"^(?:hozir\s+)?(?:soat|vaqt)\s+(?:necha|nechchi|nechida|qancha|nechi)\w*|^nechchi bo'ldi")
DATE_ASK_RE = re.compile(
    r"^(?:bugun\s+)?(?:nechanchi|necha)\s*(?:sana|chislo|kun)?\w*$|bugun qaysi kun|bugun nima kun|bugun sana|"
    r"sana qanaqa|sana nechchi|qaysi kun bugun|bugun haftaning qaysi|bugun nechanchi"
)
QUESTION_TAIL_RE = re.compile(
    r"(?:\b(?:bormi|yo'qmi|kerakmi|mumkinmi|to'g'rimi|rostmi|shumi|umi|tayyormi|joyidami|yaxshimi)|"
    r"\w(?:dimi|didimi|dingizmi|dikmi|yaptimi|yapsizmi|yapsanmi|adimi|ydimi|ladimi|mikan|mikin|misiz|misan|mizmi))"
    r"[\s?!.]*$|\?\s*$"
)
EMOJI_GROUPS = [
    ("laugh", "😂🤣😄😆😁😅😹😃"),
    ("ack", "👍👌✅✔🆗🤝☑"),
    ("love", "❤🧡💛💚💙💜🤍🖤💖💗💕😍🥰😘🙏"),
    ("fire", "🔥💪🚀⚡💯🏆🥇👏🙌⭐🌟"),
    ("sad", "😢😭😔😞☹🙁😩😫💔"),
    ("wow", "😮😲😱🤯😳👀"),
]


def emoji_kind(text: str) -> str:
    for kind, chars in EMOJI_GROUPS:
        if any(c in text for c in chars):
            return kind
    return "other"


BYE_RE = re.compile(r"^(?:xayr|hayr|ko'rishguncha|poka|yaxshi qoling|xayrli tun|hayrli tun|good night|bye)\b")
ABOUT_RE = re.compile(r"^(?:sen kimsan|kimsan|isming nima|o'zing haqingda|sen nima qilasan)")
HELP_RE = re.compile(
    r"^(?:yordam\w*|help|start|nima qila olasan|nimalar qila olasan|nima qilasan|qanday ishlatiladi|"
    r"qanday ishlataman|buyruqlar|komandalar|pomosh|qo'llanma|instruksiya|imkoniyatlar\w*|\?)\b"
)

LIST_KW = (
    r"^(zametka\w*|zamitka\w*|ro'yxat\w*|royxat\w*|spisok|vazifalar\w*|zadach\w*|tasks|ishlar\w*|"
    r"qolganlar\w*|qolgan ishlar|nima qoldi|nimalar qoldi|nima qolgan|nimalar qolgan|nima ishlar bor|"
    r"qanday ishlar bor|nima qilish kerak|nimalar qilish kerak|nima qilishim kerak|nima qilishimiz kerak|"
    r"qilinadigan\w*|reja\w*|plan\w*|list|notes|todo|dela|ochiq\w*|bajarilmagan\w*|qilinmagan\w*|"
    r"bajarilgan\w*|qilingan\w*|bo'lganlar\w*|bo'lgan ishlar|tugaganlar\w*|yopilgan\w*|done|hammasi|"
    r"barchasi|hamma ishlar|barcha ishlar|muhimlar\w*|muhim ishlar|bugungi\w*|ertangi\w*|"
    r"muddati o'tgan\w*|kechikkan\w*|qaydlar\w*|yozuvlar\w*)"
)
LIST_NOUN = r"(zametka\w*|zamitka\w*|ro'yxat\w*|royxat\w*|spisok|vazifa\w*|zadach\w*|ishlar\w*|reja\w*|qaydlar\w*|yozuvlar\w*|dela)"
SHOW_VERB = r"\b(ko'rsat\w*|korsat\w*|ber|bering|chiqar\w*|tashla|qani|qaysi|nima\w*|bor|bormi|pokaj\w*|show)\b"

NOTE_PREFIX = re.compile(
    r"^(?:zametka(?:ga)?(?: qil)?|yoz(?:ib qo'y|ib qoy|ib ol|ib qo'ying)?|qayd et|qo'sh(?:ib qo'y)?|"
    r"eslab qol|esda tut|note|zapishi|\+)\b\s*[:\-]?\s*|^\+\s*",
    re.IGNORECASE,
)
NOTE_SUFFIX = re.compile(
    r"\s*(?:deb\s+)?(?:yozib qo'y\w*|yozib qoy|yozib ol\w*|zametka qil\w*|qayd et\w*|eslab qol\w*|"
    r"esda tut|yozvol|yozib qo'yasanmi)\s*[.!]*$",
    re.IGNORECASE,
)
REMIND_HEAD = re.compile(
    r"^(?:eslat(?:ib qo'y\w*|ib qoy|gin|ib qo'yasan|ma qo'y|ma)?|esimga sol\w*|yodimga sol\w*|esga sol\w*|"
    r"napomni|remind|budilnik qo'y)\b[\s:,-]*(.*)$",
    re.IGNORECASE | re.DOTALL,
)
REMIND_TAIL = re.compile(
    r"^(.+?)(?:ni|ga)?\s+(?:eslat(?:ib qo'y\w*|ib qoy|gin|ib qo'yasan)?|esimga sol\w*|yodimga sol\w*|esga sol\w*)[\s.!]*$",
    re.IGNORECASE | re.DOTALL,
)
WHO_WORDS = {"kim", "kimlar", "kimga", "kimni", "kimlarga", "kimlarni", "qaysi mijoz", "qaysi mijozlar"}


ASSIGN_RE = re.compile(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_]{3,31})\b")


def extract_assignees(text: str) -> tuple[str, str | None]:
    users = [u.lower() for u in ASSIGN_RE.findall(text)]
    clean = re.sub(r"\s{2,}", " ", ASSIGN_RE.sub("", text)).strip(" ,")
    clean = re.sub(r"^(?:ga|uchun)\b\s*[:,-]?\s*", "", clean)  # "@ali ga: ..." -> "..."
    return clean, ",".join(dict.fromkeys(f"@{u}" for u in users)) or None


ASSIGN_VERB = r"(?:o'tkaz|ber|biriktir|topshir|yukla|ulab ber)\w*"
ASSIGN_PHRASE_RE = re.compile(rf"((?:@\w+[\s,]*(?:va\s+)?)+)\s*(?:ga|ka)?\s+{ASSIGN_VERB}", re.IGNORECASE)
REMIND_WORD_RE = re.compile(
    r"\b(?:eslatib tur\w*|eslatib qo'y\w*|eslatib bor\w*|eslat\w*|esiga sol\w*|nazorat qil\w*|kuzatib bor\w*)",
    re.IGNORECASE,
)


def split_instructions(text: str, now: datetime) -> tuple[str, str | None, bool, datetime | None]:
    """'Ali, Vali, @sardor ga o'tkaz, ertaga eslat' -> ('Ali, Vali', '@sardor', True, ertaga 9:00).

    Mas'ul va eslatish ko'rsatmasi bor vergul/qator bo'laklari matndan olib tashlanadi.
    """
    assignee, remind, when = None, False, None
    out_lines = []
    for line in text.splitlines() or [""]:
        kept = []
        for part in re.split(r"(?<=[,;])\s*", line):
            core = part.strip(" ,;")
            m = ASSIGN_PHRASE_RE.search(core)
            r = REMIND_WORD_RE.search(core)
            if not m and not r:
                kept.append(part)
                continue
            if m:
                _, assignee = extract_assignees(m.group(1))
                core = (core[: m.start()] + core[m.end():]).strip()
            if r:
                remind = True
                core = REMIND_WORD_RE.sub("", core).strip()
                core = re.sub(r"\b(?:har kuni|har doim|doim|doimo|muntazam|tez-tez|unga|ularga)\b", "", core,
                              flags=re.IGNORECASE).strip()
                w, core = parse_when(core, now)
                when = when or w
            core = re.sub(r"^(?:va|hamda|keyin)\b|\b(?:va|hamda)$", "", core.strip(" ,;")).strip(" ,;")
            if core:  # ko'rsatmadan oldin turgan ism: "Vali @sardor ga ber"
                kept.append(core + ("," if part.rstrip().endswith(",") else ""))
        joined = " ".join(p.strip() for p in kept).strip(" ,;")
        if joined:
            out_lines.append(joined)
    return "\n".join(out_lines), assignee, remind, when


WEEKDAY_ALT = "|".join(WEEKDAYS)
RECUR_RE = re.compile(
    r"^(?:har|xar)\s+(?P<what>kuni|kun|ertalab|kechqurun|ish kun\w*|hafta\w*|"
    r"oy(?:da|ning)?(?:\s+(?P<mday>\d{1,2})\s*-?\s*(?:sana|kun|chi)\w*)?|"
    rf"(?P<wday>{WEEKDAY_ALT})\w*(?:\s+kuni)?)\b[\s,:-]*(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_recurring(text: str, now: datetime) -> Intent | None:
    m = RECUR_RE.match(text)
    if not m:
        return None
    what = m.group("what").lower()
    hour, minute = 9, 0
    if what.startswith(("kun", "ertalab")):
        rule = "daily"
    elif what.startswith("kechqurun"):
        rule, hour = "daily", 19
    elif what.startswith("ish kun"):
        rule = "workdays"
    elif what.startswith("hafta"):
        rule = "weekly:0"
    elif m.group("wday"):
        rule = f"weekly:{WEEKDAYS[m.group('wday').lower()]}"
    else:
        rule = f"monthly:{min(int(m.group('mday') or 1), 28)}"
    rest = m.group("rest")
    lead = re.match(r"^(?:soat\s*)?([01]?\d|2[0-3])\s*(?:da|ga)\b\s*", rest, re.IGNORECASE)  # "har kuni 9 da ..."
    if lead:
        rest = f"soat {lead.group(1)} " + rest[lead.end():]
    when, body = parse_when(rest, now)
    if when:
        hour, minute = when.hour, when.minute
    elif what.startswith("kechqurun"):
        hour = 19
    body, important = extract_important(body)
    body, assignee = extract_assignees(body)
    body, tags = extract_tags(body)
    if not body:
        return None
    return Intent("recurring_add", text=body, rule=rule, when=datetime(2000, 1, 1, hour, minute),
                  category=tags[0] if tags else None, assignee=assignee, important=important)


def _strip_fillers(text: str) -> str:
    text = re.sub(rf"^(?:{FILLER}\b[\s,!.]*)+", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"(?:[\s,]+{FILLER})+[\s!.?]*$", "", text, flags=re.IGNORECASE)
    return text.rstrip(" ?.").strip()


def _numeric(low: str) -> str:
    """Tartib so'zlarini raqamga: 'uchinchisi bo'ldi' -> '3 bo'ldi', 'oxirgisi' -> '0' (eng so'nggi)."""
    low = _ORD_RE.sub(lambda m: str(ORDINALS[m.group(1)]), low)
    return _LAST_RE.sub("0", low)


def _tag(text: str) -> str | None:
    _, tags = extract_tags(text)
    return tags[0] if tags else None


SMALLTALK_RES = [("thanks", THANKS_RE), ("fine", FINE_RE), ("how", HOW_RE), ("ack", ACK_HEAD_RE), ("no", NO_HEAD_RE)]


def _smalltalk_at(low: str) -> tuple[str, int, str | None] | None:
    g = GREET_RE.match(low)
    if g:
        return "greet", g.end(), g.lastgroup
    for kind, rx in SMALLTALK_RES:
        m = rx.match(low)
        if m:
            return kind, m.end(), None
    return None


def _consume_smalltalk(text: str) -> tuple[list[str], str | None, str]:
    """Gap boshidagi salom/rahmat/hol-ahvolni ketma-ket ajratadi.

    "rahmat yaxshi, Assalomu alaykum, nima bor bugunga?" -> (["thanks", "fine", "greet"], "salam", "nima bor bugunga")
    Bo'lak faqat undan keyin tinish belgisi, gap oxiri yoki yana suhbat so'zi kelsa ajratiladi:
    "zo'r ish qildik" o'zgarishsiz qoladi.
    """
    kinds: list[str] = []
    greeting = None
    while text:
        found = _smalltalk_at(text.lower())
        if not found:
            break
        kind, end, g = found
        rest = text[end:]
        nxt = rest.lstrip()
        boundary = not nxt or nxt[0] in ",.!?;" or _smalltalk_at(nxt.lower()) is not None
        if kind != "greet" and not boundary:
            break
        kinds.append(kind)
        greeting = greeting or g
        text = _strip_fillers(rest.strip(" ,.!?;"))
    return kinds, greeting, text


def parse(raw: str, now: datetime | None = None) -> Intent:
    """Gap boshidagi suhbat qismini (salom, rahmat, hol-ahvol) ajratib, qolganini tahlil qiladi.

    "Assalomu alaykum" -> greet; "Assalomu alaykum, ro'yxatni ber" -> list (greeting="salam").
    """
    raw_low = normalize(raw).lower()
    if len(raw_low.split()) <= 7 and not re.search(r"\d", raw_low) and COMPLIMENT_RE.search(raw_low):  # "aqlli bot" — "bot" so'zi kerak
        return Intent("compliment")
    text = _strip_fillers(normalize(raw))
    kinds, greeting, rest = _consume_smalltalk(text)
    if not kinds:
        return _as_question(_parse(text, now), raw)
    if not rest:
        if greeting:
            return Intent("greet", greeting=greeting, smalltalk=kinds)
        if "how" in kinds:
            return Intent("howareyou", smalltalk=kinds)
        if "fine" in kinds:
            return Intent("fine", smalltalk=kinds)
        if "thanks" in kinds:
            return Intent("thanks", smalltalk=kinds)
        return Intent("no" if kinds[-1] == "no" else "ack", smalltalk=kinds)
    intent = _as_question(_parse(rest, now), raw)
    intent.greeting = greeting
    intent.smalltalk = kinds
    return intent


def _as_question(intent: Intent, raw: str) -> Intent:
    """Savol ("ertaga yig'ilish bormi?") zametka bo'lib ketmasin — qidiruv/javob sifatida ko'riladi."""
    if intent.kind != "note" or NOTE_PREFIX.match(normalize(raw).strip()):
        return intent
    if QUESTION_TAIL_RE.search(normalize(raw).strip()):
        return Intent("question", text=intent.text)
    return intent


def _parse(text: str, now: datetime | None = None) -> Intent:
    now = now or datetime.now()
    low = text.lower()

    if not low:
        return Intent("labbay")
    if not re.search(r"[^\W_]", low):  # faqat emoji / belgilar
        if re.fullmatch(r"[\s)]+", low):
            return Intent("laugh")
        if "?" in low:
            return Intent("labbay")
        return Intent("emoji", value=emoji_kind(low))
    if HELP_RE.match(low):
        return Intent("help")
    if ACK_RE.match(low):
        return Intent("ack")
    if NO_RE.match(low):
        return Intent("no")
    if LAUGH_RE.match(low):
        return Intent("laugh")
    if ALIVE_RE.match(low):
        return Intent("alive")
    if TIME_ASK_RE.search(low):
        return Intent("time_now")
    if DATE_ASK_RE.search(low):
        return Intent("date_now")
    short = len(low.split()) <= 7 and not re.search(r"\d", low)  # raqam bor — demak ish haqida
    if short and JOKE_RE.search(low):
        return Intent("joke")
    if short and MOTIV_RE.search(low):
        return Intent("motivation")
    if short and COMPLIMENT_RE.search(low):
        return Intent("compliment")
    if short and INSULT_RE.search(low):
        return Intent("insult")
    if SORRY_RE.match(low):
        return Intent("sorry")
    m = re.match(r"^nechta\s+(?:ochiq\s+|qolgan\s+)?(ish|vazifa|zametka|mijoz|klient)\w*", low)
    if m:
        if m.group(1) in ("mijoz", "klient"):
            return Intent("clients", category=_tag(text), status="open")
        return Intent("list", status="open", category=_tag(text))
    if HOW_RE.match(low):
        return Intent("howareyou")
    if ABOUT_RE.match(low):
        return Intent("about")
    if BYE_RE.match(low):
        return Intent("bye")
    if THANKS_RE.match(low) and len(low.split()) <= 4:
        return Intent("thanks")

    num = _numeric(low)

    # --- eslatma ---
    m = REMIND_HEAD.match(text)
    # "... @vali ga o'tkaz, eslatib tur" — bu mas'ulga eslatish, oddiy eslatma emas
    tail = None if m or ASSIGN_PHRASE_RE.search(text) else REMIND_TAIL.match(text)
    if m or tail:
        when, body = parse_when((m or tail).group(1), now)
        if tail:  # "hisobotni ertaga eslat" -> "hisobot"
            body = re.sub(r"(?<=\w\w\w)(?:ni|ga)$", "", body)
        return Intent("remind", text=body, when=when)
    if re.match(r"^(eslatmalar\w*|budilniklar\w*|qanday eslatmalar|faol eslatmalar)", low):
        return Intent("reminders")

    # --- takroriy vazifalar / sozlamalar ---
    rec = parse_recurring(text, now)
    if rec:
        return rec
    if re.match(r"^(takroriy\w*|takrorlanuvchi\w*|jadval\w*|doimiy vazifa\w*|doimiy ishlar|har kungi ishlar)", low):
        return Intent("recurring_list")
    if re.match(r"^(sozlama\w*|settings|nastroyk\w*|sozla)", low):
        return Intent("settings")

    # --- mijozlar: qo'shish ---
    m = re.match(
        rf"^(?:\+\s*{CLIENT_WORD}|yangi {CLIENT_WORD}\w*|{CLIENT_WORD}\w*\s+{ADD_VERB}|{CLIENT_WORD}\s*:|"
        rf"(?:mijozlar )?bazaga {ADD_VERB}|mijozlar bazasiga {ADD_VERB})"
        r"[\s:,-]*(.+)$",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        m = re.match(
            r"^(.+?)(?:ni|larni)?\s+(?:mijoz\w* (?:qilib|sifatida) )?(?:mijozlarga|mijozlar bazasiga|bazaga|mijoz qilib)\s+"
            r"(?:qo'sh|qosh|kirit|yoz)\w*[\s.!]*$",
            text,
            re.IGNORECASE | re.DOTALL,
        )
    if m and not re.match(rf"^{CLIENT_WORD}\s+#?\d+\s*$", low):
        body, assignee, remind, when = split_instructions(m.group(1).strip(), now)
        return Intent("client_add", text=body, assignee=assignee, remind=remind, when=when)

    # --- mas'ul bo'yicha mijozlar: "@vali mijozlari", "mening ishlanmagan mijozlarim" ---
    m = re.match(
        r"^(?:(@\w+)|mening|o'zimning)\s*(?:ning)?\s*(ishlanmagan\w*|ishlamagan\w*|gaplashilmagan\w*)?\s*"
        r"(?:mijoz|klient)\w*",
        low,
    ) or re.match(r"^(@\w+)\s*(?:ning)?\s*(ishlanmaganlari|ishlamaganlari|gaplashilmaganlari)\b", low)
    if m:
        who = m.group(1) or "me"
        if m.group(2):
            return Intent("not_worked", period=parse_period(low) or "all", category=_tag(text), assignee=who)
        return Intent("clients", category=_tag(text), status="open", assignee=who)

    # --- mijozlarni mas'ulga biriktirish: "Ali ni @vali ga o'tkaz", "#rangor mijozlarini @vali ga ber" ---
    if ASSIGN_PHRASE_RE.search(text):
        body, assignee, remind, when = split_instructions(text, now)
        sel = re.sub(r"(?:larini|larni|lari|ni)$", "", body.strip()).strip()
        has_client_word = re.search(rf"\b{CLIENT_WORD}\w*", sel, re.IGNORECASE)
        sel = re.sub(rf"\b{CLIENT_WORD}\w*\b", "", sel, flags=re.IGNORECASE).strip(" ,")
        selector, names = None, []
        if re.fullmatch(r"(?:barcha|hamma|hammasi|butun)\w*", sel, re.IGNORECASE):
            selector = "all"
        elif re.fullmatch(r"(?:ishlanmagan|ishlamagan|gaplashilmagan)\w*", sel, re.IGNORECASE):
            selector = "not_worked"
        elif TAG_RE.fullmatch(sel.strip()):
            selector = "category"
        elif sel and (has_client_word or not re.fullmatch(r"[#\d\s,va]+", sel)):
            names = split_names(re.sub(r"\b(?:ni|larni)\b", "", sel))
        if assignee and (selector or names):
            return Intent("client_assign", names=names, filter=selector, category=_tag(sel), assignee=assignee,
                          remind=remind, when=when, text=body)

    # --- mijoz arxiv/o'chirish ---
    m = re.match(rf"^{CLIENT_WORD}\s+{NUMS}\s*(?:ni)?\s*(?:{DEL_WORDS}|arxiv\w*)", low)
    if m:
        return Intent("client_archive", numbers=parse_numbers(m.group(1)))

    # --- ishlanmaganlar / ishlanganlar (worked'dan oldin: "kim bilan ishlamadik") ---
    if re.search(
        r"\b(ishlanmagan|ishlamagan|ishlamadik|ishlamadim|gaplashilmagan|gaplashmagan|gaplashmadik|aloqa qilinmagan|"
        r"bog'lanilmagan|bog'lanmagan|bog'lanmadik|qo'ng'iroq qilinmagan|qo'ng'iroq qilmagan|qo'ng'iroq qilmadik|"
        r"chiqilmagan|tegilmagan|e'tiborsiz|unutilgan mijoz|qolgan mijoz|kimlar qoldi|kim qoldi|kimlar qolgan|"
        r"kimga qo'ng'iroq qilish kerak|kim bilan gaplashish kerak|kimlar bilan ishlash kerak|kim bilan ishlash kerak)",
        low,
    ):
        return Intent("not_worked", period=parse_period(low) or "all", category=_tag(text))
    if re.search(
        r"\b(ishlanganlar|ishlangan mijoz|ishlagan mijoz|kim bilan ishla|kimlar bilan ishla|gaplashilgan|"
        r"gaplashganlar|kimlar bilan gaplash|kim bilan gaplash|qo'ng'iroq qilinganlar|bog'lanilganlar|faol mijoz)",
        low,
    ):
        return Intent("worked_list", period=parse_period(low) or "week", category=_tag(text))

    # --- mijoz bilan ishlandi ---
    m = (
        re.match(rf"^(.+?)(?:\s+bilan|\s*ga|\s*ni)\s+{WORKED_WORDS}\b[\s,:.-]*(.*)$", text, re.IGNORECASE | re.DOTALL)
        or re.match(rf"^{WORKED_WORDS}\s+(.+?)\s+bilan\b[\s,:.-]*(.*)$", text, re.IGNORECASE | re.DOTALL)
        or re.match(
            r"^(.+?)\s*[:\-—]\s*(?:ishlandi|gaplashildi|bog'lanildi|qo'ng'iroq qilindi)\b[\s,:.-]*(.*)$",
            text, re.IGNORECASE | re.DOTALL,
        )
        or re.match(rf"^{WORKED_WORDS}\s*[:\-]\s*(.+?)()$", text, re.IGNORECASE | re.DOTALL)
    )
    if m:
        names_part = re.sub(rf"^{CLIENT_WORD}\s+", "", m.group(1).strip(), flags=re.IGNORECASE)
        if names_part.lower() in WHO_WORDS:
            return Intent("worked_list", period=parse_period(low) or "week", category=_tag(text))
        return Intent("worked", names=split_names(names_part), text=m.group(2).strip())

    # --- mijozni tahrirlash ---
    cu = _client_update(text)
    if cu:
        return cu

    # --- mijozlar ro'yxati / kartochka ---
    if re.match(rf"^(?:barcha |hamma |bazadagi |butun )?(?:{CLIENTS_PLURAL}|mijoz bazasi|mijozlar bazasi)", low):
        return Intent("clients", category=_tag(text), status="all" if "arxiv" in low else "open")
    m = re.match(r"^(?:mijoz|klient|client|karta|kartochka)\s+(#?\d+|.+)$", text, re.IGNORECASE)
    if m and not re.match(r"^\w+\s+(ro'yxat|royxat|#[^\d])", low):
        return Intent("client_card", names=[m.group(1).lstrip("#").strip()])
    m = re.match(r"^(.+?)\s+(?:haqida|to'g'risida|haqidagi)(?: ma'lumot\w*)?(?: ber\w*| ko'rsat\w*| nima bilasan)?$", text, re.IGNORECASE)
    if m:
        return Intent("client_card", names=[m.group(1).strip()])

    # --- done / undo / delete / edit (raqam bilan) ---
    m = re.match(
        rf"^{NUMS}\s*(?:-?(?:chi|nchi|raqam\w*))?\s*(?:zametka\w*|vazifa\w*|ish\w*)?\s*(?:ni|ham|ni ham)?\s*{DONE_WORDS}[\s.!]*$", num
    ) or re.match(rf"^{DONE_WORDS}\s*[:\-]?\s*{NUMS}\s*$", num)
    if not m:  # "bugun kayfiyat zo'r, 2 bo'ldi"
        m = re.search(rf"(?:[,;.!]|\s(?:lekin|ammo|biroq|va|hamda))\s*{NUMS}\s*(?:ni|ham|ni ham)?\s*{DONE_WORDS}[\s.!]*$", num)
    if m:
        return Intent("done", numbers=parse_numbers(m.group(1)))

    m = re.match(rf"^{NUMS}\s*(?:ni|ni ham)?\s*{UNDO_WORDS}", num) or re.match(rf"^{UNDO_WORDS}\s*[:\-]?\s*{NUMS}\s*$", num)
    if m:
        return Intent("undo", numbers=parse_numbers(m.group(1)))

    m = re.match(rf"^{NUMS}\s*(?:ni|ni ham)?\s*{DEL_WORDS}", num) or re.match(rf"^{DEL_WORDS}\s*[:\-]?\s*{NUMS}\s*$", num)
    if m:
        return Intent("delete", numbers=parse_numbers(m.group(1)))

    m = re.match(rf"^#?(\d+)\s*(?:ni)?\s*{EDIT_WORDS}\s*[:\-]?\s*(.+)$", _numeric(text), re.IGNORECASE | re.DOTALL)
    if m:
        return Intent("edit", numbers=[int(m.group(1))], text=m.group(2).strip())

    # --- zametkani o'zgartirish: kategoriya / muhim / mas'ul / muddat ---
    nu = _note_update(text, num, now)
    if nu:
        return nu

    # --- raqamsiz: "bo'ldi", "shuni o'chir" (reply qilingan xabardan yoki tanlov orqali) ---
    bare = r"^(?:bu|shu|buni|shuni|u|uni|ana|hammasi|barchasi)?\s*(?:ham)?\s*"
    if re.match(bare + DONE_WORDS + r"[\s.!]*$", low):
        return Intent("done")
    if re.match(bare + UNDO_WORDS + r"[\s.!]*$", low):
        return Intent("undo")
    if re.match(bare + DEL_WORDS + r"[\s.!]*$", low):
        return Intent("delete")

    # --- qidirish ---
    m = re.match(r"^(?:qidir\w*|izla\w*|top(?:ib ber)?|search|find|qayerda|naydi)\b[\s:,-]*(.+)$", text, re.IGNORECASE)
    if not m:
        m = re.match(r"^(.+?)(?:ni)?\s+(?:qidir\w*|izla\w*|topib ber\w*|top)[\s.!]*$", text, re.IGNORECASE)
    if m:
        return Intent("search", text=m.group(1).strip())

    # --- statistika / kundalik / kategoriyalar / eksport ---
    stats_words = r"(?:statistika\w*|stat|stats|hisobot\w*|natija\w*|progress|ko'rsatkich\w*|otchet\w*|otchyot\w*|analitika|reyting)"
    stats_tail = r"(?:\s+(?:ber\w*|ko'rsat\w*|chiqar\w*|qani|bugun\w*|kecha\w*|hafta\w*|shu|bu|oy\w*|\d+|kun\w*|haftalik|oylik|umumiy))*"
    if re.fullmatch(rf"(?:haftalik |oylik |bugungi |umumiy )?{stats_words}{stats_tail}", low) or re.search(
        r"\b(qalay ketyapmiz|qanday ketyapmiz|ishlar qanday ketyapti|kim eng ko'p)", low
    ):
        return Intent("stats", period=parse_period(low) or "all")
    if re.search(
        r"\b(kundalik\w*|nima qildik|nima qildim|nimalar qildik|nimalar qildim|xulosa\w*|sarhisob\w*|kun yakuni|"
        r"nima bo'ldi bugun|bugun nima bo'ldi|kecha nima bo'ldi|hafta qanday o'tdi|kun qanday o'tdi|dnevnik|itog\w*)",
        low,
    ):
        return Intent("diary", period=parse_period(low) or "today")
    if re.match(r"^(kategoriya\w*|teglar\w*|teg|bo'limlar\w*|toifalar\w*|categories|rubrika\w*|papkalar\w*)", low):
        return Intent("categories")
    if re.match(r"^(eksport\w*|export|yuklab ber\w*|excel\w*|csv|faylga|fayl qilib ber|skachat|vigruzka)", low):
        return Intent("export")

    if re.match(
        r"^(?:ertalabki reja|kun rejasi|bugungi reja|bugungi plan|agenda|reja|rejalar|bugun nima qilamiz|"
        r"nima bor bugun\w*|bugun\w* nima bor|bugun\w* nima ish\w* bor|nima ishlar bor bugun\w*|nima bor$|"
        r"nima yangilik\w*|bugun nima qilishimiz kerak|bugun nima qilish kerak|bugunga nima)",
        low,
    ):
        return Intent("agenda")

    # --- mas'ul bo'yicha ro'yxat: "mening ishlarim", "@ali ishlari" ---
    if re.match(r"^(?:mening|meni|o'zimning|menga tegishli|menga berilgan)\b\s*(?:ish|vazifa|zametka|topshiriq)?\w*", low):
        return Intent("list", status="done" if re.search(r"bajarilgan|qilingan", low) else "open", assignee="me")
    m = re.match(r"^@(\w+)\s*(?:ning)?\s*(?:ishlari|vazifalari|zametkalari|topshiriqlari|nima qilyapti|nimalar qilyapti|ro'yxati)", low)
    if m:
        return Intent("list", status="open", assignee=f"@{m.group(1)}")

    # --- zametkalar ro'yxati ---
    stripped = TAG_RE.sub("", low).strip()
    short_show = len(stripped.split()) <= 6 and re.search(LIST_NOUN, stripped) and re.search(SHOW_VERB, stripped)
    if re.match(LIST_KW, stripped) or short_show or (stripped == "" and TAG_RE.search(low)):
        status = "open"
        if re.search(r"(bajarilgan|bo'lgan|tugagan|done|qilingan|yopilgan|bitgan)", stripped) and not re.search(
            r"(bajarilmagan|bo'lmagan|qilinmagan)", stripped
        ):
            status = "done"
        elif re.search(r"\b(hammasi|barchasi|hamma|barcha)\b", stripped):
            status = "all"
        flt = None
        if re.search(r"\bbugun", stripped):
            flt = "today"
        elif re.search(r"\bertang|\bertaga", stripped):
            flt = "tomorrow"
        elif re.search(r"\b(muhim|srochno|shoshilinch)", stripped):
            flt = "important"
        elif re.search(r"\b(muddati o'tgan|kechikkan|o'tib ketgan)", stripped):
            flt = "overdue"
        return Intent("list", status=status, category=_tag(text), filter=flt)

    # --- matn bo'yicha done: "tovar sanash bo'ldi", "hisobotni tugatdim" ---
    m = re.match(rf"^(.+?)\s+(?:ham\s+)?{DONE_WORDS}[\s.!]*$", text, re.IGNORECASE)
    if m and len(m.group(1)) >= 3:
        return Intent("done_text", text=re.sub(r"(?:ni|ning)$", "", m.group(1).strip()))

    # --- default: yangi zametka ---
    body = NOTE_SUFFIX.sub("", NOTE_PREFIX.sub("", text)).strip()
    body, important = extract_important(body)
    body, assignee = extract_assignees(body)
    body, tags = extract_tags(body)
    when, _ = parse_when(body, now)
    return Intent("note", text=body, category=tags[0] if tags else None, important=important, when=when,
                  assignee=assignee)


MOVE_VERB = r"(?:o'tkaz|ko'chir|qo'y|joyla|qo'sh)\w*"


def _note_update(text: str, num: str, now: datetime) -> Intent | None:
    m = re.match(rf"^#?(\d+)\s*(?:-?ni)?\s*#([^\W\d][\w\-]*)\s*(?:ga|ka)?\s*(?:{MOVE_VERB})?$", num)
    if m:
        return Intent("note_update", numbers=[int(m.group(1))], field="category", value=m.group(2))
    m = re.match(r"^#?(\d+)\s*(?:ni)?\s*(muhim emas|oddiy\w*|muhim|shoshilinch|srochno)\s*(?:qil\w*|deb belgila\w*)?$", num)
    if m:
        value = not m.group(2).startswith(("muhim emas", "oddiy"))
        return Intent("note_update", numbers=[int(m.group(1))], field="important", value=value)
    m = re.match(
        r"^#?(\d+)\s*(?:ni)?\s*((?:@\w+[\s,]*(?:va\s+)?)+?)\s*(?:ga)?\s*(?:ber\w*|topshir\w*|biriktir\w*|yukla\w*|o'tkaz\w*)?$",
        num,
    )
    if m:
        _, assignee = extract_assignees(m.group(2))
        return Intent("note_update", numbers=[int(m.group(1))], field="assignee", value=assignee)
    m = re.match(r"^#?(\d+)\s*(?:ni|ning)?\s*(?:muddat\w*|deadline|srok\w*)\s*[:\-]?\s*(.+)$", num) or re.match(
        r"^#?(\d+)\s*(?:ni)?\s+(.+?)(?:\s+(?:ga|gacha))?\s+(?:sur\w*|o'tkaz\w*|ko'chir\w*|qoldir\w*|belgila\w*)$", num
    )
    if m:
        when, _ = parse_when(m.group(2), now)
        if when:
            return Intent("note_update", numbers=[int(m.group(1))], field="due", when=when)
    return None


def _client_update(text: str) -> Intent | None:
    prefix = rf"^(?:{CLIENT_WORD}\s+)?"
    m = re.match(prefix + r"(.+?)(?:ning)?\s+(?:telefon\w*|nomer\w*|raqami|tel)\s*[:\-]?\s*(\+?\d[\d\s\-()]{6,}\d)$",
                 text, re.IGNORECASE)
    if m:
        return Intent("client_update", names=[m.group(1).strip()], field="phone",
                      value=re.sub(r"[\s\-()]", "", m.group(2)))
    m = re.match(prefix + r"(.+?)(?:ga)?\s+(?:izoh\w*|komment\w*)\s*[:\-]\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
    if m:
        return Intent("client_update", names=[m.group(1).strip()], field="comment", value=m.group(2).strip())
    m = re.match(prefix + rf"(.+?)\s*(?:ni)?\s+#([^\W\d][\w\-]*)\s*(?:ga|ka)?\s+{MOVE_VERB}$", text, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        has_prefix = re.match(rf"^{CLIENT_WORD}\s+", text, re.IGNORECASE)
        if not name.lstrip("#").isdigit() or has_prefix:
            return Intent("client_update", names=[name.lstrip("#")], field="category", value=m.group(2).lower())
    return None
