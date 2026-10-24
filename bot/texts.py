from datetime import datetime
from html import escape

from bot.media import describe as describe_media
from bot.media import icon as media_icon
from bot.models import Client, Interaction, Note, Reminder
from bot.services.clients import ClientActivity
from bot.services.common import local_now, period_title, to_local
from bot.services.reports import Diary, Stats

MAX_LEN = 3900


def e(s: str | None) -> str:
    return escape(s or "")


def ago(dt_utc: datetime | None) -> str:
    if dt_utc is None:
        return "hech qachon"
    local = to_local(dt_utc)
    days = (local_now().date() - local.date()).days
    if days == 0:
        return f"bugun {local:%H:%M}"
    if days == 1:
        return f"kecha {local:%H:%M}"
    if days < 7:
        return f"{days} kun oldin"
    return f"{local:%d.%m.%Y}"


def note_line(n: Note) -> str:
    mark = "✅" if n.status == "done" else ("❗" if n.important else "▫️")
    clip_icon = f"{media_icon(n.file_type)} " if n.file_id else ""
    short = n.text if len(n.text) <= 160 else n.text[:157].rstrip() + "…"
    parts = [f"{mark} <b>#{n.number}</b> {clip_icon}{e(short.replace(chr(10), ' '))}"]
    if n.category:
        parts.append(f"<i>#{e(n.category.name)}</i>")
    if n.due_at and n.status == "open":
        overdue = n.due_at < local_now()
        parts.append(f"{'🔥' if overdue else '⏰'} {n.due_at:%d.%m %H:%M}")
    if n.assignee and n.status == "open":
        parts.append(f"👤 {e(n.assignee.replace(',', ', '))}")
    if n.status == "done" and n.done_by:
        parts.append(f"<i>— {e(n.done_by)}</i>")
    return " ".join(parts)


def note_saved(n: Note, head: str) -> str:
    extra = []
    if n.category:
        extra.append(f"🏷 #{e(n.category.name)}")
    if n.important:
        extra.append("❗ muhim")
    if n.due_at:
        extra.append(f"⏰ {n.due_at:%d.%m.%Y %H:%M}")
    if n.assignee:
        extra.append(f"👤 {e(n.assignee.replace(',', ', '))}")
    if n.file_id:
        extra.append(f"📎 {e(describe_media(n.file_type, n.file_name))}")
    tail = ("\n" + " · ".join(extra)) if extra else ""
    return f"{head}\n\n📌 <b>#{n.number}</b> · {e(n.text)}{tail}"


LIST_TITLES = {"open": "📋 Ochiq zametkalar", "done": "✅ Bajarilganlar", "all": "🗂 Barcha zametkalar"}
FILTER_TITLES = {"today": "bugungi", "tomorrow": "ertangi", "important": "muhim", "overdue": "muddati o'tgan"}


def notes_list(
    notes: list[Note], total: int, status: str, category: str | None, flt: str | None, offset: int,
    assignee: str | None = None,
) -> str:
    title = LIST_TITLES.get(status, LIST_TITLES["open"])
    if flt:
        title += f" ({FILTER_TITLES[flt]})"
    if category:
        title += f" · #{e(category)}"
    if assignee:
        title += f" · 👤 {e(assignee)}"
    if not notes:
        return f"{title}\n\nHech narsa yo'q 🎉" if status == "open" else f"{title}\n\nHech narsa topilmadi."
    lines = [f"{title} — {total} ta", ""] + [note_line(n) for n in notes]
    if total > offset + len(notes) or offset:
        lines.append(f"\n<i>{offset + 1}–{offset + len(notes)} / {total}</i>")
    return "\n".join(lines)


def client_line(c: Client) -> str:
    s = f"👤 <b>#{c.number}</b> {e(c.name)}"
    if c.phone:
        s += f" · 📞 {e(c.phone)}"
    if c.assignee:
        s += f" · 🙋 {e(c.assignee)}"
    if c.category:
        s += f" <i>#{e(c.category.name)}</i>"
    return s


