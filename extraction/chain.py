"""LangChain call that turns a chalani photo into a `ChalaniExtraction`."""

from __future__ import annotations

import base64
import logging

from django.conf import settings

from nepal import dates as npdates

from .prompts import SYSTEM_PROMPT, USER_INSTRUCTION
from .schema import ChalaniExtraction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class ExtractionUnavailable(RuntimeError):
    """Raised when extraction is switched off or has no API key to work with."""


def build_chain():
    """`ChatAnthropic(...).with_structured_output(ChalaniExtraction)` — that's the pipeline."""
    if not settings.EXTRACTION_ENABLED:
        raise ExtractionUnavailable(
            _("CHALAANI_EXTRACTION_ENABLED=0 — AI reading is switched off.")
        )
    if not settings.ANTHROPIC_API_KEY:
        raise ExtractionUnavailable(
            _(
                "ANTHROPIC_API_KEY is not set — put it in .env; AI reading is disabled without it."
            )
        )

    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(
        model=settings.EXTRACTION_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=8000,
        reasoning_effort=settings.EXTRACTION_EFFORT,
        timeout=240,
        max_retries=2,
    )
    # `json_schema` uses Claude's own structured-output support rather than a
    # forced tool call, which keeps optional fields genuinely optional.
    return llm.with_structured_output(ChalaniExtraction, method="json_schema")


def extract_from_image(
    image_bytes: bytes, mime_type: str = "image/jpeg"
) -> ChalaniExtraction:
    from langchain_core.messages import HumanMessage, SystemMessage

    today = npdates.today_bs()
    instruction = USER_INSTRUCTION.format(
        today_bs=f"{today.year}-{today.month:02d}-{today.day:02d}",
        today_ad=today.to_datetime_date().isoformat(),
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {
                    "type": "image",
                    "base64": base64.standard_b64encode(image_bytes).decode("ascii"),
                    "mime_type": mime_type,
                },
                {"type": "text", "text": instruction},
            ]
        ),
    ]
    logger.info(
        "chalani extraction: sending %d bytes to %s",
        len(image_bytes),
        settings.EXTRACTION_MODEL,
    )
    return build_chain().invoke(messages)
