from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AddMemberForm, OrganizationForm
from .models import Membership, Organization


@login_required
def create(request):
    """Shown when a user belongs to no firm yet."""
    if request.method == "POST":
        form = OrganizationForm(request.POST)
        if form.is_valid():
            organization = form.save()
            Membership.objects.create(
                organization=organization, user=request.user, role=Membership.Role.OWNER
            )
            request.user.active_organization = organization
            request.user.save(update_fields=["active_organization"])
            messages.success(request, f"{organization} दर्ता भयो.")
            return redirect("chalani:dashboard")
    else:
        form = OrganizationForm()
    return render(request, "orgs/create.html", {"form": form})


@login_required
@require_POST
def switch(request, pk):
    membership = get_object_or_404(Membership, organization_id=pk, user=request.user)
    request.user.active_organization = membership.organization
    request.user.save(update_fields=["active_organization"])
    messages.info(request, f"{membership.organization} मा स्विच भयो.")
    return redirect("chalani:dashboard")


@login_required
def settings_view(request):
    if request.organization is None:
        return redirect("orgs:create")
    is_owner = request.membership.role == Membership.Role.OWNER
    form = OrganizationForm(instance=request.organization)
    member_form = AddMemberForm()

    if request.method == "POST" and is_owner:
        if "add_member" in request.POST:
            member_form = AddMemberForm(request.POST)
            if member_form.is_valid():
                user = member_form.cleaned_data["username"]
                _, created = Membership.objects.get_or_create(
                    organization=request.organization,
                    user=user,
                    defaults={"role": member_form.cleaned_data["role"]},
                )
                messages.success(
                    request,
                    f"{user} {'थपियो' if created else 'पहिले नै सदस्य हुनुहुन्छ'}.",
                )
                return redirect("orgs:settings")
        else:
            form = OrganizationForm(request.POST, instance=request.organization)
            if form.is_valid():
                form.save()
                messages.success(request, "फर्मको विवरण सुरक्षित भयो.")
                return redirect("orgs:settings")
    elif request.method == "POST":
        messages.error(request, "यो परिवर्तन मालिकले मात्र गर्न सक्नुहुन्छ.")
        return redirect("orgs:settings")

    return render(
        request,
        "orgs/settings.html",
        {
            "form": form,
            "member_form": member_form,
            "is_owner": is_owner,
            "members": request.organization.memberships.select_related("user"),
        },
    )


@login_required
@require_POST
def remove_member(request, pk):
    if request.membership.role != Membership.Role.OWNER:
        messages.error(request, "मालिकले मात्र हटाउन सक्नुहुन्छ.")
        return redirect("orgs:settings")
    membership = get_object_or_404(
        Membership, pk=pk, organization=request.organization
    )
    if membership.user_id == request.user.id:
        messages.error(request, "आफैंलाई हटाउन मिल्दैन.")
    else:
        membership.delete()
        messages.success(request, "सदस्य हटाइयो.")
    return redirect("orgs:settings")
