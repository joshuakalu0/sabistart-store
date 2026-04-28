from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class NotificationSettings(models.Model):
    """
    Email and SMS notification configuration.
    
    CONTROLS:
    - Email notification triggers
    - SMS notification settings
    - Admin notifications
    - Customer notifications
    - Marketing communications
    
    IMPACT:
    - Customer communication
    - Order updates
    - Marketing campaigns
    
    SHOPIFY EQUIVALENT: Settings > Notifications
    """
    
    # === EMAIL NOTIFICATIONS - ORDERS ===
    send_order_confirmation = models.BooleanField(
        default=True,
        help_text="Send order confirmation email"
    )
    
    send_order_processing = models.BooleanField(
        default=True,
        help_text="Send email when order is being processed"
    )
    
    send_order_shipped = models.BooleanField(
        default=True,
        help_text="Send shipping notification"
    )
    
    send_order_delivered = models.BooleanField(
        default=True,
        help_text="Send delivery confirmation"
    )
    
    send_order_cancelled = models.BooleanField(
        default=True,
        help_text="Send cancellation notification"
    )
    
    send_order_refunded = models.BooleanField(
        default=True,
        help_text="Send refund notification"
    )
    
    send_order_on_hold = models.BooleanField(
        default=True,
        help_text="Send notification when order on hold"
    )
    
    # === EMAIL NOTIFICATIONS - CUSTOMER ===
    send_welcome_email = models.BooleanField(
        default=True,
        help_text="Send welcome email to new customers"
    )
    
    send_password_reset = models.BooleanField(
        default=True,
        help_text="Send password reset emails"
    )
    
    send_account_verification = models.BooleanField(
        default=True,
        help_text="Send email verification link"
    )
    
    send_wishlist_reminder = models.BooleanField(
        default=False,
        help_text="Send wishlist reminder emails"
    )
    
    wishlist_reminder_days = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="Days before sending wishlist reminder"
    )
    
    # === EMAIL NOTIFICATIONS - MARKETING ===
    send_abandoned_cart = models.BooleanField(
        default=True,
        help_text="Send abandoned cart recovery emails"
    )
    
    abandoned_cart_delay_hours = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(72)],
        help_text="Hours before sending first abandoned cart email"
    )
    
    abandoned_cart_series_count = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Number of abandoned cart emails to send"
    )
    
    send_back_in_stock = models.BooleanField(
        default=True,
        help_text="Notify customers when out-of-stock items return"
    )
    
    send_price_drop_alert = models.BooleanField(
        default=False,
        help_text="Notify customers of price drops on wishlist items"
    )
    
    send_newsletter = models.BooleanField(
        default=True,
        help_text="Send newsletter emails"
    )
    
    send_promotional_emails = models.BooleanField(
        default=True,
        help_text="Send promotional/marketing emails"
    )
    
    # === SMS NOTIFICATIONS ===
    enable_sms = models.BooleanField(
        default=False,
        help_text="Enable SMS notifications"
    )
    
    sms_provider = models.CharField(
        max_length=20,
        choices=[
            ('twilio', 'Twilio'),
            ('nexmo', 'Nexmo/Vonage'),
            ('aws_sns', 'AWS SNS'),
            ('messagebird', 'MessageBird'),
            ('plivo', 'Plivo'),
        ],
        blank=True,
        help_text="SMS service provider"
    )
    
    sms_order_confirmation = models.BooleanField(
        default=False,
        help_text="Send SMS for order confirmation"
    )
    
    sms_order_shipped = models.BooleanField(
        default=True,
        help_text="Send SMS when order ships"
    )
    
    sms_order_delivered = models.BooleanField(
        default=False,
        help_text="Send SMS when order delivered"
    )
    
    sms_order_cancelled = models.BooleanField(
        default=True,
        help_text="Send SMS for order cancellation"
    )
    
    sms_verification_code = models.BooleanField(
        default=True,
        help_text="Send SMS verification codes"
    )
    
    # === ADMIN NOTIFICATIONS ===
    notify_admin_new_order = models.BooleanField(
        default=True,
        help_text="Notify admin of new orders"
    )
    
    notify_admin_low_stock = models.BooleanField(
        default=True,
        help_text="Notify admin when stock is low"
    )
    
    low_stock_threshold = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Stock level to trigger low stock alert"
    )
    
    notify_admin_out_of_stock = models.BooleanField(
        default=True,
        help_text="Notify admin when product out of stock"
    )
    
    notify_admin_new_review = models.BooleanField(
        default=True,
        help_text="Notify admin of new product reviews"
    )
    
    notify_admin_new_customer = models.BooleanField(
        default=False,
        help_text="Notify admin of new customer registrations"
    )
    
    notify_admin_failed_payment = models.BooleanField(
        default=True,
        help_text="Notify admin of failed payments"
    )
    
    notify_admin_refund_request = models.BooleanField(
        default=True,
        help_text="Notify admin of refund requests"
    )
    
    admin_notification_emails = models.JSONField(
        default=list,
        blank=True,
        help_text="List of admin emails to notify"
    )
    
    # === NOTIFICATION TIMING ===
    quiet_hours_enabled = models.BooleanField(
        default=False,
        help_text="Enable quiet hours (no notifications during this time)"
    )
    
    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        help_text="Start of quiet hours (e.g., 22:00)"
    )
    
    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        help_text="End of quiet hours (e.g., 08:00)"
    )
    
    respect_customer_timezone = models.BooleanField(
        default=True,
        help_text="Send notifications based on customer's timezone"
    )
    
    # === EMAIL PREFERENCES ===
    email_from_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Sender name for emails (defaults to store name)"
    )
    
    email_reply_to = models.EmailField(
        blank=True,
        help_text="Reply-to email address"
    )
    
    include_order_details_in_email = models.BooleanField(
        default=True,
        help_text="Include full order details in emails"
    )
    
    include_tracking_link = models.BooleanField(
        default=True,
        help_text="Include order tracking link in shipping emails"
    )
    
    # === PUSH NOTIFICATIONS ===
    enable_push_notifications = models.BooleanField(
        default=False,
        help_text="Enable browser/app push notifications"
    )
    
    push_order_updates = models.BooleanField(
        default=True,
        help_text="Send push notifications for order updates"
    )
    
    push_promotional = models.BooleanField(
        default=False,
        help_text="Send promotional push notifications"
    )
    
    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notification_settings'
        verbose_name = 'Notification Setting'
        verbose_name_plural = 'Notification Settings'
    
    def __str__(self):
        return "Notification Settings"
    
    def clean(self):
        errors = {}
        
        if self.quiet_hours_enabled:
            if not self.quiet_hours_start or not self.quiet_hours_end:
                errors['quiet_hours_start'] = "Both start and end times required for quiet hours."
        
        if self.enable_sms and not self.sms_provider:
            errors['sms_provider'] = "SMS provider required when SMS is enabled."
        
        if errors:
            raise ValidationError(errors)