def clients_list(
    clients: list[Client], total: int, category: str | None, offset: int, archived: bool = False,
    assignee: str | None = None,
) -> str:
    title = "🗄 Arxivdagi mijozlar" if archived else "👥 Mijozlar"
    if category:
        title += f" · #{e(category)}"
    if assignee:
        title += f" · 🙋 {e(assignee)}"
    if not clients:
        return f"{title}\n\nHali mijoz yo'q. Qo'shish: <code>mijoz qo'sh: Ali, Vali</code>"
    lines = [f"{title} — {total} ta", ""] + [client_line(c) for c in clients]
    if total > offset + len(clients) or offset:
        lines.append(f"\n<i>{offset + 1}–{offset + len(clients)} / {total}</i>")
    return "\n".join(lines)


def activity_list(
    items: list[ClientActivity], worked: bool, period: str, category: str | None, offset: int, limit: int,
    assignee: str | None = None,
) -> str:
    head = "✅ Ishlangan mijozlar" if worked else "⏳ Ishlanmagan mijozlar"
    head += f" ({period_title(period)})"
    if category:
        head += f" · #{e(category)}"
    if assignee:
        head += f" · 🙋 {e(assignee)}"
    if not items:
        return f"{head}\n\n" + ("Hali hech kim bilan ishlanmagan." if worked else "Hammasi bilan ishlangan 🎉")
    page = items[offset: offset + limit]
    lines = [f"{head} — {len(items)} ta", ""]
    for a in page:
        extra = f" · {a.count} marta" if worked and a.count > 1 else ""
        lines.append(f"{'✔️' if worked else '⏳'} 👤 <b>#{a.client.number}</b> {e(a.client.name)} — <i>oxirgi: {ago(a.last_at)}</i>{extra}")
    if len(items) > limit:
        lines.append(f"\n<i>{offset + 1}–{offset + len(page)} / {len(items)}</i>")
    return "\n".join(lines)


def client_card(c: Client, items: list[Interaction], total: int) -> str:
    lines = [f"👤 <b>#{c.number} {e(c.name)}</b>"]
    if c.phone:
        lines.append(f"📞 {e(c.phone)}")
    if c.category:
        lines.append(f"🏷 #{e(c.category.name)}")
    if c.assignee:
        lines.append(f"🙋 Mas'ul: {e(c.assignee)}" + (" (har kuni eslatiladi)" if c.remind_assignee else ""))
    if c.comment:
        lines.append(f"💬 {e(c.comment)}")
    if c.archived:
        lines.append("🗄 arxivda")
    lines.append(f"📅 qo'shilgan: {to_local(c.created_at):%d.%m.%Y}")
    lines.append(f"\n<b>Aloqalar tarixi</b> ({total} ta):")
    if not items:
        lines.append("— hali ishlanmagan")
    for i in items:
        txt = f": {e(i.text)}" if i.text else ""
        lines.append(f"• {to_local(i.created_at):%d.%m %H:%M} — {e(i.author_name)}{txt}")
    return "\n".join(lines)


def stats_text(s: Stats, period: str) -> str:
    lines = [
        f"📊 <b>Statistika</b> ({period_title(period)})", "",
        f"📋 Ochiq zametkalar: <b>{s.open}</b> (muhim: {s.important_open})",
        f"✅ Bajarilgan (jami): <b>{s.done}</b>",
    ]
    if period != "all":
        lines += [f"➕ Shu davrda yozilgan: {s.created}", f"✔️ Shu davrda bajarilgan: {s.closed}"]
    pct = f" ({round(100 * s.clients_worked / s.clients)}%)" if s.clients else ""
    lines += [
        "", f"👥 Mijozlar: <b>{s.clients}</b>",
        f"🤝 Ishlangan mijozlar: <b>{s.clients_worked}</b>{pct}, aloqalar: {s.interactions}",
    ]
    if s.top_doers:
        lines += ["", "🏆 <b>Eng ko'p bajarganlar:</b>"] + [f"  {e(n or '—')}: {c}" for n, c in s.top_doers]
    if s.top_workers:
        lines += ["", "🤝 <b>Mijozlar bilan eng faol:</b>"] + [f"  {e(n or '—')}: {c}" for n, c in s.top_workers]
    return "\n".join(lines)


