"""Excel/CSV fayllarni qabul qilib, mijozlar bazasiga import qilish."""

import logging
import secrets

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import Document, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.handlers.actions import PENDING, Reply, first_name, send
from bot.handlers.mention import strip_mention
from bot.parser import extract_assignees, extract_tags, split_instructions
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


@router.message(F.document)
async def on_document(msg: Message, session: AsyncSession, bot: Bot, bot_username: str, bot_id: int) -> None:
    doc = msg.document
    if not is_table(doc):
        return
    caption, mentioned = strip_mention(msg, bot_username, bot_id)
    private = msg.chat.type == ChatType.PRIVATE
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

