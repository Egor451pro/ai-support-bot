# AI Telegram Support Bot (HITL)

Асинхронный Telegram-бот поддержки: **aiogram 3** + **FastAPI** + **PostgreSQL (Supabase)** + **Groq (Llama 3)**.

## Режимы

- `AI_MODE` — ответы по `data/faq.txt` через Groq, кнопка «Позвать оператора»
- `OPERATOR_MODE` — AI выключен; сообщения клиента в Support Group; Reply оператора → клиенту; `/close` → снова AI

## Быстрый старт

```powershell
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m bot.main
```

Заполните в `.env`: `BOT_TOKEN`, `DATABASE_URL`, `GROQ_API_KEY`, `SUPPORT_GROUP_CHAT_ID`.  
Локально: `MODE=polling`. На Render: `MODE=webhook` + `WEBHOOK_BASE_URL` + `WEBHOOK_SECRET`.  
Health: `GET http://127.0.0.1:8000/health` (HTTP 200).

## Структура (ключевые файлы)

- `bot/config.py` — pydantic-settings
- `bot/database/models.py` — User, ChatState, MessageLog, MessageBinding
- `bot/database/connection.py` — async engine / session factory
- `bot/middlewares/db_session.py` — сессия БД в хендлеры
- `bot/handlers/client.py` — /start, Groq, эскалация
- `bot/handlers/operator.py` — Reply-мост и /close
- `bot/main.py` — FastAPI, `/health`, polling/webhook

## Деплой

См. `render.yaml`: `MODE=webhook`, `WEBHOOK_BASE_URL=https://...`, `WEBHOOK_SECRET=...`, start:  
`uvicorn bot.main:app --host 0.0.0.0 --port $PORT`  
Webhook при остановке/засыпании не удаляется (`drop_pending_updates=False`).
