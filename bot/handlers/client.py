from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.crud import (
    add_message_log,
    create_binding,
    format_customer_label,
    get_or_create_chat_state,
    get_recent_messages,
    set_chat_mode,
    touch_chat_state,
    trim_message_log,
    upsert_user,
)
from bot.database.models import ChatMode, MessageRole
from bot.keyboards.inline import CALL_OPERATOR_CALLBACK, call_operator_keyboard
from bot.services.ai_client import AIClient

logger = logging.getLogger(__name__)


async def _ensure_user_and_state(message_or_cb_user, chat_id: int, session: AsyncSession):
    full_name = " ".join(
        part for part in (message_or_cb_user.first_name, message_or_cb_user.last_name) if part
    ).strip() or str(message_or_cb_user.id)
    user = await upsert_user(
        session,
        user_id=message_or_cb_user.id,
        username=message_or_cb_user.username,
        full_name=full_name,
    )
    state = await get_or_create_chat_state(session, chat_id)
    return user, state


def create_client_router() -> Router:
    router = Router(name="client")
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

    @router.message(CommandStart())
    async def cmd_start(message: Message, session: AsyncSession) -> None:
        if message.from_user is None:
            return
        user, _state = await _ensure_user_and_state(message.from_user, message.chat.id, session)
        await message.answer(
            f"Здравствуйте, {user.full_name}!\n"
            "Я AI-ассистент студии «Северный Микрофон».\n"
            "Спросите про цены, расписание или отмену записи.\n"
            "Если нужна помощь человека — нажмите «Позвать оператора».",
            reply_markup=call_operator_keyboard(),
        )

    @router.message(F.text, ~F.text.startswith("/"))
    async def client_text_message(
        message: Message,
        session: AsyncSession,
        settings: Settings,
        ai_client: AIClient,
    ) -> None:
        if message.from_user is None or not message.text:
            return

        user, state = await _ensure_user_and_state(message.from_user, message.chat.id, session)
        await touch_chat_state(session, state)

        if state.mode == ChatMode.OPERATOR_MODE:
            await add_message_log(
                session,
                chat_id=message.chat.id,
                role=MessageRole.user,
                content=message.text,
            )
            header = f"💬 От {format_customer_label(user)}"
            body = escape(message.text)
            sent = await message.bot.send_message(
                settings.support_group_chat_id,
                f"{header}\n\n{body}",
            )
            await create_binding(
                session,
                operator_msg_id=sent.message_id,
                client_chat_id=message.chat.id,
            )
            await message.answer("Сообщение передано оператору. Ожидайте ответа.")
            return

        await add_message_log(
            session,
            chat_id=message.chat.id,
            role=MessageRole.user,
            content=message.text,
        )
        recent = await get_recent_messages(
            session,
            message.chat.id,
            limit=settings.message_history_limit,
        )
        history = [
            {
                "role": "assistant"
                if item.role in (MessageRole.assistant, MessageRole.operator)
                else "user",
                "content": item.content,
            }
            for item in recent
            if item.role in (MessageRole.user, MessageRole.assistant, MessageRole.operator)
        ]
        reply_text = await ai_client.generate_reply(history)
        await message.answer(
            reply_text,
            reply_markup=call_operator_keyboard(),
            parse_mode=None,
        )
        await add_message_log(
            session,
            chat_id=message.chat.id,
            role=MessageRole.assistant,
            content=reply_text,
        )
        await trim_message_log(session, message.chat.id, keep=settings.message_log_keep)

    @router.callback_query(F.data == CALL_OPERATOR_CALLBACK)
    async def call_operator(
        callback: CallbackQuery,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        if callback.from_user is None or callback.message is None:
            await callback.answer("Недостаточно данных.", show_alert=True)
            return

        if callback.from_user.id != callback.message.chat.id:
            await callback.answer("Недостаточно прав.", show_alert=True)
            return

        user, state = await _ensure_user_and_state(
            callback.from_user,
            callback.message.chat.id,
            session,
        )
        if state.mode == ChatMode.OPERATOR_MODE:
            await callback.answer("Оператор уже подключён.")
            return

        recent = await get_recent_messages(session, callback.message.chat.id, limit=6)
        digest_lines = []
        for item in recent:
            prefix = {
                MessageRole.user: "Клиент",
                MessageRole.assistant: "AI",
                MessageRole.operator: "Оператор",
                MessageRole.system: "System",
            }.get(item.role, item.role.value)
            digest_lines.append(f"{prefix}: {escape(item.content[:300])}")
        digest = "\n".join(digest_lines) if digest_lines else "(история пуста)"

        text = (
            "🆘 <b>Эскалация к оператору</b>\n"
            f"Клиент: {format_customer_label(user)}\n\n"
            f"<b>Последние сообщения:</b>\n{digest}\n\n"
            "Ответьте <b>Reply</b> на это сообщение, чтобы написать клиенту.\n"
            "Команда /close — завершить диалог "
            "(можно без Reply, если активен один клиент).\n"
            "Клиент также может завершить диалог командой /close или /ai."
        )

        try:
            sent = await callback.bot.send_message(settings.support_group_chat_id, text)
        except Exception:
            logger.exception(
                "Failed to notify support group chat_id=%s",
                settings.support_group_chat_id,
            )
            await callback.answer(
                "Не удалось связаться с группой поддержки. "
                "Проверьте SUPPORT_GROUP_CHAT_ID и что бот добавлен в группу админом.",
                show_alert=True,
            )
            await callback.message.answer(
                "⚠️ Вызов оператора не удался: группа поддержки недоступна.\n"
                "Админу нужно указать реальный SUPPORT_GROUP_CHAT_ID в .env "
                "и добавить бота в группу администратором."
            )
            return

        await set_chat_mode(session, state, ChatMode.OPERATOR_MODE)
        await create_binding(
            session,
            operator_msg_id=sent.message_id,
            client_chat_id=callback.message.chat.id,
        )
        await callback.answer("Оператор вызван")
        await callback.message.answer(
            "Вы подключены к оператору. AI временно отключён.\n"
            "Пишите сюда — сообщения увидит служба поддержки."
        )

    return router
