from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    NotificationChannel,
    EmailChannelConfig,
    SMSChannelConfig,
    PushChannelConfig,
    SlackChannelConfig,
    NotificationCategory,
    NotificationTemplate,
    NotificationTemplateVersion,
    WebhookEndpoint,
    WebhookEventSubscription,
    WebhookSigningSecret,
    InAppNotification,
    ChannelType
)


class NotificationChannelForm(forms.ModelForm):
    class Meta:
        model = NotificationChannel
        fields = [
            'name', 'channel_type', 'status', 'description',
            'is_default', 'priority', 'rate_limit_per_minute', 'rate_limit_per_hour',
            'rate_limit_per_day', 'failure_threshold'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class EmailChannelConfigForm(forms.ModelForm):
    class Meta:
        model = EmailChannelConfig
        fields = [
            'provider', 'from_email', 'from_name', 'reply_to', 'bounce_email',
            'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_encryption',
            'api_key', 'api_domain', 'api_region', 'aws_region', 'aws_access_key_id',
            'aws_secret_access_key', 'enable_open_tracking', 'enable_click_tracking',
            'enable_unsubscribe_header', 'test_email'
        ]
        widgets = {
            'smtp_password': forms.PasswordInput(render_value=True),
            'api_key': forms.PasswordInput(render_value=True),
            'aws_secret_access_key': forms.PasswordInput(render_value=True),
        }


class SMSChannelConfigForm(forms.ModelForm):
    class Meta:
        model = SMSChannelConfig
        fields = [
            'provider', 'sender_id', 'account_sid', 'api_key', 'api_secret',
            'api_url', 'webhook_url', 'default_country_code', 'supports_unicode',
            'supports_delivery_receipts', 'test_phone_number'
        ]
        widgets = {
            'account_sid': forms.PasswordInput(render_value=True),
            'api_key': forms.PasswordInput(render_value=True),
            'api_secret': forms.PasswordInput(render_value=True),
        }


class PushChannelConfigForm(forms.ModelForm):
    class Meta:
        model = PushChannelConfig
        fields = [
            'fcm_server_key', 'fcm_sender_id', 'fcm_project_id', 'fcm_service_account_json',
            'apns_key_id', 'apns_team_id', 'apns_bundle_id', 'apns_private_key', 'apns_use_sandbox',
            'vapid_public_key', 'vapid_private_key', 'vapid_subject',
            'default_icon_url', 'default_sound', 'default_click_action'
        ]
        widgets = {
            'fcm_server_key': forms.PasswordInput(render_value=True),
            'fcm_service_account_json': forms.PasswordInput(render_value=True),
            'apns_private_key': forms.PasswordInput(render_value=True),
            'vapid_private_key': forms.PasswordInput(render_value=True),
        }


class SlackChannelConfigForm(forms.ModelForm):
    class Meta:
        model = SlackChannelConfig
        fields = [
            'webhook_url', 'bot_token', 'default_channel', 'default_username',
            'default_icon_emoji', 'default_icon_url', 'mention_channel'
        ]
        widgets = {
            'webhook_url': forms.PasswordInput(render_value=True),
            'bot_token': forms.PasswordInput(render_value=True),
        }


class NotificationCategoryForm(forms.ModelForm):
    class Meta:
        model = NotificationCategory
        fields = [
            'name', 'slug', 'description', 'display_order',
            'is_customer_visible', 'allow_customer_opt_out', 'default_opt_in',
            'icon', 'color'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'color': forms.TextInput(attrs={'type': 'color'}),
        }


class NotificationTemplateForm(forms.ModelForm):
    class Meta:
        model = NotificationTemplate
        fields = [
            'name', 'category', 'channel', 'event_slug', 'channel_type', 'locale',
            'status', 'is_enabled', 'send_delay_seconds', 'max_send_attempts',
            'retry_delay_seconds', 'dedup_window_seconds', 'ab_test_enabled',
            'ab_test_percentage', 'ab_test_variant_b', 'description'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter ab_test_variant_b to only show templates for the same event and channel
        if self.instance and self.instance.pk:
            self.fields['ab_test_variant_b'].queryset = NotificationTemplate.objects.filter(
                event_slug=self.instance.event_slug,
                channel_type=self.instance.channel_type
            ).exclude(pk=self.instance.pk)


class NotificationTemplateVersionForm(forms.ModelForm):
    class Meta:
        model = NotificationTemplateVersion
        fields = [
            'version_label', 'subject', 'preheader', 'html_body', 'text_body',
            'title', 'body', 'action_url', 'action_label', 'email_template_id',
            'image_url', 'icon_url', 'change_notes'
        ]
        widgets = {
            'html_body': forms.Textarea(attrs={'rows': 10}),
            'text_body': forms.Textarea(attrs={'rows': 5}),
            'body': forms.Textarea(attrs={'rows': 5}),
            'change_notes': forms.Textarea(attrs={'rows': 2}),
        }


class WebhookEndpointForm(forms.ModelForm):
    class Meta:
        model = WebhookEndpoint
        fields = [
            'name', 'url', 'description', 'status', 'payload_format', 'api_version',
            'secret_token', 'max_retry_attempts', 'retry_delay_seconds',
            'use_exponential_backoff', 'timeout_seconds'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'secret_token': forms.PasswordInput(render_value=True),
        }


class WebhookEventSubscriptionForm(forms.ModelForm):
    class Meta:
        model = WebhookEventSubscription
        fields = [
            'event_slug', 'is_active'
        ]


class InAppNotificationForm(forms.ModelForm):
    class Meta:
        model = InAppNotification
        fields = [
            'title', 'body', 'icon', 'image_url', 'notification_type', 'audience',
            'delivery_scope', 'target_role', 'action_url', 'action_label',
            'is_active', 'expires_at', 'is_pinned', 'send_push', 'send_email',
            'color', 'badge_count'
        ]
        widgets = {
            'body': forms.Textarea(attrs={'rows': 3}),
            'color': forms.TextInput(attrs={'type': 'color'}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
