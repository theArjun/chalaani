"""Turning an AI reading into rows a clerk can verify.

Matching is deliberately conservative: a wrong vendor link is much more
expensive than an unlinked draft, because the link is what every later report
adds up by. Anything below the confidence bar is left null with the paper text
preserved, and the verify screen asks a human.
"""

from __future__ import annotations

import difflib
import logging
from decimal import Decimal, InvalidOperation

from nepal.dates import ascii_digits
from nepal.units import normalise_unit

from .models import Chalani, ChalaniItem, Item, Vendor, _search_key

logger = logging.getLogger(__name__)

#: difflib ratio a fuzzy name match must clear before we link it automatically.
MATCH_CUTOFF = 0.86


def _decimal(value, places="0.001") -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(ascii_digits(value)).replace(",", "").strip())
        # `Decimal("nan")` and `Decimal("inf")` parse fine but no column takes
        # them — treat them as unread, the way any other rubbish is treated.
        if not number.is_finite():
            return None
        return number.quantize(Decimal(places))
    except (InvalidOperation, ValueError):
        return None


def _best_match(candidates: dict[str, object], *keys: str):
    """`candidates` maps search_key -> object. Exact first, then close-enough."""
    wanted = [_search_key(k) for k in keys if k]
    for key in wanted:
        if key in candidates:
            return candidates[key]
    for key in wanted:
        # A supplier writes "Shree Ram Hardware" on one slip and
        # "Shree Ram Hardware Pvt. Ltd." on the next.
        contained = [v for k, v in candidates.items() if key and (key in k or k in key)]
        if len(contained) == 1:
            return contained[0]
    for key in wanted:
        close = difflib.get_close_matches(
            key, list(candidates), n=1, cutoff=MATCH_CUTOFF
        )
        if close:
            return candidates[close[0]]
    return None


def match_vendor(organization, *, name=None, name_np=None, pan=None) -> Vendor | None:
    vendors = list(Vendor.objects.for_org(organization).filter(is_active=True))
    if pan:
        digits = ascii_digits(pan).strip()
        for vendor in vendors:
            if vendor.pan_no and ascii_digits(vendor.pan_no).strip() == digits:
                return vendor  # PAN is an exact identifier — trust it outright
    index = {}
    for vendor in vendors:
        for label in (vendor.name, vendor.name_np):
            if label:
                index.setdefault(_search_key(label), vendor)
    return _best_match(index, name_np, name)


def match_item(organization, *, description=None, description_en=None) -> Item | None:
    items = list(Item.objects.for_org(organization).filter(is_active=True))
    index = {}
    for item in items:
        for label in (item.name, item.name_np):
            if label:
                index.setdefault(_search_key(label), item)
    return _best_match(index, description, description_en)


def apply_extraction(chalani: Chalani, extraction) -> Chalani:
    """Copy an AI reading onto a draft chalani. Never overwrites clerk input."""
    data = extraction

    if not chalani.vendor_id:
        chalani.vendor = match_vendor(
            chalani.organization,
            name=data.vendor_name,
            name_np=data.vendor_name_np,
            pan=data.vendor_pan,
        )
    if not chalani.chalani_no and data.chalani_no:
        chalani.chalani_no = str(data.chalani_no)[:50]
    if not chalani.date_bs and data.date_bs:
        chalani.date_bs = ascii_digits(str(data.date_bs))[:12]
    if not chalani.date_bs and not chalani.date and data.date_ad:
        # Only an AD date on the slip — `sync_dates()` fills the BS mirror in.
        from datetime import date as _date

        try:
            chalani.date = _date.fromisoformat(ascii_digits(str(data.date_ad))[:10])
        except ValueError:
            pass
    if not chalani.vehicle_no and data.vehicle_no:
        chalani.vehicle_no = str(data.vehicle_no)[:30]
    if not chalani.received_by and data.received_by:
        chalani.received_by = str(data.received_by)[:100]
    if not chalani.remarks:
        remarks = " · ".join(
            str(part)
            for part in (data.destination, data.driver_name, data.remarks)
            if part
        )
        chalani.remarks = remarks[:300]

    if not chalani.items.exists():
        lines = []
        for position, row in enumerate(data.items, start=1):
            qty = _decimal(row.qty)
            if qty is None and not row.description:
                continue
            lines.append(
                ChalaniItem(
                    chalani=chalani,
                    item=match_item(
                        chalani.organization,
                        description=row.description,
                        description_en=row.description_en,
                    ),
                    description=(row.description or "")[:200],
                    qty=qty if qty is not None else Decimal("0"),
                    unit=normalise_unit(row.unit),
                    rate=_decimal(row.rate, "0.01"),
                    line_no=position,
                )
            )
        ChalaniItem.objects.bulk_create(lines)
    return chalani


def next_line_no(chalani: Chalani) -> int:
    last = chalani.items.order_by("-line_no").values_list("line_no", flat=True).first()
    return (last or 0) + 1
