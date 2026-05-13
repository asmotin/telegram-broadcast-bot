from aiogram import Router
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.types import ChatMemberUpdated

from shared.database import SessionLocal
from shared.models import Group

router = Router()


def _upsert_group(telegram_id: int, title: str, username: str | None, active: int):
    with SessionLocal() as db:
        group = db.query(Group).filter_by(telegram_id=telegram_id).first()
        if group:
            group.title = title
            group.username = username
            group.is_active = active
        else:
            db.add(Group(telegram_id=telegram_id, title=title, username=username, is_active=active))
        db.commit()


@router.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def bot_added(event: ChatMemberUpdated):
    chat = event.chat
    _upsert_group(chat.id, chat.title or str(chat.id), chat.username, active=1)


@router.my_chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def bot_removed(event: ChatMemberUpdated):
    chat = event.chat
    _upsert_group(chat.id, chat.title or str(chat.id), chat.username, active=0)
