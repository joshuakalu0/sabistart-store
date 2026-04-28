"""
Management command: generate_products

Creates one or more Product records from command-line arguments.

Usage examples
--------------
# Create a single simple product
python manage.py generate_products --name "Blue T-Shirt" --sku "TSH-001" --price 19.99

# Create a variable product, published, with 50 units of stock
python manage.py generate_products \\
    --name "Wireless Headphones" --sku "WH-PRO-42" \\
    --price 129.00 --type variable --stock 50 --status published

# Seed 10 random demo products under tenant schema "acme"
python manage.py generate_products --demo 10 --schema acme

# Dry run (validate args, print what would be created, save nothing)
python manage.py generate_products --name "Test" --sku "T-000" --dry-run
"""

from __future__ import annotations

import random
import string
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_sku(prefix: str = "DEMO") -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{suffix}"


def _unique_slug(model_cls, base: str) -> str:
    slug = slugify(base) or f"product-{str(uuid.uuid4())[:8]}"
    counter = 1
    candidate = slug
    while model_cls.objects.filter(slug=candidate).exists():
        candidate = f"{slug}-{counter}"
        counter += 1
    return candidate


DEMO_NAMES = [
    ("Organic Cotton Tee", "simple", 24.99),
    ("Leather Wallet", "simple", 49.99),
    ("Bamboo Water Bottle", "simple", 29.99),
    ("Wireless Earbuds", "variable", 79.99),
    ("Yoga Mat Pro", "simple", 59.99),
    ("Running Shoes", "variable", 119.99),
    ("Smart Watch Band", "variable", 34.99),
    ("Ceramic Coffee Mug", "simple", 14.99),
    ("Laptop Stand Adjustable", "simple", 89.99),
    ("Scented Candle Set", "simple", 39.99),
    ("Stainless Steel Pan", "simple", 69.99),
    ("Bluetooth Speaker Mini", "variable", 54.99),
    ("Desk Organizer Wood", "simple", 44.99),
    ("Yoga Block Set", "simple", 22.99),
    ("Face Serum Premium", "simple", 64.99),
]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Create one or more Product records from CLI arguments. "
        "Use --demo N to seed N random products for testing."
    )

    def add_arguments(self, parser):
        # ---- Single product args ----
        single = parser.add_argument_group("Single product")
        single.add_argument("--name", type=str, default="", help="Product name")
        single.add_argument("--sku", type=str, default="", help="Unique SKU")
        single.add_argument(
            "--price", type=float, default=0.00, help="Price (default: 0.00)"
        )
        single.add_argument(
            "--compare-price",
            type=float,
            default=None,
            dest="compare_at_price",
            help="Compare-at / was price",
        )
        single.add_argument(
            "--cost", type=float, default=None, dest="cost_price", help="Cost price"
        )
        single.add_argument(
            "--type",
            type=str,
            default="simple",
            choices=["simple", "variable"],
            dest="product_type",
            help="Product type (default: simple)",
        )
        single.add_argument(
            "--stock", type=int, default=0, help="Stock quantity (default: 0)"
        )
        single.add_argument(
            "--status",
            type=str,
            default="draft",
            choices=["draft", "pending", "private", "published", "archived"],
            help="Status (default: draft)",
        )
        single.add_argument(
            "--featured", action="store_true", help="Mark as featured"
        )
        single.add_argument(
            "--description", type=str, default="", help="Product description"
        )

        # ---- Demo / bulk args ----
        bulk = parser.add_argument_group("Bulk / demo")
        bulk.add_argument(
            "--demo",
            type=int,
            default=0,
            metavar="N",
            help="Seed N random demo products (ignores single-product args)",
        )

        # ---- Tenant / runtime args ----
        runtime = parser.add_argument_group("Runtime")
        runtime.add_argument(
            "--schema",
            type=str,
            default="",
            help="Tenant schema to operate under (for django-tenants). "
            "Leave blank to use the current active schema.",
        )
        runtime.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and print what would be created without saving.",
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        schema = options["schema"]

        if schema:
            try:
                from django_tenants.utils import schema_context

                with schema_context(schema):
                    self._run(options)
            except ImportError:
                self.stderr.write(
                    self.style.WARNING(
                        "django-tenants not installed — running without schema context."
                    )
                )
                self._run(options)
        else:
            self._run(options)

    # ------------------------------------------------------------------

    def _run(self, options):
        dry_run: bool = options["dry_run"]
        demo_count: int = options["demo"]

        if dry_run:
            self.stdout.write(self.style.WARNING("--- DRY RUN (nothing will be saved) ---"))

        if demo_count > 0:
            self._seed_demo(demo_count, options["status"], dry_run)
        else:
            self._create_single(options, dry_run)

    # ------------------------------------------------------------------

    def _create_single(self, options, dry_run: bool):
        from public.product.models import Product

        name = options["name"].strip()
        sku = options["sku"].strip()

        if not name:
            raise CommandError("--name is required when not using --demo.")
        if not sku:
            raise CommandError("--sku is required when not using --demo.")

        # Check SKU uniqueness
        if Product.objects.filter(sku=sku).exists():
            raise CommandError(f'A product with SKU "{sku}" already exists.')

        slug = _unique_slug(Product, name)

        payload = dict(
            name=name,
            sku=sku,
            slug=slug,
            price=Decimal(str(options["price"])),
            product_type=options["product_type"],
            manage_stock=True,
            stock_quantity=options["stock"],
            status=options["status"],
            is_featured=options["featured"],
            short_description=options["description"],
        )
        if options["compare_at_price"] is not None:
            payload["compare_at_price"] = Decimal(str(options["compare_at_price"]))
        if options["cost_price"] is not None:
            payload["cost_price"] = Decimal(str(options["cost_price"]))

        self.stdout.write(f"\nProduct to create:")
        for k, v in payload.items():
            self.stdout.write(f"  {k:25s}: {v}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("\n[DRY RUN] Product NOT saved."))
            return

        product = Product.objects.create(**payload)
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Created "{product.name}" '
                f"| SKU: {product.sku} "
                f"| ID: {product.id}"
            )
        )

    # ------------------------------------------------------------------

    def _seed_demo(self, count: int, status: str, dry_run: bool):
        from public.product.models import Product

        pool = DEMO_NAMES * ((count // len(DEMO_NAMES)) + 1)
        random.shuffle(pool)
        pool = pool[:count]

        created = 0
        skipped = 0

        for name, ptype, price in pool:
            sku = _random_sku()
            # ensure no collision (extremely unlikely but safe)
            while Product.objects.filter(sku=sku).exists():
                sku = _random_sku()

            slug = _unique_slug(Product, name)

            self.stdout.write(f"  → {name:35s} SKU={sku}  ${price:.2f}")

            if not dry_run:
                try:
                    Product.objects.create(
                        name=name,
                        sku=sku,
                        slug=slug,
                        price=Decimal(str(price)),
                        product_type=ptype,
                        manage_stock=True,
                        stock_quantity=random.randint(0, 200),
                        status=status,
                        is_featured=random.random() < 0.2,
                        is_bestseller=random.random() < 0.15,
                        is_new=random.random() < 0.3,
                        is_on_sale=random.random() < 0.25,
                        average_rating=round(random.uniform(3.0, 5.0), 2),
                        rating_count=random.randint(0, 500),
                        review_count=random.randint(0, 300),
                        sales_count=random.randint(0, 1000),
                        view_count=random.randint(0, 5000),
                    )
                    created += 1
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"    ✗ Failed: {exc}")
                    skipped += 1
            else:
                created += 1

        label = "[DRY RUN] Would create" if dry_run else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ {label} {created} demo products. "
                + (f"({skipped} skipped due to errors)" if skipped else "")
            )
        )
