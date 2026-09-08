def organization(request):
    return {
        "organization": getattr(request, "organization", None),
        "membership": getattr(request, "membership", None),
        "memberships": (
            request.user.memberships.select_related("organization")
            if getattr(request, "user", None) is not None
            and request.user.is_authenticated
            else []
        ),
    }
