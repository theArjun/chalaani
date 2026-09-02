"""Helpers that keep org scoping impossible to forget."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from functools import wraps
from django.utils.translation import gettext_lazy as _


def org_required(view):
    """Login + an organization on the request; otherwise send them to set one up."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if getattr(request, "organization", None) is None:
            return redirect("orgs:create")
        return view(request, *args, **kwargs)

    return wrapper


def verifier_required(view):
    """Owners and managers may verify/bill; staff may only draft."""

    @wraps(view)
    @org_required
    def wrapper(request, *args, **kwargs):
        if not request.membership.can_verify:
            raise PermissionDenied(_("Only a manager or the owner can do this."))
        return view(request, *args, **kwargs)

    return wrapper


def org_objects(model, request):
    """`org_objects(Vendor, request)` — the only way views should reach data."""
    return model.objects.for_org(request.organization)
