from datetime import timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.handlers.actions import (
    PENDING, Reply, done_message, record_work, render_activity, render_card, render_clients, render_notes,
)
from bot.phrases import say
from bot.parser import ClientInput
from bot.services import clients as clients_svc
from bot.services import notes as notes_svc
from bot.services import recurring as rec_svc
from bot.services import reminders as rem_svc
from bot.services.common import local_now

router = Router()


async def edit(cb: CallbackQuery, reply: Reply) -> None:
    try:
        await cb.message.edit_text(reply.text, reply_markup=reply.markup, disable_web_page_preview=True)
    except TelegramBadRequest:
        pass  # "message is not modified"


def who(cb: CallbackQuery) -> str:
    return cb.from_user.full_name


def first(cb: CallbackQuery) -> str:
    return cb.from_user.first_name


def list_context(cb: CallbackQuery, prefix: str) -> tuple[str, int] | None:
    """Tugma ro'yxat xabarida bo'lsa — 🔄 tugmasidagi ro'yxat kaliti va sahifasi."""
    markup = cb.message.reply_markup if cb.message else None
    for row in (markup.inline_keyboard if markup else []):
        for b in row:
            if b.text == kb.REFRESH and b.callback_data and b.callback_data.startswith(prefix):
                _, key, off = b.callback_data.split(":")
                return key, int(off)
    return None


@router.callback_query(F.data.startswith(("nd:", "nu:")))
async def note_status(cb: CallbackQuery, session: AsyncSession) -> None:
    action, num = cb.data.split(":")
    status = "done" if action == "nd" else "open"
    chat_id = cb.message.chat.id
    changed, missing = await notes_svc.set_status(session, chat_id, [int(num)], status, who(cb))
    if missing:
        await cb.answer("Zametka topilmadi", show_alert=True)
        return
    await cb.answer(("✅ #%s bajarildi" if status == "done" else "↩️ #%s qayta ochildi") % num)

    ctx = list_context(cb, "nl:")
    if ctx:
        await edit(cb, await render_notes(session, chat_id, *ctx, name=first(cb)))
        return
    note = (await notes_svc.get_notes(session, chat_id, [int(num)]))[int(num)]
    if status == "done":
        text = await done_message(session, chat_id, changed or [note], first(cb))
        await edit(cb, Reply(f"{text}\n<i>— {texts.e(who(cb))}</i>", kb.note_done(note)))
    else:
        await edit(cb, Reply(f"{say('undo', first(cb))}\n\n🔄 <b>#{note.number}</b> {texts.e(note.text)}",
                             kb.note_saved(note)))


@router.callback_query(F.data.startswith("nx:"))
async def note_cancel(cb: CallbackQuery, session: AsyncSession) -> None:
    num = int(cb.data.split(":")[1])
    deleted = await notes_svc.delete_notes(session, cb.message.chat.id, [num])
    await cb.answer("🗑 O'chirildi" if deleted else "Topilmadi")
    if deleted:
        await edit(cb, Reply(f"{say('delete', first(cb))}\n🗑 #{num}"))


@router.callback_query(F.data.startswith("nl:"))
async def notes_page(cb: CallbackQuery, session: AsyncSession) -> None:
    _, key, off = cb.data.split(":")
    await cb.answer()
    await edit(cb, await render_notes(session, cb.message.chat.id, key, int(off), first(cb)))


@router.callback_query(F.data.startswith("al:"))
async def activity_page(cb: CallbackQuery, session: AsyncSession) -> None:
    _, key, off = cb.data.split(":")
    await cb.answer()
    await edit(cb, await render_activity(session, cb.message.chat.id, key, int(off), first(cb)))


@router.callback_query(F.data.startswith("cl:"))
async def clients_page(cb: CallbackQuery, session: AsyncSession) -> None:
    _, key, off = cb.data.split(":")
    await cb.answer()
    await edit(cb, await render_clients(session, cb.message.chat.id, key, int(off)))


@router.callback_query(F.data.startswith("cw:"))
async def choose_client(cb: CallbackQuery, session: AsyncSession) -> None:
    _, token, num = cb.data.split(":")
    pending = PENDING.pop(token, {"text": ""})
    client = await clients_svc.get_by_number(session, cb.message.chat.id, int(num))
    if not client:
        await cb.answer("Mijoz topilmadi", show_alert=True)
        return
    await cb.answer("🤝 Yozildi")
    await edit(cb, Reply(await record_work(session, client, pending["text"], who(cb), first(cb))))


