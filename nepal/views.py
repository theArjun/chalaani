"""Tiny HTMX endpoints backing the Bikram Sambat date input."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from . import dates
from .forms import BikramSambatDateInput


@require_GET
@login_required
def date_preview(request):
    """Echo back what a typed BS date means in AD — fires on every keystroke."""
    raw = ""
    for value in request.GET.values():
        if value.strip():
            raw = value.strip()
            break
    if not raw:
        return render(request, "nepal/date_preview.html", {})
    try:
        bs = dates.parse_bs(raw)
    except dates.InvalidBikramSambatDate as exc:
        return render(request, "nepal/date_preview.html", {"error": str(exc)})
    ad = bs.to_datetime_date()
    return render(
        request,
        "nepal/date_preview.html",
        {
            "ad": ad,
            "bs_np": dates.bs_display(bs),
            "weekday": dates.format_bs(bs, "{weekday_np}"),
            "fy": dates.fiscal_year(bs),
        },
    )


@require_GET
@login_required
def date_input(request):
    """Re-render a BS date input, pre-filled — used by the आज (today) button."""
    name = request.GET.get("name", "date_bs")
    value = request.GET.get("value", "")
    if value == "today":
        today = dates.today_bs()
        value = f"{today.year}-{today.month:02d}-{today.day:02d}"
    widget = BikramSambatDateInput()
    return HttpResponse(widget.render(name, value, attrs={"id": f"id_{name}"}))
