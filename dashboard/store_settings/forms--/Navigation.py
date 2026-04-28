import logging
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from ..models import NavigationMenu, NavigationMenuItem

logger = logging.getLogger(__name__)


class NavigationMenuForm(forms.ModelForm):
    """
    Form for creating and editing Navigation Menus.
    """

    class Meta:
        model = NavigationMenu
        fields = ['name', 'location', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Main Menu, Footer Links'
            }),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_name(self):
        """Validate menu name is unique within tenant."""
        name = self.cleaned_data.get('name')
        instance = self.instance

        # Check for duplicate names (case-insensitive)
        queryset = NavigationMenu.objects.filter(name__iexact=name)
        if instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        if queryset.exists():
            raise ValidationError(_("A menu with this name already exists."))

        return name

    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()

        location = cleaned_data.get('location')
        is_active = cleaned_data.get('is_active')

        # Check for existing active menu at this location
        if is_active and location:
            existing = NavigationMenu.objects.filter(
                location=location,
                is_active=True
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)

            if existing.exists():
                raise ValidationError(
                    _("There is already an active menu at this location. "
                      "Please deactivate the existing menu first.")
                )

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"NavigationMenu saved: {instance.name} (ID: {instance.id})"
        )
        return instance


class NavigationMenuItemForm(forms.ModelForm):
    """
    Form for creating and editing Navigation Menu Items.
    Supports nested items and different link types.
    """

    class Meta:
        model = NavigationMenuItem
        fields = [
            'menu',
            'parent',
            'label',
            'link_type',
            'url',
            'category_id',
            'page_id',
            'display_order',
            'is_active',
            'open_in_new_tab',
            'icon_class',
            'show_as_mega_menu',
            'mega_menu_columns',
        ]
        widgets = {
            'menu': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={
                'class': 'form-select',
                'placeholder': 'Top level (no parent)'
            }),
            'label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Display text'
            }),
            'link_type': forms.Select(attrs={'class': 'form-select'}),
            'url': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '/custom-path or https://external.com'
            }),
            'category_id': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Category ID'
            }),
            'page_id': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Page ID'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'open_in_new_tab': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'icon_class': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., fa fa-home'
            }),
            'show_as_mega_menu': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'mega_menu_columns': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 6
            }),
        }

    def __init__(self, *args, **kwargs):
        """Filter parent choices to exclude self and children."""
        super().__init__(*args, **kwargs)

        # Filter parent choices to only show items from same menu
        if self.instance.pk:
            # Exclude self and descendants
            self.fields['parent'].queryset = NavigationMenuItem.objects.filter(
                menu=self.instance.menu
            ).exclude(
                pk=self.instance.pk
            )
        elif 'menu' in self.initial:
            self.fields['parent'].queryset = NavigationMenuItem.objects.filter(
                menu=self.initial['menu']
            )
        else:
            self.fields['parent'].queryset = NavigationMenuItem.objects.none()

        # Make certain fields conditional based on link_type
        self._setup_conditional_fields()

    def _setup_conditional_fields(self):
        """Setup field requirements based on link type."""
        # These will be validated in clean()
        pass

    def clean_label(self):
        """Validate label is not empty."""
        label = self.cleaned_data.get('label')
        if not label or not label.strip():
            raise ValidationError(_("Label cannot be empty."))
        return label.strip()

    def clean_url(self):
        """Validate URL format for custom URL link type."""
        url = self.cleaned_data.get('url')
        link_type = self.cleaned_data.get('link_type')

        if link_type == 'url' and not url:
            raise ValidationError(
                _("URL is required for custom URL link type."))

        if url and link_type == 'url':
            # Basic URL validation
            if not (url.startswith('/') or url.startswith('http://') or url.startswith('https://')):
                raise ValidationError(
                    _("URL must start with /, http://, or https://"))

        return url

    def clean_category_id(self):
        """Validate category ID for category link type."""
        category_id = self.cleaned_data.get('category_id')
        link_type = self.cleaned_data.get('link_type')

        if link_type == 'category' and not category_id:
            raise ValidationError(
                _("Category ID is required for category link type."))

        return category_id

    def clean_page_id(self):
        """Validate page ID for page link type."""
        page_id = self.cleaned_data.get('page_id')
        link_type = self.cleaned_data.get('link_type')

        if link_type == 'page' and not page_id:
            raise ValidationError(_("Page ID is required for page link type."))

        return page_id

    def clean_mega_menu_columns(self):
        """Validate mega menu columns range."""
        columns = self.cleaned_data.get('mega_menu_columns')
        show_mega = self.cleaned_data.get('show_as_mega_menu')

        if show_mega and columns and not (1 <= columns <= 6):
            raise ValidationError(
                _("Mega menu columns must be between 1 and 6."))

        return columns

    def clean(self):
        """Cross-field validation for link type requirements."""
        cleaned_data = super().clean()

        link_type = cleaned_data.get('link_type')
        url = cleaned_data.get('url')
        category_id = cleaned_data.get('category_id')
        page_id = cleaned_data.get('page_id')
        parent = cleaned_data.get('parent')
        show_mega = cleaned_data.get('show_as_mega_menu')

        # Validate link type specific requirements
        if link_type == 'url' and not url:
            self.add_error(
                'url', _("URL is required for custom URL link type."))

        if link_type == 'category' and not category_id:
            self.add_error('category_id', _(
                "Category ID is required for category link type."))

        if link_type == 'page' and not page_id:
            self.add_error('page_id', _(
                "Page ID is required for page link type."))

        # Mega menu can only be enabled on parent items (no parent)
        if show_mega and parent:
            self.add_error(
                'show_as_mega_menu',
                _("Mega menu can only be enabled on top-level items (no parent).")
            )

        # Validate parent is from same menu
        if parent and parent.menu != cleaned_data.get('menu'):
            self.add_error(
                'parent',
                _("Parent item must be from the same menu.")
            )

        return cleaned_data

    def save(self, commit=True):
        """Save and log changes."""
        instance = super().save(commit=commit)
        logger.info(
            f"NavigationMenuItem saved: {instance.label} (ID: {instance.id})"
        )
        return instance


class NavigationMenuItemInlineFormSet(forms.BaseInlineFormSet):
    """
    Inline formset for managing menu items within a menu.
    Supports nested items with drag-and-drop ordering.
    """

    def clean(self):
        """Validate formset."""
        super().clean()

        # Check for at least one item
        if any(self.forms) and not any(f.cleaned_data for f in self.forms if not f.cleaned_data.get('DELETE')):
            raise ValidationError(_("At least one menu item is required."))

        # Validate display_order uniqueness
        orders = []
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                order = form.cleaned_data.get('display_order', 0)
                if order in orders:
                    form.add_error(
                        'display_order',
                        _("Display order must be unique.")
                    )
                orders.append(order)
