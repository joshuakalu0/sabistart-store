from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from dashboard.pos.models import Store, POSProduct, StoreInventory, POSTransaction
from decimal import Decimal


class Command(BaseCommand):
    help = 'Setup sample POS data'

    def handle(self, *args, **options):
        # Create sample store
        store, created = Store.objects.get_or_create(
            code='MAIN',
            defaults={
                'name': 'Main Store',
                'address': '123 Main Street, City, State',
                'tax_rate': Decimal('0.1000'),  # 10% tax
                'is_active': True
            }
        )
        
        if created:
            self.stdout.write(f'Created store: {store.name}')
        
        # Create sample POS products
        sample_products = [
            {'name': 'Coffee - Medium', 'sku': 'COFFEE-M', 'barcode': 'BAR001', 'cost': '2.50', 'price': '4.99', 'category': 'Beverages'},
            {'name': 'Sandwich - Club', 'sku': 'SAND-CLUB', 'barcode': 'BAR002', 'cost': '3.00', 'price': '8.99', 'category': 'Food'},
            {'name': 'Chips - Regular', 'sku': 'CHIPS-REG', 'barcode': 'BAR003', 'cost': '0.75', 'price': '2.49', 'category': 'Snacks'},
            {'name': 'Water Bottle', 'sku': 'WATER-500ML', 'barcode': 'BAR004', 'cost': '0.50', 'price': '1.99', 'category': 'Beverages'},
            {'name': 'Candy Bar', 'sku': 'CANDY-CHOC', 'barcode': 'BAR005', 'cost': '0.60', 'price': '1.79', 'category': 'Snacks'},
        ]
        
        for product_data in sample_products:
            product, created = POSProduct.objects.get_or_create(
                sku=product_data['sku'],
                defaults={
                    'name': product_data['name'],
                    'barcode': product_data['barcode'],
                    'cost_price': Decimal(product_data['cost']),
                    'selling_price': Decimal(product_data['price']),
                    'category': product_data['category'],
                    'is_taxable': True,
                    'is_active': True
                }
            )
            
            if created:
                self.stdout.write(f'Created POS product: {product.name}')
            
            # Add to store inventory
            inventory, inv_created = StoreInventory.objects.get_or_create(
                store=store,
                product=product,
                defaults={
                    'quantity': 50,
                    'low_stock_threshold': 5,
                    'location': f'Aisle {product_data["category"][0]}'
                }
            )
            
            if inv_created:
                self.stdout.write(f'Added to inventory: {product.name}')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully setup POS data')
        )