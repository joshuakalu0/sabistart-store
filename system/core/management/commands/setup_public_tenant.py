"""
Management command to create the public tenant for django-tenants.
This must be run before any other operations.

Usage:
    python manage.py setup_public_tenant
"""

from django.core.management.base import BaseCommand
from system.core.models import Shop as  Client, Domain
from system.account.models import Owner as User
from datetime import date


class Command(BaseCommand):
    help = 'Creates the public tenant required by django-tenants'

    def handle(self, *args, **options):
        self.stdout.write('Setting up public tenant...')

        # Check if public tenant already exists
        if Client.objects.filter(schema_name='public').exists():
            self.stdout.write(self.style.WARNING(
                'Public tenant already exists. Skipping.'))
            return

        # Create superuser for public tenant if doesn't exist
        if not User.objects.filter(email='admin@admin.com').exists():
            admin_user = User.objects.create_superuser(
                username='admin2',
                email='admin@admin.co',
                password='password.123',
                first_name='Admin',
                last_name='User'
            )
            self.stdout.write(self.style.SUCCESS(
                f'Created admin user: {admin_user.email}'))
        else:
            admin_user = User.objects.get(email='admin@admin.com')
            self.stdout.write(self.style.WARNING('Admin user already exists'))

        # Create public tenant
        tenant = Client(
            schema_name='public',
            name='Public Schema',
            paid_until=date(2100, 12, 31),  # Far future date
            on_trial=False
        )
        tenant.save()



        self.stdout.write(self.style.SUCCESS(
            f'Created public tenant: {tenant.name}'))

        # Add domain for public tenant
        domain = Domain(
            domain='localhost',
            tenant=tenant
        )
        domain.save()

        self.stdout.write(self.style.SUCCESS(
            f'Created domain: {domain.domain}'))

        self.stdout.write(self.style.SUCCESS(
            '\n✓ Public tenant setup complete!'))
        self.stdout.write(self.style.SUCCESS(
            'Admin: admin@admin.com / password.123'))
        self.stdout.write(self.style.SUCCESS(
            'Run: python manage.py migrate_schemas'))
