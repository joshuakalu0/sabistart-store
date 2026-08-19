from django import forms
from django.test import SimpleTestCase

from sabistart.navigation import build_platform_navigation, iter_tenant_navigation
from sabistart.ui.forms import TailwindFormMixin


class NavigationRegistryTests(SimpleTestCase):
    def test_build_platform_navigation_exposes_only_live_sections(self):
        navigation = build_platform_navigation("platform_payments")
        keys = [item["key"] for section in navigation for item in section["items"]]

        self.assertEqual(
            keys,
            [
                "platform_dashboard",
                "platform_stores",
                "platform_features",
                "platform_payments",
            ],
        )
        self.assertTrue(all(item["url"] != "#" for section in navigation for item in section["items"]))

    def test_iter_tenant_navigation_only_builds_real_links(self):
        sections = list(iter_tenant_navigation("admin"))
        item_urls = [
            child["url"]
            for section in sections
            for item in section["items"]
            for child in item.get("children", [])
        ]
        top_level_urls = [item["url"] for section in sections for item in section["items"]]

        self.assertTrue(sections)
        self.assertTrue(all(url != "#" for url in top_level_urls))
        self.assertTrue(all(url != "#" for url in item_urls))
        self.assertIn("dashboard", {item["key"] for section in sections for item in section["items"]})
        self.assertNotIn("theme_marketplace", {item["key"] for section in sections for item in section["items"]})


class TailwindFormMixinTests(SimpleTestCase):
    def test_tailwind_form_mixin_styles_fields_consistently(self):
        class DemoForm(TailwindFormMixin, forms.Form):
            name = forms.CharField()
            notes = forms.CharField(widget=forms.Textarea)
            category = forms.ChoiceField(choices=[("a", "A")])
            enabled = forms.BooleanField(required=False)

        form = DemoForm()

        self.assertIn("rounded-2xl", form.fields["name"].widget.attrs["class"])
        self.assertIn("min-h-[120px]", form.fields["notes"].widget.attrs["class"])
        self.assertIn("focus:ring-4", form.fields["category"].widget.attrs["class"])
        self.assertIn("h-4 w-4", form.fields["enabled"].widget.attrs["class"])
