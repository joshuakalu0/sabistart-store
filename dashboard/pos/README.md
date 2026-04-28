# POS System

## Overview
Tenant-scoped Point of Sale for physical stores, separate from the storefront
catalog and order domain.

## V1 Scope
- Store management
- POS-only products
- Store inventory
- Inventory adjustments and low-stock reporting
- Sales transactions
- Transaction items and payments
- Receipt generation
- POS discounts

## Architecture Notes
- POS lives under the tenant dashboard route family: `/<prefix>/pos/`
- POS data is isolated per tenant schema
- `TenantUser` is the user type for store managers, cashiers, and audit fields
- POS products are separate from storefront `Product`
- Inventory mutations and sale completion live in `dashboard.pos.services`

## Intentionally Out Of V1
- `POSSession`
- `POSTerminal`
- Refund workflows
- Exchanges
- Cash drawer reconciliation

## Setup
```bash
python manage.py makemigrations pos
python manage.py migrate_schemas --tenant
python manage.py setup_pos_data
```

## Main Routes
- `/<prefix>/pos/`
- `/<prefix>/pos/sales/`
- `/<prefix>/pos/inventory/`
- `/<prefix>/pos/products/`
- `/<prefix>/pos/stores/`
- `/<prefix>/pos/discounts/`
- `/<prefix>/pos/receipt/<transaction_id>/`
