from django import forms

from sabistart.ui.forms import TailwindFormMixin
from system.theme_marketplace.models import Theme, ThemeCategory
from system.theme_marketplace.services import get_themes_root


class ThemeCategoryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ThemeCategory
        fields = ["name", "slug", "description", "is_active", "sort_order"]


class ThemeForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Theme
        fields = [
            "category",
            "name",
            "slug",
            "description",
            "version",
            "currency",
            "price",
            "is_free",
            "preview_image_path",
            "thumbnail_path",
            "demo_url",
            "schema_path",
            "changelog_path",
            "feature_bullets",
            "preview_gallery",
            "status",
            "is_published",
            "is_featured",
            "is_internal",
            "metadata",
        ]

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        theme_dir = get_themes_root() / slug
        if not theme_dir.exists():
            raise forms.ValidationError(
                "No shared theme directory exists for this slug under the central themes/ folder."
            )
        if not (theme_dir / "theme.json").exists():
            raise forms.ValidationError(
                "The shared theme directory is missing theme.json, so it cannot be managed from the platform UI yet."
            )
        return slug
