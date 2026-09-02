"""Form field + widget for entering dates the way the paper shows them (BS)."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy

from .dates import InvalidBikramSambatDate, ascii_digits, bs_to_ad, parse_bs


class BikramSambatDateInput(forms.TextInput):
    """A plain text input that live-previews the AD date over HTMX."""

    template_name = "nepal/widgets/bs_date.html"

    def __init__(self, attrs=None):
        defaults = {
            "class": "input input-bordered w-full font-mono",
            "placeholder": "2082-05-17",
            "inputmode": "numeric",
            "autocomplete": "off",
            "hx-get": reverse_lazy("nepal:date_preview"),
            "hx-trigger": "input changed delay:250ms, load",
            "hx-target": "next .bs-date-preview",
            "hx-swap": "innerHTML",
        }
        defaults.update(attrs or {})
        super().__init__(defaults)


class BikramSambatDateField(forms.CharField):
    """Accepts `2082-05-17`, `2082/5/17` or `२०८२।०५।१७`; stores `2082-05-17`.

    `clean()` returns the *normalised BS string* so it can be assigned straight
    to a `date_bs` CharField; use `.to_ad()` for the Gregorian mirror.
    """

    widget = BikramSambatDateInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 12)
        kwargs.setdefault("label", "मिति (बि.सं.)")
        kwargs.setdefault("help_text", "ढाँचा: YYYY-MM-DD")
        super().__init__(*args, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return ""
        try:
            bs = parse_bs(value)
        except InvalidBikramSambatDate as exc:
            raise ValidationError(str(exc), code="invalid_bs_date") from exc
        return f"{bs.year}-{bs.month:02d}-{bs.day:02d}"

    @staticmethod
    def to_ad(value):
        return bs_to_ad(value) if value else None


class NepaliDecimalField(forms.DecimalField):
    """A decimal field that also accepts Devanagari digits (`१२.५`)."""

    def to_python(self, value):
        if isinstance(value, str):
            value = ascii_digits(value).replace(",", "").strip()
        return super().to_python(value)
