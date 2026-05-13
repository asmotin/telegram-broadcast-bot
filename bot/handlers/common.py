from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "👋 <b>Привет!</b>\n\n"
            "Я бот для рассылки сообщений по группам.\n\n"
            "<b>Команды для администраторов:</b>\n"
            "/groups — список групп\n"
            "/labels — список ярлыков\n"
            "/newlabel &lt;название&gt; — создать ярлык\n"
            "/dellabel &lt;название&gt; — удалить ярлык\n"
            "/assign — назначить ярлык группе\n"
            "/unassign — снять ярлык с группы\n"
            "/broadcast — отправить рассылку\n"
            "/history — история рассылок",
            parse_mode="HTML",
        )
