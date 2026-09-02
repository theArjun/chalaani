"""Background extraction: upload returns immediately, HTMX polls for the draft."""

from __future__ import annotations

import logging
import mimetypes

from django.utils import timezone

logger = logging.getLogger(__name__)


def enqueue_extraction(chalani) -> str | None:
    """Queue a photo for reading. Returns the Django-Q task id, if queued.

    With `Q_SYNC=1` (or a cluster that isn't running) django-q2 falls back to
    running the task inline, which is what the test suite relies on.
    """
    from django_q.tasks import async_task

    from chalani.models import Chalani

    if not chalani.photo:
        return None
    Chalani.objects.filter(pk=chalani.pk).update(
        status=Chalani.Status.EXTRACTING, extraction_error=""
    )
    return async_task(
        "extraction.tasks.run_extraction",
        chalani.pk,
        task_name=f"chalani-{chalani.pk}",
        group="chalani-extraction",
    )


def run_extraction(chalani_id: int) -> str:
    """Read the photo, apply what came back, and always land on a usable status."""
    from chalani.models import Chalani
    from chalani.services import apply_extraction

    from .chain import ExtractionUnavailable, extract_from_image

    chalani = Chalani.objects.select_related("organization").get(pk=chalani_id)
    try:
        with chalani.photo.open("rb") as fh:
            data = fh.read()
        mime = mimetypes.guess_type(chalani.photo.name)[0] or "image/jpeg"
        extraction = extract_from_image(data, mime)
    except ExtractionUnavailable as exc:
        _fail(chalani, str(exc))
        return "unavailable"
    except Exception as exc:  # noqa: BLE001 — a draft a human can fix beats a 500
        logger.exception("chalani %s extraction failed", chalani_id)
        _fail(chalani, f"{type(exc).__name__}: {exc}")
        return "error"

    apply_extraction(chalani, extraction)
    chalani.extracted_by_ai = True
    chalani.extraction_error = ""
    chalani.status = Chalani.Status.DRAFT
    chalani.raw_extraction = {
        "extracted_at": timezone.now().isoformat(),
        "data": extraction.model_dump(mode="json"),
    }
    chalani.save()
    return "ok"


def _fail(chalani, message: str) -> None:
    from chalani.models import Chalani

    Chalani.objects.filter(pk=chalani.pk).update(
        status=Chalani.Status.DRAFT,
        extraction_error=message[:2000],
        extracted_by_ai=False,
    )
