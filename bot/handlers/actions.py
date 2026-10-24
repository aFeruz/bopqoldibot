"""Intent -> bajarish -> javob. Mention, slash buyruqlar va tugmalar shu yerdan foydalanadi."""

import re
import secrets
from dataclasses import dataclass

from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.models import Note
from bot.parser import Intent, parse_client_list, parse_when
from bot.phrases import greet, greet_prefix, say
from bot.services import clients as clients_svc
from bot.services import notes as notes_svc
from bot.services import reminders as rem_svc
from bot.services import recurring as rec_svc
from bot.services import reports
from bot.services.common import local_now, period_end, period_start

NOTES_PAGE = 10
CLIENTS_PAGE = 20
ACTIVITY_PAGE = 20
MILESTONES = {5, 10, 15, 20, 25, 30, 40, 50, 75, 100}
SIMPLE_REPLIES = {"labbay", "alive", "ack", "no", "laugh", "sorry", "compliment", "insult", "joke", "motivation"}
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]
WEEKDAYS_UZ = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
QUESTION_STOPWORDS = {
    "bormi", "nima", "qachon", "qayerda", "kim", "kimga", "nechta", "qanday", "qaysi", "bugun", "ertaga", "kecha",
    "uchun", "bilan", "edi", "ekan", "mikan", "kerakmi", "bo'ladimi", "bo'ldimi", "qildimi", "keldimi", "yo'qmi",
}

# "Ali bilan ishladim: izoh" noaniq bo'lsa, tugma bosilguncha izohni shu yerda saqlaymiz.
PENDING: dict[str, dict] = {}


@dataclass
class Reply:
    text: str
    markup: InlineKeyboardMarkup | None = None


def author(msg: Message) -> str:
    u = msg.from_user
    return u.full_name if u else "?"


def first_name(msg: Message) -> str | None:
    u = msg.from_user
    return u.first_name if u else None


def resolve_me(msg: Message, assignee: str | None) -> tuple[str | None, bool]:
    """'me' -> '@username'. (natija, muvaffaqiyatli)."""
    if assignee != "me":
        return assignee, True
    username = msg.from_user.username if msg.from_user else None
    return (f"@{username.lower()}", True) if username else (None, False)


def headed(head: str, body: str) -> str:
    return f"{head}\n\n{body}"


# --- ro'yxatlarni chizish (callback'lar ham ishlatadi) -------------------------

def notes_key(status: str, category: str | None, flt: str | None, assignee: str | None = None) -> str:
    return f"{status[0]}.{flt or ''}.{category or ''}.{assignee or ''}"


async def render_notes(session: AsyncSession, chat_id: int, key: str, offset: int = 0, name: str | None = None) -> Reply:
    s, flt, cat, asg = (key.split(".", 3) + [""])[:4]  # eski tugmalarda 3 qism bo'ladi
    status = {"o": "open", "d": "done", "a": "all"}[s]
    items, total = await notes_svc.list_notes(
        session, chat_id, status, cat or None, flt or None, offset, NOTES_PAGE, assignee=asg or None
    )
    if not items and offset:  # oxirgi sahifa bo'shab qoldi
        return await render_notes(session, chat_id, key, max(0, offset - NOTES_PAGE), name)
    body = texts.notes_list(items, total, status, cat or None, flt or None, offset, asg or None)
    if not items and asg:
        head = say("my_empty", name)
    elif not items and status == "open" and not cat and not flt:
        head = say("list_empty", name)
    else:
        head = say("done_head" if status == "done" else "list_head", name)
    return Reply(headed(head, body), kb.notes_list(items, key, offset, NOTES_PAGE, total))


