from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from bot.config import Settings, get_settings
from bot.database.connection import dispose_engine, init_db
from bot.handlers import setup_routers
from bot.middlewares.db_session import DbSessionMiddleware
from bot.services.ai_client import AIClient
from bot.services.faq_loader import faq_content_hash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

_polling_task: asyncio.Task | None = None


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    dp = Dispatcher()
    dp["settings"] = settings
    dp["ai_client"] = AIClient(settings)
    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(setup_routers())
    return dp


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _polling_task
    settings: Settings = app.state.settings
    bot: Bot = app.state.bot
    dp: Dispatcher = app.state.dp

    await init_db()
    logger.info("Database schema ensured")

    if settings.mode == "webhook":
        webhook_url = (
            f"{settings.webhook_base_url.rstrip('/')}/webhook/{settings.webhook_secret}"
        )
        # Keep webhook across free-tier sleeps so Telegram can wake Render.
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=False,
        )
        logger.info("Webhook registered: %s", webhook_url)
    else:
        # Local debug: remove webhook and use long-polling.
        await bot.delete_webhook(drop_pending_updates=False)
        _polling_task = asyncio.create_task(dp.start_polling(bot))
        logger.info("Long-polling started in background task")

    logger.info("Bot is ready, mode=%s", settings.mode)

    yield

    if _polling_task is not None:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
        _polling_task = None

    # CRITICAL: do NOT call delete_webhook() on shutdown.
    # After Render free sleep, Telegram must still deliver updates to this URL.

    await bot.session.close()
    await dispose_engine()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    bot = create_bot(settings)
    dp = create_dispatcher(settings)

    docs_disabled = settings.mode == "webhook"
    app = FastAPI(
        title="AI Telegram Support Bot",
        lifespan=lifespan,
        docs_url=None if docs_disabled else "/docs",
        redoc_url=None if docs_disabled else "/redoc",
        openapi_url=None if docs_disabled else "/openapi.json",
    )
    app.state.settings = settings
    app.state.bot = bot
    app.state.dp = dp

    @app.get("/health")
    async def health() -> JSONResponse:
        faq_ok = Path(settings.faq_path).is_file()
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "mode": settings.mode,
                "faq_loaded": faq_ok,
                "faq_hash": faq_content_hash() if faq_ok else None,
            },
        )

    @app.post("/webhook/{secret}")
    async def telegram_webhook(
        secret: str,
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> JSONResponse:
        if secret != settings.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
        if x_telegram_bot_api_secret_token != settings.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid secret token header")

        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": bot})
        await dp.feed_update(bot, update)
        return JSONResponse({"ok": True})

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    # Pass the app object directly — string "bot.main:app" re-imports the module
    # when launched via `python -m bot.main` (as __main__), which used to attach
    # the same routers twice and raise RuntimeError.
    uvicorn.run(
        app,
        host=settings.host,  # 0.0.0.0
        port=settings.port,  # Render injects PORT
        reload=False,
    )


if __name__ == "__main__":
    main()
