from datetime import datetime

from aiogram.types import Chat, Message, MessageEntity, User

from bot.handlers.mention import strip_mention

BOT_ID = 42


def make(text, entities):
    return Message(
        message_id=1, date=datetime.now(), chat=Chat(id=-1, type="supergroup"),
        from_user=User(id=1, is_bot=False, first_name="F"), text=text, entities=entities,
    )


def test_strip_username_mention():
    text = "@Kundalik_bot 3 bo'ldi"
    msg = make(text, [MessageEntity(type="mention", offset=0, length=13)])
    assert strip_mention(msg, "kundalik_bot", BOT_ID) == ("3 bo'ldi", True)


def test_mention_in_middle_with_emoji():
    text = "😀 tovar sanash @kundalik_bot kerak"
    # 😀 UTF-16 da 2 birlik
    msg = make(text, [MessageEntity(type="mention", offset=16, length=13)])
    assert strip_mention(msg, "kundalik_bot", BOT_ID) == ("😀 tovar sanash  kerak", True)


def test_other_mention_ignored():
    msg = make("@someone salom", [MessageEntity(type="mention", offset=0, length=8)])
    assert strip_mention(msg, "kundalik_bot", BOT_ID) == ("@someone salom", False)
