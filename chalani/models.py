"""The chalani register itself.

`Chalani` is the delivery note (चलानी / डेलिभरी चलान) a supplier hands over
with the goods. The paper is the source of truth, so the model keeps what was
written (`description`, `date_bs`, `chalani_no`) *and* the normalised links
(`item`, `date`) that a clerk confirms during verification — that split is what
makes vendor-wise reporting possible later without lying about the paper.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import PurePath

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse

from nepal import dates as npdates
from nepal.units import UNIT_CHOICES, normalise_unit
from nepal.validators import validate_nepali_phone, validate_pan, validate_vehicle_no
from orgs.models import OrgScoped, OrgScopedQuerySet
from django.utils.translation import gettext_lazy as _


def chalani_upload_path(instance, filename):
    """`chalani/<org_id>/<uuid>.<ext>` — org-scoped, unguessable, flat."""
    suffix = PurePath(filename).suffix.lower() or ".jpg"
    return f"chalani/{instance.organization_id}/{uuid.uuid4().hex}{suffix}"


def _search_key(*parts) -> str:
    """Fold names for matching: case, spaces and Devanagari digits."""
    joined = " ".join(p for p in parts if p)
    return " ".join(npdates.ascii_digits(joined).lower().split())


class Vendor(OrgScoped):
    name = models.CharField("Supplier name", max_length=200)
    name_np = models.CharField(_("Supplier name (Nepali)"), max_length=200, blank=True)
    pan_no = models.CharField(
        "PAN/VAT", max_length=20, blank=True, validators=[validate_pan]
    )
    phone = models.CharField(
        _("Phone"), max_length=20, blank=True, validators=[validate_nepali_phone]
    )
    address = models.CharField(_("Address"), max_length=200, blank=True)
    district = models.CharField(_("District"), max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    search_key = models.CharField(max_length=420, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["organization", "name"])]

    def __str__(self):
        return self.name_np or self.name

    def save(self, *args, **kwargs):
        self.search_key = _search_key(self.name, self.name_np, self.pan_no)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("chalani:vendor_edit", args=[self.pk])


class Item(OrgScoped):
    name = models.CharField("Item name", max_length=200)
    name_np = models.CharField(_("Item name (Nepali)"), max_length=200, blank=True)
    unit = models.CharField(
        _("Unit"), max_length=20, choices=UNIT_CHOICES, default="pcs"
    )
    default_rate = models.DecimalField(
        _("Default rate"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    search_key = models.CharField(max_length=420, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["organization", "name"])]

    def __str__(self):
        return self.name_np or self.name

    def save(self, *args, **kwargs):
        self.unit = normalise_unit(self.unit)
        self.search_key = _search_key(self.name, self.name_np)
        super().save(*args, **kwargs)


class ChalaniQuerySet(OrgScopedQuerySet):
    def with_totals(self):
        return self.annotate(
            line_count=models.Count("items", distinct=True),
            total=models.Sum(
                models.F("items__qty") * models.F("items__rate"),
                output_field=models.DecimalField(max_digits=16, decimal_places=2),
            ),
        )

    def in_fiscal_year(self, fy):
        if not fy:
            return self
        start, end = npdates.fiscal_year_bounds(fy)
        return self.filter(date__gte=start, date__lte=end)

    def pending_review(self):
        return self.filter(status__in=[Chalani.Status.EXTRACTING, Chalani.Status.DRAFT])


class Chalani(OrgScoped):
    class Status(models.TextChoices):
        EXTRACTING = "extracting", _("Extracting")
        DRAFT = "draft", _("Draft")
        VERIFIED = "verified", _("Verified")
        BILLED = "billed", _("Billed")

    vendor = models.ForeignKey(
        Vendor, null=True, blank=True, on_delete=models.PROTECT, related_name="chalanis"
    )
    chalani_no = models.CharField(_("Chalani no."), max_length=50, blank=True)
    date = models.DateField(_("Date (AD)"), null=True, blank=True)
    date_bs = models.CharField(_("Date (BS)"), max_length=12, blank=True)
    fiscal_year = models.CharField(
        _("Fiscal year"), max_length=9, blank=True, db_index=True
    )
    vehicle_no = models.CharField(
        _("Vehicle no."), max_length=30, blank=True, validators=[validate_vehicle_no]
    )
    received_by = models.CharField(_("Received by"), max_length=100, blank=True)
    remarks = models.CharField(_("Remarks"), max_length=300, blank=True)
    photo = models.ImageField(upload_to=chalani_upload_path, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    extracted_by_ai = models.BooleanField(default=False)
    raw_extraction = models.JSONField(null=True, blank=True)
    extraction_error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chalanis_created",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="chalanis_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ChalaniQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "-date"]),
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "fiscal_year"]),
        ]
        constraints = [
            # Only *settled* chalani are held to unique numbering, so an AI
            # draft with a misread number can never block a save. Blank numbers
            # are exempt too — several drafts legitimately have none yet.
            models.UniqueConstraint(
                fields=["organization", "vendor", "chalani_no"],
                condition=Q(status__in=["verified", "billed"]) & ~Q(chalani_no=""),
                name="unique_verified_chalani",
            )
        ]

    def __str__(self):
        label = self.chalani_no or f"#{self.pk}"
        return f"{label} · {self.vendor or _('unknown supplier')}"

    def get_absolute_url(self):
        return reverse("chalani:detail", args=[self.pk])

    # ------------------------------------------------------------------ dates
    def sync_dates(self):
        """Keep `date` (AD), `date_bs` and `fiscal_year` consistent.

        `date_bs` wins when it is present and parseable — it is what the paper
        says. Anything unparseable is left untouched for a human to fix.
        """
        if self.date_bs:
            try:
                bs = npdates.parse_bs(self.date_bs)
            except npdates.InvalidBikramSambatDate:
                bs = None
            if bs is not None:
                self.date_bs = f"{bs.year}-{bs.month:02d}-{bs.day:02d}"
                self.date = bs.to_datetime_date()
        elif self.date:
            self.date_bs = npdates.format_bs(self.date)
        self.fiscal_year = npdates.fiscal_year(self.date) if self.date else ""

    def save(self, *args, **kwargs):
        self.sync_dates()
        super().save(*args, **kwargs)

    # ----------------------------------------------------------------- totals
    @property
    def total_amount(self) -> Decimal:
        return sum(
            (line.amount for line in self.items.all() if line.amount is not None),
            Decimal("0"),
        )

    @property
    def has_rates(self) -> bool:
        return any(line.rate is not None for line in self.items.all())

    @property
    def is_editable(self) -> bool:
        return self.status in {self.Status.DRAFT, self.Status.VERIFIED}

    @property
    def date_bs_np(self) -> str:
        return npdates.bs_display(self.date) if self.date else self.date_bs

    def missing_for_verification(self) -> list[str]:
        """Human-readable list of what still blocks verification."""
        gaps = []
        if not self.vendor_id:
            gaps.append(_("no supplier chosen"))
        if not self.chalani_no:
            gaps.append(_("no chalani number"))
        if not self.date:
            gaps.append(_("no date"))
        if not self.items.exists():
            gaps.append(_("no goods added"))
        elif self.items.filter(item__isnull=True).exists():
            gaps.append(_("some lines are not linked to the catalog"))
        return gaps


class ChalaniItem(models.Model):
    chalani = models.ForeignKey(Chalani, related_name="items", on_delete=models.CASCADE)
    item = models.ForeignKey(
        Item,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="chalani_lines",
    )
    description = models.CharField(_("As written on paper"), max_length=200)
    qty = models.DecimalField(_("Qty"), max_digits=12, decimal_places=3)
    unit = models.CharField(
        _("Unit"), max_length=20, choices=UNIT_CHOICES, default="pcs"
    )
    rate = models.DecimalField(
        _("Rate"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    line_no = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["line_no", "id"]

    def __str__(self):
        return f"{self.description} — {self.qty} {self.unit}"

    def save(self, *args, **kwargs):
        self.unit = normalise_unit(self.unit)
        super().save(*args, **kwargs)

    @property
    def amount(self) -> Decimal | None:
        if self.rate is None or self.qty is None:
            return None
        return (self.qty * self.rate).quantize(Decimal("0.01"))
