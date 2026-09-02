"""Forms for the register. Every queryset is org-scoped at construction time."""

from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from nepal.forms import BikramSambatDateField, NepaliDecimalField
from nepal.units import UNIT_CHOICES

from .models import Chalani, ChalaniItem, Item, Vendor

INPUT = "input input-bordered w-full"
SELECT = "select select-bordered w-full"


class OrgFormMixin:
    """Pass `organization=` and the form both filters and stamps it."""

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.organization is not None and obj.organization_id is None:
            obj.organization = self.organization
        if commit:
            obj.save()
        return obj


class ChalaniUploadForm(forms.Form):
    photo = forms.ImageField(
        label="चलानीको फोटो",
        help_text="कागजको फोटो खिच्नुहोस् — AI ले पढेर मस्यौदा बनाउँछ.",
        widget=forms.ClearableFileInput(
            attrs={"class": "file-input file-input-bordered w-full", "accept": "image/*", "capture": "environment"}
        ),
    )
    use_ai = forms.BooleanField(
        label="AI ले पढोस् (Read it with AI)",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "toggle toggle-primary"}),
    )


class ChalaniForm(OrgFormMixin, forms.ModelForm):
    date_bs = BikramSambatDateField(required=False)

    class Meta:
        model = Chalani
        fields = ["vendor", "chalani_no", "date_bs", "vehicle_no", "received_by", "remarks"]
        widgets = {
            "vendor": forms.Select(attrs={"class": SELECT}),
            "chalani_no": forms.TextInput(attrs={"class": INPUT, "placeholder": "जस्तै C/०७८-१२०४"}),
            "vehicle_no": forms.TextInput(attrs={"class": INPUT, "placeholder": "बा १२ ख ३४५६"}),
            "received_by": forms.TextInput(attrs={"class": INPUT}),
            "remarks": forms.TextInput(attrs={"class": INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendor"].queryset = Vendor.objects.for_org(self.organization).filter(
            is_active=True
        )
        self.fields["vendor"].empty_label = "— आपूर्तिकर्ता छान्नुहोस् —"


class ChalaniItemForm(forms.ModelForm):
    qty = NepaliDecimalField(
        max_digits=12,
        decimal_places=3,
        widget=forms.TextInput(attrs={"class": INPUT + " text-right font-mono", "inputmode": "decimal"}),
    )
    rate = NepaliDecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT + " text-right font-mono", "inputmode": "decimal"}),
    )

    class Meta:
        model = ChalaniItem
        fields = ["item", "description", "qty", "unit", "rate"]
        widgets = {
            "item": forms.Select(attrs={"class": "select select-bordered select-sm w-full"}),
            "description": forms.TextInput(attrs={"class": INPUT, "placeholder": "कागजमा जस्तो लेखिएको छ"}),
            "unit": forms.Select(attrs={"class": "select select-bordered w-full"}, choices=UNIT_CHOICES),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.for_org(organization).filter(is_active=True)
        self.fields["item"].empty_label = "— क्याटलगमा जोड्नुहोस् —"
        self.fields["item"].required = False


class BaseChalaniItemFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["organization"] = self.organization
        return kwargs


ChalaniItemFormSet = inlineformset_factory(
    Chalani,
    ChalaniItem,
    form=ChalaniItemForm,
    formset=BaseChalaniItemFormSet,
    fields=["item", "description", "qty", "unit", "rate"],
    extra=0,
    can_delete=True,
)


class VendorForm(OrgFormMixin, forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "name_np", "pan_no", "phone", "address", "district", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT, "placeholder": "Shree Ram Hardware"}),
            "name_np": forms.TextInput(attrs={"class": INPUT, "placeholder": "श्री राम हार्डवेयर"}),
            "pan_no": forms.TextInput(attrs={"class": INPUT + " font-mono", "inputmode": "numeric", "maxlength": 9}),
            "phone": forms.TextInput(attrs={"class": INPUT + " font-mono", "inputmode": "tel"}),
            "address": forms.TextInput(attrs={"class": INPUT}),
            "district": forms.TextInput(attrs={"class": INPUT, "placeholder": "काठमाडौँ"}),
            "is_active": forms.CheckboxInput(attrs={"class": "toggle toggle-success"}),
        }


class ItemForm(OrgFormMixin, forms.ModelForm):
    class Meta:
        model = Item
        fields = ["name", "name_np", "unit", "default_rate", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT, "placeholder": "Cement OPC 50kg"}),
            "name_np": forms.TextInput(attrs={"class": INPUT, "placeholder": "सिमेन्ट ओ.पि.सि. ५० के.जी."}),
            "unit": forms.Select(attrs={"class": SELECT}),
            "default_rate": forms.TextInput(attrs={"class": INPUT + " text-right font-mono", "inputmode": "decimal"}),
            "is_active": forms.CheckboxInput(attrs={"class": "toggle toggle-success"}),
        }
