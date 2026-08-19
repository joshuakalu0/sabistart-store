from uuid import uuid4

from django.core.management import call_command
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from dashboard.store_settings.content_services import get_or_create_blog_settings, get_or_create_managed_page
from dashboard.store_settings.models import BlogPost, CustomPage, FAQEntry
from public.userauth.models import TenantUser
from system.account.models import PlatformUser


class ContentManagerTenantTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        if not hasattr(cls, "_test_schema_name"):
            cls._test_schema_name = f"content{uuid4().hex[:16]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "Content",
                "last_name": "Owner",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "Content Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command("migrate_schemas", schema=cls.tenant.schema_name, tenant=True, interactive=False, verbosity=0)
            for model in (TenantUser, CustomPage, BlogPost, FAQEntry):
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
        self.client = TenantClient(self.tenant)
        self.prefix = "admin"
        self.user = TenantUser.objects.create_user(
            email="editor@example.com",
            password="StrongPass123!",
            first_name="Ada",
            last_name="Editor",
            user_type=TenantUser.UserType.STAFF,
            is_staff=True,
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        self.client.force_login(
            self.user,
            backend="sabistart.auth_backends.SchemaAwareAuthenticationBackend",
        )


class ContentManagerRouteTests(ContentManagerTenantTestCase):
    def test_dashboard_content_overview_renders(self):
        response = self.client.get(reverse("dashboard:content_manager:overview", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage storefront content")
        self.assertContains(response, reverse("dashboard:content_manager:managed_pages", kwargs={"prefix": self.prefix}))

    def test_managed_page_toggle_controls_public_policy_route(self):
        page = get_or_create_managed_page("privacy_policy")
        public_url = reverse("legal:privacy_policy")

        live_response = self.client.get(public_url)
        self.assertEqual(live_response.status_code, 200)

        page.is_enabled = False
        page.save(update_fields=["is_enabled", "updated_at"])

        disabled_response = self.client.get(public_url)
        self.assertEqual(disabled_response.status_code, 404)

    def test_blog_routes_render_when_blog_and_post_are_enabled(self):
        settings = get_or_create_blog_settings()
        settings.enable_blog = True
        settings.blog_title = "Store Journal"
        settings.save()
        post = BlogPost.objects.create(
            title="Launching Our New Collection",
            slug="launching-our-new-collection",
            excerpt="A quick look at what is coming next.",
            content="<p>Fresh arrivals are now available.</p>",
            status="published",
            is_enabled=True,
        )

        index_response = self.client.get(reverse("content:blog_index"))
        detail_response = self.client.get(reverse("content:blog_post", kwargs={"post_slug": post.slug}))

        self.assertEqual(index_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(index_response, "Launching Our New Collection")
        self.assertContains(detail_response, "Fresh arrivals are now available.")

    def test_help_center_and_faq_detail_render_from_tenant_content(self):
        help_page = get_or_create_managed_page("help_center")
        help_page.content = "Find answers below."
        help_page.save(update_fields=["content", "updated_at"])
        faq = FAQEntry.objects.create(
            question="How long does delivery take?",
            slug="how-long-does-delivery-take",
            answer="<p>Delivery takes 2 to 5 business days.</p>",
            is_enabled=True,
            sort_order=1,
        )

        index_response = self.client.get(reverse("support:help_center"))
        detail_response = self.client.get(reverse("support:faq_detail", kwargs={"faq_slug": faq.slug}))

        self.assertEqual(index_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(index_response, "How long does delivery take?")
        self.assertContains(detail_response, "Delivery takes 2 to 5 business days.")

    def test_custom_page_renders_when_published_and_enabled(self):
        page = CustomPage.objects.create(
            page_kind="generic",
            title="About Our Brand",
            slug="about-our-brand",
            content="<p>We build thoughtful products.</p>",
            status="published",
            is_enabled=True,
        )

        response = self.client.get(reverse("content:custom_page", kwargs={"page_slug": page.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "We build thoughtful products.")