async def render_activity(session: AsyncSession, chat_id: int, key: str, offset: int = 0, name: str | None = None) -> Reply:
    w, period, cat, asg = (key.split(".", 3) + [""])[:4]
    worked_flag = w == "w"
    worked, not_worked = await clients_svc.activity(
        session, chat_id, period_start(period), period_end(period), cat or None, asg or None
    )
    items = worked if worked_flag else not_worked
    if offset >= len(items):
        offset = max(0, (len(items) - 1) // ACTIVITY_PAGE * ACTIVITY_PAGE)
    page = items[offset: offset + ACTIVITY_PAGE]
    body = texts.activity_list(items, worked_flag, period, cat or None, offset, ACTIVITY_PAGE, asg or None)
    if worked_flag:
        head = say("worked_head", name)
    else:
        head = say("not_worked_head" if items else "not_worked_empty", name)
    return Reply(headed(head, body), kb.activity(page, key, offset, ACTIVITY_PAGE, len(items), worked_flag))


async def render_clients(session: AsyncSession, chat_id: int, key: str, offset: int = 0, name: str | None = None) -> Reply:
    arch, cat, asg = (key.split(".", 2) + [""])[:3]
    archived = arch == "a"
    items, total = await clients_svc.list_clients(
        session, chat_id, cat or None, archived, offset, CLIENTS_PAGE, assignee=asg or None
    )
    body = texts.clients_list(items, total, cat or None, offset, archived, asg or None)
    return Reply(headed(say("clients_head", name), body) if items else body,
                 kb.clients_list(key, offset, CLIENTS_PAGE, total))


async def render_card(session: AsyncSession, client) -> Reply:
    items, total = await clients_svc.history(session, client)
    return Reply(texts.client_card(client, items, total), kb.client_card(client))


async def record_work(session: AsyncSession, client, comment: str, who: str, name: str | None = None) -> str:
    await clients_svc.add_interaction(session, client, comment, who)
    tail = f"\n💬 {texts.e(comment)}" if comment else ""
    head = say("worked", name, client=f"<b>{texts.e(client.name)}</b>")
    return f"{head}\n👤 #{client.number} · {texts.e(who)}{tail}"


async def done_message(session: AsyncSession, chat_id: int, notes: list[Note], name: str | None) -> str:
    """Bajarilgan ishlar uchun jonli javob: maqtov + qolganlar soni / bayram + kunlik rekord."""
    head = say("done_many", name, n=len(notes)) if len(notes) > 1 else say("done", name)
    lines = [head, ""] + [f"✅ <s>#{n.number} {texts.e(n.text)}</s>" for n in notes]
    left = await notes_svc.count_open(session, chat_id)
    lines.append("")
    lines.append(say("all_clear", name) if left == 0 else say("remaining", name, n=left))
    today = await notes_svc.count_done_since(session, chat_id, period_start("today"))
    if today in MILESTONES:
        lines.append(say("milestone", name, n=today))
    return "\n".join(lines)


async def _resolve_latest(session: AsyncSession, chat_id: int, intent: Intent) -> None:
    """Raqam 0 — "oxirgisi": done uchun oxirgi ochiq, undo uchun oxirgi bajarilgan, aks holda oxirgi yozilgan."""
    if 0 not in intent.numbers:
        return
    status = {"done": "open", "undo": "done"}.get(intent.kind)
    note = await notes_svc.latest(session, chat_id, status)
    intent.numbers = [n for n in intent.numbers if n != 0] + ([note.number] if note else [])


# --- asosiy dispatcher ----------------------------------------------------------

async def execute(intent: Intent, msg: Message, session: AsyncSession, bot_username: str) -> list[Reply]:
    replies = await _execute(intent, msg, session, bot_username)
    prefix = smalltalk_prefix(intent, first_name(msg))
    if prefix and replies:
        # "rahmat yaxshi, Assalomu alaykum, ro'yxatni ber" — avval suhbatga javob, keyin ish
        first = replies[0]
        replies[0] = Reply(f"{prefix}\n{first.text}", first.markup)
    return replies


def smalltalk_prefix(intent: Intent, user: str | None) -> str:
    """Gap boshidagi suhbat qismiga qisqa javob (asosiy javob o'zi shu turda bo'lsa — takrorlamaymiz)."""
    own = {"greet": "greet", "thanks": "thanks", "fine": "fine", "howareyou": "how"}.get(intent.kind)
    parts = []
    kinds = intent.smalltalk or (["greet"] if intent.greeting else [])
    if "greet" in kinds and own != "greet":
        parts.append(greet_prefix(intent.greeting, user))
    if "fine" in kinds and own != "fine":
        parts.append(say("fine_short", user))
    elif "thanks" in kinds and own not in ("thanks", "fine"):
        parts.append(say("thanks_short", user))
    if "how" in kinds and own not in ("how", "greet"):
        parts.append(say("how_short", user))
    return " ".join(parts)


async def _execute(intent: Intent, msg: Message, session: AsyncSession, bot_username: str) -> list[Reply]:
    chat_id = msg.chat.id
    who = author(msg)
    name = first_name(msg)
    k = intent.kind

    # --- suhbat ---
    if k == "help":
        return [Reply(texts.HELP.format(u=bot_username))]
    if k == "greet":
        text = greet(intent.greeting, name)
        if "how" in intent.smalltalk:
            text += "\n" + say("how_short", name)
        return [Reply(text)]
    if k in SIMPLE_REPLIES:
        return [Reply(say(k, name))]
    if k == "emoji":
        return [Reply(say(f"emoji_{intent.value}", name))]
    if k == "time_now":
        return [Reply(say("time_now", name, t=f"{local_now():%H:%M}"))]
    if k == "date_now":
        now = local_now()
        return [Reply(say("date_now", name, d=f"{now.day}-{MONTHS[now.month - 1]}, {WEEKDAYS_UZ[now.weekday()]}"))]
    if k == "reminder_done":
        return [Reply(say("reminder_done", name) + f"\n✅ {texts.e(intent.text)}")]
    if k == "files":
        return await files_reply(msg, session, chat_id, intent.category, intent.value, intent.filter == "send", name)
    if k == "send_file":
        notes = await notes_svc.get_notes(session, chat_id, intent.numbers)
        replies, sent = [], 0
        for num in intent.numbers:
            note = notes.get(num)
            if note is None:
                replies.append(Reply(say("not_found", name, what=f"#{num} zametkani")))
            elif note.file_id:
                await send_note_file(msg.bot, chat_id, note, reply_to=msg.message_id)
                sent += 1
            else:
                replies.append(Reply(headed(say("no_file", name), texts.note_card(note)), kb.note_saved(note)))
        return replies
    if k == "question":
        return [await answer_question(session, chat_id, intent.text, name)]
    if k in ("thanks", "bye", "howareyou", "about", "fine"):
        return [Reply(say(k, name))]

    # --- zametkalar ---
    if k == "note":
        if not intent.text:
            return [Reply(say("note_empty", name) + f"\nMasalan: <code>@{bot_username} tovar sanash kerak</code>")]
        note = await notes_svc.add_note(
            session, chat_id, intent.text, msg.from_user.id if msg.from_user else None, who,
            intent.category, intent.important, intent.when, intent.assignee,
        )
        head = say("note_important" if note.important else ("assigned" if note.assignee else "note_saved"), name)
        return [Reply(texts.note_saved(note, head), kb.note_saved(note))]

    if k == "list":
        assignee, ok = resolve_me(msg, intent.assignee)
        if not ok:
            return [Reply(say("no_username", name))]
        key = notes_key(intent.status or "open", intent.category, intent.filter, assignee)
        return [await render_notes(session, chat_id, key, name=name)]

    if k == "agenda":
        return [Reply(texts.clip(headed(say("agenda_head", name), await agenda_body(session, chat_id))))]

    if k == "note_update":
        note = await notes_svc.update_note(
            session, chat_id, intent.numbers[0], intent.field, intent.when if intent.field == "due" else intent.value
        )
        if not note:
            return [Reply(say("not_found", name, what=f"#{intent.numbers[0]} zametkani"))]
        head = say("assigned" if intent.field == "assignee" else "note_updated", name)
        return [Reply(headed(head, texts.note_card(note)), kb.note_saved(note) if note.status == "open" else None)]

    if k in ("done", "undo", "delete") and not intent.numbers:
        status = {"done": "open", "undo": "done", "delete": None}[k]
        options = await notes_svc.recent(session, chat_id, status)
        if not options:
            return [Reply(say("list_empty", name) if k == "done" else say("not_found", name, what="zametka"))]
        action = {"done": "nd", "undo": "nu", "delete": "nx"}[k]
        return [Reply(say("which_number", name), kb.choose_notes(options, action))]

    await _resolve_latest(session, chat_id, intent)

    if k in ("done", "undo"):
        status = "done" if k == "done" else "open"
        changed, missing = await notes_svc.set_status(session, chat_id, intent.numbers, status, who)
        changed_nums = {c.number for c in changed}
        skipped = [n for n in intent.numbers if n not in missing and n not in changed_nums]
        lines = []
        if changed:
            if k == "done":
                lines.append(await done_message(session, chat_id, changed, name))
            else:
                lines.append(say("undo", name))
                lines += [f"🔄 <b>#{n.number}</b> {texts.e(n.text)}" for n in changed]
        if skipped:
            lines.append(say("already_done" if k == "done" else "already_open", name)
                         + " " + ", ".join(f"#{n}" for n in skipped))
        if missing:
            lines.append(say("not_found", name, what=", ".join(f"#{n}" for n in missing)))
        markup = kb.note_done(changed[0]) if k == "done" and len(changed) == 1 else None
        return [Reply("\n".join(lines), markup)]

    if k == "done_text":
        matches = await notes_svc.find_open_by_text(session, chat_id, intent.text)
        if not matches:
            return [Reply(say("not_found", name, what=f"«{texts.e(intent.text)}» ga o'xshash ochiq ishni")
                          + f"\n📋 Ro'yxat: <code>@{bot_username} zametkalar</code>")]
        if len(matches) == 1:
            changed, _ = await notes_svc.set_status(session, chat_id, [matches[0].number], "done", who)
            return [Reply(await done_message(session, chat_id, changed, name), kb.note_done(matches[0]))]
        return [Reply(say("which_one", name), kb.choose_notes(matches))]

    if k == "delete":
        deleted = await notes_svc.delete_notes(session, chat_id, intent.numbers)
        if not deleted:
            return [Reply(say("not_found", name, what="bunday zametkani"))]
        return [Reply(say("delete", name) + "\n🗑 " + ", ".join(f"#{n}" for n in deleted))]

    if k == "edit":
        note = await notes_svc.edit_note(session, chat_id, intent.numbers[0], intent.text)
        if not note:
            return [Reply(say("not_found", name, what="bunday zametkani"))]
        return [Reply(f"{say('edit', name)}\n\n✏️ <b>#{note.number}</b> {texts.e(note.text)}")]

    if k == "search":
        found = await notes_svc.search_notes(session, chat_id, intent.text)
        if not found:
            return [Reply(say("not_found", name, what=f"«{texts.e(intent.text)}» bo'yicha hech narsa"))]
        lines = [say("search_head", name), f"🔎 «{texts.e(intent.text)}» — {len(found)} ta", ""]
        lines += [texts.note_line(n) for n in found]
        return [Reply(texts.clip("\n".join(lines)))]

    # --- mijozlar ---
    if k == "client_add":
        items = parse_client_list(intent.text)
        if not items:
            return [Reply(say("client_empty", name))]
        added, dupes = await clients_svc.add_clients(
            session, chat_id, items, default_assignee=intent.assignee, remind=intent.remind
        )
        lines = []
        if added:
            lines += [say("client_added", name), f"➕ {len(added)} ta mijoz:"] + [texts.client_line(c) for c in added]
        if dupes:
            lines.append(("\n" if added else "") + "ℹ️ " + say("client_dupe", name) + ": "
                         + ", ".join(f"#{c.number} {texts.e(c.name)}" for c in dupes))
        if intent.assignee and (added or dupes):
            if dupes:
                await clients_svc.assign(session, dupes, intent.assignee, intent.remind)
            lines.append("")
            lines.append(await assignment_notice(session, chat_id, added + dupes, intent, who))
        return [Reply(texts.clip("\n".join(lines)))]

    if k == "client_assign":
        clients = await select_clients(session, chat_id, intent)
        if not clients:
            if intent.names and not re.search(r"mijoz|klient", intent.text or "", re.IGNORECASE):
                # "hisobotni @vali ga ber" — mijoz emas, topshiriq
                text = re.sub(r"(?:ni|larni)$", "", intent.text.strip()).strip()
                fallback = Intent("note", text=text, assignee=intent.assignee)
                return await _execute(fallback, msg, session, bot_username)
            return [Reply(say("not_found", name, what="bunday mijozlarni"))]
        await clients_svc.assign(session, clients, intent.assignee, intent.remind)
        lines = [say("assigned", name)]
        lines += [texts.client_line(c) for c in clients[:15]]
        if len(clients) > 15:
            lines.append(f"… va yana {len(clients) - 15} ta")
        lines += ["", await assignment_notice(session, chat_id, clients, intent, who)]
        return [Reply(texts.clip("\n".join(lines)))]

    if k == "worked":
        replies = []
        done_lines = []
        for client_name in intent.names:
            found = await clients_svc.resolve(session, chat_id, client_name)
            if len(found) == 1:
                done_lines.append(await record_work(session, found[0], intent.text, who, name))
                followup = await schedule_followup(session, chat_id, found[0], intent.text, who)
                if followup:
                    done_lines[-1] += "\n" + followup
                continue
            token = secrets.token_hex(4)
            PENDING[token] = {"text": intent.text, "name": client_name, "author": who}
            if found:
                replies.append(Reply(say("worked_ask_which", name, name=texts.e(client_name)),
                                     kb.choose_clients(found, token)))
            else:
                replies.append(Reply(say("worked_ask_new", name, name=texts.e(client_name)),
                                     kb.choose_clients([], token, allow_new=client_name)))
        if done_lines:
            replies.insert(0, Reply("\n\n".join(done_lines)))
        return replies

    if k in ("not_worked", "worked_list"):
        assignee, ok = resolve_me(msg, intent.assignee)
        if not ok:
            return [Reply(say("no_username", name))]
        key = f"{'w' if k == 'worked_list' else 'n'}.{intent.period or 'all'}.{intent.category or ''}.{assignee or ''}"
        return [await render_activity(session, chat_id, key, name=name)]

    if k == "clients":
        assignee, ok = resolve_me(msg, intent.assignee)
        if not ok:
            return [Reply(say("no_username", name))]
        key = f"{'a' if intent.status == 'all' else 'o'}.{intent.category or ''}.{assignee or ''}"
        return [await render_clients(session, chat_id, key, name=name)]

    if k == "client_card":
        query = intent.names[0]
        found = await clients_svc.resolve(session, chat_id, query)
        if not found and query.lstrip("#").isdigit():
            c = await clients_svc.get_by_number(session, chat_id, int(query.lstrip("#")))
            found = [c] if c else []
        if not found:
            return [Reply(say("not_found", name, what=f"«{texts.e(query)}» degan mijozni"))]
        if len(found) > 1:
            return [Reply("\n".join([say("which_one", name)] + [texts.client_line(c) for c in found]))]
        return [await render_card(session, found[0])]

    if k == "client_update":
        found = await clients_svc.resolve(session, chat_id, intent.names[0])
        if len(found) != 1:
            if found:
                return [Reply("\n".join([say("which_one", name)] + [texts.client_line(c) for c in found]))]
            return [Reply(say("not_found", name, what=f"«{texts.e(intent.names[0])}» degan mijozni"))]
        client = await clients_svc.update_client(session, found[0], intent.field, intent.value)
        card = await render_card(session, client)
        return [Reply(headed(say("client_updated", name), card.text), card.markup)]

    if k == "client_archive":
        rows = await clients_svc.archive(session, chat_id, intent.numbers)
        if not rows:
            return [Reply(say("not_found", name, what="bunday mijozni"))]
        return [Reply(say("archived", name) + "\n🗄 " + ", ".join(f"#{c.number} {texts.e(c.name)}" for c in rows))]

    # --- hisobotlar ---
    if k == "stats":
        body = texts.stats_text(await reports.stats(session, chat_id, intent.period), intent.period or "all")
        return [Reply(headed(say("stats_head", name), body))]

    if k == "diary":
        d = await reports.diary(session, chat_id, intent.period)
        return [Reply(texts.clip(headed(say("diary_head", name), texts.diary_text(d, intent.period or "today"))))]

    if k == "categories":
        return [Reply(texts.categories_text(await reports.categories(session, chat_id)))]

    if k == "remind":
        if not intent.when:
            return [Reply(say("remind_when", name))]
        if intent.when <= local_now():
            return [Reply(say("remind_past", name))]
        r = await rem_svc.add(session, chat_id, intent.text or "(eslatma)", intent.when, who)
        return [Reply(headed(say("remind_set", name), texts.reminder_saved(r)))]

    if k == "recurring_add":
        r = await rec_svc.add(session, chat_id, intent.text, intent.rule, intent.when.hour, intent.when.minute,
                              intent.category, intent.assignee, who)
        return [Reply(headed(say("recurring_set", name), texts.recurring_saved(r)))]

    if k == "recurring_list":
        items = await rec_svc.list_active(session, chat_id)
        return [Reply(texts.recurring_list(items), kb.recurring(items))]

    if k == "settings":
        cs = await rem_svc.get_settings(session, chat_id)
        await session.commit()
        return [Reply(texts.settings_text(cs), kb.settings(cs))]

    if k == "reminders":
        items = await rem_svc.pending(session, chat_id)
        return [Reply(texts.reminders_list(items), kb.reminders(items))]

    if k == "export":
        files = await reports.export_csv(session, chat_id)
        for fname, data in files.items():
            await msg.answer_document(BufferedInputFile(data, filename=fname))
        return [Reply(say("export_done", name))]

    return [Reply("Tushunmadim 🤔 /help")]


async def select_clients(session: AsyncSession, chat_id: int, intent: Intent) -> list:
    if intent.filter == "all":
        clients, _ = await clients_svc.list_clients(session, chat_id, limit=10_000)
        return clients
    if intent.filter == "not_worked":
        _, not_worked = await clients_svc.activity(session, chat_id, None, category=intent.category)
        return [a.client for a in not_worked]
    if intent.filter == "category":
        return await clients_svc.by_category(session, chat_id, intent.category)
    found = []
    for n in intent.names:
        match = await clients_svc.resolve(session, chat_id, n)
        if len(match) == 1 and match[0] not in found:
            found.append(match[0])
    return found


async def assignment_notice(session: AsyncSession, chat_id: int, clients: list, intent: Intent, who: str) -> str:
    """Mas'ulga murojaat (Telegram mention orqali xabar boradi) va kerak bo'lsa eslatma qo'yish."""
    names = ", ".join(c.name for c in clients[:5]) + (f" va yana {len(clients) - 5} ta" if len(clients) > 5 else "")
    line = say("assigned_clients", None, who=texts.e(intent.assignee), n=len(clients))
    if intent.when and intent.when > local_now():
        text = f"{intent.assignee}, mijozlar bilan bog'lanish: {names}"
        r = await rem_svc.add(session, chat_id, text, intent.when, who)
        line += "\n" + say("followup_set", None, when=f"{intent.when:%d.%m %H:%M}") + f" <i>(eslatma #{r.id})</i>"
    elif intent.remind:
        line += "\n" + say("digest_on", None, who=texts.e(intent.assignee))
    return line


FILES_PAGE = 10


async def send_note_file(bot, chat_id: int, note: Note, reply_to: int | None = None) -> None:
    from bot.media import send_media
    await send_media(bot, chat_id, note.file_id, note.file_type, texts.note_caption(note), reply_to)


async def files_reply(
    msg: Message, session: AsyncSession, chat_id: int, category: str | None, ftype: str | None, send_all: bool,
    name: str | None,
) -> list[Reply]:
    notes, total = await notes_svc.list_files(session, chat_id, category, ftype, limit=FILES_PAGE)
    if not notes:
        return [Reply(say("files_empty", name) + "\nSaqlash: faylga reply qilib <code>@bot eslab qol #kategoriya</code>")]
    if send_all:
        for n in reversed(notes):
            await send_note_file(msg.bot, chat_id, n)
        more = f"\nYana {total - len(notes)} ta bor — kategoriya yoki turini aniqlashtiring" if total > len(notes) else ""
        return [Reply(say("files_sent", name, n=len(notes)) + more)]
    body = texts.files_list(notes, total, category, ftype)
    return [Reply(headed(say("files_head", name), body), kb.files_list(notes, category, ftype))]


async def answer_question(session: AsyncSession, chat_id: int, text: str, name: str | None) -> Reply:
    """Noma'lum savol: kalit so'zlar bo'yicha zametka va mijozlardan qidiradi, topilmasa saqlashni taklif qiladi."""
    words = []
    for w in re.findall(r"[^\W\d_][\w']{2,}", text.lower()):
        w = re.sub(r"(?:mi|mikan|chi|ni|ga|da|dan|ning|lar|lari)$", "", w)
        if len(w) >= 3 and w not in QUESTION_STOPWORDS:
            words.append(w)
    notes, clients = [], []
    for w in words[:4]:
        for n in await notes_svc.search_notes(session, chat_id, w, limit=5):
            if n not in notes:
                notes.append(n)
        for c in await clients_svc.resolve(session, chat_id, w):
            if c not in clients and w in c.name.lower():
                clients.append(c)
    if notes or clients:
        lines = [say("question_found", name), ""]
        lines += [texts.note_line(n) for n in notes[:6]]
        lines += [texts.client_line(c) for c in clients[:5]]
        return Reply(texts.clip("\n".join(lines)))
    token = secrets.token_hex(4)
    PENDING[token] = {"text": text}
    return Reply(say("question_unknown", name), kb.save_offer(token))


FOLLOWUP_RE = r"\b(qayta|yana|keyin|keyingi|takror|eslat|qo'ng'iroq qilaman|bog'lanaman|uchrashamiz)"


async def schedule_followup(session: AsyncSession, chat_id: int, client, comment: str, who: str) -> str | None:
    """'Ali bilan gaplashdim, 3 kundan keyin qayta qo'ng'iroq' -> eslatma qo'yadi."""
    if not comment or not re.search(FOLLOWUP_RE, comment.lower()):
        return None
    when, _ = parse_when(comment, local_now())
    if not when or when <= local_now():
        return None
    text = f"📞 {client.name} (#{client.number}) bilan qayta bog'lanish: {comment}"
    r = await rem_svc.add(session, chat_id, text, when, who)
    return say("followup_set", None, when=f"{when:%d.%m %H:%M}") + f" <i>(eslatma #{r.id})</i>"


async def agenda_body(session: AsyncSession, chat_id: int) -> str:
    today, overdue, important, open_count = await notes_svc.agenda(session, chat_id)
    _, not_worked = await clients_svc.activity(session, chat_id, period_start("7d"))
    return texts.agenda_text(today, overdue, important, open_count, not_worked)


async def send(msg: Message, replies: list[Reply]) -> None:
    for r in replies:
        await msg.reply(r.text, reply_markup=r.markup, disable_web_page_preview=True)
