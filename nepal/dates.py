"""Bikram Sambat <-> Gregorian helpers.

Everything is stored in the database as an AD `date` (so ordering, range
queries and reports are plain SQL) and rendered as BS at the edges. The one
exception is `Chalani.date_bs`, which keeps the BS string exactly as it was
written on the paper — useful when a supplier's numbering disagrees with the
converted date.
"""

from __future__ import annotations

import datetime as _dt
import re

import nepali_datetime as ndt
from django.utils.translation import gettext_lazy as _

# Baishakh .. Chaitra
MONTHS_NP = [
    "बैशाख",
    "जेठ",
    "असार",
    "श्रावण",
    "भदौ",
    "आश्विन",
    "कार्तिक",
    "मंसिर",
    "पुष",
    "माघ",
    "फाल्गुन",
    "चैत्र",
]
MONTHS_EN = [
    "Baishakh",
    "Jestha",
    "Ashar",
    "Shrawan",
    "Bhadau",
    "Ashoj",
    "Kartik",
    "Mangsir",
    "Poush",
    "Magh",
    "Falgun",
    "Chaitra",
]

# The Nepali week starts on Sunday.
WEEKDAYS_NP = ["आइतबार", "सोमबार", "मंगलबार", "बुधबार", "बिहीबार", "शुक्रबार", "शनिबार"]
WEEKDAYS_EN = [
    "Aaitabar",
    "Sombar",
    "Mangalbar",
    "Budhabar",
    "Bihibar",
    "Sukrabar",
    "Sanibar",
]

#: Nepali fiscal year opens on Shrawan 1 (month 4).
FISCAL_YEAR_START_MONTH = 4

DEVANAGARI_DIGITS = "०१२३४५६७८९"
_ASCII_TO_DEV = str.maketrans("0123456789", DEVANAGARI_DIGITS)
_DEV_TO_ASCII = str.maketrans(DEVANAGARI_DIGITS, "0123456789")

_BS_RE = re.compile(r"^\s*(\d{4})\s*[-/.\s]\s*(\d{1,2})\s*[-/.\s]\s*(\d{1,2})\s*$")


class InvalidBikramSambatDate(ValueError):
    """Raised when a BS string cannot be understood or is out of range."""


def ascii_digits(value: str) -> str:
    """Fold Devanagari digits down to ASCII so `२०८२-०५-१७` parses."""
    return str(value).translate(_DEV_TO_ASCII)


def devanagari_digits(value) -> str:
    return str(value).translate(_ASCII_TO_DEV)


def parse_bs(value: str) -> ndt.date:
    """Parse `2082-05-17`, `2082/5/17` or `२०८२।०५।१७` into a BS date."""
    if value is None:
        raise InvalidBikramSambatDate(_("The date is empty"))
    if isinstance(value, ndt.date):
        return value
    text = ascii_digits(str(value)).replace("।", "-")
    match = _BS_RE.match(text)
    if not match:
        raise InvalidBikramSambatDate(
            _("Could not read the date '%(value)s' — use YYYY-MM-DD (e.g. 2082-05-17)")
            % {"value": value}
        )
    year, month, day = (int(part) for part in match.groups())
    try:
        return ndt.date(year, month, day)
    except Exception as exc:  # nepali_datetime raises bare ValueError/KeyError
        raise InvalidBikramSambatDate(
            _("BS %(date)s does not exist (%(error)s)")
            % {"date": f"{year}-{month:02d}-{day:02d}", "error": exc}
        ) from exc


def bs_to_ad(value: str) -> _dt.date:
    return parse_bs(value).to_datetime_date()


def ad_to_bs(value) -> ndt.date:
    """Accepts a `date`, a `datetime`, or an ISO `YYYY-MM-DD` string."""
    if isinstance(value, _dt.datetime):
        value = value.date()
    elif isinstance(value, str):
        value = _dt.date.fromisoformat(ascii_digits(value)[:10])
    return ndt.date.from_datetime_date(value)


def today_bs() -> ndt.date:
    return ndt.date.today()


def format_bs(value, fmt: str = "{y}-{m:02d}-{d:02d}", devanagari: bool = False) -> str:
    """Format an AD or BS date as BS text.

    Placeholders: {y} {m} {d} {month_np} {month_en} {weekday_np} {weekday_en}.
    """
    if value is None:
        return ""
    bs = value if isinstance(value, ndt.date) else ad_to_bs(value)
    ad = bs.to_datetime_date()
    weekday = ad.isoweekday() % 7  # Sunday -> 0
    text = fmt.format(
        y=bs.year,
        m=bs.month,
        d=bs.day,
        month_np=MONTHS_NP[bs.month - 1],
        month_en=MONTHS_EN[bs.month - 1],
        weekday_np=WEEKDAYS_NP[weekday],
        weekday_en=WEEKDAYS_EN[weekday],
    )
    return devanagari_digits(text) if devanagari else text


def bs_display(value, devanagari: bool = True) -> str:
    """`१७ भदौ २०८२` — the way a date is read out loud in Nepal."""
    return format_bs(value, "{d} {month_np} {y}", devanagari=devanagari)


def fiscal_year(value) -> str:
    """`2082/83` for any AD or BS date. Shrawan 1 opens the new year."""
    if value is None:
        return ""
    bs = value if isinstance(value, ndt.date) else ad_to_bs(value)
    start = bs.year if bs.month >= FISCAL_YEAR_START_MONTH else bs.year - 1
    return f"{start}/{(start + 1) % 100:02d}"


def fiscal_year_bounds(fy: str) -> tuple[_dt.date, _dt.date]:
    """AD (start, end) dates covering a `2082/83`-style fiscal year, inclusive."""
    start_year = int(ascii_digits(fy).split("/")[0])
    start = ndt.date(start_year, FISCAL_YEAR_START_MONTH, 1).to_datetime_date()
    end = ndt.date(start_year + 1, FISCAL_YEAR_START_MONTH, 1).to_datetime_date()
    return start, end - _dt.timedelta(days=1)


def recent_fiscal_years(count: int = 5, around=None) -> list[str]:
    """Newest first, for a filter dropdown."""
    bs = ad_to_bs(around or _dt.date.today())
    latest = bs.year if bs.month >= FISCAL_YEAR_START_MONTH else bs.year - 1
    return [f"{y}/{(y + 1) % 100:02d}" for y in range(latest, latest - count, -1)]


def month_bounds(bs_year: int, bs_month: int) -> tuple[_dt.date, _dt.date]:
    """AD (start, end) dates for a whole BS month, inclusive."""
    start = ndt.date(bs_year, bs_month, 1).to_datetime_date()
    if bs_month == 12:
        nxt = ndt.date(bs_year + 1, 1, 1)
    else:
        nxt = ndt.date(bs_year, bs_month + 1, 1)
    return start, nxt.to_datetime_date() - _dt.timedelta(days=1)
