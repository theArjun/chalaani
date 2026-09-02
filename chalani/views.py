"""Views for the chalani register.

Every page renders whole on a normal request and as a fragment on `HX-Request`
by naming a partial from the same template (`"register.html#rows"`), so there
is exactly one template per screen.
"""

from __future__ import annotations

import mimetypes

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, F, Q, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from extraction.tasks import enqueue_extraction
from nepal import dates as npdates
from orgs.mixins import org_required, verifier_required

from .forms import (
    ChalaniForm,
    ChalaniItemFormSet,
    ChalaniUploadForm,
    ItemForm,
    VendorForm,
)
from .models import Chalani, ChalaniItem, Item, Vendor
from .services import next_line_no
from django.utils.translation import gettext as _

AMOUNT = DecimalField(max_digits=16, decimal_places=2)


def _filtered_register(request):
    """Shared queryset + filter state for the register and its CSV export."""
    qs = (
        Chalani.objects.for_org(request.organization)
        .select_related("vendor", "created_by")
        .with_totals()
    )
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    vendor_id = request.GET.get("vendor", "").strip()
    fy = request.GET.get("fy", "").strip()
    date_from = request.GET.get("from", "").strip()
    date_to = request.GET.get("to", "").strip()

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
    if status:
        qs = qs.filter(status=status)
    if vendor_id.isdigit():
        qs = qs.filter(vendor_id=int(vendor_id))
    if fy:
        qs = qs.in_fiscal_year(fy)
    for raw, lookup in ((date_from, "date__gte"), (date_to, "date__lte")):
        if raw:
            try:
                qs = qs.filter(**{lookup: npdates.bs_to_ad(raw)})
            except npdates.InvalidBikramSambatDate:
                messages.warning(
                    request,
                    _("Could not read the date '%(value)s' — filter skipped.") % {"value": raw},
                )
    return qs, {
        "q": query,
        "status": status,
        "vendor": vendor_id,
        "fy": fy,
        "from": date_from,
        "to": date_to,
    }


@org_required
def register(request):
    chalanis, filters = _filtered_register(request)
    chalanis = list(chalanis[:300])
    context = {
        "chalanis": chalanis,
        "filters": filters,
        "vendors": Vendor.objects.for_org(request.organization).filter(is_active=True),
        "statuses": Chalani.Status.choices,
        "fiscal_years": npdates.recent_fiscal_years(),
        "totals": {
            "count": len(chalanis),
            "amount": sum((c.total or 0) for c in chalanis),
            "pending": sum(1 for c in chalanis if c.status in {"extracting", "draft"}),
        },
    }
    if request.htmx:
        return render(request, "chalani/register.html#rows", context)
    return render(request, "chalani/register.html", context)


@org_required
def upload(request):
    if request.method == "POST":
        form = ChalaniUploadForm(request.POST, request.FILES)
        if form.is_valid():
            chalani = Chalani(
                organization=request.organization,
                created_by=request.user,
                photo=form.cleaned_data["photo"],
                status=Chalani.Status.DRAFT,
            )
            chalani.save()
            if form.cleaned_data["use_ai"]:
                enqueue_extraction(chalani)
                messages.info(request, _("Reading the photo — the draft will be ready in a moment."))
            return redirect(chalani)
    else:
        form = ChalaniUploadForm()
    return render(request, "chalani/upload.html", {"form": form})


def _get_chalani(request, pk) -> Chalani:
    return get_object_or_404(
        Chalani.objects.for_org(request.organization).select_related("vendor"), pk=pk
    )


