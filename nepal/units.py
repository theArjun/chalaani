"""Units of measure as they are actually written on Nepali chalani slips.

`UNITS` is the canonical list; `normalise_unit()` folds the many spellings an
AI (or a hurried clerk) may produce — `bora`, `बोरा`, `Bag`, `sack` — onto one
code so that vendor-wise and item-wise reports add up.
"""

from __future__ import annotations

# code, Nepali label, English label, aliases
UNITS = [
    ("pcs", "थान", "Pieces", ["pcs", "pc", "piece", "pieces", "nos", "no", "थान", "गोटा", "नग", "वटा"]),
    ("bag", "बोरा", "Bag / Sack", ["bag", "bags", "sack", "bora", "बोरा", "बोरे"]),
    ("kg", "के.जी.", "Kilogram", ["kg", "kgs", "kilo", "kilogram", "के.जी.", "केजी", "किलो"]),
    ("quintal", "क्विन्टल", "Quintal", ["quintal", "qtl", "क्विन्टल"]),
    ("ton", "टन", "Metric ton", ["ton", "tonne", "mt", "टन"]),
    ("ltr", "लिटर", "Litre", ["l", "ltr", "litre", "liter", "लिटर"]),
    ("m", "मिटर", "Metre", ["m", "mtr", "metre", "meter", "मिटर"]),
    ("rft", "रनिङ फिट", "Running foot", ["rft", "ft", "feet", "foot", "फिट", "रनिङ फिट"]),
    ("sqft", "वर्ग फिट", "Square foot", ["sqft", "sq.ft", "sq ft", "वर्ग फिट", "स्क्वायर फिट"]),
    ("cft", "घन फिट", "Cubic foot", ["cft", "cu.ft", "cuft", "घन फिट"]),
    ("cum", "घन मिटर", "Cubic metre", ["cum", "m3", "cu.m", "घन मिटर"]),
    ("trip", "ट्रिप", "Trip / Load", ["trip", "load", "gadi", "ट्रिप", "गाडी"]),
    ("bundle", "बन्डल", "Bundle", ["bundle", "bdl", "बन्डल", "मुठा"]),
    ("roll", "रोल", "Roll", ["roll", "रोल"]),
    ("dozen", "दर्जन", "Dozen", ["dozen", "dz", "दर्जन"]),
    ("packet", "प्याकेट", "Packet", ["packet", "pkt", "pack", "प्याकेट", "पोका"]),
    ("carton", "कार्टुन", "Carton", ["carton", "ctn", "box", "कार्टुन", "बट्टा"]),
    ("set", "सेट", "Set", ["set", "सेट"]),
    ("pair", "जोर", "Pair", ["pair", "jor", "जोर"]),
    ("sheet", "पाता", "Sheet", ["sheet", "पाता", "प्लेट"]),
]

UNIT_CHOICES = [(code, f"{np} ({en})") for code, np, en, _ in UNITS]
UNIT_CODES = [code for code, *_ in UNITS]
UNIT_LABELS_NP = {code: np for code, np, _, _ in UNITS}
UNIT_LABELS_EN = {code: en for code, _, en, _ in UNITS}

_ALIAS_TO_CODE = {}
for _code, _np, _en, _aliases in UNITS:
    for _alias in [_code, _np, _en, *_aliases]:
        _ALIAS_TO_CODE[_alias.strip().lower().replace(".", "").replace(" ", "")] = _code


def normalise_unit(raw: str | None, default: str = "pcs") -> str:
    """Best-effort fold of free text onto a canonical unit code."""
    if not raw:
        return default
    key = str(raw).strip().lower().replace(".", "").replace(" ", "")
    if key in _ALIAS_TO_CODE:
        return _ALIAS_TO_CODE[key]
    # Trailing plural / possessive noise: "bags.", "borahru"
    for suffix in ("s", "हरु", "हरू"):
        if key.endswith(suffix) and key[: -len(suffix)] in _ALIAS_TO_CODE:
            return _ALIAS_TO_CODE[key[: -len(suffix)]]
    return default


def unit_label(code: str, devanagari: bool = True) -> str:
    if devanagari:
        return UNIT_LABELS_NP.get(code, code)
    return UNIT_LABELS_EN.get(code, code)