@router.callback_query(F.data.startswith("ca:"))
async def add_and_work(cb: CallbackQuery, session: AsyncSession) -> None:
    token = cb.data.split(":")[1]
    pending = PENDING.pop(token, None)
    if not pending:
        await cb.answer("Eskirgan tugma, qaytadan yozing", show_alert=True)
        return
    added, dupes = await clients_svc.add_clients(session, cb.message.chat.id, [ClientInput(name=pending["name"])])
    client = (added or dupes)[0]
    await cb.answer("➕ Qo'shildi")
    text = (f"{say('client_added', first(cb))}\n{texts.client_line(client)}\n\n"
            + await record_work(session, client, pending["text"], who(cb), first(cb)))
    await edit(cb, Reply(text))


@router.callback_query(F.data.startswith("cq:"))
async def quick_work(cb: CallbackQuery, session: AsyncSession) -> None:
    num = int(cb.data.split(":")[1])
    chat_id = cb.message.chat.id
    client = await clients_svc.get_by_number(session, chat_id, num)
    if not client:
        await cb.answer("Mijoz topilmadi", show_alert=True)
        return
    await clients_svc.add_interaction(session, client, "", who(cb))
    await cb.answer(f"🤝 {client.name} — ishlandi")
    ctx = list_context(cb, "al:")
    if ctx:
        await edit(cb, await render_activity(session, chat_id, *ctx, name=first(cb)))
    elif (cb.message.text or "").startswith("👤"):
        await edit(cb, await render_card(session, client))


@router.callback_query(F.data.startswith(("cz:", "cr:")))
async def client_archive(cb: CallbackQuery, session: AsyncSession) -> None:
    action, num = cb.data.split(":")
    rows = await clients_svc.archive(session, cb.message.chat.id, [int(num)], value=action == "cz")
    if not rows:
        await cb.answer("Topilmadi")
        return
    await cb.answer(say("archived") if action == "cz" else "♻️ Qaytarildi")
    await edit(cb, await render_card(session, rows[0]))


@router.callback_query(F.data.startswith("rx:"))
async def reminder_cancel(cb: CallbackQuery, session: AsyncSession) -> None:
    rid = int(cb.data.split(":")[1])
    ok = await rem_svc.cancel(session, cb.message.chat.id, rid)
    await cb.answer("❌ Bekor qilindi" if ok else "Topilmadi")
    items = await rem_svc.pending(session, cb.message.chat.id)
    await edit(cb, Reply(texts.reminders_list(items), kb.reminders(items)))


@router.callback_query(F.data.startswith("st:"))
async def toggle_setting(cb: CallbackQuery, session: AsyncSession) -> None:
    field = cb.data.split(":")[1]
    try:
        cs = await rem_svc.set_flag(session, cb.message.chat.id, field)
    except ValueError:
        await cb.answer("Noma'lum sozlama")
        return
    await cb.answer(say("settings_saved"))
    await edit(cb, Reply(texts.settings_text(cs), kb.settings(cs)))


@router.callback_query(F.data.startswith("rr:"))
async def recurring_delete(cb: CallbackQuery, session: AsyncSession) -> None:
    rid = int(cb.data.split(":")[1])
    chat_id = cb.message.chat.id
    ok = await rec_svc.deactivate(session, chat_id, rid)
    await cb.answer(say("recurring_deleted") if ok else "Topilmadi")
    items = await rec_svc.list_active(session, chat_id)
    await edit(cb, Reply(texts.recurring_list(items), kb.recurring(items)))


@router.callback_query(F.data.startswith("nz:"))
async def snooze(cb: CallbackQuery, session: AsyncSession) -> None:
    _, num, how = cb.data.split(":")
    now = local_now().replace(second=0, microsecond=0)
    if how == "tomorrow":
        when = (now + timedelta(days=1)).replace(hour=9, minute=0)
    else:
        when = now + timedelta(minutes=int(how))
    note = await notes_svc.update_note(session, cb.message.chat.id, int(num), "due", when)
    if not note:
        await cb.answer("Zametka topilmadi", show_alert=True)
        return
    msg = say("snoozed", first(cb), when=f"{when:%d.%m %H:%M}")
    await cb.answer(msg)
    await edit(cb, Reply(f"{msg}\n\n{texts.due_alert(note)}", kb.note_saved(note)))
