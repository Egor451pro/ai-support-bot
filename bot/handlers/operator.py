from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.crud import (
    add_message_log,
    assign_operator_if_empty,
    create_binding,
    get_binding_by_operator_msg,
    get_or_create_chat_state,
    list_operator_mode_chats,
    set_chat_mode,
)
from bot.database.models import ChatMode, MessageRole, User

logger = logging.getLogger(__name__)


def _is_support_group(message: Message, settings: Settings) -> bool:
    return message.chat.id == settings.support_group_chat_id


def _parse_close_chat_id(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    arg = parts[1].strip()
    if arg.lstrip("-").isdigit():
        return int(arg)
    return None


async def _close_client_session(
    *,
    bot,
    session: AsyncSession,
    client_chat_id: int,
) -> None:
    state = await get_or_create_chat_state(session, client_chat_id)
    await set_chat_mode(session, state, ChatMode.AI_MODE, clear_operator=True)
    await bot.send_message(
        client_chat_id,
        "Диалог с оператором завершён. Снова на связи AI-ассистент — задайте вопрос.",
    )


def create_operator_router() -> Router:
    router = Router(name="operator")

    @router.message(Command("close"))
    async def cmd_close_group(message: Message, session: AsyncSession, settings: Settings) -> None:
        if not _is_support_group(message, settings):
            return

        client_chat_id = _parse_close_chat_id(message.text)

        if client_chat_id is None and message.reply_to_message is not None:
            binding = await get_binding_by_operator_msg(
                session, message.reply_to_message.message_id
            )
            if binding is None:
                await message.reply(
                    "На это сообщение нет привязки клиента.\n"
                    "Reply на карточку эскалации / «💬 От …», "
                    "или просто <code>/close</code> без Reply "
                    "(закроет последний активный диалог)."
                )
                return
            client_chat_id = binding.client_chat_id

        if client_chat_id is None:
            active = await list_operator_mode_chats(session)
            if not active:
                await message.reply("Нет активных диалогов в OPERATOR_MODE.")
                return
            if len(active) == 1:
                client_chat_id = active[0].chat_id
            else:
                lines = [
                    "Несколько активных диалогов. Сделайте Reply на сообщение клиента "
                    "или укажите ID:",
                ]
                for state in active[:10]:
                    user = await session.get(User, state.chat_id)
                    label = (
                        f"{user.full_name} (@{user.username})"
                        if user and user.username
                        else (user.full_name if user else str(state.chat_id))
                    )
                    lines.append(f"• <code>/close {state.chat_id}</code> — {label}")
                await message.reply("\n".join(lines))
                return

        await _close_client_session(
            bot=message.bot,
            session=session,
            client_chat_id=client_chat_id,
        )
        await message.reply(
            f"Диалог закрыт, клиент <code>{client_chat_id}</code> возвращён в AI_MODE."
        )

    @router.message(F.reply_to_message)
    async def operator_reply_bridge(
        message: Message,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        if not _is_support_group(message, settings):
            return
        if message.from_user is None or message.from_user.is_bot:
            return
        if message.text and message.text.startswith("/"):
            return
        if message.reply_to_message is None:
            return

        binding = await get_binding_by_operator_msg(session, message.reply_to_message.message_id)
        if binding is None:
            return

        text = message.text or message.caption
        if not text:
            await message.reply("Сейчас поддерживается только текстовый ответ клиенту.")
            return

        await message.bot.send_message(
            binding.client_chat_id,
            f"👨‍💼 Оператор:\n{text}",
            parse_mode=None,
        )

        await create_binding(
            session,
            operator_msg_id=message.message_id,
            client_chat_id=binding.client_chat_id,
        )

        state = await get_or_create_chat_state(session, binding.client_chat_id)
        if state.mode == ChatMode.OPERATOR_MODE:
            await assign_operator_if_empty(session, state, message.from_user.id)

        await add_message_log(
            session,
            chat_id=binding.client_chat_id,
            role=MessageRole.operator,
            content=text,
        )

    return router
