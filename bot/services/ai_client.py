from __future__ import annotations

import logging
from typing import Any

from groq import AsyncGroq

from bot.config import Settings, get_settings
from bot.services.faq_loader import load_faq

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """Ты — вежливый AI-ассистент службы поддержки студии «Северный Микрофон» в Telegram.
Отвечай кратко, по делу и на русском языке, если пользователь не просит иначе.
Используй только базу знаний FAQ ниже. Если ответа нет в FAQ или вопрос требует человека —
честно скажи об этом и предложи нажать кнопку «Позвать оператора».
Не выдумывай цены, акции и политики, которых нет в FAQ.

=== FAQ ===
{faq}
=== КОНЕЦ FAQ ===
"""


class AIClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = AsyncGroq(api_key=self.settings.groq_api_key, timeout=30.0)

    def build_system_prompt(self) -> str:
        return SYSTEM_TEMPLATE.format(faq=load_faq())

    async def generate_reply(self, history: list[dict[str, str]]) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt()},
            *history,
        ]
        try:
            completion = await self._client.chat.completions.create(
                model=self.settings.groq_model,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )
            content = completion.choices[0].message.content
            if not content:
                return (
                    "Извините, не удалось сформировать ответ. "
                    "Попробуйте ещё раз или позовите оператора."
                )
            return content.strip()
        except Exception:
            logger.exception("Groq API error")
            return (
                "Сейчас AI временно недоступен. "
                "Попробуйте позже или нажмите «Позвать оператора»."
            )