@org_required
def detail(request, pk):
    chalani = _get_chalani(request, pk)
    if request.method == "POST":
        if chalani.status == Chalani.Status.BILLED:
            messages.error(request, _("A billed chalani cannot be edited."))
            return redirect(chalani)
        form = ChalaniForm(
            request.POST, instance=chalani, organization=request.organization
        )
        formset = ChalaniItemFormSet(
            request.POST, instance=chalani, organization=request.organization
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                lines = formset.save(commit=False)
                for line in formset.deleted_objects:
                    line.delete()
                position = next_line_no(chalani)
                for line in lines:
                    if not line.line_no:
                        line.line_no = position
                        position += 1
                    line.save()
            messages.success(request, _("Saved."))
            return redirect(chalani)
        messages.error(request, _("Some fields need fixing — see below."))
    else:
        form = ChalaniForm(instance=chalani, organization=request.organization)
        formset = ChalaniItemFormSet(instance=chalani, organization=request.organization)

    return render(
        request,
        "chalani/detail.html",
        {
            "chalani": chalani,
            "form": form,
            "formset": formset,
            "gaps": chalani.missing_for_verification(),
            "can_verify": request.membership.can_verify,
        },
    )


@org_required
@require_GET
def status_fragment(request, pk):
    """Polled every few seconds while `status == extracting`."""
    chalani = _get_chalani(request, pk)
    response = render(request, "chalani/detail.html#status", {"chalani": chalani})
    if chalani.status != Chalani.Status.EXTRACTING:
        # Reading finished — tell HTMX to reload the page so the form fills in.
        response["HX-Refresh"] = "true"
    return response


@org_required
@require_GET
def add_item_row(request, pk):
    """Append one blank formset row, and bump TOTAL_FORMS out of band."""
    chalani = _get_chalani(request, pk)
    try:
        total = int(request.GET.get("items-TOTAL_FORMS", chalani.items.count()))
    except ValueError:
        total = chalani.items.count()
    formset = ChalaniItemFormSet(instance=chalani, organization=request.organization)
    formset.extra = total + 1
    empty = formset.empty_form
    empty.prefix = f"items-{total}"
    return render(
        request,
        "chalani/detail.html#item_row",
        {"form": empty, "chalani": chalani, "new_total": total + 1, "oob": True},
    )


@verifier_required
@require_POST
def verify(request, pk):
    chalani = _get_chalani(request, pk)
    gaps = chalani.missing_for_verification()
    if gaps:
        messages.error(
            request, _("Cannot verify yet: %(gaps)s") % {"gaps": ", ".join(str(g) for g in gaps)}
        )
        return redirect(chalani)
    chalani.status = Chalani.Status.VERIFIED
    chalani.verified_by = request.user
    chalani.verified_at = timezone.now()
    try:
        with transaction.atomic():
            chalani.save()
    except IntegrityError:
        chalani.status = Chalani.Status.DRAFT
        messages.error(
            request,
            _("Chalani no. %(no)s is already verified for this supplier.")
            % {"no": chalani.chalani_no},
        )
        return redirect(chalani)
    messages.success(request, _("Chalani verified ✓"))
    return redirect(chalani)


@verifier_required
@require_POST
def mark_billed(request, pk):
    chalani = _get_chalani(request, pk)
    if chalani.status != Chalani.Status.VERIFIED:
        messages.error(request, _("Verify it first."))
    else:
        chalani.status = Chalani.Status.BILLED
        chalani.save()
        messages.success(request, _("Marked as billed."))
    return redirect(chalani)


@verifier_required
@require_POST
def reopen(request, pk):
    chalani = _get_chalani(request, pk)
    chalani.status = Chalani.Status.DRAFT
    chalani.verified_by = None
    chalani.verified_at = None
    chalani.save()
    messages.info(request, _("Sent back to draft."))
    return redirect(chalani)


@org_required
@require_POST
def reextract(request, pk):
    chalani = _get_chalani(request, pk)
    if not chalani.photo:
        messages.error(request, _("There is no photo."))
    elif chalani.items.exists():
        messages.error(request, _("Remove the existing lines first — AI never overwrites what is filled in."))
    else:
        enqueue_extraction(chalani)
        messages.info(request, _("Reading it again…"))
    return redirect(chalani)


@org_required
@require_POST
def delete(request, pk):
    chalani = _get_chalani(request, pk)
    if chalani.status in {Chalani.Status.VERIFIED, Chalani.Status.BILLED}:
        messages.error(request, _("A verified chalani cannot be deleted."))
        return redirect(chalani)
    chalani.delete()
    messages.success(request, _("Draft deleted."))
    return redirect("chalani:register")


@org_required
@require_GET
def photo(request, pk):
    """The only way a photo is ever served — MEDIA_ROOT is not public."""
    chalani = _get_chalani(request, pk)
    if not chalani.photo:
        raise Http404(_("There is no photo"))
    content_type = mimetypes.guess_type(chalani.photo.name)[0] or "application/octet-stream"
    response = FileResponse(chalani.photo.open("rb"), content_type=content_type)
    response["Cache-Control"] = "private, max-age=3600"
    response["Content-Disposition"] = f'inline; filename="chalani-{chalani.pk}"'
    return response


# --------------------------------------------------------------------- catalog
@org_required
def vendor_list(request):
    query = request.GET.get("q", "").strip()
    vendors = Vendor.objects.for_org(request.organization).annotate(
        chalani_count=Count("chalanis")
    )
    if query:
        vendors = vendors.filter(
            Q(name__icontains=query) | Q(name_np__icontains=query) | Q(pan_no__icontains=query)
        )
    context = {"vendors": vendors, "q": query}
    if request.htmx:
        return render(request, "chalani/vendor_list.html#rows", context)
    return render(request, "chalani/vendor_list.html", context)


@org_required
def vendor_form(request, pk=None):
    vendor = get_object_or_404(Vendor.objects.for_org(request.organization), pk=pk) if pk else None
    if request.method == "POST":
        form = VendorForm(request.POST, instance=vendor, organization=request.organization)
        if form.is_valid():
            vendor = form.save()
            messages.success(request, _("%(vendor)s saved.") % {"vendor": vendor})
            if request.GET.get("next") == "chalani":
                return redirect(reverse("chalani:register"))
            return redirect("chalani:vendor_list")
    else:
        form = VendorForm(instance=vendor, organization=request.organization)
    return render(request, "chalani/vendor_form.html", {"form": form, "vendor": vendor})


@org_required
def item_list(request):
    query = request.GET.get("q", "").strip()
    items = Item.objects.for_org(request.organization).annotate(
        line_count=Count("chalani_lines")
    )
    if query:
        items = items.filter(Q(name__icontains=query) | Q(name_np__icontains=query))
    context = {"items": items, "q": query}
    if request.htmx:
        return render(request, "chalani/item_list.html#rows", context)
    return render(request, "chalani/item_list.html", context)


@org_required
def item_form(request, pk=None):
    item = get_object_or_404(Item.objects.for_org(request.organization), pk=pk) if pk else None
    if request.method == "POST":
        form = ItemForm(request.POST, instance=item, organization=request.organization)
        if form.is_valid():
            form.save()
            messages.success(request, _("Item saved."))
            return redirect("chalani:item_list")
    else:
        form = ItemForm(instance=item, organization=request.organization)
    return render(request, "chalani/item_form.html", {"form": form, "item": item})


# --------------------------------------------------------------------- reports
@org_required
def vendor_report(request):
    """Vendor-wise totals for one fiscal year — the payoff of normalising items."""
    fy = request.GET.get("fy") or npdates.fiscal_year(npdates.today_bs())
    chalanis = Chalani.objects.for_org(request.organization).in_fiscal_year(fy)
    rows = (
        chalanis.values("vendor", "vendor__name", "vendor__name_np")
        .annotate(
            chalani_count=Count("id", distinct=True),
            amount=Sum(F("items__qty") * F("items__rate"), output_field=AMOUNT),
            verified=Count("id", distinct=True, filter=Q(status__in=["verified", "billed"])),
        )
        .order_by("-amount")
    )
    item_rows = (
        ChalaniItem.objects.filter(chalani__in=chalanis)
        .values("item", "item__name", "item__name_np", "unit")
        .annotate(
            # `qty` would shadow the column F("qty") below — alias it.
            total_qty=Sum("qty"),
            amount=Sum(F("qty") * F("rate"), output_field=AMOUNT),
            chalani_count=Count("chalani", distinct=True),
        )
        .order_by("-amount")
    )
    return render(
        request,
        "chalani/report.html",
        {
            "fy": fy,
            "fiscal_years": npdates.recent_fiscal_years(6),
            "rows": rows,
            "item_rows": item_rows,
            "grand_total": sum((r["amount"] or 0) for r in rows),
            "period": npdates.fiscal_year_bounds(fy),
        },
    )


@org_required
def export_csv(request):
    import csv

    chalanis, _ = _filtered_register(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="chalani-register.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            _("Date (BS)"), _("Date (AD)"), _("Fiscal year"), _("Chalani no."),
            _("Supplier"), _("Vehicle no."), _("Lines"), _("Total amount"), _("Status"),
        ]
    )
    for chalani in chalanis.iterator():
        writer.writerow(
            [
                chalani.date_bs,
                chalani.date.isoformat() if chalani.date else "",
                chalani.fiscal_year,
                chalani.chalani_no,
                str(chalani.vendor) if chalani.vendor_id else "",
                chalani.vehicle_no,
                chalani.line_count,
                chalani.total or 0,
                chalani.get_status_display(),
            ]
        )
    return response


