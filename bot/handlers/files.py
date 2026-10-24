"""Excel/CSV fayllarni qabul qilib, mijozlar bazasiga import qilish."""

import logging
import re
import secrets

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import Document, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.handlers.actions import PENDING, Reply, first_name, send
from bot.handlers.mention import strip_mention
from bot.handlers.saving import SAVE_RE, message_content, origin_name, save_text_note
from bot.media import Media, describe, extract_media
from bot.parser import extract_assignees, extract_tags, normalize, parse_note, split_instructions
from bot.services import notes as notes_svc
from bot.phrases import say
from bot.services import clients as clients_svc
from bot.services import reminders as rem_svc
from bot.services.common import local_now
from bot.services.importer import parse_table

log = logging.getLogger("bot.files")
router = Router()

TABLE_EXT = (".xlsx", ".xlsm", ".csv", ".tsv")
MAX_SIZE = 10 * 1024 * 1024


def is_table(doc: Document | None) -> bool:
    return bool(doc and (doc.file_name or "").lower().endswith(TABLE_EXT))


async def import_document(
    bot: Bot, session: AsyncSession, chat_id: int, doc_file_id: str, filename: str, caption: str,
    who: str, user: str | None,
) -> Reply:
    """Faylni yuklab oladi, mijozlarni kiritadi va hisobot qaytaradi."""
    # izoh: "#rangor @vali ga o'tkaz, eslatib tur" yoki shunchaki "#rangor @vali"
    body, assignee, remind, when = split_instructions(caption or "", local_now())
    body, plain_assignee = extract_assignees(body)
    _, tags = extract_tags(body)
    assignee = assignee or plain_assignee
    category = tags[0] if tags else None

    buf = await bot.download(doc_file_id)
    try:
        items, report = parse_table(buf.read(), filename)
    except Exception:
        log.exception("fayl o'qilmadi: %s", filename)
        return Reply(say("import_empty", user))
    if not items:
        return Reply(say("import_empty", user))

    batch = secrets.token_hex(4)
    added, dupes = await clients_svc.add_clients(
        session, chat_id, items, batch=batch, default_category=category, default_assignee=assignee, remind=remind,
    )
    text = f"{say('import_done', user)}\n\n" + texts.import_report(report, added, dupes, category, assignee)
    if assignee and added:
        names = ", ".join(c.name for c in added[:5])
        text += "\n\n" + say("assigned_clients", None, who=texts.e(assignee), n=len(added))
        if when and when > local_now():
            r = await rem_svc.add(session, chat_id, f"{assignee}, mijozlar bilan bog'lanish: {names} va boshqalar",
                                  when, who)
            text += "\n" + say("followup_set", None, when=f"{when:%d.%m %H:%M}") + f" <i>(eslatma #{r.id})</i>"
        elif remind:
            text += "\n" + say("digest_on", None, who=texts.e(assignee))
    return Reply(texts.clip(text), kb.import_done(batch) if added else None)


IMPORT_RE = re.compile(r"\b(?:kirit|import|bazaga|mijoz)\w*", re.IGNORECASE)


async def save_media(
    session: AsyncSession, chat_id: int, media: Media, caption: str, author_id: int | None, who: str,
    user: str | None, fallback_text: str = "",
) -> Reply:
    """Media xabarni zametka sifatida saqlaydi: izohdan kategoriya, mas'ul, muddat va matn olinadi."""
    caption = (caption or "").strip()
    intent = parse_note(caption, local_now())
    text = intent.text or normalize(fallback_text).strip() or describe(media.type, media.name, media.duration)
    note = await notes_svc.add_note(
        session, chat_id, text, author_id, who, intent.category, intent.important, intent.when, intent.assignee,
        file_id=media.file_id, file_type=media.type, file_name=media.name,
    )
    return Reply(texts.note_saved(note, say("file_saved", user)), kb.note_saved(note))


