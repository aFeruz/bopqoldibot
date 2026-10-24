from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.actions import execute, send
from bot.parser import Intent, normalize, parse, parse_note, parse_numbers, split_names
from bot.services import reminders as rem_svc
from bot.services.common import local_now

router = Router()

# /buyruq -> erkin matn shabloni (parserga beriladi)
TEMPLATES = {
    "notes": "zametkalar {}",
    "done_list": "bajarilganlar {}",
    "find": "qidir {}",
    "client": "mijoz qo'sh: {}",
    "clients": "mijozlar {}",
    "notworked": "ishlanmaganlar {}",
    "workedlist": "ishlanganlar {}",
    "card": "mijoz {}",
    "categories": "kategoriyalar",
    "stats": "statistika {}",
    "diary": "kundalik {}",
    "remind": "eslat {}",
    "reminders": "eslatmalar",
    "export": "export",
    "my": "mening ishlarim",
    "agenda": "kun rejasi",
    "recurring": "takroriylar",
    "settings": "sozlamalar",
}


async def run(msg: Message, intent: Intent, session: AsyncSession, bot_username: str) -> None:
    await send(msg, await execute(intent, msg, session, bot_username))


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(msg: Message, session: AsyncSession, bot_username: str) -> None:
    await run(msg, Intent("help"), session, bot_username)


@router.message(Command(*TEMPLATES))
async def cmd_template(msg: Message, command: CommandObject, session: AsyncSession, bot_username: str) -> None:
    args = (command.args or "").strip()
    await run(msg, parse(TEMPLATES[command.command].format(args).strip(), local_now()), session, bot_username)


@router.message(Command("note"))
async def cmd_note(msg: Message, command: CommandObject, session: AsyncSession, bot_username: str) -> None:
    text = command.args or (msg.reply_to_message.text if msg.reply_to_message else "") or ""
    intent = parse_note(text, local_now()) if text else Intent("note")
    await run(msg, intent, session, bot_username)


@router.message(Command("done", "undo", "del"))
async def cmd_status(msg: Message, command: CommandObject, session: AsyncSession, bot_username: str) -> None:
    args = (command.args or "").strip()
    kind = {"done": "done", "undo": "undo", "del": "delete"}[command.command]
    nums = parse_numbers(args)
    if nums:
        intent = Intent(kind, numbers=nums)
    elif args and kind == "done":
        intent = Intent("done_text", text=normalize(args))
    else:
        await msg.reply(f"Raqam yozing: <code>/{command.command} 3</code>")
        return
    await run(msg, intent, session, bot_username)


@router.message(Command("edit"))
async def cmd_edit(msg: Message, command: CommandObject, session: AsyncSession, bot_username: str) -> None:
    await run(msg, parse(f"{command.args or ''}".replace(" ", " o'zgartir: ", 1), local_now()), session, bot_username)


@router.message(Command("worked"))
async def cmd_worked(msg: Message, command: CommandObject, session: AsyncSession, bot_username: str) -> None:
    args = (command.args or "").strip()
    if not args:
        await msg.reply("Kim bilan? <code>/worked Ali, Vali: narx kelishildi</code>")
        return
    names, _, comment = args.partition(":")
    await run(msg, Intent("worked", names=split_names(normalize(names)), text=comment.strip()), session, bot_username)


@router.message(Command("archive"))
async def cmd_archive(msg: Message, command: CommandObject, session: AsyncSession, bot_username: str) -> None:
    await run(msg, Intent("client_archive", numbers=parse_numbers(command.args or "")), session, bot_username)


@router.message(Command("dailyon", "dailyoff"))
async def cmd_daily(msg: Message, command: CommandObject, session: AsyncSession) -> None:
    on = command.command == "dailyon"
    await rem_svc.set_daily(session, msg.chat.id, on)
    await msg.reply("📔 Har kuni kechqurun kundalik yuboraman." if on else "📔 Kunlik xulosa o'chirildi.")
