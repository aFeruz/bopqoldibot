"""Xabardagi media (rasm, ovoz, video, fayl) ni aniqlash, tavsiflash va qayta yuborish.

Bot faylni yuklab olmaydi: Telegram bergan file_id saqlanadi va shu bot orqali qayta yuboriladi.
"""

from dataclasses import dataclass

from aiogram.types import Message

TYPE_LABELS = {
    "photo": "🖼 Rasm",
    "voice": "🎤 Ovozli xabar",
    "video": "🎬 Video",
    "video_note": "📹 Video-xabar",
    "audio": "🎵 Audio",
    "document": "📄 Fayl",
    "animation": "🎞 GIF",
}
NO_CAPTION = {"video_note"}


@dataclass
class Media:
    file_id: str
    type: str
    name: str | None = None
    duration: int | None = None


def extract_media(msg: Message | None) -> Media | None:
    if msg is None:
        return None
    if msg.photo:
        return Media(msg.photo[-1].file_id, "photo")
    if msg.animation:  # animation document'dan oldin: GIF ham document sifatida keladi
        return Media(msg.animation.file_id, "animation", msg.animation.file_name, msg.animation.duration)
    for kind in ("voice", "video", "video_note", "audio", "document"):
        obj = getattr(msg, kind, None)
        if obj:
            name = getattr(obj, "file_name", None) or getattr(obj, "title", None)
            return Media(obj.file_id, kind, name, getattr(obj, "duration", None))
    return None


def _duration(sec: int | None) -> str:
    return f"{sec // 60}:{sec % 60:02d}" if sec else ""


def describe(media_type: str | None, name: str | None = None, duration: int | None = None) -> str:
    """Zametka matni berilmaganda: "🎤 Ovozli xabar · 0:23", "📄 shartnoma.pdf"."""
    label = TYPE_LABELS.get(media_type or "", "📎 Fayl")
    parts = [label if not name else f"{label.split(' ', 1)[0]} {name}"]
    if duration:
        parts.append(_duration(duration))
    return " · ".join(parts)


def icon(media_type: str | None) -> str:
    return TYPE_LABELS.get(media_type or "", "📎").split(" ", 1)[0]


async def send_media(bot, chat_id: int, file_id: str, media_type: str, caption: str | None = None,
                     reply_to: int | None = None) -> None:
    method = getattr(bot, f"send_{media_type}")
    kwargs = {media_type: file_id, "reply_to_message_id": reply_to}
    if caption and media_type not in NO_CAPTION:
        kwargs["caption"] = caption[:1000]
    await method(chat_id, **kwargs)
