from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from orgs.models import Membership, Organization

INPUT = "input input-bordered w-full"


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT)


class SignupForm(UserCreationForm):
    """One form creates the user, their firm, and the owner membership."""

    full_name_np = forms.CharField(
        label="तपाईंको नाम", max_length=150, widget=forms.TextInput(attrs={"class": INPUT})
    )
    phone = forms.CharField(
        label="फोन", max_length=20, required=False, widget=forms.TextInput(attrs={"class": INPUT})
    )
    organization_name = forms.CharField(
        label="फर्मको नाम (English)",
        max_length=200,
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Shree Ram Traders"}),
    )
    organization_name_np = forms.CharField(
        label="फर्मको नाम (नेपाली)",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "श्री राम ट्रेडर्स"}),
    )

    class Meta(UserCreationForm.Meta):
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name_np = self.cleaned_data["full_name_np"]
        user.phone = self.cleaned_data.get("phone", "")
        user.save()
        organization = Organization.objects.create(
            name=self.cleaned_data["organization_name"],
            name_np=self.cleaned_data.get("organization_name_np", ""),
        )
        Membership.objects.create(
            organization=organization, user=user, role=Membership.Role.OWNER
        )
        user.active_organization = organization
        user.save(update_fields=["active_organization"])
        return user
