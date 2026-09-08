"""An MCP server named `chalaani` over the chalani register.

The tool bodies are plain functions that take an `Organization`, so they can be
called (and tested) without an MCP client. `build_server()` wires them to a
`MCPServer`; `manage.py mcp` runs it.

Scoping is the same rule the web app follows: every query starts from one
organization and never crosses it. The stdio transport has no user to
authenticate, so the org is pinned once at startup by the operator and writes
stay off unless they are explicitly enabled.
"""

from __future__ import annotations

import functools
from decimal import Decimal

from django.db import close_old_connections
from django.db.models import Count, DecimalField, F, Q, Sum
from django.utils import timezone

from nepal import dates as npdates
from nepal.units import unit_label

from .models import Chalani, ChalaniItem, Item, Vendor

AMOUNT = DecimalField(max_digits=16, decimal_places=2)

SERVER_NAME = "chalaani"
INSTRUCTIONS = """\
Query a chalaani delivery-challan register (Nepali paper चलानी slips read into a
database). Dates are Bikram Sambat: `date_bs` is `YYYY-MM-DD` in BS and `date`
is the Gregorian mirror — pass BS to every date argument, and use `convert_date`
if you need to move between the two. Fiscal years run Shrawan to Ashad and are
written `2082/83`. Money is NPR.

`description` on a line is what the paper said; `item` is the catalog link a
clerk confirmed. Report by `item` — a null one means nobody has confirmed it yet.
"""


