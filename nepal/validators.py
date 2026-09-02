"""Validators for the identifiers Nepali businesses actually key in."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

from .dates import ascii_digits
from django.utils.translation import gettext_lazy as _

_PAN_RE = re.compile(r"^\d{9}$")
# NTC/Ncell/Smart mobiles are 98x/97x/96x/988...; landlines are 0<area><number>.
_MOBILE_RE = re.compile(r"^(?:\+?977)?9[678]\d{8}$")
_LANDLINE_RE = re.compile(r"^(?:\+?977)?0?\d{1,3}\d{6,7}$")


def validate_pan(value):
    """PAN/VAT numbers issued by the IRD are nine digits."""
    if not value:
        return
    digits = ascii_digits(value).replace(" ", "").replace("-", "")
    if not _PAN_RE.match(digits):
        raise ValidationError(
            _("PAN/VAT number must be exactly 9 digits."),
            code="invalid_pan",
        )


def validate_nepali_phone(value):
    if not value:
        return
    digits = ascii_digits(value).replace(" ", "").replace("-", "")
    if _MOBILE_RE.match(digits) or _LANDLINE_RE.match(digits):
        return
    raise ValidationError(
        _("That phone number does not look right — use a mobile (98########) or a landline (01-#######)."),
        code="invalid_phone",
    )


def normalise_phone(value: str) -> str:
    """Strip separators and the +977 country code for storage/lookup."""
    if not value:
        return ""
    digits = ascii_digits(value).replace(" ", "").replace("-", "").replace("+", "")
    if digits.startswith("977") and len(digits) > 10:
        digits = digits[3:]
    return digits


# Nepali plates read like "बा १२ प ३४५६" / "BA 12 PA 3456"; provinces added
# numbers such as "प्रदेश ३-०१-००१ च ०४३४". Keep validation permissive — a
# rejected plate is worse than a slightly odd one.
_VEHICLE_RE = re.compile(r"^[\wऀ-ॿ][\wऀ-ॿ \-./]{2,29}$")


def validate_vehicle_no(value):
    if not value:
        return
    if not _VEHICLE_RE.match(value.strip()):
        raise ValidationError(
            _("Unexpected characters in the vehicle number."),
            code="invalid_vehicle",
        )