def diary_text(d: Diary, period: str) -> str:
    lines = [f"📔 <b>Kundalik</b> — {period_title(period)}", ""]
    if not (d.created or d.closed or d.interactions):
        return lines[0] + "\n\nBu davrda hech narsa yozilmagan."
    if d.created:
        lines.append(f"📝 <b>Yozildi ({len(d.created)}):</b>")
        lines += [f"  {to_local(n.created_at):%H:%M} {note_line(n)}" for n in d.created]
        lines.append("")
    if d.closed:
        lines.append(f"✅ <b>Bajarildi ({len(d.closed)}):</b>")
        lines += [f"  {to_local(n.done_at):%H:%M} #{n.number} {e(n.text)} — <i>{e(n.done_by)}</i>" for n in d.closed]
        lines.append("")
    if d.interactions:
        lines.append(f"🤝 <b>Mijozlar bilan ({len(d.interactions)}):</b>")
        for i in d.interactions:
            txt = f": {e(i.text)}" if i.text else ""
            lines.append(f"  {to_local(i.created_at):%H:%M} #{i.client.number} {e(i.client.name)} — <i>{e(i.author_name)}</i>{txt}")
    return "\n".join(lines).strip()


def categories_text(rows: list[tuple[str, int, int, int]]) -> str:
    if not rows:
        return "🏷 Hali kategoriya yo'q.\nZametka yoki mijozga <code>#teg</code> qo'shsangiz, avtomatik yaratiladi."
    lines = ["🏷 <b>Kategoriyalar</b>", ""]
    for name, o, d, k in rows:
        lines.append(f"<b>#{e(name)}</b> — ochiq: {o}, bajarilgan: {d}, mijozlar: {k}")
    return "\n".join(lines)


def reminder_saved(r: Reminder) -> str:
    return f"⏰ Eslatma qo'yildi: <b>{to_local(r.remind_at):%d.%m.%Y %H:%M}</b>\n{e(r.text)}"


def reminders_list(items: list[Reminder]) -> str:
    if not items:
        return "⏰ Faol eslatmalar yo'q."
    lines = ["⏰ <b>Faol eslatmalar</b>", ""]
    lines += [f"<b>{r.id}</b>. {to_local(r.remind_at):%d.%m %H:%M} — {e(r.text)}" for r in items]
    return "\n".join(lines)


def note_card(n: Note) -> str:
    """Bitta zametka: o'zgartirilgandan keyin ko'rsatish uchun."""
    lines = [f"📌 <b>#{n.number}</b> · {e(n.text)}"]
    if n.file_id:
        lines.append(f"📎 {e(describe_media(n.file_type, n.file_name))}")
    if n.category:
        lines.append(f"🏷 #{e(n.category.name)}")
    if n.important:
        lines.append("❗ muhim")
    if n.due_at:
        lines.append(f"⏰ {n.due_at:%d.%m.%Y %H:%M}")
    if n.assignee:
        lines.append(f"👤 {e(n.assignee.replace(',', ', '))}")
    return "\n".join(lines)


def recurring_list(items) -> str:
    from bot.services.recurring import describe
    if not items:
        return ("🔁 Takroriy vazifalar yo'q.\nQo'shish: <code>har kuni 9 da kassani tekshirish</code>, "
                "<code>har dushanba hisobot</code>, <code>har oyning 5-sanasida ijara</code>")
    lines = ["🔁 <b>Takroriy vazifalar</b>", ""]
    for r in items:
        extra = (f" <i>#{e(r.category)}</i>" if r.category else "") + (f" 👤 {e(r.assignee)}" if r.assignee else "")
        lines.append(f"<b>{r.id}</b>. {e(r.text)}{extra} — <i>{describe(r.rule, r.hour, r.minute)}</i>")
    return "\n".join(lines)


def recurring_saved(r) -> str:
    from bot.services.recurring import describe
    extra = (f"\n🏷 #{e(r.category)}" if r.category else "") + (f"\n👤 {e(r.assignee)}" if r.assignee else "")
    return f"🔁 <b>{e(r.text)}</b>\n📅 {describe(r.rule, r.hour, r.minute)}{extra}"


SETTINGS_LABELS = {
    "morning_summary": "☀️ Ertalabki reja (09:00)",
    "daily_summary": "📔 Kechki kundalik (20:00)",
    "weekly_summary": "📊 Haftalik hisobot (juma 18:00)",
    "due_alerts": "⏰ Muddat kelganda xabar",
}


