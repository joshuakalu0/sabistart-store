"""
system/core/platform_settings_forms.py
========================================
ModelForms for PlatformSmtpSetting, PlatformStorageSetting,
and PlatformMessagingSetting.
"""
from __future__ import annotations

from django import forms

from system.core.platform_settings import (
    PlatformMessagingSetting,
    PlatformSmtpSetting,
    PlatformStorageSetting,
)


class PlatformSmtpSettingForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to keep the current password.",
    )

    class Meta:
        model = PlatformSmtpSetting
        fields = [
            "host",
            "port",
            "security",
            "username",
            "password",
            "default_from_email",
            "default_from_name",
            "is_active",
        ]
        widgets = {
            "host": forms.TextInput(attrs={"placeholder": "smtp.sendgrid.net"}),
            "port": forms.NumberInput(attrs={"min": 1, "max": 65535}),
            "username": forms.TextInput(attrs={"placeholder": "apikey or your@email.com"}),
            "default_from_email": forms.EmailInput(attrs={"placeholder": "no-reply@yourplatform.com"}),
            "default_from_name": forms.TextInput(attrs={"placeholder": "SABIStart Platform"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # If password field was left blank, keep the existing password
        if not self.cleaned_data.get("password"):
            try:
                existing = PlatformSmtpSetting.objects.get(pk=1)
                instance.password = existing.password
            except PlatformSmtpSetting.DoesNotExist:
                pass
        if commit:
            instance.save()
        return instance


class PlatformStorageSettingForm(forms.ModelForm):
    s3_secret_access_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to keep the current secret.",
    )
    vercel_blob_read_write_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to keep the current token.",
    )

    class Meta:
        model = PlatformStorageSetting
        fields = [
            "backend",
            "s3_access_key_id",
            "s3_secret_access_key",
            "s3_bucket_name",
            "s3_region",
            "s3_endpoint_url",
            "s3_custom_domain",
            "vercel_blob_read_write_token",
            "is_active",
        ]
        widgets = {
            "s3_access_key_id": forms.TextInput(attrs={"placeholder": "AKIAIOSFODNN7EXAMPLE"}),
            "s3_bucket_name": forms.TextInput(attrs={"placeholder": "my-platform-media"}),
            "s3_region": forms.TextInput(attrs={"placeholder": "us-east-1"}),
            "s3_endpoint_url": forms.URLInput(attrs={"placeholder": "https://nyc3.digitaloceanspaces.com"}),
            "s3_custom_domain": forms.TextInput(attrs={"placeholder": "cdn.yourplatform.com"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        try:
            existing = PlatformStorageSetting.objects.get(pk=1)
        except PlatformStorageSetting.DoesNotExist:
            existing = None

        if existing:
            if not self.cleaned_data.get("s3_secret_access_key"):
                instance.s3_secret_access_key = existing.s3_secret_access_key
            if not self.cleaned_data.get("vercel_blob_read_write_token"):
                instance.vercel_blob_read_write_token = existing.vercel_blob_read_write_token

        if commit:
            instance.save()
        return instance


class PlatformMessagingSettingForm(forms.ModelForm):
    twilio_auth_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to keep the current token.",
    )
    vonage_api_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to keep the current secret.",
    )
    termii_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to keep the current key.",
    )

    class Meta:
        model = PlatformMessagingSetting
        fields = [
            "provider",
            "twilio_account_sid",
            "twilio_auth_token",
            "twilio_from_number",
            "twilio_whatsapp_from",
            "vonage_api_key",
            "vonage_api_secret",
            "vonage_from_name",
            "termii_api_key",
            "termii_sender_id",
            "is_active",
        ]
        widgets = {
            "twilio_account_sid": forms.TextInput(attrs={"placeholder": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}),
            "twilio_from_number": forms.TextInput(attrs={"placeholder": "+15005550006"}),
            "twilio_whatsapp_from": forms.TextInput(attrs={"placeholder": "whatsapp:+14155238886"}),
            "vonage_api_key": forms.TextInput(attrs={"placeholder": "a1b2c3d4"}),
            "vonage_from_name": forms.TextInput(attrs={"placeholder": "SABIStart", "maxlength": 11}),
            "termii_sender_id": forms.TextInput(attrs={"placeholder": "SABIStart", "maxlength": 11}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        try:
            existing = PlatformMessagingSetting.objects.get(pk=1)
        except PlatformMessagingSetting.DoesNotExist:
            existing = None

        if existing:
            if not self.cleaned_data.get("twilio_auth_token"):
                instance.twilio_auth_token = existing.twilio_auth_token
            if not self.cleaned_data.get("vonage_api_secret"):
                instance.vonage_api_secret = existing.vonage_api_secret
            if not self.cleaned_data.get("termii_api_key"):
                instance.termii_api_key = existing.termii_api_key

        if commit:
            instance.save()
        return instance
