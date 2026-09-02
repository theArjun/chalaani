from django import forms

from .models import Membership, Organization
from django.utils.translation import gettext_lazy as _

INPUT = "input input-bordered w-full"


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "name_np", "pan_no", "phone", "address", "district"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "name_np": forms.TextInput(attrs={"class": INPUT}),
            "pan_no": forms.TextInput(attrs={"class": INPUT + " font-mono", "maxlength": 9}),
            "phone": forms.TextInput(attrs={"class": INPUT + " font-mono"}),
            "address": forms.TextInput(attrs={"class": INPUT}),
            "district": forms.TextInput(attrs={"class": INPUT, "placeholder": _("Kathmandu")}),
        }


class AddMemberForm(forms.Form):
    username = forms.CharField(
        label=_("Username"), widget=forms.TextInput(attrs={"class": INPUT})
    )
    role = forms.ChoiceField(
        label=_("Role"),
        choices=Membership.Role.choices,
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )

    def clean_username(self):
        from django.contrib.auth import get_user_model

        username = self.cleaned_data["username"].strip()
        try:
            return get_user_model().objects.get(username__iexact=username)
        except get_user_model().DoesNotExist as exc:
            raise forms.ValidationError(_("No such user.")) from exc