def settings_text(cs) -> str:
    lines = ["⚙️ <b>Sozlamalar</b>", "Tugmani bosib yoqing yoki o'chiring:", ""]
    for field, label in SETTINGS_LABELS.items():
        lines.append(f"{'✅' if getattr(cs, field) else '⬜️'} {label}")
    return "\n".join(lines)


def agenda_text(today: list[Note], overdue: list[Note], important: list[Note], open_count: int, stale) -> str:
    if not (today or overdue or important or stale or open_count):
        return "🏖 Bugunga reja bo'sh — ochiq ish ham, kutayotgan mijoz ham yo'q.\nYangi ish: <code>tovar sanash kerak</code>"
    lines = []
    if overdue:
        lines += [f"🔥 <b>Muddati o'tgan ({len(overdue)}):</b>"] + [f"  {note_line(n)}" for n in overdue[:10]] + [""]
    if today:
        lines += [f"📅 <b>Bugun ({len(today)}):</b>"] + [f"  {note_line(n)}" for n in today[:15]] + [""]
    if important:
        lines += [f"❗ <b>Muhim ({len(important)}):</b>"] + [f"  {note_line(n)}" for n in important[:10]] + [""]
    if stale:
        lines.append(f"📞 <b>7 kundan beri gaplashilmagan mijozlar ({len(stale)}):</b>")
        lines += [f"  👤 #{a.client.number} {e(a.client.name)} — <i>{ago(a.last_at)}</i>" for a in stale[:10]]
        lines.append("")
    lines.append(f"📋 Jami ochiq ishlar: <b>{open_count}</b>")
    return "\n".join(lines).strip()


def due_alert(n: Note) -> str:
    who = f"\n👤 {e(n.assignee.replace(',', ', '))}" if n.assignee else ""
    return f"📌 <b>#{n.number}</b> · {e(n.text)}\n⏰ {n.due_at:%d.%m %H:%M}{who}"


def import_report(report, added: list[Client], dupes: list[Client], category: str | None, assignee: str | None) -> str:
    lines = [f"📊 Qatorlar: <b>{report.rows}</b>", f"➕ Yangi mijozlar: <b>{len(added)}</b>"]
    if dupes:
        lines.append(f"♻️ Bazada bor edi: {len(dupes)}")
    if report.duplicates_in_file:
        lines.append(f"🔁 Fayl ichida takrorlangan: {report.duplicates_in_file}")
    if report.skipped_test:
        lines.append(f"🧪 Test lidlar o'tkazib yuborildi: {report.skipped_test}")
    if report.skipped_empty:
        lines.append(f"⚠️ Ismsiz qatorlar: {report.skipped_empty}")
    if category:
        lines.append(f"🏷 Kategoriya: #{e(category)}")
    if assignee:
        lines.append(f"🙋 Mas'ul: {e(assignee)}")
    labels = {"name": "ism", "phone": "telefon", "interest": "qiziqish", "status": "holat", "comment": "izoh",
              "category": "kategoriya", "source": "manba", "campaign": "reklama", "created": "sana",
              "assignee": "mas'ul"}
    cols = ", ".join(f"{labels.get(f, f)} ← <code>{e(h[:25])}</code>" for f, h in report.columns.items())
    lines.append(f"\n🧭 Ustunlar: {cols}")
    if added:
        lines.append("\n<b>Birinchi mijozlar:</b>")
        lines += [client_line(c) for c in added[:10]]
        if len(added) > 10:
            lines.append(f"… va yana {len(added) - 10} ta. Hammasi: <code>mijozlar</code>")
    return "\n".join(lines)


def assignee_digest(who: str, clients: list[Client], head: str) -> str:
    lines = [f"<b>{head}</b>", ""]
    for c in clients[:20]:
        phone = f" · 📞 {e(c.phone)}" if c.phone else ""
        lines.append(f"👤 <b>#{c.number}</b> {e(c.name)}{phone}")
    if len(clients) > 20:
        lines.append(f"… va yana {len(clients) - 20} ta")
    lines.append("\nIshlagach yozing: <code>Ali bilan gaplashdim</code> yoki ✔️ tugmasini bosing")
    return "\n".join(lines)


def note_caption(n: Note) -> str:
    """Qayta yuborilgan fayl izohi: reply qilinsa kontekst (📌 #N) orqali zametka aniqlanadi."""
    tag = f" #{e(n.category.name)}" if n.category else ""
    return f"📌 <b>#{n.number}</b> · {e(n.text)}{tag}"


