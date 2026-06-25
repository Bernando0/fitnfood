"""LLM calls against the OpenAI-compatible endpoint (alem.ai / Gemma)."""
from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from bot.config import settings
from bot.llm.prompts import ANALYZE_SYSTEM, SUMMARY_SYSTEM

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


async def analyze_photo(image_b64: str, context_text: str) -> dict:
    """Vision call: recognise the dish, estimate nutrition, write a coach reply.

    Returns the parsed JSON as a dict. On any failure returns {"is_food": False}.
    """
    try:
        resp = await _client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=900,
            temperature=0.75,
            messages=[
                {"role": "system", "content": ANALYZE_SYSTEM},
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
            ],
        )
    except Exception:  # noqa: BLE001 — never crash the handler on an API hiccup
        log.exception("analyze_photo request failed")
        return {"is_food": False}

    content = resp.choices[0].message.content or ""
    data = _extract_json(content)
    if data is None:
        log.warning("could not parse analyze JSON: %r", content[:200])
        return {"is_food": False}
    return data


async def daily_summary(report_text: str) -> str:
    """Text call: turn the day's meals into one warm group summary."""
    resp = await _client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=1200,
        temperature=0.6,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": report_text},
        ],
    )
    return (resp.choices[0].message.content or "").strip()
