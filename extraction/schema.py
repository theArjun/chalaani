"""The Pydantic contract the model must fill in when it reads a chalani photo.

Every field is optional on purpose: a smudged, folded, half-photographed slip is
the normal case, and a `null` a clerk fills in beats a confident guess that
silently enters the books.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedItem(BaseModel):
    """One line of the goods table."""

    description: str = Field(
        description=(
            "The item exactly as written on the paper, in the script used there "
            "(Devanagari stays Devanagari). Do not translate or tidy it."
        )
    )
    description_en: str | None = Field(
        default=None,
        description="Romanised/English rendering of the description, if the original is Devanagari.",
    )
    qty: float | None = Field(default=None, description="Quantity as a number. Convert Devanagari digits (१२.५ -> 12.5).")
    unit: str | None = Field(
        default=None,
        description=(
            "Unit as written: थान/बोरा/के.जी./बन्डल/वर्ग फिट/ट्रिप/pcs/bag/kg/sqft ... "
            "Leave null if the slip does not say."
        ),
    )
    rate: float | None = Field(default=None, description="Per-unit rate in NPR, if the slip shows one.")
    amount: float | None = Field(default=None, description="Line total in NPR, if the slip shows one.")


class ChalaniExtraction(BaseModel):
    """Everything readable off a single chalani / delivery-note photo."""

    vendor_name: str | None = Field(
        default=None, description="Supplier firm name, romanised if the original is Devanagari."
    )
    vendor_name_np: str | None = Field(
        default=None, description="Supplier firm name exactly as printed, in Devanagari."
    )
    vendor_pan: str | None = Field(
        default=None, description="Supplier PAN/VAT number — nine digits, often labelled 'PAN No.' or 'स्थायी लेखा नं.'"
    )
    vendor_phone: str | None = Field(default=None, description="Supplier phone number as printed.")

    chalani_no: str | None = Field(
        default=None,
        description="Chalani/challan/delivery-note number (चलानी नं., बिल्टी नं., D.C. No.). Keep any prefix.",
    )
    date_bs: str | None = Field(
        default=None,
        description=(
            "Bikram Sambat date as written, normalised to YYYY-MM-DD with ASCII digits "
            "(२०८२।०५।१७ -> 2082-05-17). Null if the slip only carries an AD date."
        ),
    )
    date_ad: str | None = Field(
        default=None,
        description=(
            "Gregorian date as YYYY-MM-DD. If only a BS date is printed, convert it yourself; "
            "if only an AD date is printed, copy it."
        ),
    )
    vehicle_no: str | None = Field(
        default=None, description="Vehicle/lorry number as written, e.g. 'बा १२ ख ३४५६' or 'Ba 12 Kha 3456'."
    )
    driver_name: str | None = Field(default=None, description="Driver's name, if written.")
    received_by: str | None = Field(
        default=None, description="Name of whoever signed for the goods (बुझिलिने / प्राप्तकर्ता)."
    )
    destination: str | None = Field(default=None, description="Delivery site or address written on the slip.")

    items: list[ExtractedItem] = Field(
        default_factory=list, description="One entry per row of the goods table, top to bottom."
    )

    grand_total: float | None = Field(default=None, description="Grand total in NPR, if the slip shows one.")
    remarks: str | None = Field(default=None, description="Any other handwritten note worth keeping.")

    legibility: Literal["good", "fair", "poor"] = Field(
        default="fair", description="How readable the photo was overall."
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="0-1 confidence that the header fields are correct."
    )
    unreadable_fields: list[str] = Field(
        default_factory=list,
        description="Names of fields that were present on the paper but could not be read.",
    )
