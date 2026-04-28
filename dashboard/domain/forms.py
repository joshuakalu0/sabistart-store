# dashboard/domain/forms.py

import re
from django import forms
from django.core.exceptions import ValidationError
from dashboard.domain.models import CustomDomain
from sabistart_store.ui.forms import TailwindFormMixin


class AddDomainForm(TailwindFormMixin, forms.Form):
    """
    Form for adding a new custom domain.
    Validates domain format and checks for duplicates.
    """
    domain = forms.CharField(
        max_length=253,
        widget=forms.TextInput(attrs={
            'class': 'block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-slate-900 dark:text-white bg-white dark:bg-slate-700 focus:ring-2 focus:ring-primary focus:border-transparent placeholder-slate-400 dark:placeholder-slate-500',
            'placeholder': 'example.com or shop.example.com',
            'autocomplete': 'off',
        }),
        help_text='Enter your custom domain without http:// or https://'
    )

    def clean_domain(self):
        domain = self.cleaned_data.get('domain', '').strip().lower()
        
        # Remove protocol if present
        domain = re.sub(r'^https?://', '', domain)
        
        # Remove trailing slashes
        domain = domain.rstrip('/')
        
        # Remove www. prefix if present (we'll handle this separately)
        # domain = re.sub(r'^www\.', '', domain)
        
        # Validate domain format
        domain_pattern = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$'
        if not re.match(domain_pattern, domain):
            raise ValidationError('Please enter a valid domain name (e.g., example.com or shop.example.com)')
        
        # Check if domain already exists
        if CustomDomain.objects.filter(domain=domain).exclude(status=CustomDomain.Status.REMOVED).exists():
            raise ValidationError('This domain is already registered in our system.')
        
        # Block platform's own domains
        blocked_domains = ['sabistart.com', 'localhost', '127.0.0.1']
        if any(blocked in domain for blocked in blocked_domains):
            raise ValidationError('You cannot use this domain.')
        
        return domain


class DomainSettingsForm(TailwindFormMixin, forms.ModelForm):
    """
    Form for updating domain settings like notes and primary status.
    """
    class Meta:
        model = CustomDomain
        fields = ['notes', 'is_primary']
        widgets = {
            'notes': forms.Textarea(attrs={
                'class': 'block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-slate-900 dark:text-white bg-white dark:bg-slate-700 focus:ring-2 focus:ring-primary focus:border-transparent resize-y min-h-[80px]',
                'placeholder': 'Add internal notes about this domain...',
                'rows': 3,
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'rounded border-slate-300 dark:border-slate-600 text-primary focus:ring-primary',
            }),
        }
