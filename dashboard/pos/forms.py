from __future__ import annotations

from django import forms

from sabistart.ui.forms import TailwindFormMixin

from .models import POSProduct, POSSession, POSTerminal, Store


class POSProductForm(TailwindFormMixin, forms.ModelForm):
    stock_quantity = forms.IntegerField(min_value=0, initial=0, help_text="Opening stock for this product.")

    class Meta:
        model = POSProduct
        fields = [
            "name",
            "image",
            "selling_price",
            "stock_quantity",
            "description",
            "barcode",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Product name"
        self.fields["image"].label = "Product image"
        self.fields["selling_price"].label = "Price"
        self.fields["description"].required = False
        self.fields["barcode"].required = False
        self.fields["barcode"].label = "Barcode"


class POSPlaceForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Store
        fields = [
            "name",
            "code",
            "address",
            "contact_name",
            "contact_phone",
            "contact_email",
            "status",
            "tax_rate",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class POSRegisterForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = POSTerminal
        fields = [
            "store",
            "name",
            "code",
            "terminal_type",
            "printer_identifier",
            "receipt_header",
            "receipt_footer",
            "notes",
            "is_active",
        ]
        widgets = {
            "receipt_header": forms.Textarea(attrs={"rows": 3}),
            "receipt_footer": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class POSSessionOpenForm(TailwindFormMixin, forms.Form):
    terminal = forms.ModelChoiceField(queryset=POSTerminal.objects.none(), label="Register")
    opening_cash = forms.DecimalField(min_value=0, decimal_places=2, max_digits=12, initial=0, label="Opening cash")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, terminals=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["terminal"].queryset = terminals or POSTerminal.objects.none()


class POSSessionCloseForm(TailwindFormMixin, forms.Form):
    closing_cash = forms.DecimalField(min_value=0, decimal_places=2, max_digits=12, initial=0, label="Closing cash")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