@org_required
def dashboard(request):
    org_chalanis = Chalani.objects.for_org(request.organization)
    fy = npdates.fiscal_year(npdates.today_bs())
    this_fy = org_chalanis.in_fiscal_year(fy)
    return render(
        request,
        "chalani/dashboard.html",
        {
            "fy": fy,
            "counts": {
                "total": this_fy.count(),
                "drafts": this_fy.filter(status=Chalani.Status.DRAFT).count(),
                "extracting": this_fy.filter(status=Chalani.Status.EXTRACTING).count(),
                "verified": this_fy.filter(status=Chalani.Status.VERIFIED).count(),
                "billed": this_fy.filter(status=Chalani.Status.BILLED).count(),
            },
            "amount": ChalaniItem.objects.filter(chalani__in=this_fy).aggregate(
                total=Sum(F("qty") * F("rate"), output_field=AMOUNT)
            )["total"],
            "recent": this_fy.select_related("vendor").with_totals()[:8],
            "top_vendors": (
                this_fy.values("vendor__name", "vendor__name_np")
                .annotate(amount=Sum(F("items__qty") * F("items__rate"), output_field=AMOUNT))
                .filter(vendor__isnull=False)
                .order_by("-amount")[:5]
            ),
            "vendor_count": Vendor.objects.for_org(request.organization).count(),
            "item_count": Item.objects.for_org(request.organization).count(),
        },
    )
