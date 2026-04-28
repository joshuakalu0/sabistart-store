from django.core.management.base import BaseCommand
from django.utils.text import slugify
from public.userauth.models import Permission, Role


class Command(BaseCommand):
    """
    Management command to create initial permissions and roles for the system.
    This sets up the foundational RBAC structure for the application.
    """
    
    help = 'Create initial permissions and roles for the user management system'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing permissions and roles',
        )
    
    def handle(self, *args, **options):
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS('Setting up initial permissions and roles...')
        )
        
        # Create permissions
        self.create_permissions(force)
        
        # Create roles
        self.create_roles(force)
        
        self.stdout.write(
            self.style.SUCCESS('Successfully created initial permissions and roles!')
        )
    
    def create_permissions(self, force=False):
        """Create initial system permissions."""
        
        permissions_data = [
            # Product Management
            ('product', 'view_products', 'View Products', 'Can view product listings'),
            ('product', 'add_products', 'Add Products', 'Can create new products'),
            ('product', 'edit_products', 'Edit Products', 'Can modify existing products'),
            ('product', 'delete_products', 'Delete Products', 'Can delete products'),
            ('product', 'manage_categories', 'Manage Categories', 'Can manage product categories'),
            ('product', 'manage_attributes', 'Manage Attributes', 'Can manage product attributes'),
            
            # Order Management
            ('order', 'view_orders', 'View Orders', 'Can view order listings'),
            ('order', 'edit_orders', 'Edit Orders', 'Can modify order details'),
            ('order', 'process_orders', 'Process Orders', 'Can process and fulfill orders'),
            ('order', 'cancel_orders', 'Cancel Orders', 'Can cancel orders'),
            ('order', 'refund_orders', 'Refund Orders', 'Can process refunds'),
            
            # Customer Management
            ('customer', 'view_customers', 'View Customers', 'Can view customer profiles'),
            ('customer', 'edit_customers', 'Edit Customers', 'Can modify customer information'),
            ('customer', 'delete_customers', 'Delete Customers', 'Can delete customer accounts'),
            ('customer', 'manage_customer_groups', 'Manage Customer Groups', 'Can manage customer segmentation'),
            
            # Inventory Management
            ('inventory', 'view_inventory', 'View Inventory', 'Can view inventory levels'),
            ('inventory', 'manage_inventory', 'Manage Inventory', 'Can adjust inventory levels'),
            ('inventory', 'view_stock_reports', 'View Stock Reports', 'Can view inventory reports'),
            
            # Analytics & Reports
            ('analytics', 'view_sales_reports', 'View Sales Reports', 'Can view sales analytics'),
            ('analytics', 'view_customer_reports', 'View Customer Reports', 'Can view customer analytics'),
            ('analytics', 'view_product_reports', 'View Product Reports', 'Can view product performance'),
            ('analytics', 'export_reports', 'Export Reports', 'Can export analytical data'),
            
            # System Settings
            ('settings', 'manage_settings', 'Manage Settings', 'Can modify system settings'),
            ('settings', 'manage_users', 'Manage Users', 'Can manage user accounts'),
            ('settings', 'manage_roles', 'Manage Roles', 'Can manage user roles and permissions'),
            ('settings', 'view_system_logs', 'View System Logs', 'Can view system activity logs'),
            
            # Financial Operations
            ('financial', 'view_financial_reports', 'View Financial Reports', 'Can view financial data'),
            ('financial', 'manage_payments', 'Manage Payments', 'Can process payments and refunds'),
            ('financial', 'manage_taxes', 'Manage Taxes', 'Can configure tax settings'),
            
            # Marketing & Promotions
            ('marketing', 'manage_promotions', 'Manage Promotions', 'Can create and manage promotions'),
            ('marketing', 'manage_coupons', 'Manage Coupons', 'Can create and manage discount coupons'),
            ('marketing', 'send_newsletters', 'Send Newsletters', 'Can send marketing emails'),
        ]
        
        created_count = 0
        for category, codename, name, description in permissions_data:
            permission, created = Permission.objects.get_or_create(
                codename=codename,
                defaults={
                    'name': name,
                    'description': description,
                    'category': category,
                    'is_system': True,
                    'is_active': True,
                }
            )
            
            if created or force:
                if force and not created:
                    permission.name = name
                    permission.description = description
                    permission.category = category
                    permission.save()
                
                created_count += 1
                self.stdout.write(f'  Created permission: {name}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} permissions')
        )
    
    def create_roles(self, force=False):
        """Create initial system roles."""
        
        roles_data = [
            {
                'name': 'Super Administrator',
                'slug': 'super-admin',
                'description': 'Full system access with all permissions',
                'role_type': 'system',
                'level': 1,
                'permissions': 'all',
            },
            {
                'name': 'Administrator',
                'slug': 'admin',
                'description': 'Administrative access with most permissions',
                'role_type': 'system',
                'level': 2,
                'permissions': [
                    'view_products', 'add_products', 'edit_products', 'manage_categories',
                    'view_orders', 'edit_orders', 'process_orders', 'cancel_orders',
                    'view_customers', 'edit_customers', 'manage_customer_groups',
                    'view_inventory', 'manage_inventory', 'view_stock_reports',
                    'view_sales_reports', 'view_customer_reports', 'view_product_reports',
                    'manage_users', 'view_system_logs',
                    'view_financial_reports', 'manage_payments',
                    'manage_promotions', 'manage_coupons',
                ],
            },
            {
                'name': 'Customer',
                'slug': 'customer',
                'description': 'Standard customer account',
                'role_type': 'system',
                'level': 5,
                'permissions': [],
            },
        ]
        
        created_count = 0
        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                slug=role_data['slug'],
                defaults={
                    'name': role_data['name'],
                    'description': role_data['description'],
                    'role_type': role_data['role_type'],
                    'level': role_data['level'],
                    'is_system': True,
                    'is_active': True,
                }
            )
            
            if created or force:
                if force and not created:
                    role.name = role_data['name']
                    role.description = role_data['description']
                    role.role_type = role_data['role_type']
                    role.level = role_data['level']
                    role.save()
                
                # Assign permissions
                if role_data['permissions'] == 'all':
                    all_permissions = Permission.objects.filter(is_active=True)
                    role.permissions.set(all_permissions)
                elif role_data['permissions']:
                    permissions = Permission.objects.filter(
                        codename__in=role_data['permissions'],
                        is_active=True
                    )
                    role.permissions.set(permissions)
                else:
                    role.permissions.clear()
                
                created_count += 1
                self.stdout.write(f'  Created role: {role_data["name"]}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} roles')
        )