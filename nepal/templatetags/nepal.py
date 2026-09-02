"""Template filters that render Nepali dates, digits and money."""

from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe

from .. import dates, numbers, units

register = template.Library()


@register.filter(name="bs")
def bs(value):
    """AD date -> `2082-05-17`."""
    return dates.format_bs(value)


@register.filter(name="bs_np")
def bs_np(value):
    """AD date -> `१७ भदौ २०८२`."""
    return dates.bs_display(value)


@register.filter(name="bs_long")
def bs_long(value):
    """AD date -> `मंगलबार, १७ भदौ २०८२`."""
    return dates.format_bs(value, "{weekday_np}, {d} {month_np} {y}", devanagari=True)


@register.filter(name="fy")
def fy(value):
    return dates.fiscal_year(value)


@register.filter(name="nepnum")
def nepnum(value):
    """Any text/number -> Devanagari digits."""
    return dates.devanagari_digits(value)


@register.filter(name="nprs")
def nprs(value):
    """Decimal -> `१२,३४,५६७.५०` (lakh/crore grouping, Devanagari digits)."""
    return numbers.format_amount(value, devanagari=True)


@register.filter(name="rs")
def rs(value):
    """Decimal -> `12,34,567.50` (lakh/crore grouping, ASCII digits)."""
    return numbers.format_amount(value)


@register.filter(name="qty")
def qty(value):
    """Quantities read better without trailing zeros: `12.500` -> `12.5`."""
    text = numbers.group_indian(value, decimals=3)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return dates.devanagari_digits(text)


@register.filter(name="in_words_np")
def in_words_np(value):
    return numbers.amount_in_words_np(value)


@register.filter(name="in_words_en")
def in_words_en(value):
    return numbers.amount_in_words_en(value)


@register.filter(name="unit_np")
def unit_np(code):
    return units.unit_label(code)


@register.simple_tag
def today_bs():
    return dates.bs_display(dates.today_bs())


@register.simple_tag
def current_fiscal_year():
    return dates.fiscal_year(dates.today_bs())


@register.filter(name="status_badge")
def status_badge(status):
    """daisyUI badge class for a chalani status."""
    return {
        "extracting": "badge-warning",
        "draft": "badge-ghost",
        "verified": "badge-success",
        "billed": "badge-info",
    }.get(status, "badge-ghost")


@register.filter(name="nbsp")
def nbsp(value):
    return mark_safe(str(value).replace(" ", "&nbsp;"))
