from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.crud import get_or_create_chat_state, set_chat_mode
from bot.database.models import ChatMode


def create_common_router() -> Router:
    router = Router(name="common")

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "Я AI-ассистент студии «Северный Микрофон».\n"
            "Задайте вопрос по FAQ или нажмите «Позвать оператора».\n\n"
            "Операторы в группе поддержки:\n"
            "• отвечайте Reply на сообщение клиента\n"
            "• /close — закрыть диалог (в группе или в личке с ботом)\n\n"
            "Служебное:\n"
            "• /chatid — показать ID этого чата (нужен для SUPPORT_GROUP_CHAT_ID)\n"
            "• /ai — принудительно вернуть диалог в AI-режим"
        )

    @router.message(Command("chatid"))
    async def cmd_chatid(message: Message) -> None:
        await message.answer(
            f"chat_id = <code>{message.chat.id}</code>\n"
            f"type = {message.chat.type}"
        )

    @router.message(Command("ai"), F.chat.type == ChatType.PRIVATE)
    async def cmd_ai(message: Message, session: AsyncSession) -> None:
        state = await get_or_create_chat_state(session, message.chat.id)
        await set_chat_mode(session, state, ChatMode.AI_MODE, clear_operator=True)
        await message.answer("Режим сброшен на AI_MODE. Можете снова задавать вопросы.")

    @router.message(Command("close"), F.chat.type == ChatType.PRIVATE)
    async def cmd_close_private(message: Message, session: AsyncSession) -> None:
        state = await get_or_create_chat_state(session, message.chat.id)
        if state.mode != ChatMode.OPERATOR_MODE:
            await message.answer("Сейчас вы уже в AI-режиме. Оператор не подключён.")
            return
        await set_chat_mode(session, state, ChatMode.AI_MODE, clear_operator=True)
        await message.answer(
            "Диалог с оператором завершён. Снова на связи AI-ассистент — задайте вопрос."
        )

    return router
