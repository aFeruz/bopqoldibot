"""Matn, havola, kontakt, lokatsiya va so'rovnomalarni zametka sifatida eslab qolish.

Media (rasm, ovoz, fayl) files.py da; bu yerda — fayli yo'q xabarlar.
"""

import re

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.handlers.actions import Reply
from bot.parser import TAG_RE, parse_note, parse_when
from bot.phrases import say
from bot.services import notes as notes_svc
from bot.services.common import local_now

SAVE_RE = re.compile(
    r"\b(?:eslab qol|saqla|saqlab|esda tut|yozib qo'y|yozib qoy|yozib ol|zametka|eslatma qil|qayd et)\w*", re.IGNORECASE
)


def message_content(m: Message | None) -> str | None:
    """Xabarning saqlanadigan matni: matn/izoh, kontakt, lokatsiya yoki so'rovnoma."""
    if m is None:
        return None
    if m.text or m.caption:
        return (m.text or m.caption).strip()
    if m.contact:
        c = m.contact
        name = " ".join(x for x in (c.first_name, c.last_name) if x)
        return f"📇 {name} {c.phone_number or ''}".strip()
    if m.venue:
        v, loc = m.venue, m.venue.location
        return f"📍 {v.title}, {v.address} — https://maps.google.com/?q={loc.latitude},{loc.longitude}"
    if m.location:
        return f"📍 https://maps.google.com/?q={m.location.latitude},{m.location.longitude}"
    if m.poll:
        return f"📊 {m.poll.question}: " + " / ".join(o.text for o in m.poll.options)
    return None


def origin_name(m: Message | None) -> str | None:
    """Xabar muallifi: forward qilingan bo'lsa — asl yuboruvchi."""
    if m is None:
        return None
    o = m.forward_origin
    if o is not None:
        user = getattr(o, "sender_user", None)
        if user:
            return user.full_name
        chat = getattr(o, "sender_chat", None) or getattr(o, "chat", None)
        if chat:
            return chat.title or chat.full_name
        return getattr(o, "sender_user_name", None)
    return m.from_user.full_name if m.from_user and not m.from_user.is_bot else None


def is_save_instruction(text: str) -> bool:
    """Reply'dagi matn faqat ko'rsatma bo'lsa: "eslab qol #shartnoma", "#narx", "@vali", "ertaga muhim"."""
    if not text or SAVE_RE.search(text):
        return True
    rest = parse_note(text, local_now()).text
    _, rest = parse_when(rest, local_now())
    return not rest.strip(" ,.!")


async def save_text_note(
    session: AsyncSession, chat_id: int, content: str, instruction: str, author_id: int | None, who: str,
    user: str | None, source: str | None = None,
) -> Reply:
    """Boshqa xabar matnini zametka qiladi; kategoriya/mas'ul/muddat/qo'shimcha izoh — ko'rsatmadan."""
    intent = parse_note(instruction or "", local_now())
    body = content
    extra = re.sub(r"^[,.\s]+", "", intent.text or "")
    _, without_time = parse_when(extra, local_now())
    if not without_time.strip(" ,.!"):  # "@vali ertaga" — faqat muddat, izoh emas
        extra = ""
    if extra:
        body = f"{content}\n💬 {extra}"
    category = intent.category
    if not category:
        tag = TAG_RE.search(content)
        category = tag.group(1).lower() if tag else None
    note = await notes_svc.add_note(session, chat_id, body, author_id, who, category, intent.important,
                                    intent.when, intent.assignee)
    if source and source != who:
        head = say("text_saved", user, src=texts.e(source))
    else:
        head = say("note_saved", user)
    return Reply(texts.note_saved(note, head), kb.note_saved(note))
