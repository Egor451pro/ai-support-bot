from aiogram import Router

from bot.handlers.client import create_client_router
from bot.handlers.common import create_common_router
from bot.handlers.operator import create_operator_router


def setup_routers() -> Router:
    """Build a fresh router tree. Safe to call more than once."""
    root = Router(name="root")
    root.include_router(create_common_router())
    root.include_router(create_client_router())
    root.include_router(create_operator_router())
    return root