async def _table(msg: Message, session: AsyncSession, bot: Bot, caption: str, mentioned: bool, private: bool) -> None:
    doc = msg.document
    if doc.file_size and doc.file_size > MAX_SIZE:
        if private or mentioned:
            await msg.reply("Fayl juda katta (10 MB dan oshmasin)")
        return
    if private or mentioned:
        reply = await import_document(bot, session, msg.chat.id, doc.file_id, doc.file_name, caption,
                                      msg.from_user.full_name, first_name(msg))
        await send(msg, [reply])
        return
    # guruhda tag qilinmagan jadval — import qilishni taklif qilamiz
    token = secrets.token_hex(4)
    PENDING[token] = {"file_id": doc.file_id, "file_name": doc.file_name, "caption": caption}
    await msg.reply(say("import_offer", first_name(msg)), reply_markup=kb.import_offer(token))


@router.message(F.photo | F.video | F.voice | F.audio | F.document | F.video_note | F.animation)
async def on_media_message(msg: Message, session: AsyncSession, bot: Bot, bot_username: str, bot_id: int) -> None:
    caption, mentioned = strip_mention(msg, bot_username, bot_id)
    private = msg.chat.type == ChatType.PRIVATE
    if is_table(msg.document) and not SAVE_RE.search(caption):
        await _table(msg, session, bot, caption, mentioned, private)
        return
    media = extract_media(msg)
    user = first_name(msg)
    if private or mentioned:
        reply = await save_media(session, msg.chat.id, media, caption, msg.from_user.id, msg.from_user.full_name, user)
        await send(msg, [reply])
        return
    reply_to = msg.reply_to_message
    if reply_to and reply_to.from_user and reply_to.from_user.id == bot_id:
        # botga ovoz/rasm bilan javob — jim qolmaymiz, saqlashni taklif qilamiz
        token = secrets.token_hex(4)
        PENDING[token] = {"media": media, "caption": caption}
        await msg.reply(say("media_offer", user), reply_markup=kb.save_offer(token))


async def media_from_reply(msg: Message, session: AsyncSession, bot: Bot, text: str) -> bool:
    """Guruhdagi media xabarga reply: "@bot eslab qol #shartnoma" — saqlaydi, jadval bo'lsa import qiladi."""
    reply = msg.reply_to_message
    media = extract_media(reply)
    if not media:
        return False
    if is_table(reply.document) and not SAVE_RE.search(text):
        return await import_from_reply(msg, session, bot, text)
    result = await save_media(session, msg.chat.id, media, text, msg.from_user.id, msg.from_user.full_name,
                              first_name(msg), fallback_text=reply.caption or "")
    await send(msg, [result])
    return True


async def import_from_reply(msg: Message, session: AsyncSession, bot: Bot, text: str) -> bool:
    """Jadvalga reply qilib "@bot shuni kirit" yozilsa. Import bo'lsa True."""
    reply = msg.reply_to_message
    if not (reply and is_table(reply.document)):
        return False
    caption = " ".join(x for x in (reply.caption or "", text) if x)
    result = await import_document(bot, session, msg.chat.id, reply.document.file_id, reply.document.file_name,
                                   caption, msg.from_user.full_name, first_name(msg))
    await send(msg, [result])
    return True



@router.message(F.contact | F.location | F.venue | F.poll)
async def on_shared_item(msg: Message, session: AsyncSession, bot_id: int) -> None:
    """Kontakt, lokatsiya, so'rovnoma: shaxsiy chatda saqlanadi, botga reply bo'lsa — saqlash taklifi."""
    content = message_content(msg)
    if not content:
        return
    user = first_name(msg)
    if msg.chat.type == ChatType.PRIVATE:
        await send(msg, [await save_text_note(session, msg.chat.id, content, "", msg.from_user.id,
                                              msg.from_user.full_name, user, origin_name(msg))])
        return
    reply_to = msg.reply_to_message
    if reply_to and reply_to.from_user and reply_to.from_user.id == bot_id:
        token = secrets.token_hex(4)
        PENDING[token] = {"text": content}
        await msg.reply(say("save_offer", user), reply_markup=kb.save_offer(token))
