"""Excel/CSV fayldan mijozlarni o'qish.

Ustunlar sarlavhasi bo'yicha aniqlanadi (o'zbek, rus, ingliz; Meta Lead Ads eksporti ham).
Sof funksiyalar: bazaga bog'liq emas.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bot.parser import ClientInput, normalize

MAX_ROWS = 5000

# maydon -> sarlavhada uchraydigan kalit so'zlar (normalize + kichik harf qilingan holda)
COLUMN_KEYS: dict[str, list[str]] = {
    "name": ["polnoe_imya", "polnoe imya", "full_name", "full name", "fio", "f.i.o", "ism", "imya", "name",
             "mijoz", "klient", "client", "kontakt", "contact", "familiya"],
    "phone": ["telefon", "phone", "nomer", "tel", "raqam", "mobile", "mobil"],
    "category": ["kategoriya", "category", "toifa", "segment", "guruh", "teg", "tag"],
    "comment": ["izoh", "comment", "note", "primechanie", "kommentariy", "eslatma", "zametka"],
    "status": ["lead_status", "status", "holat", "etap", "stage"],
    "source": ["platform", "platforma", "manba", "source", "istochnik"],
    "campaign": ["ad_name", "campaign_name", "kampaniya", "reklama"],
    "created": ["created_time", "created", "sana", "date", "data", "vaqt"],
    "assignee": ["masul", "mas'ul", "menejer", "manager", "otvetstvenniy", "responsible", "assignee"],
}
# "status" ustunidagi bu qiymatlar izohga yozilmaydi
DEFAULT_STATUSES = {"created", "create", "new", "yangi", "novyy", "novyi", ".", "-", ""}
SKIP_ROW_MARKERS = ("<test lead", "test lead:", "dummy data")


@dataclass
class ImportReport:
    rows: int = 0
    skipped_test: int = 0
    skipped_empty: int = 0
    duplicates_in_file: int = 0
    columns: dict[str, str] = field(default_factory=dict)  # maydon -> sarlavha


def _norm_header(h) -> str:
    return normalize(str(h or "")).lower().strip()


def _detect_columns(header: list) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, raw in enumerate(header):
        h = _norm_header(raw)
        if not h:
            continue
        if h.endswith("?") or "?_" in h or "?" in h:
            found.setdefault("interest", idx)  # forma savoli: "nimani ijaraga berasiz?"
            continue
        if h in ("id", "ad_id", "adset_id", "campaign_id", "form_id", "form_name", "is_organic", "adset_name"):
            continue
        tokens = [t for t in re.split(r"[\s_\-./]+", h) if t]
        for fld, keys in COLUMN_KEYS.items():
            if fld in found:
                continue
            # kalit so'z sarlavhaning o'zi yoki birinchi so'zi bo'lishi kerak ("ad_name" ism emas);
            # telefon uchun istalgan so'z ("nomer_telefona", "mobil telefon")
            if any(k == h or tokens[:1] == [k] or (fld == "phone" and k in tokens) for k in keys):
                found[fld] = idx
                break
    return found


def clean_phone(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    s = re.sub(r"^[a-z]+:", "", s, flags=re.IGNORECASE)  # Meta: "p:+998..."
    if isinstance(value, float) and value.is_integer():
        s = str(int(value))
    digits = re.sub(r"\D", "", s)
    if len(digits) < 7:
        return None
    if len(digits) == 9:  # 901234567 -> +998901234567
        return "+998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return ("+" if s.lstrip().startswith("+") else "") + digits


def clean_name(value, phone: str | None) -> str:
    name = re.sub(r"\s{2,}", " ", str(value or "").strip())
    # "Shuxrat 974066030", "Mamurjon 5323" — ism ichidagi raqamlar
    if re.search(r"[^\W\d_]", name):
        name = re.sub(r"[\s_]*\+?\d[\d\s\-]{2,}\s*$", "", name).strip(" _-")
    return name or (phone or "")


def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _cell(row: list, idx: int | None):
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    return v.strip() if isinstance(v, str) else v


def _read_rows(data: bytes, filename: str) -> list[list]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        rows = []
        for i, r in enumerate(wb.active.iter_rows(values_only=True)):
            if i > MAX_ROWS:
                break
            rows.append(list(r))
        wb.close()
        return rows
    if name.endswith((".csv", ".txt", ".tsv")):
        for enc in ("utf-8-sig", "cp1251", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [list(r) for r in csv.reader(io.StringIO(text), dialect)][: MAX_ROWS + 1]
    raise ValueError("format")


def parse_table(data: bytes, filename: str) -> tuple[list[ClientInput], ImportReport]:
    rows = [r for r in _read_rows(data, filename) if any(v not in (None, "") for v in r)]
    report = ImportReport()
    if not rows:
        return [], report

    # sarlavha qatori: dastlabki 10 qatordan eng ko'p ustun tanilgani
    header_idx, cols = 0, {}
    for i, r in enumerate(rows[:10]):
        c = _detect_columns(r)
        if len(c) > len(cols):
            header_idx, cols = i, c
    if "name" not in cols and "phone" not in cols:
        # sarlavhasiz jadval: 1-ustun ism, telefonga o'xshagan ustun — telefon
        header_idx, cols = -1, {"name": 0}
        for idx, v in enumerate(rows[0]):
            if clean_phone(v) and idx != 0:
                cols["phone"] = idx
                break
    header = rows[header_idx] if header_idx >= 0 else []
    report.columns = {f: str(header[i]) if header_idx >= 0 and i < len(header) else f"{i + 1}-ustun"
                      for f, i in cols.items()}
    # Excel qatorlarni eng keng qatorgacha None bilan to'ldiradi — sarlavha oxirgi to'ldirilgan katakkacha
    width = max((i + 1 for i, v in enumerate(header) if v not in (None, "")), default=0)

    items: list[ClientInput] = []
    seen: set[str] = set()
    for row in rows[header_idx + 1:]:
        report.rows += 1
        if any(isinstance(v, str) and v.lower().startswith(SKIP_ROW_MARKERS) for v in row):
            report.skipped_test += 1
            continue
        phone = clean_phone(_cell(row, cols.get("phone")))
        name = clean_name(_cell(row, cols.get("name")), phone)
        if not name:
            report.skipped_empty += 1
            continue
        key = phone or name.lower()
        if key in seen:
            report.duplicates_in_file += 1
            continue
        seen.add(key)

        parts = []
        interest = _cell(row, cols.get("interest"))
        if interest:
            parts.append(f"Qiziqish: {interest}")
        status = _cell(row, cols.get("status"))
        if status not in (None, "") and str(status).strip().lower() not in DEFAULT_STATUSES:
            parts.append(f"Holat: {status}")
        comment = _cell(row, cols.get("comment"))
        if comment:
            parts.append(str(comment))
        # sarlavhadan tashqaridagi ustunlar (qo'lda yozilgan izohlar)
        extra = [str(v).strip() for v in row[width:] if v not in (None, "")] if header_idx >= 0 else []
        parts += [x for x in extra if x]
        src = [str(v) for v in (_cell(row, cols.get("source")), _cell(row, cols.get("campaign"))) if v]
        if src:
            parts.append("Manba: " + ", ".join(src))

        category = _cell(row, cols.get("category"))
        assignee = _cell(row, cols.get("assignee"))
        if assignee:
            assignee = "@" + str(assignee).lstrip("@").lower() if re.fullmatch(r"@?\w{4,32}", str(assignee)) else None
        items.append(ClientInput(
            name=name, phone=phone, comment=" · ".join(parts) or None,
            category=re.sub(r"\s+", "_", str(category).strip().lower()) if category else None,
            assignee=assignee, created_at=_parse_dt(_cell(row, cols.get("created"))),
        ))
    return items, report
