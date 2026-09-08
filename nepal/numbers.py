"""Nepali number rendering: lakh/crore grouping, Devanagari digits, words."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .dates import ascii_digits, devanagari_digits  # re-exported for convenience

__all__ = [
    "ascii_digits",
    "devanagari_digits",
    "group_indian",
    "format_amount",
    "amount_in_words_np",
    "amount_in_words_en",
]

_ONES_NP = [
    "शून्य",
    "एक",
    "दुई",
    "तीन",
    "चार",
    "पाँच",
    "छ",
    "सात",
    "आठ",
    "नौ",
    "दश",
    "एघार",
    "बाह्र",
    "तेह्र",
    "चौध",
    "पन्ध्र",
    "सोह्र",
    "सत्र",
    "अठार",
    "उन्नाइस",
    "बीस",
    "एक्काइस",
    "बाइस",
    "तेइस",
    "चौबिस",
    "पच्चिस",
    "छब्बिस",
    "सत्ताइस",
    "अट्ठाइस",
    "उनन्तिस",
    "तीस",
    "एकतिस",
    "बत्तिस",
    "तेत्तिस",
    "चौँतिस",
    "पैँतिस",
    "छत्तिस",
    "सर्तिस",
    "अठतिस",
    "उनन्चालिस",
    "चालिस",
    "एकचालिस",
    "बयालिस",
    "त्रिचालिस",
    "चवालिस",
    "पैँतालिस",
    "छयालिस",
    "सर्चालिस",
    "अठचालिस",
    "उनन्चास",
    "पचास",
    "एकाउन्न",
    "बाउन्न",
    "त्रिपन्न",
    "चवन्न",
    "पचपन्न",
    "छपन्न",
    "सन्ताउन्न",
    "अन्ठाउन्न",
    "उनन्साठी",
    "साठी",
    "एकसट्ठी",
    "बयसट्ठी",
    "त्रिसट्ठी",
    "चौंसट्ठी",
    "पैंसट्ठी",
    "छयसट्ठी",
    "सतसट्ठी",
    "अठसट्ठी",
    "उनन्सत्तरी",
    "सत्तरी",
    "एकहत्तर",
    "बहत्तर",
    "त्रिहत्तर",
    "चौहत्तर",
    "पचहत्तर",
    "छयहत्तर",
    "सतहत्तर",
    "अठहत्तर",
    "उनासी",
    "असी",
    "एकासी",
    "बयासी",
    "त्रियासी",
    "चौरासी",
    "पचासी",
    "छयासी",
    "सतासी",
    "अठासी",
    "उनान्नब्बे",
    "नब्बे",
    "एकानब्बे",
    "बयानब्बे",
    "त्रियानब्बे",
    "चौरानब्बे",
    "पन्चानब्बे",
    "छयानब्बे",
    "सन्तानब्बे",
    "अन्ठानब्बे",
    "उनान्सय",
]

# (divisor, Nepali name, English name) — largest first.
_SCALES = [
    (10**9, "अरब", "arab"),
    (10**7, "करोड", "crore"),
    (10**5, "लाख", "lakh"),
    (10**3, "हजार", "thousand"),
    (10**2, "सय", "hundred"),
]

_ONES_EN = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS_EN = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        number = Decimal(str(ascii_digits(value)).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    # NaN and Infinity parse but cannot be formatted or compared — read them as
    # nothing rather than raising out of a template filter.
    return number if number.is_finite() else Decimal("0")


def group_indian(value, decimals: int = 2) -> str:
    """`1234567.5` -> `12,34,567.50` (last three digits, then pairs)."""
    amount = _to_decimal(value)
    quantized = amount.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    sign = "-" if quantized < 0 else ""
    digits = f"{abs(quantized):.{decimals}f}"
    whole, _, frac = digits.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}{whole}.{frac}" if decimals else f"{sign}{whole}"


def format_amount(
    value, decimals: int = 2, devanagari: bool = False, prefix: str = ""
) -> str:
    text = group_indian(value, decimals)
    if devanagari:
        text = devanagari_digits(text)
    return f"{prefix}{text}" if prefix else text


def _words_np(number: int) -> list[str]:
    if number < 100:
        return [_ONES_NP[number]]
    for divisor, name, _ in _SCALES:
        if number >= divisor:
            head, rest = divmod(number, divisor)
            words = _words_np(head) + [name]
            if rest:
                words += _words_np(rest)
            return words
    return [_ONES_NP[number]]


def amount_in_words_np(value, currency: str = "रुपैयाँ", paisa: str = "पैसा") -> str:
    """`1250.50` -> `एक हजार दुई सय पचास रुपैयाँ पचास पैसा मात्र`."""
    amount = _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative = amount < 0
    amount = abs(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    words = _words_np(rupees) + [currency]
    if paise:
        words += _words_np(paise) + [paisa]
    text = " ".join(words) + " मात्र"
    return ("ऋणात्मक " + text) if negative else text


def _words_en(number: int) -> list[str]:
    if number < 20:
        return [_ONES_EN[number]]
    if number < 100:
        tens, ones = divmod(number, 10)
        return [_TENS_EN[tens] + (f"-{_ONES_EN[ones]}" if ones else "")]
    for divisor, _, name in _SCALES:
        if number >= divisor:
            head, rest = divmod(number, divisor)
            words = _words_en(head) + [name]
            if rest:
                words += _words_en(rest)
            return words
    return [_ONES_EN[number]]


def amount_in_words_en(value, currency: str = "rupees", paisa: str = "paisa") -> str:
    """South-Asian scale in English: `twelve lakh thirty-four thousand ...`."""
    amount = _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative = amount < 0
    amount = abs(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    words = _words_en(rupees) + [currency]
    if paise:
        words += _words_en(paise) + [paisa]
    text = " ".join(words) + " only"
    return ("minus " + text) if negative else text
