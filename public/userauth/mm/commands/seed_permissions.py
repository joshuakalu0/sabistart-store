"""
Management command to seed permissions and roles.
Usage: python manage.py seed_permissions
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from public.userauth.models import Permission, Role, RolePermission


class Command(BaseCommand):
    help = 'Seed permissions and default roles'

    def handle(self, *args, **options):
        self.stdout.write('Seeding permissions and roles...')
        
        with transaction.atomic():
            self._seed_permissions()
            self._seed_roles()
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded permissions and roles'))

    def _seed_permissions(self):
        """Seed all system permissions."""
        permissions_data = [
            # Dashboard
            ("dashboard.view", "View dashboard", "analytics"),
            
            # Orders
            ("orders.view", "View orders", "order"),
            ("orders.create", "Create orders manually", "order"),
            ("orders.edit", "Edit order details", "order"),
            ("orders.cancel", "Cancel orders", "order"),
            ("orders.refund", "Issue refunds", "order"),
            ("orders.fulfil", "Mark orders as fulfilled", "order"),
            ("orders.export", "Export orders to CSV", "order"),
            
            # Products
            ("products.view", "View products", "product"),
            ("products.create", "Create products", "product"),
            ("products.edit", "Edit products", "product"),
            ("products.delete", "Delete products", "product"),
            ("products.publish", "Publish/unpublish products", "product"),
            ("products.import", "Import products via CSV", "product"),
            
            # Inventory
            ("inventory.view", "View inventory levels", "inventory"),
            ("inventory.adjust", "Manually adjust stock", "inventory"),
            
            # Customers
            ("customers.view", "View customer list", "customer"),
            ("customers.create", "Create customers", "customer"),
            ("customers.edit", "Edit customer details", "customer"),
            ("customers.delete", "Delete customers", "customer"),
            ("customers.export", "Export customers to CSV", "customer"),
            
            # Pricing & Discounts
            ("pricing.view", "View pricing and discounts", "marketing"),
            ("pricing.manage", "Create/edit price lists and discounts", "marketing"),
            
            # Payments
            ("payments.view", "View transactions and balance", "financial"),
            ("payments.request_payout", "Request payouts", "financial"),
            ("payments.manage_gateways", "Configure payment gateways", "financial"),
            
            # Analytics
            ("analytics.view", "View analytics and reports", "analytics"),
            ("analytics.export", "Export report data", "analytics"),
            
            # Store settings
            ("settings.view", "View store settings", "settings"),
            ("settings.edit", "Edit store settings", "settings"),
            ("settings.billing", "Manage subscription and billing", "settings"),
            
            # Staff management
            ("staff.view", "View staff members", "settings"),
            ("staff.invite", "Invite new staff", "settings"),
            ("staff.edit", "Edit staff roles", "settings"),
            ("staff.remove", "Remove staff members", "settings"),
        ]
        
        created_count = 0
        for codename, name, category in permissions_data:
            permission, created = Permission.objects.get_or_create(
                codename=codename,
                defaults={
                    'name': name,
                    'category': category,
                    'is_system': True,
                    'is_active': True
                }
            )
            if created:
                created_count += 1
                self.stdout.write(f'  Created permission: {codename}')
        
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} permissions'))

    def _seed_roles(self):
        """Seed default system roles."""
        roles_data = [
            {
                'name': 'Owner',
                'slug': 'owner',
                'description': 'Full access to all features',
                'system_slug': 'owner',
                'sort_order': 1,
                'permissions': 'ALL'
            },
            {
                'name': 'Admin',
                'slug': 'admin',
                'description': 'Administrative access (all except billing)',
                'system_slug': 'admin',
                'sort_order': 2,
                'permissions': [
                    'dashboard.view', 'orders.view', 'orders.create', 'orders.edit',
                    'orders.cancel', 'orders.refund', 'orders.fulfil', 'orders.export',
                    'products.view', 'products.create', 'products.edit', 'products.delete',
                    'products.publish', 'products.import', 'inventory.view', 'inventory.adjust',
                    'customers.view', 'customers.create', 'customers.edit', 'customers.delete',
                    'customers.export', 'pricing.view', 'pricing.manage', 'payments.view',
                    'analytics.view', 'analytics.export', 'settings.view', 'settings.edit',
                    'staff.view', 'staff.invite', 'staff.edit', 'staff.remove'
                ]
            },
            {
                'name': 'Manager',
                'slug': 'manager',
                'description': 'Manage orders, products, inventory, and customers',
                'system_slug': 'manager',
                'sort_order': 3,
                'permissions': [
                    'dashboard.view', 'orders.view', 'orders.edit', 'orders.fulfil',
                    'products.view', 'products.create', 'products.edit', 'products.publish',
                    'inventory.view', 'inventory.adjust', 'customers.view', 'customers.edit',
                    'pricing.view', 'analytics.view'
                ]
            },
            {
                'name': 'Fulfillment',
                'slug': 'fulfillment',
                'description': 'View and fulfill orders only',
                'system_slug': 'fulfillment',
                'sort_order': 4,
                'permissions': [
                    'orders.view', 'orders.fulfil', 'inventory.view'
                ]
            },
            {
                'name': 'Support',
                'slug': 'support',
                'description': 'View and edit orders and customers',
                'system_slug': 'support',
                'sort_order': 5,
                'permissions': [
                    'dashboard.view', 'orders.view', 'orders.edit',
                    'customers.view', 'customers.edit'
                ]
            },
            {
                'name': 'Analyst',
                'slug': 'analyst',
                'description': 'View analytics and reports only',
                'system_slug': 'analyst',
                'sort_order': 6,
                'permissions': [
                    'dashboard.view', 'analytics.view', 'analytics.export',
                    'orders.view', 'products.view', 'customers.view'
                ]
            }
        ]
        
        created_count = 0
        for role_data in roles_data:
            permissions_list = role_data.pop('permissions')
            
            role, created = Role.objects.get_or_create(
                slug=role_data['slug'],
                defaults={
                    **role_data,
                    'is_system': True,
                    'is_active': True,
                    'role_type': 'system'
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(f'  Created role: {role.name}')
                
                # Assign permissions
                if permissions_list == 'ALL':
                    # Owner gets all permissions
                    all_permissions = Permission.objects.filter(is_active=True)
                    for perm in all_permissions:
                        RolePermission.objects.get_or_create(
                            role=role,
                            permission=perm
                        )
                else:
                    # Assign specific permissions
                    for perm_codename in permissions_list:
                        try:
                            perm = Permission.objects.get(codename=perm_codename)
                            RolePermission.objects.get_or_create(
                                role=role,
                                permission=perm
                            )
                        except Permission.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'    Permission not found: {perm_codename}'
                                )
                            )
                
                # Update permission count
                role._permission_count = role.role_permissions.count()
                role.save(update_fields=['_permission_count'])
        
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} roles'))
