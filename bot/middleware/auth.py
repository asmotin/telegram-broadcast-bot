from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.auth import is_admin


class AdminAuthMiddleware(BaseMiddleware):
    """
    Blocks private-chat messages and callback queries from non-admins.
    Group events (my_chat_member) bypass this — they don't go through
    message/callback_query observers.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")

        if user is None:
            return await handler(event, data)

        # Only restrict private chats; group messages pass through
        if isinstance(event, Message) and event.chat.type != "private":
            return await handler(event, data)

        if is_admin(user.id):
            return await handler(event, data)

        # Not authorized — inform user with their ID so they can ask an admin
        if isinstance(event, Message):
            name = user.full_name or str(user.id)
            await event.answer(
                f"⛔ <b>Нет доступа</b>\n\n"
                f"Вы не авторизованы для работы с этим ботом.\n\n"
                f"Ваш Telegram ID: <code>{user.id}</code>\n"
                f"Передайте его администратору для получения доступа.",
                parse_mode="HTML",
            )
        elif isinstance(event, CallbackQuery):
            await event.answer(
                f"⛔ Нет доступа. Ваш ID: {user.id}",
                show_alert=True,
            )
        # Stop further processing
