"""Attach the caller's current organization to every request."""

from __future__ import annotations

from .models import Membership


class CurrentOrganizationMiddleware:
    """Sets `request.organization` and `request.membership` (both may be None).

    Views must still filter their own querysets — this only decides *which*
    org is current, it is not itself the access check.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        request.membership = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            membership = self._resolve(user)
            if membership is not None:
                request.membership = membership
                request.organization = membership.organization
        return self.get_response(request)

    @staticmethod
    def _resolve(user) -> Membership | None:
        memberships = Membership.objects.select_related("organization").filter(
            user=user
        )
        active_id = user.active_organization_id
        if active_id:
            for membership in memberships:
                if membership.organization_id == active_id:
                    return membership
        membership = memberships.first()
        if membership is not None and membership.organization_id != active_id:
            # Stale or unset pointer — heal it so the next request is one query.
            user.active_organization_id = membership.organization_id
            user.save(update_fields=["active_organization"])
        return membership
