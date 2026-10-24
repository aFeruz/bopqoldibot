import re
import secrets

from aiogram import F, Router
from aiogram.enums import ChatType, MessageEntityType
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot.handlers.actions import PENDING, execute, send
from bot.handlers.context import apply_context, reply_context
from bot.handlers.saving import is_save_instruction, message_content, origin_name, save_text_note
from bot.media import extract_media
from bot.phrases import say
from bot.parser import parse
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

    now = local_now()
    user = msg.from_user.first_name if msg.from_user else None

    # shaxsiy chatga forward qilingan xabar — buyruq emas, eslab qolinadigan matn
    if private and msg.forward_origin and text:
        await send(msg, [await save_text_note(session, msg.chat.id, text, "", msg.from_user.id,
                                              msg.from_user.full_name, user, origin_name(msg))])
        return

    reply_content = None
    if reply and not reply_to_bot and (mentioned or private):
        if extract_media(reply):
            # media xabarga reply: bo'sh yoki "eslab qol #kat" — saqlash; jadval — import; boshqa buyruq — odatdagidek
            from bot.handlers.files import IMPORT_RE, media_from_reply  # files.py mention.py ni import qiladi
            if is_save_instruction(text) or IMPORT_RE.search(text) or parse(text, now).kind == "note":
                if await media_from_reply(msg, session, msg.bot, text):
                    return
        reply_content = message_content(reply)
        if reply_content and is_save_instruction(text) and not _PREFIX_ONLY.match(text):
            # matn/kontakt/lokatsiyaga reply: "@bot", "@bot eslab qol #narx", "@bot @vali ertaga"
            await send(msg, [await save_text_note(session, msg.chat.id, reply_content, text, msg.from_user.id,
                                                  msg.from_user.full_name, user, origin_name(reply))])
            return

    if reply_content and _PREFIX_ONLY.match(text):
        text = text.rstrip(":") + ":\n" + reply_content
    intent = parse(text, now)
    # "@bot ertaga 9 da eslat" boshqa xabarga reply — eslatma matni o'sha xabar
    if reply_content and intent.kind == "remind" and not intent.text:
        intent.text = reply_content

    # botning xabariga reply: kartochkadagi zametka/mijoz/eslatma kontekstida tushunamiz
    if reply_to_bot:
        ctx = reply_context(reply.text or reply.caption or "")
        if ctx:
            intent = apply_context(text, intent, ctx, local_now())

    # botning xabariga tag qilinmagan reply: tushunarsiz bo'lsa jim qolmaymiz, zametka qilishni so'raymiz
    if reply_to_bot and not mentioned and not private and intent.kind == "note":
        if intent.text:
            token = secrets.token_hex(4)
            PENDING[token] = {"text": text}
            await msg.reply(say("save_offer", msg.from_user.first_name if msg.from_user else None),
                            reply_markup=kb.save_offer(token))
        return

    replies = await execute(intent, msg, session, bot_username)
    await send(msg, replies)


@router.message(F.sticker)
async def on_media(msg: Message, bot_id: int) -> None:
    """Botga stiker bilan javob berilsa ham jim qolmaymiz (ovoz/rasm — files.py da saqlash taklifi)."""
    reply = msg.reply_to_message
    to_bot = bool(reply and reply.from_user and reply.from_user.id == bot_id)
    if not (to_bot or msg.chat.type == ChatType.PRIVATE):
        return
    await msg.reply(say("sticker", msg.from_user.first_name if msg.from_user else None))
