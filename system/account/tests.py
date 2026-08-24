import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from system.account.models import OnboardingSession
from system.account.views import _formatted_store_domain, _platform_domain_suffix, _resume_onboarding_url, check_subdomain


class OnboardingResumeRoutingTests(SimpleTestCase):
    def test_resume_url_points_to_account_when_profile_is_incomplete(self):
        session = SimpleNamespace(
            email="",
            business_name="",
            metadata={},
            selected_bundle_slug="",
            payment_status=OnboardingSession.PaymentStatus.PENDING,
            desired_subdomain="",
        )

        self.assertEqual(_resume_onboarding_url(session), reverse("platform:onboarding_account"))

    def test_resume_url_points_to_subdomain_when_plan_exists_but_subdomain_is_missing(self):
        session = SimpleNamespace(
            email="owner@example.com",
            business_name="Sabi Test",
            metadata={"password_hash": "hashed"},
            selected_bundle_slug="starter",
            payment_status=OnboardingSession.PaymentStatus.PENDING,
            desired_subdomain="",
        )

        self.assertEqual(_resume_onboarding_url(session), reverse("platform:onboarding_subdomain"))

    def test_resume_url_points_to_checkout_when_subdomain_exists_but_payment_is_pending(self):
        session = SimpleNamespace(
            email="owner@example.com",
            business_name="Sabi Test",
            metadata={"password_hash": "hashed"},
            selected_bundle_slug="starter",
            payment_status=OnboardingSession.PaymentStatus.PENDING,
            desired_subdomain="sabi-test",
        )

        self.assertEqual(_resume_onboarding_url(session), reverse("platform:onboarding_checkout"))

    def test_resume_url_points_to_review_when_required_data_exists(self):
        session = SimpleNamespace(
            email="owner@example.com",
            business_name="Sabi Test",
            metadata={"password_hash": "hashed"},
            selected_bundle_slug="starter",
            payment_status=OnboardingSession.PaymentStatus.PAID,
            desired_subdomain="sabi-test",
        )

        self.assertEqual(_resume_onboarding_url(session), reverse("platform:onboarding_review"))


class CheckSubdomainEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    @patch("system.account.views.TenantService.is_subdomain_available", return_value=True)
    def test_check_subdomain_returns_available_payload(self, mocked_available):
        request = self.factory.get("/platform/register/check-subdomain/", {"subdomain": "my-test-store"})

        response = check_subdomain(request)
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["subdomain"], "my-test-store")
        mocked_available.assert_called_once_with("my-test-store")

    def test_check_subdomain_rejects_invalid_values(self):
        request = self.factory.get("/platform/register/check-subdomain/", {"subdomain": "Admin"})

        response = check_subdomain(request)
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["available"])


class PlatformDomainHelpersTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(SUBDOMAIN_SUFFIX="stores.example.com")
    def test_formatted_store_domain_uses_configured_suffix(self):
        request = self.factory.get("/platform/register/")

        self.assertEqual(_formatted_store_domain(request, "demo"), "demo.stores.example.com")
        self.assertEqual(_platform_domain_suffix(request), "stores.example.com")