def files_list(notes: list[Note], total: int, category: str | None, ftype: str | None) -> str:
    titles = {"photo": "🖼 Rasmlar", "voice": "🎤 Ovozli xabarlar", "video": "🎬 Videolar", "document": "📄 Hujjatlar"}
    title = titles.get(ftype or "", "📎 Fayllar")
    if category:
        title += f" · #{e(category)}"
    lines = [f"{title} — {total} ta", ""]
    for n in notes:
        date = f"{to_local(n.created_at):%d.%m}"
        lines.append(f"{media_icon(n.file_type)} <b>#{n.number}</b> {e(n.text)} <i>· {date} · {e(n.author_name)}</i>")
    if total > len(notes):
        lines.append(f"\n<i>Oxirgi {len(notes)} tasi ko'rsatildi</i>")
    lines.append("\nOlish: tugmani bosing yoki <code>3 ni tashla</code>")
    return "\n".join(lines)


def clip(text: str) -> str:
    return text if len(text) <= MAX_LEN else text[:MAX_LEN] + "\n…"


HELP = """🤖 <b>Men jamoaning kundaligiman!</b> Meni tag qilib (@{u}) oddiy gapiring.

<b>📝 Zametkalar</b>
• <code>tovar sanash kerak</code>, <code>! #ombor @ali ertaga kechqurun inventarizatsiya</code>
• <code>nima ishlar bor</code>, <code>#ombor</code>, <code>bugungi</code>, <code>muhimlar</code>, <code>mening ishlarim</code>
• <code>3 bo'ldi</code>, <code>uchinchisi tayyor</code>, <code>oxirgisi bo'ldi</code>, <code>hisobotni tugatdim</code>
• <code>3 ni qaytar</code>, <code>3 o'chir</code>, <code>3 tuzat: ...</code>, <code>3 muhim</code>, <code>3 ni ertaga sur</code>, <code>3 ni @vali ga ber</code>
• <code>tovarni qidir</code>
• Istalgan xabarga reply: <code>@{u}</code>, <code>@{u} eslab qol #narx</code>, <code>@{u} @vali ertaga</code>, <code>@{u} ertaga 9 da eslat</code>

<b>📎 Fayllar</b>
• Rasm/ovoz/fayl/kontakt/lokatsiyaga reply: <code>@{u} eslab qol #shartnoma</code>
• <code>#shartnoma fayllari</code>, <code>rasmlar</code>, <code>ovozli xabarlarni tashla</code>, <code>3 ni tashla</code>

<b>👥 Mijozlar</b>
• <code>mijoz qo'sh: Ali, Vali #vip</code>; Excel/CSV faylni tashlang — hammasini kiritaman
• <code>Ali bilan gaplashdim, 3 kundan keyin qayta qo'ng'iroq</code>, <code>Valiga taklif yubordim</code>
• <code>kimlar qoldi</code>, <code>bu hafta ishlanmaganlar #vip</code>, <code>Ali haqida</code>
• <code>Ali telefoni +998...</code>, <code>Ali izoh: ...</code>, <code>mijoz 5 o'chir</code>
• <code>Ali, Vali ni @sardor ga o'tkaz, eslatib tur</code>, <code>@sardor mijozlari</code>

<b>🔁 Eslatma va jadval</b>
• <code>eslat ertaga 9:00 hisobot</code>, <code>har kuni 9 da kassani tekshirish</code>, <code>har dushanba hisobot</code>
• <code>eslatmalar</code>, <code>takroriylar</code>, <code>kun rejasi</code>, <code>sozlamalar</code>

<b>📔 Hisobot</b>
• <code>kun yakuni</code>, <code>kecha nima qildik</code>, <code>statistika</code>, <code>kategoriyalar</code>, <code>excel qilib ber</code>

<b>💬 Reply bilan</b>
• Zametkamga: <code>bo'ldi</code>, <code>muhim</code>, <code>ertaga sur</code>, <code>tashla</code>
• Mijoz kartochkasiga: <code>gaplashdim, narx kelishildi</code>
• Eslatmaga: <code>bo'ldi</code> yoki <code>10 minutdan keyin yana eslat</code>

Salom-alik, latifa, motivatsiya, soat va sana ham tushunaman 😊 /help"""
