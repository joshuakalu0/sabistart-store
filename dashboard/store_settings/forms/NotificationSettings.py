import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import NotificationSettings

logger = logging.getLogger(__name__)


class NotificationSettingsForm(forms.ModelForm):
    """
    Comprehensive form for managing Notification Settings.
    Organized into logical sections for better UX.
    """

    # JSON Field for admin emails - using a text area for simplicity
    admin_notification_emails = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
            'rows': 3,
            'placeholder': 'admin@example.com, manager@example.com'
        }),
        help_text="Comma-separated list of admin emails to notify"
    )

    class Meta:
        model = NotificationSettings
        exclude = ['created_at', 'updated_at']
        widgets = {
            # === EMAIL NOTIFICATIONS - ORDERS ===
            'send_order_confirmation': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_order_processing': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_order_shipped': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_order_delivered': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_order_cancelled': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_order_refunded': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_order_on_hold': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === EMAIL NOTIFICATIONS - CUSTOMER ===
            'send_welcome_email': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_password_reset': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_account_verification': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_wishlist_reminder': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'wishlist_reminder_days': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 90
            }),

            # === EMAIL NOTIFICATIONS - MARKETING ===
            'send_abandoned_cart': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'abandoned_cart_delay_hours': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 72
            }),
            'abandoned_cart_series_count': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 5
            }),
            'send_back_in_stock': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_price_drop_alert': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_newsletter': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'send_promotional_emails': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === SMS NOTIFICATIONS ===
            'enable_sms': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'sms_provider': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 appearance-none transition duration-150'}),
            'sms_order_confirmation': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'sms_order_shipped': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'sms_order_delivered': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'sms_order_cancelled': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'sms_verification_code': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === ADMIN NOTIFICATIONS ===
            'notify_admin_new_order': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'notify_admin_low_stock': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'low_stock_threshold': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'min': 1,
                'max': 100
            }),
            'notify_admin_out_of_stock': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'notify_admin_new_review': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'notify_admin_new_customer': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'notify_admin_failed_payment': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'notify_admin_refund_request': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === NOTIFICATION TIMING ===
            'quiet_hours_enabled': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'quiet_hours_start': forms.TimeInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'time'
            }),
            'quiet_hours_end': forms.TimeInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'type': 'time'
            }),
            'respect_customer_timezone': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === EMAIL PREFERENCES ===
            'email_from_name': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'Store Name'
            }),
            'email_reply_to': forms.EmailInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition duration-150',
                'placeholder': 'noreply@store.com'
            }),
            'include_order_details_in_email': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'include_tracking_link': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),

            # === PUSH NOTIFICATIONS ===
            'enable_push_notifications': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'push_order_updates': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
            'push_promotional': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 shadow-sm focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition duration-150'}),
        }

    def clean_wishlist_reminder_days(self):
        """Validate wishlist reminder days range."""
        days = self.cleaned_data.get('wishlist_reminder_days')
        if days and not (1 <= days <= 90):
            raise ValidationError(
                _("Wishlist reminder days must be between 1 and 90."))
        return days

    def clean_abandoned_cart_delay_hours(self):
        """Validate abandoned cart delay hours range."""
        hours = self.cleaned_data.get('abandoned_cart_delay_hours')
        if hours and not (1 <= hours <= 72):
            raise ValidationError(
                _("Abandoned cart delay must be between 1 and 72 hours."))
        return hours

    def clean_abandoned_cart_series_count(self):
        """Validate abandoned cart series count range."""
        count = self.cleaned_data.get('abandoned_cart_series_count')
        if count and not (1 <= count <= 5):
            raise ValidationError(
                _("Abandoned cart series count must be between 1 and 5."))
        return count

    def clean_low_stock_threshold(self):
        """Validate low stock threshold range."""
        threshold = self.cleaned_data.get('low_stock_threshold')
        if threshold and not (1 <= threshold <= 100):
            raise ValidationError(
                _("Low stock threshold must be between 1 and 100."))
        return threshold

    def clean_admin_notification_emails(self):
        """Validate and convert admin notification emails from comma-separated string to list."""
        emails_str = self.cleaned_data.get('admin_notification_emails', '')

        if not emails_str:
            return []

        # Split by comma and clean up
        emails = [email.strip()
                  for email in emails_str.split(',') if email.strip()]

        # Validate email format
        from django.core.validators import validate_email
        for email in emails:
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError(
                    _("Invalid email address: %(email)s") % {'email': email})

        return emails

    def clean(self):
        """Cross-field validation for conditional fields."""
        cleaned_data = super().clean()

        # === SMS Logic ===
        sms_enabled = cleaned_data.get('enable_sms')
        sms_provider = cleaned_data.get('sms_provider')

        if sms_enabled and not sms_provider:
            self.add_error(
                'sms_provider',
                _("SMS provider is required when SMS notifications are enabled.")
            )

        if not sms_enabled:
            logger.info(
                "SMS notifications disabled - SMS-specific settings will be ignored")

        # === Quiet Hours Logic ===
        quiet_hours_enabled = cleaned_data.get('quiet_hours_enabled')
        quiet_hours_start = cleaned_data.get('quiet_hours_start')
        quiet_hours_end = cleaned_data.get('quiet_hours_end')

        if quiet_hours_enabled:
            if not quiet_hours_start or not quiet_hours_end:
                self.add_error(
                    'quiet_hours_start',
                    _("Both start and end times are required when quiet hours is enabled.")
                )
                self.add_error(
                    'quiet_hours_end',
                    _("Both start and end times are required when quiet hours is enabled.")
                )

        # === Abandoned Cart Logic ===
        abandoned_cart_enabled = cleaned_data.get('send_abandoned_cart')
        abandoned_cart_delay = cleaned_data.get('abandoned_cart_delay_hours')
        abandoned_cart_series = cleaned_data.get('abandoned_cart_series_count')

        if abandoned_cart_enabled and not abandoned_cart_delay:
            self.add_error(
                'abandoned_cart_delay_hours',
                _("Abandoned cart delay is required when abandoned cart emails are enabled.")
            )

        # === Wishlist Reminder Logic ===
        wishlist_enabled = cleaned_data.get('send_wishlist_reminder')
        wishlist_days = cleaned_data.get('wishlist_reminder_days')

        if wishlist_enabled and not wishlist_days:
            self.add_error(
                'wishlist_reminder_days',
                _("Wishlist reminder days is required when wishlist reminders are enabled.")
            )

        # === Low Stock Logic ===
        notify_low_stock = cleaned_data.get('notify_admin_low_stock')
        low_stock_threshold = cleaned_data.get('low_stock_threshold')

        if notify_low_stock and not low_stock_threshold:
            self.add_error(
                'low_stock_threshold',
                _("Low stock threshold is required when low stock notifications are enabled.")
            )

        # === Push Notifications Logic ===
        push_enabled = cleaned_data.get('enable_push_notifications')
        if not push_enabled:
            logger.info(
                "Push notifications disabled - push-specific settings will be ignored")

        # === Email Preferences Logic ===
        email_from_name = cleaned_data.get('email_from_name')
        if email_from_name and len(email_from_name) > 100:
            self.add_error(
                'email_from_name',
                _("Email from name cannot exceed 100 characters.")
            )

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=False)

        # Convert admin emails from string to list for JSONField
        admin_emails_str = self.cleaned_data.get(
            'admin_notification_emails', '')
        if admin_emails_str:
            instance.admin_notification_emails = [
                email.strip() for email in admin_emails_str.split(',') if email.strip()
            ]
        else:
            instance.admin_notification_emails = []

        if commit:
            instance.save()
            logger.info(
                f"NotificationSettings saved (tenant schema: {instance._meta.db_table})"
            )

        return instance
