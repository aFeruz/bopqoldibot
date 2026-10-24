from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup

from bot.models import Client, Note


def _rows(buttons: list[B], per_row: int) -> list[list[B]]:
    return [buttons[i: i + per_row] for i in range(0, len(buttons), per_row)]


REFRESH = "🔄"


def _pager(prefix: str, offset: int, limit: int, total: int, refresh: bool = False) -> list[B]:
    row = []
    if offset > 0:
        row.append(B(text="⬅️", callback_data=f"{prefix}:{max(0, offset - limit)}"))
    if refresh:
        # joriy ro'yxat kaliti/sahifasi shu tugmada saqlanadi — boshqa tugmalar ro'yxatni joyida yangilaydi
        row.append(B(text=REFRESH, callback_data=f"{prefix}:{offset}"))
    if offset + limit < total:
        row.append(B(text="➡️", callback_data=f"{prefix}:{offset + limit}"))
    return row


def note_saved(n: Note) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        B(text="✅ Bajarildi", callback_data=f"nd:{n.number}"),
        B(text="↩️ Bekor qilish", callback_data=f"nx:{n.number}"),
    ]])


def note_done(n: Note) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="↩️ Qaytarish", callback_data=f"nu:{n.number}")]])


def notes_list(notes: list[Note], list_key: str, offset: int, limit: int, total: int) -> InlineKeyboardMarkup | None:
    btns = [
        B(text=f"↩️{n.number}", callback_data=f"nu:{n.number}") if n.status == "done"
        else B(text=f"✅{n.number}", callback_data=f"nd:{n.number}")
        for n in notes
    ]
    rows = _rows(btns, 5)
    if notes or offset:
        rows.append(_pager(f"nl:{list_key}", offset, limit, total, refresh=True))
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


CHOOSE_ICONS = {"nd": "✅", "nu": "↩️", "nx": "🗑"}


def choose_notes(notes: list[Note], action: str = "nd") -> InlineKeyboardMarkup:
    icon = CHOOSE_ICONS[action]
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text=f"{icon} #{n.number} {n.text[:40]}", callback_data=f"{action}:{n.number}")] for n in notes
    ])


def choose_clients(clients: list[Client], token: str, allow_new: str | None = None) -> InlineKeyboardMarkup:
    rows = [[B(text=f"👤 #{c.number} {c.name[:40]}", callback_data=f"cw:{token}:{c.number}")] for c in clients]
    if allow_new:
        rows.append([B(text=f"➕ Yangi mijoz: {allow_new[:30]}", callback_data=f"ca:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def activity(items, list_key: str, offset: int, limit: int, total: int, worked: bool) -> InlineKeyboardMarkup | None:
    rows = []
    if not worked:
        btns = [B(text=f"✔️ {a.client.name[:18]}", callback_data=f"cq:{a.client.number}") for a in items]
        rows = _rows(btns, 2)
    if items or offset:
        rows.append(_pager(f"al:{list_key}", offset, limit, total, refresh=not worked))
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def clients_list(list_key: str, offset: int, limit: int, total: int) -> InlineKeyboardMarkup | None:
    pager = _pager(f"cl:{list_key}", offset, limit, total)
    return InlineKeyboardMarkup(inline_keyboard=[pager]) if pager else None


def client_card(c: Client) -> InlineKeyboardMarkup:
    if c.archived:
        return InlineKeyboardMarkup(inline_keyboard=[[B(text="♻️ Arxivdan chiqarish", callback_data=f"cr:{c.number}")]])
    return InlineKeyboardMarkup(inline_keyboard=[[
        B(text="✔️ Ishladim", callback_data=f"cq:{c.number}"),
        B(text="🗄 Arxivlash", callback_data=f"cz:{c.number}"),
    ]])


def reminders(items) -> InlineKeyboardMarkup | None:
    rows = [[B(text=f"❌ {r.id}. {r.text[:30]}", callback_data=f"rx:{r.id}")] for r in items[:10]]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def settings(cs) -> InlineKeyboardMarkup:
    from bot.texts import SETTINGS_LABELS
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text=f"{'✅' if getattr(cs, f) else '⬜️'} {label}", callback_data=f"st:{f}")]
        for f, label in SETTINGS_LABELS.items()
    ])


def recurring(items) -> InlineKeyboardMarkup | None:
    rows = [[B(text=f"❌ {r.id}. {r.text[:30]}", callback_data=f"rr:{r.id}")] for r in items[:15]]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def due_alert(n: Note) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="✅ Bajarildi", callback_data=f"nd:{n.number}")],
        [
            B(text="⏰ +1 soat", callback_data=f"nz:{n.number}:60"),
            B(text="📅 Ertaga", callback_data=f"nz:{n.number}:tomorrow"),
        ],
    ])


def import_offer(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        B(text="📥 Mijozlarga import qilish", callback_data=f"im:{token}"),
        B(text="✖️ Kerak emas", callback_data=f"ix:{token}"),
    ]])


def import_done(batch: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="↩️ Importni bekor qilish", callback_data=f"iu:{batch}")]])


def assignee_digest(clients) -> InlineKeyboardMarkup | None:
    btns = [B(text=f"✔️ {c.name[:18]}", callback_data=f"cq:{c.number}") for c in clients[:10]]
    return InlineKeyboardMarkup(inline_keyboard=_rows(btns, 2)) if btns else None
