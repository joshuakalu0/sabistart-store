from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from dashboard.notification.models import ChannelType, EmailChannelConfig, NotificationChannel
from dashboard.notification.utiles.email_testing import EmailSmokeTestResult
from public.userauth.models import TenantUser
from system.account.models import PlatformUser


@override_settings(ALLOWED_HOSTS=["*", ".tenant.test.com", "tenant.test.com", "localhost", "127.0.0.1"])
class NotificationTenantTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        if not hasattr(cls, "_test_schema_name"):
            cls._test_schema_name = f"notify{uuid4().hex[:16]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "Notify",
                "last_name": "Owner",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "Notification Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command(
                "migrate_schemas",
                schema=cls.tenant.schema_name,
                tenant=True,
                interactive=False,
                verbosity=0,
            )
            for model in (TenantUser, NotificationChannel, EmailChannelConfig):
                cls._ensure_tenant_model_table_exists(model)

    @classmethod
    def _ensure_tenant_model_table_exists(cls, model):
        table_name = model._meta.db_table
        with schema_context(cls.tenant.schema_name):
            if table_name not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        for model in (TenantUser, NotificationChannel, EmailChannelConfig):
            self._ensure_tenant_model_table_exists(model)

        self.client = TenantClient(self.tenant)
        self.prefix = "admin"
        self.user = TenantUser.objects.create_user(
            email="notify-admin@example.com",
            password="StrongPass123!",
            first_name="Amina",
            last_name="Admin",
            user_type=TenantUser.UserType.STAFF,
            is_staff=True,
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        self.client.force_login(
            self.user,
            backend="sabistart_store.auth_backends.SchemaAwareAuthenticationBackend",
        )

        self.channel = NotificationChannel.objects.create(
            name="Transactional SMTP",
            channel_type=ChannelType.EMAIL,
            status=NotificationChannel.ChannelStatus.ACTIVE,
            created_by=self.user,
        )
        self.config = EmailChannelConfig.objects.create(
            channel=self.channel,
            provider=EmailChannelConfig.EmailProvider.SMTP,
            from_email="mailer@example.com",
            from_name="Sabistart Mailer",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="mailer@example.com",
            smtp_password="app-password",
            smtp_encryption=EmailChannelConfig.SMTPEncryption.STARTTLS,
            test_email="qa@example.com",
        )


class NotificationChannelRouteTests(NotificationTenantTestCase):
    def test_email_channel_test_page_renders(self):
        response = self.client.get(
            reverse("dashboard:notification_channel_test_email", kwargs={"prefix": self.prefix, "pk": self.channel.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Test Email")
        self.assertContains(response, "smtp.example.com")
        self.assertContains(response, "qa@example.com")

    @patch("dashboard.notification.views.channels.send_smtp_smoke_test")
    def test_email_channel_test_post_runs_smoke_test(self, send_smtp_smoke_test_mock):
        send_smtp_smoke_test_mock.return_value = EmailSmokeTestResult(
            success=True,
            recipient="qa@example.com",
            subject="SMTP test",
            latency_ms=124,
            diagnostic="Test email accepted for delivery to qa@example.com.",
        )

        response = self.client.post(
            reverse("dashboard:notification_channel_test_email", kwargs={"prefix": self.prefix, "pk": self.channel.pk}),
            {
                "recipient_email": "qa@example.com",
                "subject": "SMTP test",
                "message": "This is only a test.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SMTP test passed")
        self.assertContains(response, "accepted for delivery")
        send_smtp_smoke_test_mock.assert_called_once()

    def test_non_email_channel_redirects_away_from_smtp_test(self):
        sms_channel = NotificationChannel.objects.create(
            name="SMS Alerts",
            channel_type=ChannelType.SMS,
            status=NotificationChannel.ChannelStatus.ACTIVE,
            created_by=self.user,
        )

        response = self.client.get(
            reverse("dashboard:notification_channel_test_email", kwargs={"prefix": self.prefix, "pk": sms_channel.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("dashboard:notification_channel_detail", kwargs={"prefix": self.prefix, "pk": sms_channel.pk}),
            response.url,
        )
