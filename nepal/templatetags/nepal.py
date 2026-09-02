"""Template filters that render dates, digits, money and units.

Each one follows the active language: Devanagari script and digits under `ne`,
Latin script and ASCII digits under `en`. Bikram Sambat itself never changes —
only how it is written.
"""

from __future__ import annotations

import datetime

from django import template
from django.utils import timezone
from django.utils.translation import get_language, gettext as _, ngettext

from .. import dates, numbers, units

register = template.Library()


def in_nepali() -> bool:
    language = get_language() or ""
    return language.startswith("ne")


@register.filter(name="bs")
def bs(value):
    """AD date -> `2082-05-17` (ASCII in both languages — it is an identifier)."""
    return dates.format_bs(value)


@register.filter(name="bs_date")
def bs_date(value):
    """AD date -> `१७ भदौ २०८२` / `17 Bhadau 2082`."""
    if value is None:
        return ""
    if in_nepali():
        return dates.bs_display(value)
    return dates.format_bs(value, "{d} {month_en} {y}")


@register.filter(name="bs_date_long")
def bs_date_long(value):
    """AD date -> `मंगलबार, १७ भदौ २०८२` / `Mangalbar, 17 Bhadau 2082`."""
    if value is None:
        return ""
    if in_nepali():
        return dates.format_bs(value, "{weekday_np}, {d} {month_np} {y}", devanagari=True)
    return dates.format_bs(value, "{weekday_en}, {d} {month_en} {y}")


@register.filter(name="fy")
def fy(value):
    return dates.fiscal_year(value)


@register.filter(name="num")
def num(value):
    """Digits in the active script: `२०८२-०५-१७` / `2082-05-17`."""
    if value is None:
        return ""
    return dates.devanagari_digits(value) if in_nepali() else str(value)


@register.filter(name="money")
def money(value):
    """`१२,३४,५६७.५०` / `12,34,567.50` — lakh/crore grouping either way."""
    return numbers.format_amount(value, devanagari=in_nepali())


@register.filter(name="qty")
def qty(value):
    """Quantities read better without trailing zeros: `12.500` -> `12.5`."""
    text = numbers.group_indian(value, decimals=3)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return dates.devanagari_digits(text) if in_nepali() else text


@register.filter(name="in_words")
def in_words(value):
    if in_nepali():
        return numbers.amount_in_words_np(value)
    return numbers.amount_in_words_en(value)


@register.filter(name="unit_label")
def unit_label(code):
    return units.unit_label(code, devanagari=in_nepali())


@register.simple_tag
def today_bs():
    return bs_date(dates.today_bs().to_datetime_date())


@register.simple_tag
def current_fiscal_year():
    return dates.fiscal_year(dates.today_bs())


@register.filter(name="status_badge")
def status_badge(status):
    """Theme classes for a chalani status chip (see static/css/theme.css)."""
    known = {"extracting", "draft", "verified", "billed"}
    return f"chip chip-{status}" if status in known else "chip chip-draft"


@register.filter(name="ago")
def ago(value):
    """`2 days ago` / `२ दिन अघि` — relative time, in the active language.

    Takes a `date` or a `datetime`. The absolute Bikram Sambat date stays the
    headline everywhere; this is the human-scale hint next to it.
    """
    if not value:
        return ""
    now = timezone.localtime()
    if isinstance(value, datetime.datetime):
        delta = now - timezone.localtime(value)
    else:
        delta = now.date() - value
        delta = datetime.timedelta(days=delta.days)

    future = delta.total_seconds() < 0
    delta = abs(delta)
    days = delta.days
    seconds = int(delta.total_seconds())

    if isinstance(value, datetime.datetime) and days == 0:
        if seconds < 60:
            text = _("just now")
            return dates.devanagari_digits(text) if in_nepali() else text
        if seconds < 3600:
            n = seconds // 60
            text = ngettext("%(n)d minute", "%(n)d minutes", n) % {"n": n}
        else:
            n = seconds // 3600
            text = ngettext("%(n)d hour", "%(n)d hours", n) % {"n": n}
    elif days == 0:
        text = _("today")
        return dates.devanagari_digits(text) if in_nepali() else text
    elif days == 1:
        text = _("tomorrow") if future else _("yesterday")
        return dates.devanagari_digits(text) if in_nepali() else text
    elif days < 30:
        text = ngettext("%(n)d day", "%(n)d days", days) % {"n": days}
    elif days < 365:
        n = days // 30
        text = ngettext("%(n)d month", "%(n)d months", n) % {"n": n}
    else:
        n = days // 365
        text = ngettext("%(n)d year", "%(n)d years", n) % {"n": n}

    phrase = (_("in %(time)s") if future else _("%(time)s ago")) % {"time": text}
    return dates.devanagari_digits(phrase) if in_nepali() else phrase
