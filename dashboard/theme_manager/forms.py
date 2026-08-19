from __future__ import annotations

import json

from django import forms

from sabistart.ui.forms import TailwindFormMixin


class TenantThemeConfigureForm(TailwindFormMixin, forms.Form):
    store_name = forms.CharField(max_length=200, required=False, label="Store name")
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Bio")
    profile_image = forms.URLField(required=False, label="Profile image URL")
    social_links = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Enter one social link per line.",
        label="Social links",
    )

    def __init__(self, *args, theme_schema: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.theme_schema = theme_schema or {}
        for field in self.theme_schema.get("fields", []):
            key = str(field.get("key", "")).strip()
            if not key:
                continue
            field_type = str(field.get("type", "text")).strip().lower()
            label = field.get("label") or key.replace("_", " ").title()
            required = bool(field.get("required", False))
            help_text = field.get("help_text", "")
            initial = field.get("default", "")
            if field_type in {"textarea", "richtext"}:
                self.fields[key] = forms.CharField(
                    required=required,
                    label=label,
                    help_text=help_text,
                    initial=initial,
                    widget=forms.Textarea(attrs={"rows": 4}),
                )
            elif field_type == "url":
                self.fields[key] = forms.URLField(required=required, label=label, help_text=help_text, initial=initial)
            elif field_type == "integer":
                self.fields[key] = forms.IntegerField(required=required, label=label, help_text=help_text, initial=initial or None)
            elif field_type == "decimal":
                self.fields[key] = forms.DecimalField(required=required, label=label, help_text=help_text, initial=initial or None)
            elif field_type == "list":
                self.fields[key] = forms.CharField(
                    required=required,
                    label=label,
                    help_text=help_text or "Enter one item per line.",
                    initial="\n".join(initial) if isinstance(initial, list) else initial,
                    widget=forms.Textarea(attrs={"rows": 4}),
                )
            elif field_type == "json":
                self.fields[key] = forms.CharField(
                    required=required,
                    label=label,
                    help_text=help_text or "Enter valid JSON.",
                    initial=json.dumps(initial, indent=2) if initial not in ("", None) else "",
                    widget=forms.Textarea(attrs={"rows": 6}),
                )
            else:
                self.fields[key] = forms.CharField(required=required, label=label, help_text=help_text, initial=initial)

    def initial_from_content(self, universal_content: dict, theme_content: dict):
        self.initial.update(
            {
                "store_name": universal_content.get("name", ""),
                "bio": universal_content.get("bio", ""),
                "profile_image": universal_content.get("profile_image", ""),
                "social_links": "\n".join(universal_content.get("social_links", [])),
            }
        )
        for field in self.theme_schema.get("fields", []):
            key = field.get("key")
            if not key or key not in self.fields:
                continue
            value = theme_content.get(key, field.get("default", ""))
            field_type = str(field.get("type", "text")).strip().lower()
            if field_type == "list" and isinstance(value, list):
                value = "\n".join(str(item) for item in value)
            elif field_type == "json" and value not in ("", None):
                value = json.dumps(value, indent=2)
            self.initial[key] = value
        for name, field in self.fields.items():
            if name in self.initial:
                field.initial = self.initial[name]

    def build_content_payloads(self):
        universal = {
            "name": self.cleaned_data.get("store_name", "").strip(),
            "bio": self.cleaned_data.get("bio", "").strip(),
            "profile_image": self.cleaned_data.get("profile_image", "").strip(),
            "social_links": [
                line.strip()
                for line in (self.cleaned_data.get("social_links", "") or "").splitlines()
                if line.strip()
            ],
        }
        theme_payload = {}
        for field in self.theme_schema.get("fields", []):
            key = field.get("key")
            if not key or key not in self.cleaned_data:
                continue
            value = self.cleaned_data[key]
            field_type = str(field.get("type", "text")).strip().lower()
            if field_type == "list":
                value = [line.strip() for line in (value or "").splitlines() if line.strip()]
            elif field_type == "json":
                value = json.loads(value or "{}")
            theme_payload[key] = value
        return universal, theme_payload
