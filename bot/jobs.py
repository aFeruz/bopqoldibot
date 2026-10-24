"""Fon vazifalari: eslatmalar, muddatlar, takroriy ishlar va avtomatik xulosalar."""

import logging

from aiogram import Bot

from bot import keyboards as kb
from bot import texts
from bot.handlers.actions import agenda_body
from bot.phrases import say
from bot.services import notes as notes_svc
from bot.services import recurring as rec_svc
from bot.services import reminders as rem_svc
from bot.services import reports
from bot.services.common import local_now

log = logging.getLogger("bot.jobs")


async def _send(bot: Bot, chat_id: int, text: str, markup=None) -> None:
    try:
        await bot.send_message(chat_id, texts.clip(text), reply_markup=markup)
    except Exception:
        log.exception("xabar yuborilmadi: %s", chat_id)


async def send_due_reminders(bot: Bot, sessionmaker) -> None:
    async with sessionmaker() as session:
        for r in await rem_svc.due(session):
            head = say("remind_fire", (r.author_name or "").split(" ")[0] or None)
            await _send(bot, r.chat_id, f"<b>{head}</b>\n\n🔔 {texts.e(r.text)}\n<i>— {texts.e(r.author_name)}</i>")
            r.sent = True
        await session.commit()


async def send_due_alerts(bot: Bot, sessionmaker) -> None:
    async with sessionmaker() as session:
        disabled = await rem_svc.alerts_disabled(session)
        for n in await notes_svc.due_for_alert(session):
            n.due_notified = True
            if n.chat_id in disabled:
                continue
            await _send(bot, n.chat_id, f"<b>{say('due_alert')}</b>\n\n{texts.due_alert(n)}", kb.due_alert(n))
        await session.commit()


async def run_recurring(bot: Bot, sessionmaker) -> None:
    now = local_now()
    async with sessionmaker() as session:
        for r in await rec_svc.due_now(session, now):
            r.last_run = now.date().isoformat()
            note = await notes_svc.add_note(
                session, r.chat_id, r.text, None, r.author_name or "🔁", r.category, False, None, r.assignee
            )
            await _send(bot, r.chat_id, f"<b>{say('recurring_fire')}</b>\n\n{texts.note_card(note)}", kb.note_saved(note))
        await session.commit()


async def tick(bot: Bot, sessionmaker) -> None:
    """Har 30 soniyada: eslatmalar, muddatlar, takroriy vazifalar."""
    for job in (send_due_reminders, send_due_alerts, run_recurring):
        try:
            await job(bot, sessionmaker)
        except Exception:
            log.exception("%s xato", job.__name__)


async def send_morning(bot: Bot, sessionmaker) -> None:
    async with sessionmaker() as session:
        for chat_id in await rem_svc.chats_with(session, "morning_summary"):
            await _send(bot, chat_id, f"<b>{say('morning_head')}</b>\n\n{await agenda_body(session, chat_id)}")


async def send_daily(bot: Bot, sessionmaker) -> None:
    async with sessionmaker() as session:
        for chat_id in await rem_svc.chats_with(session, "daily_summary"):
            d = await reports.diary(session, chat_id, "today")
            if d.created or d.closed or d.interactions:
                await _send(bot, chat_id, texts.diary_text(d, "today"))


async def send_weekly(bot: Bot, sessionmaker) -> None:
    async with sessionmaker() as session:
        for chat_id in await rem_svc.chats_with(session, "weekly_summary"):
            st = await reports.stats(session, chat_id, "week")
            await _send(bot, chat_id, f"<b>{say('weekly_head')}</b>\n\n{texts.stats_text(st, 'week')}")
