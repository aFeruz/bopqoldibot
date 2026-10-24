"""Botning o'z xabariga qilingan reply'ni kontekst bilan tushunish.

Bot xabarida bitta zametka (📌 #12) yoki bitta mijoz (👤 #5) bo'lsa, raqamsiz buyruq shu obyektga
tegishli deb olinadi: zametka kartochkasiga "muhim" — "#12 muhim", mijoz kartochkasiga
"gaplashdim, narx kelishildi" — "#5 bilan gaplashdim, narx kelishildi".
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.parser import Intent, parse, parse_when

NOTE_MARK_RE = re.compile(r"(?:📌|✅|🔄|❗|▫️|✏️|🔥)\s*(?:<[^>]+>)*#(\d+)")
CLIENT_MARK_RE = re.compile(r"👤\s*(?:<[^>]+>)*#(\d+)")
REMINDER_RE = re.compile(r"^(?:⏰|🔔).*\n\n🔔 (.+?)(?:\n|$)", re.DOTALL)

NOTE_KINDS = {"done", "undo", "delete", "edit", "note_update"}
CLIENT_KINDS = {"worked", "client_update", "client_assign", "client_archive"}
SNOOZE_RE = re.compile(r"\b(keyinroq|keyin|yana eslat\w*|qayta eslat\w*|eslat\w*|kechiktir\w*|sur\w*)\b", re.IGNORECASE)
DONE_ACK_RE = re.compile(
    r"^(?:bo'ldi|boldi|bajarildi|bajardim|qildim|qildik|tayyor|ok|okey|xo'p|mayli|done|bitdi|tamom|👍|✅)\b",
    re.IGNORECASE,
)


@dataclass
class ReplyContext:
    kind: str  # note / client / reminder
    number: int | None = None
    text: str = ""


def reply_context(bot_text: str) -> ReplyContext | None:
    """Bot xabaridan kontekst: aniq bitta zametka yoki mijoz, yoki eslatma."""
    if not bot_text:
        return None
    r = REMINDER_RE.match(bot_text)
    if r:
        return ReplyContext("reminder", text=r.group(1).strip())
    clients = set(CLIENT_MARK_RE.findall(bot_text))
    notes = set(NOTE_MARK_RE.findall(bot_text))
    if len(clients) == 1 and not notes:
        return ReplyContext("client", int(clients.pop()))
    if len(notes) == 1 and not clients:
        return ReplyContext("note", int(notes.pop()))
    return None


def apply_context(text: str, intent: Intent, ctx: ReplyContext, now: datetime) -> Intent:
    """Raqamsiz buyruqni kontekstdagi obyektga bog'laydi. Mos kelmasa — asl intent."""
    if intent.numbers or intent.names:
        return intent
    if ctx.kind == "note":
        for candidate in (f"{ctx.number} {text}", f"{ctx.number} ni {text}"):
            i = parse(candidate, now)
            if i.kind in NOTE_KINDS and ctx.number in i.numbers:
                i.smalltalk = intent.smalltalk
                return i
    elif ctx.kind == "client":
        for candidate in (f"mijoz {ctx.number} bilan {text}", f"mijoz {ctx.number} {text}", f"mijoz {ctx.number} ni {text}"):
            i = parse(candidate, now)
            if i.kind in CLIENT_KINDS and (str(ctx.number) in i.names or ctx.number in i.numbers):
                return i
    elif ctx.kind == "reminder":
        if DONE_ACK_RE.match(text.strip()):
            return Intent("reminder_done", text=ctx.text)
        when, _ = parse_when(text, now)
        if when or SNOOZE_RE.search(text):
            return Intent("remind", text=ctx.text, when=when or now + timedelta(minutes=30))
    return intent
