from __future__ import annotations

from html import escape

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    ChatMode,
    ChatState,
    MessageBinding,
    MessageLog,
    MessageRole,
    User,
    utcnow,
)


async def upsert_user(
    session: AsyncSession,
    *,
    user_id: int,
    username: str | None,
    full_name: str,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id, username=username, full_name=full_name)
        session.add(user)
    else:
        user.username = username
        user.full_name = full_name
    await session.commit()
    await session.refresh(user)
    return user


async def get_or_create_chat_state(session: AsyncSession, chat_id: int) -> ChatState:
    state = await session.get(ChatState, chat_id)
    if state is None:
        state = ChatState(chat_id=chat_id, mode=ChatMode.AI_MODE, last_interaction=utcnow())
        session.add(state)
        await session.commit()
        await session.refresh(state)
    return state


async def touch_chat_state(session: AsyncSession, state: ChatState) -> ChatState:
    state.last_interaction = utcnow()
    await session.commit()
    await session.refresh(state)
    return state


async def set_chat_mode(
    session: AsyncSession,
    state: ChatState,
    mode: ChatMode,
    *,
    assigned_operator_id: int | None = None,
    clear_operator: bool = False,
) -> ChatState:
    state.mode = mode
    state.last_interaction = utcnow()
    if mode == ChatMode.OPERATOR_MODE and assigned_operator_id is not None:
        state.assigned_operator_id = assigned_operator_id
    if mode == ChatMode.AI_MODE or clear_operator:
        state.assigned_operator_id = None
    await session.commit()
    await session.refresh(state)
    return state


async def assign_operator_if_empty(
    session: AsyncSession,
    state: ChatState,
    operator_id: int,
) -> ChatState:
    if state.assigned_operator_id is None:
        state.assigned_operator_id = operator_id
        state.last_interaction = utcnow()
        await session.commit()
        await session.refresh(state)
    return state


async def add_message_log(
    session: AsyncSession,
    *,
    chat_id: int,
    role: MessageRole,
    content: str,
    max_len: int = 4000,
) -> MessageLog:
    entry = MessageLog(chat_id=chat_id, role=role, content=content[:max_len])
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def get_recent_messages(
    session: AsyncSession,
    chat_id: int,
    limit: int = 8,
) -> list[MessageLog]:
    result = await session.execute(
        select(MessageLog)
        .where(MessageLog.chat_id == chat_id)
        .order_by(MessageLog.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def trim_message_log(session: AsyncSession, chat_id: int, keep: int = 50) -> int:
    result = await session.execute(
        select(MessageLog.id)
        .where(MessageLog.chat_id == chat_id)
        .order_by(MessageLog.created_at.desc())
        .offset(keep)
    )
    ids = list(result.scalars().all())
    if not ids:
        return 0
    await session.execute(delete(MessageLog).where(MessageLog.id.in_(ids)))
    await session.commit()
    return len(ids)


async def create_binding(
    session: AsyncSession,
    *,
    operator_msg_id: int,
    client_chat_id: int,
) -> MessageBinding:
    binding = MessageBinding(operator_msg_id=operator_msg_id, client_chat_id=client_chat_id)
    session.add(binding)
    await session.commit()
    await session.refresh(binding)
    return binding


async def get_binding_by_operator_msg(
    session: AsyncSession,
    operator_msg_id: int,
) -> MessageBinding | None:
    result = await session.execute(
        select(MessageBinding).where(MessageBinding.operator_msg_id == operator_msg_id)
    )
    return result.scalar_one_or_none()


async def list_operator_mode_chats(session: AsyncSession) -> list[ChatState]:
    result = await session.execute(
        select(ChatState)
        .where(ChatState.mode == ChatMode.OPERATOR_MODE)
        .order_by(ChatState.last_interaction.desc())
    )
    return list(result.scalars().all())


async def get_latest_binding_for_client(
    session: AsyncSession,
    client_chat_id: int,
) -> MessageBinding | None:
    result = await session.execute(
        select(MessageBinding)
        .where(MessageBinding.client_chat_id == client_chat_id)
        .order_by(MessageBinding.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def format_customer_label(user: User) -> str:
    uname = f"@{user.username}" if user.username else "без username"
    return f"{escape(user.full_name)} ({escape(uname)}, id={user.id})"
