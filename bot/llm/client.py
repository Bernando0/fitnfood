"""LLM calls against the OpenAI-compatible endpoint (alem.ai / Gemma)."""
from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from bot.config import settings
from bot.llm.prompts import (
    build_analyze_system,
    build_ask_system,
    build_eat_system,
    build_summary_system,
)

log = logging.getLogger(__name__)

_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def _extract_json(text: str) -> dict | None:
    """Parse a JSON object, tolerating stray prose or ```json fences around it."""
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            pass
    return None


async def _analyze(messages: list[dict]) -> dict:
    try:
        resp = await _client.chat.completions.create(
            model=settings.llm_model, max_tokens=900, temperature=0.75, messages=messages
        )
    except Exception:  # noqa: BLE001 — never crash the handler on an API hiccup
        log.exception("analyze request failed")
        return {"is_food": False}
    content = resp.choices[0].message.content or ""
    data = _extract_json(content)
    if data is None:
        log.warning("could not parse analyze JSON: %r", content[:200])
        return {"is_food": False}
    return data


async def analyze_photo(image_b64: str, context_text: str, tone: str = "savage") -> dict:
    """Vision call: recognise the dish, estimate nutrition, write a coach reply."""
    return await _analyze(
        [
            {"role": "system", "content": build_analyze_system(tone)},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": context_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ]
    )


async def analyze_text(description: str, context_text: str, tone: str = "savage") -> dict:
    """Text-only meal log (no photo): estimate the dish/КБЖУ from a description."""
    user = (
        context_text
        + f"\n\nФОТО НЕТ. Человек написал словами, что съел: «{description}». "
        "Оцени блюда и КБЖУ по описанию (учитывай порции и способ готовки), поставь зону и верни JSON."
    )
    return await _analyze(
        [
            {"role": "system", "content": build_analyze_system(tone)},
            {"role": "user", "content": user},
        ]
    )


async def _chat(system: str, user: str, max_tokens: int = 600) -> str:
    resp = await _client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        temperature=0.7,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


async def daily_summary(report_text: str, tone: str = "savage") -> str:
    """Turn the day's meals into one group summary in the chat's tone."""
    return await _chat(build_summary_system(tone), report_text, max_tokens=1200)


async def ask_coach(question: str, status_text: str, tone: str = "savage") -> str:
    """Answer a nutrition question, grounded in the user's status/history."""
    user = f"Статус человека:\n{status_text}\n\nВопрос: {question}"
    return await _chat(build_ask_system(tone), user)


async def eat_advice(status_text: str, products: str | None, tone: str = "savage") -> str:
    """Recommend what to eat next, given history/goal and optional products."""
    user = f"Статус человека:\n{status_text}"
    if products and products.strip():
        user += f"\n\nПродукты, что есть под рукой: {products.strip()}."
    else:
        user += "\n\nПродукты не указаны — посоветуй из обычно доступного."
    return await _chat(build_eat_system(tone), user)
