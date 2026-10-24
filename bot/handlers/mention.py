import re

from aiogram import F, Router
from aiogram.enums import ChatType, MessageEntityType
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.actions import execute, send
from bot.parser import Intent, parse
from bot.services.common import local_now

router = Router()

# "@bot mijozlar qo'sh" ni ro'yxatli xabarga reply qilib yozish mumkin — matn reply'dan olinadi.
_PREFIX_ONLY = re.compile(r"^(?:mijoz\w*|klient\w*)\s+(?:qo'sh|qosh|kirit)\w*\s*:?$|^yangi mijoz\w*\s*:?$", re.IGNORECASE)


def strip_mention(msg: Message, bot_username: str, bot_id: int) -> tuple[str, bool]:
    text = msg.text or msg.caption or ""
    entities = msg.entities or msg.caption_entities or []
    mentioned = False
    # entity offset'lari UTF-16 da
    raw = text.encode("utf-16-le")
    cut = []
    for ent in entities:
        part = raw[ent.offset * 2: (ent.offset + ent.length) * 2].decode("utf-16-le")
        if ent.type == MessageEntityType.MENTION and part.lower() == f"@{bot_username.lower()}":
            cut.append((ent.offset, ent.length))
        elif ent.type == MessageEntityType.TEXT_MENTION and ent.user and ent.user.id == bot_id:
            cut.append((ent.offset, ent.length))
    for off, ln in sorted(cut, reverse=True):
        raw = raw[: off * 2] + raw[(off + ln) * 2:]
        mentioned = True
    return raw.decode("utf-16-le").strip(" ,:\n"), mentioned


@router.message(F.text | F.caption)
async def on_message(msg: Message, session: AsyncSession, bot_username: str, bot_id: int) -> None:
    if (msg.text or "").startswith("/"):
        return
    text, mentioned = strip_mention(msg, bot_username, bot_id)
    private = msg.chat.type == ChatType.PRIVATE
    reply = msg.reply_to_message
    reply_to_bot = bool(reply and reply.from_user and reply.from_user.id == bot_id)

    if not (private or mentioned or reply_to_bot):
        return

    if reply and reply.document and (mentioned or private):
        from bot.handlers.files import import_from_reply  # files.py mention.py ni import qiladi
        if await import_from_reply(msg, session, msg.bot, text):
            return

    reply_text = (reply.text or reply.caption or "") if reply and not reply_to_bot else ""
    if not text and reply_text:
        # reply + @bot — o'sha xabarni zametka qilamiz
        intent = parse("zametka: " + reply_text, local_now())
        if intent.kind != "note":
            intent = Intent("note", text=reply_text)
    else:
        if reply_text and _PREFIX_ONLY.match(text):
            text = text.rstrip(":") + ":\n" + reply_text
        intent = parse(text, local_now())

    # botning xabariga reply qilib "bo'ldi" / "o'chir" — o'sha xabardagi #raqam olinadi
    if intent.kind in ("done", "undo", "delete") and not intent.numbers and reply:
        nums = re.findall(r"#(\d+)", reply.text or reply.caption or "")
        if nums:
            intent.numbers = [int(nums[0])]

    # botning xabariga oddiy reply zametka bo'lib ketmasin ("rahmat" ga esa javob beramiz)
    if reply_to_bot and not mentioned and not private and intent.kind in ("note", "help"):
        return

    replies = await execute(intent, msg, session, bot_username)
    await send(msg, replies)