def _managed(fn):
    """Each tool call runs on an anyio worker thread — don't leak connections."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return wrapper


def _money(value) -> float | None:
    return float(value) if isinstance(value, Decimal) else value


def _chalani_row(chalani) -> dict:
    return {
        "id": chalani.pk,
        "chalani_no": chalani.chalani_no,
        "date_bs": chalani.date_bs,
        "date_ad": chalani.date.isoformat() if chalani.date else None,
        "fiscal_year": chalani.fiscal_year,
        "vendor": str(chalani.vendor) if chalani.vendor_id else None,
        "vendor_id": chalani.vendor_id,
        "vehicle_no": chalani.vehicle_no,
        "status": chalani.status,
        "extracted_by_ai": chalani.extracted_by_ai,
        "total": _money(chalani.total_amount),
    }


# ------------------------------------------------------------------ read tools


@_managed
def list_chalani(
    organization,
    status: str | None = None,
    vendor_id: int | None = None,
    fiscal_year: str | None = None,
    date_from_bs: str | None = None,
    date_to_bs: str | None = None,
    query: str | None = None,
    limit: int = 25,
) -> dict:
    """List chalani, newest first, filtered the same way the register page is."""
    qs = Chalani.objects.for_org(organization).select_related("vendor")
    if status:
        qs = qs.filter(status=status)
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    if fiscal_year:
        qs = qs.in_fiscal_year(fiscal_year)
    for raw, lookup in ((date_from_bs, "date__gte"), (date_to_bs, "date__lte")):
        if raw:
            qs = qs.filter(**{lookup: npdates.bs_to_ad(raw)})
    if query:
        needle = npdates.ascii_digits(query)
        qs = qs.filter(
            Q(chalani_no__icontains=needle)
            | Q(vehicle_no__icontains=query)
            | Q(received_by__icontains=query)
            | Q(vendor__name__icontains=query)
            | Q(vendor__name_np__icontains=query)
            | Q(items__description__icontains=query)
        ).distinct()
    rows = list(qs.prefetch_related("items")[: max(1, min(limit, 200))])
    return {"count": len(rows), "chalani": [_chalani_row(c) for c in rows]}


@_managed
def get_chalani(organization, chalani_id: int) -> dict:
    """One chalani in full, including its goods lines and what blocks verification."""
    chalani = (
        Chalani.objects.for_org(organization)
        .select_related("vendor", "created_by", "verified_by")
        .prefetch_related("items__item")
        .get(pk=chalani_id)
    )
    row = _chalani_row(chalani)
    row.update(
        {
            "received_by": chalani.received_by,
            "remarks": chalani.remarks,
            "has_photo": bool(chalani.photo),
            "created_by": chalani.created_by.display_name,
            "created_at": chalani.created_at.isoformat(),
            "verified_by": (
                chalani.verified_by.display_name if chalani.verified_by_id else None
            ),
            "verified_at": (
                chalani.verified_at.isoformat() if chalani.verified_at else None
            ),
            "extraction_error": chalani.extraction_error,
            "blocks_verification": [
                str(gap) for gap in chalani.missing_for_verification()
            ],
            "items": [
                {
                    "line_id": line.pk,
                    "line_no": line.line_no,
                    "description": line.description,
                    "item_id": line.item_id,
                    "item": str(line.item) if line.item_id else None,
                    "qty": float(line.qty),
                    "unit": line.unit,
                    "unit_label": unit_label(line.unit, devanagari=False),
                    "rate": _money(line.rate),
                    "amount": _money(line.amount),
                }
                for line in chalani.items.all()
            ],
        }
    )
    return row


@_managed
def search_vendors(organization, query: str | None = None, limit: int = 20) -> dict:
    """Find suppliers by name (either script) or PAN."""
    vendors = Vendor.objects.for_org(organization).annotate(
        chalani_count=Count("chalanis")
    )
    if query:
        vendors = vendors.filter(
            Q(name__icontains=query)
            | Q(name_np__icontains=query)
            | Q(pan_no__icontains=npdates.ascii_digits(query))
        )
    return {
        "vendors": [
            {
                "id": v.pk,
                "name": v.name,
                "name_np": v.name_np,
                "pan_no": v.pan_no,
                "phone": v.phone,
                "district": v.district,
                "is_active": v.is_active,
                "chalani_count": v.chalani_count,
            }
            for v in vendors[: max(1, min(limit, 200))]
        ]
    }


@_managed
def search_items(organization, query: str | None = None, limit: int = 20) -> dict:
    """Find catalog items — these are what chalani lines get linked to."""
    items = Item.objects.for_org(organization)
    if query:
        items = items.filter(Q(name__icontains=query) | Q(name_np__icontains=query))
    return {
        "items": [
            {
                "id": i.pk,
                "name": i.name,
                "name_np": i.name_np,
                "unit": i.unit,
                "unit_label": unit_label(i.unit, devanagari=False),
                "default_rate": _money(i.default_rate),
                "is_active": i.is_active,
            }
            for i in items[: max(1, min(limit, 200))]
        ]
    }


@_managed
def vendor_report(organization, fiscal_year: str | None = None) -> dict:
    """Vendor-wise and item-wise totals for one fiscal year (default: current)."""
    fy = fiscal_year or npdates.fiscal_year(npdates.today_bs())
    chalanis = Chalani.objects.for_org(organization).in_fiscal_year(fy)
    vendors = (
        chalanis.values("vendor", "vendor__name", "vendor__name_np")
        .annotate(
            chalani_count=Count("id", distinct=True),
            amount=Sum(F("items__qty") * F("items__rate"), output_field=AMOUNT),
        )
        .order_by("-amount")
    )
    items = (
        ChalaniItem.objects.filter(chalani__in=chalanis)
        .values("item", "item__name", "unit")
        .annotate(
            total_qty=Sum("qty"),
            amount=Sum(F("qty") * F("rate"), output_field=AMOUNT),
        )
        .order_by("-amount")
    )
    start, end = npdates.fiscal_year_bounds(fy)
    return {
        "fiscal_year": fy,
        "period_bs": [npdates.format_bs(start), npdates.format_bs(end)],
        "period_ad": [start.isoformat(), end.isoformat()],
        "by_vendor": [
            {
                "vendor_id": row["vendor"],
                "vendor": row["vendor__name_np"] or row["vendor__name"],
                "chalani_count": row["chalani_count"],
                "amount": _money(row["amount"]),
            }
            for row in vendors
        ],
        "by_item": [
            {
                "item_id": row["item"],
                "item": row["item__name"],
                "unit": row["unit"],
                "qty": float(row["total_qty"] or 0),
                "amount": _money(row["amount"]),
            }
            for row in items
        ],
    }


@_managed
def register_summary(organization) -> dict:
    """Counts and totals for the current fiscal year — the dashboard, as JSON."""
    fy = npdates.fiscal_year(npdates.today_bs())
    this_fy = Chalani.objects.for_org(organization).in_fiscal_year(fy)
    amount = ChalaniItem.objects.filter(chalani__in=this_fy).aggregate(
        total=Sum(F("qty") * F("rate"), output_field=AMOUNT)
    )["total"]
    return {
        "organization": str(organization),
        "fiscal_year": fy,
        "today_bs": npdates.format_bs(npdates.today_bs()),
        "counts": {
            status: this_fy.filter(status=status).count()
            for status, _ in Chalani.Status.choices
        },
        "total_chalani": this_fy.count(),
        "total_amount": _money(amount),
        "vendors": Vendor.objects.for_org(organization).count(),
        "items": Item.objects.for_org(organization).count(),
    }


@_managed
def pending_verification(organization, limit: int = 20) -> dict:
    """Drafts a clerk still has to confirm, with the reason each one is stuck."""
    rows = list(
        Chalani.objects.for_org(organization)
        .pending_review()
        .select_related("vendor")
        .prefetch_related("items")[: max(1, min(limit, 200))]
    )
    return {
        "count": len(rows),
        "chalani": [
            _chalani_row(c)
            | {"blocks_verification": [str(g) for g in c.missing_for_verification()]}
            for c in rows
        ],
    }


def convert_date(bs: str | None = None, ad: str | None = None) -> dict:
    """Convert between Bikram Sambat and Gregorian. Give exactly one of `bs`/`ad`."""
    import datetime

    if bool(bs) == bool(ad):
        raise ValueError("pass exactly one of bs= or ad=")
    bs_date = (
        npdates.parse_bs(bs)
        if bs
        else npdates.ad_to_bs(
            datetime.date.fromisoformat(npdates.ascii_digits(ad)[:10])
        )
    )
    ad_date = bs_date.to_datetime_date()
    return {
        "bs": npdates.format_bs(bs_date),
        "bs_nepali": npdates.bs_display(bs_date),
        "ad": ad_date.isoformat(),
        "weekday": npdates.format_bs(bs_date, "{weekday_en}"),
        "fiscal_year": npdates.fiscal_year(bs_date),
    }


# ----------------------------------------------------------------- write tools


@_managed
def update_chalani(
    organization,
    chalani_id: int,
    chalani_no: str | None = None,
    date_bs: str | None = None,
    vendor_id: int | None = None,
    vehicle_no: str | None = None,
    received_by: str | None = None,
    remarks: str | None = None,
) -> dict:
    """Set header fields on a draft. `date_bs` is Bikram Sambat, `YYYY-MM-DD`.

    Omitted fields are left alone — this never blanks something a clerk typed.
    """
    chalani = Chalani.objects.for_org(organization).get(pk=chalani_id)
    if chalani.status == Chalani.Status.BILLED:
        raise ValueError("a billed chalani cannot be edited")
    changed = []
    for name, value in (
        ("chalani_no", chalani_no),
        ("date_bs", date_bs),
        ("vehicle_no", vehicle_no),
        ("received_by", received_by),
        ("remarks", remarks),
    ):
        if value not in (None, ""):
            setattr(chalani, name, value)
            changed.append(name)
    if date_bs:
        npdates.parse_bs(date_bs)  # reject an unreadable date before saving
    if vendor_id:
        chalani.vendor = Vendor.objects.for_org(organization).get(pk=vendor_id)
        changed.append("vendor")
    chalani.save()
    return {"updated": changed, "chalani": _chalani_row(chalani)}


@_managed
def link_line_item(organization, line_id: int, item_id: int) -> dict:
    """Link one goods line to a catalog item — the step reports depend on."""
    line = ChalaniItem.objects.select_related("chalani").get(
        pk=line_id, chalani__organization=organization
    )
    line.item = Item.objects.for_org(organization).get(pk=item_id)
    line.save()
    return {
        "line_id": line.pk,
        "description": line.description,
        "item": str(line.item),
        "chalani_id": line.chalani_id,
    }


@_managed
def verify_chalani(
    organization, chalani_id: int, verified_by: str | None = None
) -> dict:
    """Mark a chalani verified. Refuses while anything is still missing."""
    from django.contrib.auth import get_user_model

    chalani = Chalani.objects.for_org(organization).get(pk=chalani_id)
    gaps = [str(gap) for gap in chalani.missing_for_verification()]
    if gaps:
        return {"verified": False, "blocks_verification": gaps}
    user = None
    if verified_by:
        user = get_user_model().objects.filter(username=verified_by).first()
    chalani.status = Chalani.Status.VERIFIED
    chalani.verified_by = user or chalani.created_by
    chalani.verified_at = timezone.now()
    chalani.save()
    return {"verified": True, "chalani": _chalani_row(chalani)}


READ_TOOLS = [
    list_chalani,
    get_chalani,
    search_vendors,
    search_items,
    vendor_report,
    register_summary,
    pending_verification,
]
WRITE_TOOLS = [update_chalani, link_line_item, verify_chalani]


def build_server(organization, allow_writes: bool = False):
    """Wire the tools above to an MCP server named `chalaani`."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name=SERVER_NAME,
        title="chalaani — chalani register",
        instructions=INSTRUCTIONS
        + f"\nOrganization: {organization} (id {organization.pk}).",
        version="0.1.0",
    )

    def register(fn, *, read_only: bool):
        """Bind `organization` so it never appears in the tool's schema."""

        @functools.wraps(fn)
        def bound(*args, **kwargs):
            return fn(organization, *args, **kwargs)

        # Drop the bound first parameter from the generated JSON schema.
        bound.__signature__ = _signature_without_organization(fn)
        server.add_tool(
            bound,
            name=fn.__name__,
            description=(fn.__doc__ or "").strip(),
            annotations={"readOnlyHint": read_only, "destructiveHint": False},
        )

    for fn in READ_TOOLS:
        register(fn, read_only=True)
    server.add_tool(
        convert_date,
        name="convert_date",
        description=(convert_date.__doc__ or "").strip(),
    )
    if allow_writes:
        for fn in WRITE_TOOLS:
            register(fn, read_only=False)
    return server


def _signature_without_organization(fn):
    import inspect

    signature = inspect.signature(fn)
    params = [p for name, p in signature.parameters.items() if name != "organization"]
    return signature.replace(parameters=params)
