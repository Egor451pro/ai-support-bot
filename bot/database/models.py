from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Enum, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ChatMode(str, enum.Enum):
    AI_MODE = "AI_MODE"
    OPERATOR_MODE = "OPERATOR_MODE"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    operator = "operator"
    system = "system"


class User(Base):
    """Telegram user profile. Primary key = telegram user id."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")


class ChatState(Base):
    """Active session state for a private chat (chat_id = telegram private chat id)."""

    __tablename__ = "chat_states"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    mode: Mapped[ChatMode] = mapped_column(
        Enum(ChatMode, name="chat_mode", native_enum=False),
        default=ChatMode.AI_MODE,
        nullable=False,
    )
    last_interaction: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    assigned_operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class MessageLog(Base):
    """Short-term conversational memory for the LLM (last N messages per chat)."""

    __tablename__ = "message_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", native_enum=False),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
        nullable=False,
    )


class MessageBinding(Base):
    """Links a support-group message to a client chat for Reply routing."""

    __tablename__ = "message_bindings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator_msg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    client_chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
