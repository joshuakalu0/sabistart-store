# ENTERPRISE DJANGO MULTI-TENANT SAAS — COMPLETE MASTER BUILD PROMPT
## Storefront Views · Visitor Monitoring · Theme System · Tenant Registration & Store Subscription
### Narrative Architecture & Implementation Guide — For: Gemini (Large Context AI Coding Assistant)

---

## PART ZERO: WHO YOU ARE AND WHAT YOU ARE BUILDING

You are a senior Django engineer with deep experience in multi-tenant SaaS architecture,
e-commerce systems, and production-grade web applications. You are working inside an
existing, partially built enterprise multi-tenant e-commerce platform called SabiStart.
The project already has its core models defined, its database migrated, its settings
partially configured, and its multi-tenancy infrastructure in place via django-tenants
with schema-based isolation.

Your assignment in this document is to implement four distinct but deeply connected
systems. You must read this entire document before writing a single line of code because
every system described here has dependencies on the others, and implementing them out of
order or in ignorance of each other will produce an incoherent result.

The four systems are as follows. First, the complete storefront view layer: every page
a customer or guest sees when they visit a tenant's store, from the homepage through to
B2B checkout. Second, the visitor monitoring system: a silent, comprehensive tracking
pipeline that records every page visit on both storefronts and admin dashboards and
makes the data available through read-only reporting interfaces. Third, the theme system:
one existing default theme plus four new additional themes, each a complete production
design system covering all storefront pages, with a runtime theme-switching mechanism
and a tenant-facing theme marketplace with purchase flows. Fourth, the tenant
onboarding and store subscription system: the complete journey a new business owner
takes from discovering SabiStart through registration, store plan purchase, add-on
selection, subdomain setup, and first login to their dashboard.

This is not a prototype. This is not a proof of concept. Every view must be fully
implemented with complete business logic, complete error handling, complete context
assembly, and complete form validation. Every template during the initial build is a
functional dummy that proves the view works. Every slow operation is a Celery task.
Every write is in a database transaction. No stub functions. No placeholder comments.
No class-based views. No skipped pages.

---

## PART ONE: GOLDEN RULES AND PROJECT CONVENTIONS

### Rule One: Function-Based Views Only

Every view in this project is a plain Python function. It accepts a request object as
its first argument and returns an HttpResponse. There are no class-based views, no
generic views, no LoginRequiredMixin, no TemplateView, no ListView anywhere in the
codebase. Where class-based views would normally provide mixins or base behaviour, you
instead write decorator functions or plain helper functions that wrap the view function
and achieve the same result. This applies to every view in every app described in this
document without exception.

### Rule Two: App-Per-Group Inside the Public Folder

Customer-facing storefront views live in a folder called public at the top level of
the Django project directory. This folder is a Python package. Inside it, there is one
Django app per logical page group. Each app has its own views.py, its own urls.py, its
own tasks.py for Celery tasks, its own utils.py for helper functions, and its own
templates subdirectory. The root urls.py includes each app's URL configuration under
the storefront namespace.

The apps that must exist inside public are: home, category, product, search, cart,
checkout, account, promotions, content, store, support, legal, i18n, b2b, and
monitoring. The monitoring app is new and described in Part Three of this document.

Platform-level concerns that are not tenant-storefront concerns live at the platform
level outside the public folder. The tenant onboarding app, the theme management app,
and the platform admin app live at this level. They are described in Parts Four and
Five.

### Rule Three: Authentication View Pattern

Authentication views (login, register, email verification, password reset) are function-
based views that instantiate Django's built-in auth forms directly — AuthenticationForm,
UserCreationForm, PasswordResetForm, SetPasswordForm, PasswordChangeForm — and pass
those form instances into a render() call. The template handles all rendering. Allauth
is used for the underlying machinery (email verification, social OAuth token handling,
adapter pattern) but allauth's own class-based views are never used as URL endpoints.
Instead, allauth's internal functions and adapters are called programmatically from
within your function-based view wrappers.

### Rule Four: Dummy Templates

Every page starts with a dummy template. The dummy template extends the base template
of the home app at home/base.html. It defines the title block using the meta_title
context variable and defines the content block as a heading with the page name, a note
that this is a placeholder, and a collapsible details element listing all context keys
passed by the view. The dummy template's only purpose is to confirm the view runs
without errors and passes complete context. The production UI replaces these later.

### Rule Five: Completeness

Do not write stub functions. Do not write pass inside a view. Do not write TODO. Every
view is fully implemented. If a model that a view needs does not yet exist in the
project, you note it at the top of the file as DEPENDENCY NEEDED: ModelName — fields
description, but you still write the view as if the model is fully present, importing
it from the expected path.

### Rule Six: Standard Engineering Practices

Every views.py file defines a module-level logger using logging.getLogger(__name__).
Every form POST wraps its database writes in transaction.atomic(). Every operation that
involves sending email, making an external API call, updating a search index, or firing
an analytics event is dispatched as a Celery task using .delay() or .apply_async().
Every queryset that involves related objects uses select_related and prefetch_related
to prevent N+1 queries. Every listing view paginates its queryset. Every paginator
handles PageNotAnInteger and EmptyPage silently by falling back to page one. Every view
passes context_keys as a list of its context dictionary keys for the dummy template.

---

## PART TWO: THE COMPLETE STOREFRONT VIEW LAYER

### Project Stack

The project runs on Python 3.11 or higher and Django 4.2 LTS. The database is
PostgreSQL accessed via psycopg2 or psycopg3. django-tenants provides schema-based
multi-tenancy. Celery with Redis handles async task processing. django-allauth handles
authentication including social OAuth. django-filter handles queryset filtering.
django-mptt or treebeard provides the category tree. Pillow handles image processing.
django-storages pointed at an S3-compatible bucket handles media files in production.
django-redis provides the cache backend. Payment gateways — Stripe, Paystack, and
Flutterwave — are abstracted behind a payment service layer that your views call
through service functions rather than touching gateway SDKs directly.

### Shared Utility Functions

Before building any app, you will create a shared utilities module at public/utils.py.
This module is the foundation everything else depends on.

The get_site_settings function retrieves the SiteSettings singleton from a Redis cache
keyed as storefront:site_settings with a 3600 second TTL. On cache miss it queries the
database. On database failure it returns a safe default object with sensible fallback
values for every field. It never raises an exception under any circumstances.

The get_or_create_cart function is the single canonical source for resolving the current
cart. For authenticated users it finds or creates a Cart linked to that user and merges
any session-keyed anonymous cart into it before deleting the session cart. For anonymous
users it uses the Django session key to find or create a Cart and ensures the session
key is stored in the session. This function is called by every view that needs the cart.
No other code path creates or finds a cart.

The get_cart_item_count function calls get_or_create_cart and returns only the total
item count. For authenticated users the result is cached by user ID for 60 seconds.

The build_seo_context function accepts a title, a description, an optional image URL,
and an optional canonical URL. It returns a dictionary with meta_title, meta_description
truncated cleanly at a word boundary to 160 characters, og_image, and canonical_url.

The get_client_ip function extracts the validated client IP from the request, checking
HTTP_X_FORWARDED_FOR and taking only the first entry, falling back to REMOTE_ADDR, and
validating the result is a real IP address before returning it.

The paginate_queryset function wraps Django's Paginator, accepts a queryset, a page
number from the request GET parameters, and an optional per_page count. It handles
PageNotAnInteger and EmptyPage by falling back to page one and returns a tuple of the
page object and the paginator object.

The login_required_view decorator wraps any function-based view and redirects
unauthenticated users to the login page with the current full URL as the next parameter.

The require_b2b_account decorator wraps any function-based view and checks that the
authenticated user has an associated B2BAccount record. If they do not, it redirects
to the B2B application page with a message. If they are not authenticated, it redirects
to the login page.

The rate_limit decorator uses the Redis cache to enforce a maximum number of requests
per time window on a per-IP and optional per-user basis. When the limit is exceeded it
returns a 429 response with a Retry-After header. It is applied to login, registration,
password reset, contact form, newsletter subscription, and cart mutation endpoints.

### The Existing Models

All models described below already exist. Import them by name. Do not redefine them.

The Product model has: name, slug, sku, description, status (draft/active/archived),
is_active, is_featured, product_type (simple/configurable/digital/subscription/pre-order/
bundle), FK to Brand, FK to Category, M2M to Tag, meta_title, meta_description,
created_at, updated_at.

The ProductVariant model has: FK to Product, sku, price, compare_at_price, cost_price,
stock_quantity, weight, barcode, attributes_json, is_active.

The ProductImage model has: FK to Product, nullable FK to ProductVariant, image,
alt_text, sort_order, is_primary.

The ProductAttribute model has: name, slug, type. The ProductAttributeValue model has
allowed values per attribute. The ProductVariantAttribute is a through model linking
ProductVariant to ProductAttributeValue.

The Category model is an MPTT or treebeard tree with: name, slug, nullable parent,
image, description, meta_title, meta_description, is_active, sort_order.

The Brand model has: name, slug, logo, description, is_active.

The Tag model has: name, slug.

The Collection model has: name, slug, description, image, is_active, M2M to Product,
sort_order, start_date, end_date. Note is_gift_guide as a dependency BooleanField if
not present.

The Bundle model has: name, slug, price, is_active, items through BundleItem. The
BundleItem model has: FK to Bundle, FK to Product, nullable FK to ProductVariant,
quantity.

The DigitalProduct model has a OneToOne to Product and adds: file_field, download_limit,
expiry_days.

The ProductReview model has: FK to Product, FK to User, rating 1-5, title, body,
is_approved, is_verified_purchase, helpful_count, created_at.

The ProductQuestion model has: FK to Product, FK to asker user, question, is_approved,
created_at. The ProductAnswer model has: FK to ProductQuestion, FK to answerer user,
answer, is_approved, is_staff_answer, created_at.

The Inventory model has a OneToOne to ProductVariant and tracks: quantity_on_hand,
quantity_reserved, quantity_available, reorder_point, reorder_quantity,
warehouse_location. The StockAlert model records users or guest emails waiting for
restock notifications. The InventoryTransaction model is an append-only stock movement
log.

The Order model has: nullable FK to User, guest_email, order_number, status (pending/
processing/shipped/delivered/cancelled/refunded), payment_status, fulfillment_status,
currency, subtotal, discount_amount, shipping_amount, tax_amount, grand_total, shipping
and billing addresses as JSON, FK to ShippingMethod, payment_method, payment_gateway,
gateway_reference for idempotency, nullable FK to Coupon, notes, ip_address,
user_agent, timestamps. The OrderItem model has: FK to Order, FK to Product, nullable
FK to ProductVariant, snapshot fields product_name, variant_title, sku, quantity,
unit_price, discount_amount, line_total, is_digital, download_url. The
OrderStatusHistory model records every status change immutably. The OrderReturn model
tracks return requests. The OrderReturnItem model tracks return line items. The
OrderTracking model stores carrier name, tracking number, tracking URL, estimated
delivery, events JSON, last_synced_at.

The Cart model has: nullable FK to User, session_key, currency, nullable FK to Coupon,
timestamps. The CartItem model has: FK to Cart, FK to Product, nullable FK to
ProductVariant, quantity, unit_price, saved_for_later boolean.

The CustomerProfile model has a OneToOne to User and adds: phone, date_of_birth, gender,
avatar, accepts_marketing, loyalty_points, tier, referral_code, nullable referred_by FK,
store_credit, created_at.

The Address model has: FK to User, label, first_name, last_name, company, line1, line2,
city, state, postal_code, country, phone, is_default_shipping, is_default_billing.

The SavedPaymentMethod model has: FK to User, gateway, gateway_token, last4, brand,
expiry_month, expiry_year, is_default, created_at.

The Wishlist model has: FK to User, name, slug, is_public, created_at. The WishlistItem
model has: FK to Wishlist, FK to Product, nullable FK to ProductVariant, added_at.

The RecentlyViewed model has: nullable FK to User, session_key, FK to Product, viewed_at.

The Notification model has: FK to User, type, title, body, link, is_read, created_at.

The LoyaltyTransaction model has: FK to User, points, transaction_type, description,
nullable FK to Order, created_at. The LoyaltyTier model has: name, min_points,
discount_percent, perks JSON.

The Referral model has: FK to referrer user, nullable FK to referred user, code, status,
reward_points, created_at.

The Coupon model has: code, type, value, min_order_value, max_discount, usage_limit,
used_count, per_user_limit, start_date, end_date, is_active, applies_to scope,
product_ids JSON, category_ids JSON. The CouponUsage model has: FK to Coupon, nullable
FK to User, FK to Order, used_at.

The Promotion model has: name, slug, type, banner_image, description, start_date,
end_date, is_active, priority. The FlashSale model has: FK to Promotion, start_datetime,
end_datetime, items through FlashSaleItem. The FlashSaleItem model has: FK to FlashSale,
FK to ProductVariant, sale_price, original_price, quantity_limit, sold_count.

The GiftCard model has: code, initial_value, current_balance, currency, nullable FK to
purchaser user, recipient_email, is_active, expires_at, created_at. The
GiftCardTransaction model has: FK to GiftCard, nullable FK to Order, amount, created_at.

The SubscriptionPlan model has: name, slug, billing_interval, billing_interval_count,
price, trial_days, is_active. The CustomerSubscription model has: FK to User, FK to
SubscriptionPlan, nullable FK to Product, nullable FK to ProductVariant, status,
gateway, gateway_subscription_id, current_period_start, current_period_end,
cancel_at_period_end, created_at.

The ShippingZone model has: name, countries JSON, is_active. The ShippingMethod model
has: FK to ShippingZone, name, carrier, type, min_order_value, max_order_value, price,
free_above, estimated_days_min, estimated_days_max, is_active.

The PhysicalStore model has: name, slug, address fields, phone, email, latitude,
longitude, hours JSON, is_active. The ClickCollectSlot model has: FK to PhysicalStore,
nullable FK to Order, date, time_slot, status.

The BlogPost model has: title, slug, FK to author, excerpt, body, featured_image, FK to
BlogCategory, M2M to Tag, status, published_at, meta_title, meta_description.

The BlogCategory model has: name, slug, description.

The BuyingGuide model has: title, slug, nullable FK to Category, body, published_at,
is_active.

The Lookbook model has: title, slug, description, cover_image, is_active, published_at.
The LookbookItem model has: FK to Lookbook, image, nullable FK to Product, x_position,
y_position, caption.

The UGCPhoto model has: nullable FK to User, FK to Product, image, caption, is_approved,
created_at.

The VideoGalleryItem model has: title, description, video_url, thumbnail, nullable FK to
Product, is_active, sort_order.

The FAQCategory model has: name, slug, sort_order. The FAQ model has: FK to FAQCategory,
question, answer, sort_order, is_active. Note view_count IntegerField as a dependency.

The SupportTicket model has: nullable FK to User, guest_email, nullable FK to Order,
subject, body, status, priority, nullable FK to assigned_to staff, timestamps. The
SupportTicketMessage model has: FK to SupportTicket, nullable FK to sender, body,
is_staff, created_at.

The NewsletterSubscriber model has: email, first_name, is_active, source,
unsubscribe_token, subscribed_at.

The CampaignLandingPage model has: name, slug, nullable FK to Coupon, headline,
subheadline, body, is_active, start_date, end_date.

The Competition model has: name, slug, description, rules, start_date, end_date,
is_active. The CompetitionEntry model has: FK to Competition, nullable FK to User,
email, entry_data JSON, created_at.

The B2BApplication model has: company_name, contact_name, email, phone, website,
vat_number, status, submitted_at, nullable FK to reviewed_by staff, notes.

The B2BAccount model has: FK to User, company_name, credit_limit, payment_terms_days,
tax_exempt, tax_certificate, approved_at.

The QuoteRequest model has: FK to User, nullable FK to B2BAccount, reference, status,
items JSON, notes, created_at. The Quote model has: FK to QuoteRequest, reference,
valid_until, items JSON, subtotal, discount_amount, tax_amount, total, notes,
created_at.

The PurchaseOrder model has: FK to B2BAccount, nullable FK to Order, po_number, status,
due_date, amount, created_at.

The ContractPricing model has: FK to B2BAccount, FK to ProductVariant, price,
min_quantity, start_date, end_date, is_active.

The CompanySubUser model has: FK to B2BAccount, FK to User, role, spending_limit,
requires_approval, is_active.

The SiteSettings model is a singleton with: site_name, logo, favicon, currency,
currency_symbol, tax_rate, maintenance_mode, meta_title, meta_description,
google_analytics_id, facebook_pixel_id, support_email, support_phone,
loyalty_earn_rate, loyalty_redemption_rate, return_window_days, freight_delivery_info
JSON, available_regions JSON, active_theme (note as dependency if not present,
CharField with default classic), enabled_gateways JSON.

### The Storefront Pages by App

The following describes every view that must be built. Every view is a function-based
view. Every view assembles a complete context dictionary. Every view passes context_keys
in its context. Every view has a corresponding URL pattern and a dummy template.

The home app owns the homepage, the HTML sitemap, the maintenance page, and the 404
and 500 error handlers. The homepage resolves SiteSettings first and redirects to the
maintenance page if maintenance_mode is true and the user is not staff. It then
assembles featured products (active, is_featured, 12 records with images and variants
prefetched, randomly ordered), active collections within their valid date window (6
records with products prefetched), top-level active categories by sort_order (8
records), any currently active flash sale with its items, the 12 most recently created
active products as new arrivals, the 12 best-selling products aggregated from OrderItem
quantities over the last 30 days and cached for 30 minutes, all active in-window
promotions and banners, and for authenticated users a personalised recommendation set
derived from the categories of their recently viewed products plus their loyalty tier
and next-tier progress. The cart item count and wishlist product IDs are always
included. An analytics event page_view homepage is dispatched as a Celery task. If any
data fetch fails individually it is caught, logged at warning level, and replaced with
an empty fallback — the homepage must never return a 500. The HTML sitemap assembles all
active categories in tree order, all active products as value lists, all published blog
posts, all FAQ categories, and all active collections, cached for one hour. The
maintenance view redirects staff users to the homepage and renders the maintenance
template for everyone else. The 404 handler resolves cart item count silently, fetches
four popular categories and four featured products as suggestions, logs at warning level
with the requested path, and returns status 404. The 500 handler makes no database calls
and returns a static safe response at status 500.

The category app owns eleven browse and navigation page views. The category listing view
resolves a Category by slug (404 if not found or inactive, with staff preview exception).
In subcategory grid mode (when the category has children and show_products is not in
the query string) it shows child categories with images and product counts. In product
mode it fetches all active products belonging to the category and all its descendants
via MPTT or treebeard traversal, applies ProductFilter from django-filter, applies
sorting by price_asc, price_desc, newest, popular (order count), or rating (average
review), paginates at 24, computes brand count facets, price range facets, attribute
value count facets, builds the breadcrumb trail via get_ancestors(), fetches sibling
categories, checks for a linked active promotion banner, and dispatches a
category_view analytics event. The subcategory listing view reuses category listing
logic but validates the parent slug in the URL matches the resolved category's actual
parent. The brand page view resolves Brand by slug and applies the same filter, sort,
and facet logic with an additional related-brands context. The collection view resolves
Collection by slug and shows an is_active false state rather than 404 when outside its
date window. The new arrivals view accepts a days parameter (7/14/30/90/all) to narrow
the window. The best sellers view aggregates OrderItem by product_id summing quantity,
accepts a period parameter, and caches by period for 30 minutes. The trending view
computes a weighted score from RecentlyViewed count (weight 0.2), OrderItem count
(weight 0.5), and WishlistItem count (weight 0.3) over 7 days, cached 15 minutes, with
a fallback to recent high-rated products if signals are empty. The deals view merges
sale variants, active flash sale items, and for B2B users active contract pricing items.
The flash sale view resolves the active FlashSale by datetime window, shows has_active_sale
false rather than 404 when none is active, computes ends_in_seconds, flags sold-out items,
and caches for 30 seconds. The clearance view fetches products tagged clearance or in
a clearance collection. The gift guide view fetches Collections with is_gift_guide true.

The product app owns nine detail page views. The product detail view is the system's
most complex view. It resolves Product by slug with full select_related and
prefetch_related, handles staff preview of inactive products, resolves the active
variant from a variant query parameter falling back to the first active variant, computes
discount_percent from compare_at_price vs price, computes stock status label (In Stock,
Low Stock below 5, Out of Stock), checks wishlist membership for the current user,
fetches approved reviews with aggregate stats (average rating, rating distribution
dictionary) paginated at 5, fetches approved Q&A paginated at 5, checks if the user
can review (verified purchase check) and has already reviewed, fetches related products
by same category (8), fetches upsell products from a product upsells M2M if present,
fetches cross-sell recommendations from a frequently-bought-together OrderItem
aggregation cached one hour, checks for an active FlashSaleItem for this variant,
checks for active bundles containing this product, records the view in RecentlyViewed
via a Celery task, constructs a Product JSON-LD structured data block, assembles the
breadcrumb trail, and dispatches a product_view analytics event. The comparison view
accepts an ids query parameter of up to four product IDs, filters out invalid ones
silently, redirects to the homepage with a warning if fewer than two remain, and builds
a comparison matrix of attributes across all valid products. The bundle detail view
resolves Bundle, loads BundleItem with products and variants, computes bundle_savings,
and determines in-stock status (true only if all items are in stock). The digital
product detail view extends product detail logic, generates time-limited signed download
URLs for users with delivered orders containing this product, and validates against
download_limit and expiry_days. The subscription product view loads all SubscriptionPlan
objects for the product and sets has_active_subscription true if the user has an active
CustomerSubscription for it. The configurable product view builds a dynamic form from
configurable ProductAttribute types on GET and stores configuration in the session on
valid POST. The notify-me view creates StockAlert records (handling duplicates
gracefully), validates stock before showing the form, and dispatches a confirmation
email. The pre-order view validates product_type is pre_order and sets a session flag
for PENDING_FULFILLMENT checkout status.

The search app owns five page views. The search results view reads the q parameter,
validates its length (1-200 chars), uses Q objects across product name, description,
sku, tag names, brand name, and category name with distinct(), applies ProductFilter
on top, applies sorting and pagination at 24, computes facets, records the search in a
SearchLog model (note as dependency) via a Celery task, fetches 4 featured products as
fallback when zero results, and computes related search suggestions from SearchLog.
The advanced search view exposes all ProductFilter dimensions in a structured form and
on submission redirects to search results with encoded parameters. The visual search
view accepts an image file upload (JPEG/PNG/WebP, 5MB max), creates a VisualSearchJob
(note as dependency), dispatches a Celery task for similarity search, and returns
immediately with the job ID; a polling endpoint at a distinct URL returns results when
available. The tag browse view resolves Tag by slug and computes related tags from co-
occurrences. The filtered browse view applies all ProductFilter dimensions to all active
products with no required parameters.

The cart app owns three functional units. The cart view resolves the cart via
get_or_create_cart, loads all items with select_related for products, variants, and
inventories, computes current unit prices from variants (not stored prices), line totals,
is_in_stock, max_available, and exceeds_stock for each item, computes cart totals
(subtotal, discount from coupon, estimated tax, estimated total), fetches four cross-sell
recommendations by category, and handles coupon apply/remove via POST with specific
validation error messages for each failure case (inactive, expired, usage exceeded,
per-user limit exceeded, minimum order not met, scope mismatch). The cart update view
accepts POST actions (add/update/remove/save_later/move_to_cart) and returns JSON
(success, cart_count, cart_subtotal, message), with all writes in transaction.atomic()
and rate-limited at 30 mutations per minute per session. The cart abandonment recovery
view resolves a CartRecoveryToken (note as dependency), validates it is unused and
unexpired, merges the cart, marks the token used, applies any recovery coupon, and
redirects to the cart page.

The checkout app owns ten views. The guest-or-account choice view redirects
authenticated users directly to the information step, checks for a non-empty cart,
sets checkout_started and checkout_digital_only session flags, and presents the login/
register/guest three-way choice for anonymous users. The information view pre-fills
from the user's profile and address book on GET, validates CheckoutInformationForm on
POST, stores the address in the session, and redirects to shipping or directly to
payment for digital-only carts. The shipping method view resolves applicable
ShippingMethod objects by matching destination country to ShippingZone countries,
filters by order value constraints, flags free methods, sorts by price, shows an error
state (not a crash) when no methods cover the destination, and saves the selected method
to the session. The payment view computes final totals, initialises gateway client-side
data via the payment service layer (Stripe client_secret, Paystack and Flutterwave
transaction references), shows saved payment methods for authenticated users, and
handles gift card validation and store credit toggle. The review view re-validates
stock and coupon before rendering the full summary and an order notes field. The
payment callback view resolves the gateway from a query parameter, calls
payment_service.verify_payment(), and on success opens a transaction.atomic() block in
which it creates the Order and all OrderItem records, decrements inventory with
InventoryTransaction records, records CouponUsage, redeems gift card balance and store
credit, dispatches Celery tasks for loyalty point award, confirmation email, and
analytics event, clears the cart and all checkout session keys, and redirects to the
confirmation page. It is fully idempotent: it checks for an existing Order by
gateway_reference before doing any of this. On payment failure it logs with the error
code and redirects to the payment step with a specific message. The payment webhook
view is CSRF-exempt, validates the gateway's HMAC signature, returns 200 immediately,
and dispatches the event processing to a Celery task. The express checkout view handles
Apple Pay, Google Pay, and PayPal Express tokens, creates the order atomically, and
returns JSON with a redirect URL. The order confirmation view validates access by user
ownership or session guest token, generates signed download URLs for digital items,
fetches four post-purchase recommendations, and clears checkout session flags.

The account app owns all authentication and customer self-service views. The login view
rate-limits by IP (five attempts per 15 minutes), validates AuthenticationForm, merges
the session cart on success, and auto-logs in. The registration view validates first
name, last name, email (specific error with login link if already registered), password
strength, accepts_marketing, and optional referral code; creates User and
CustomerProfile atomically; dispatches referral reward and verification email tasks;
auto-logs in and merges the session cart. The email verification view handles three
states: valid (mark verified, redirect), expired (show resend option, rate-limited at
three per hour), already verified (show state). The forgot password view always returns
the same message regardless of whether the email exists. The reset password view
validates the Django token, validates SetPasswordForm, invalidates other sessions, auto-
logs in. The account overview assembles: last five orders, wishlist count, loyalty tier
and progress, pending returns count, open ticket count, unread notification count, active
subscription count, and pending B2B quotes. Order history paginates at 10 with status/
year/order-number filters. Order detail validates ownership strictly, computes can_cancel
(pending/processing and under one hour old) and can_return (delivered and within return
window). Order tracking has an authenticated version (ownership validated) and a public
version at a separate URL (email and order number validated against the order); both
dispatch a re-sync Celery task if last_synced_at is more than 30 minutes old. Return
request validates delivery and return window, accepts item selection, quantities, reasons,
conditions, notes, and up to three photos (2MB each). Profile view resizes avatar to
200x200 via Pillow; email changes dispatch verification to new address without changing
the active email. Password and security view handles password change via
PasswordChangeForm, two-factor device management via allauth or django-otp, and active
session management via a UserSession model (note as dependency). Address book handles
add, edit, delete (blocked for addresses on open orders), and default-setting actions.
Saved payment methods handles listing (last4 only, never full numbers), addition via
gateway-hosted setup flow, deletion via gateway API then local record, and default
toggle. Wishlist list shows all user wishlists with counts. Wishlist detail shows items
with current prices and stock status and price-change-since-added flags. Wishlist share
resolves by public token (404 if is_public is false) and shows only product names,
images, and the owner's display name. Recently viewed shows 50 most recent distinct
products paginated at 20. Loyalty shows points, tier ladder, progress, paginated
transaction history, and pending points. Referral gets or creates a Referral record and
shows code, shareable URL, and conversion counts. Store credit shows balance and
paginated transaction history from a StoreCreditTransaction model (note as dependency).
Subscriptions management lists all CustomerSubscription records and handles pause,
resume, and cancel actions (cancel sets cancel_at_period_end, calls the payment service
layer, dispatches confirmation email). Notification preferences loads and saves a
NotificationPreference model (note as dependency). Privacy and data view dispatches
DataExportRequest and DataDeletionRequest (note both as dependencies) as Celery tasks.
Account deletion validates password, anonymises data if order history exists. My reviews
and my questions show the user's own records with edit-within-seven-days and delete
options.

The promotions app owns nine views. Coupon landing resolves by code case-insensitively
and applies to the cart. Loyalty programme info shows LoyaltyTier objects and earn/
redemption rates with current-tier context for authenticated users. Referral landing
stores the code in session and shows already-a-member state for authenticated users.
Gift card purchase adds to cart as a special item; after order confirmation a task
creates the GiftCard record and emails the code to the recipient. Gift card balance
accepts a code, looks up by code, and returns balance and status without exposing
purchaser data. Newsletter subscribe is a rate-limited AJAX endpoint that creates or
reactivates NewsletterSubscriber and dispatches a welcome email. Unsubscribe resolves
by token and sets is_active false while offering a preference centre. Competition
prevents duplicate entries and creates CompetitionEntry records. Seasonal campaign
auto-applies attached coupons to the session on page load and shows ended/not-started
states gracefully.

The content app owns eight views. Blog index paginates at 12 with category, tag, and
keyword filters and a sidebar of recent posts, categories with counts, and tag cloud.
Blog post handles staff preview of drafts via preview=1 query parameter and constructs
Article JSON-LD. Buying guide appends linked category products to context. Lookbook
loads LookbookItem records with linked product prices and stock status. Video gallery
extracts embed IDs from YouTube and Vimeo URLs. UGC gallery allows authenticated users
to submit photos as Celery-dispatched moderation tasks. Product Q&A restricts answer
submission to staff and verified purchasers. Review submission requires verified
purchase and dispatches a moderation notification.

The store app owns six views. Store locator computes Haversine distances when lat and
lng parameters are present and passes store coordinates as JSON for map rendering.
Store detail computes is_open_now from hours JSON. Click and collect reserves a
ClickCollectSlot and sets the checkout session shipping method to click-and-collect.
Delivery information and international shipping pages load ShippingZone and
ShippingMethod data and cache for one hour. Freight delivery serves static content from
SiteSettings.

The support app owns seven views. Help centre supports keyword search across FAQ
question and answer fields. FAQ detail increments view_count as a Celery task and
handles helpful votes via a FAQHelpfulVote model (note as dependency) deduplicated by
session. Contact view enforces five-per-IP-per-hour rate limiting and creates a
SupportTicket. Ticket submission accepts category, priority, order association, and up
to three file attachments (JPEG/PNG/PDF/TXT, 5MB each). Ticket status validates
ownership by user match or guest token, loads the full message thread, and reopens
resolved tickets on reply. Warranty claim creates a WarrantyClaim model (note as
dependency). Product recall lists active ProductRecall models (note as dependency) and
shows personalised alerts for users who have purchased affected items.

The legal app owns eight content page views (terms, privacy, cookie policy, DMCA,
accessibility policy, modern slavery, regulatory compliance, and the returns policy)
all following the same pattern: load content from SiteSettings, cache for one hour,
render with page name, last_updated, and content as HTML-safe text. The cookie
preference centre view reads consent state from the cookie on GET and on POST sets the
cookie_consent cookie (365-day expiry, SameSite=Lax, Secure in production) from a JSON
body with analytics, marketing, and preferences booleans and returns a JSON response.

The i18n app owns three views. Region selector shows available regions from
SiteSettings.available_regions, determines the current region from session or IP
geolocation (cached by IP for 24 hours), and saves the selection to session and a one-
year cookie on POST. Geo-redirect shows a one-time interstitial skipped if the
geo_redirect_dismissed cookie is set or the user agent is a known crawler. Set-language
wraps Django's built-in set_language after validating the language code.

The b2b app owns nine views. B2B application checks for existing account or pending
application before showing the form, which captures company info, estimated spend,
category interests, and B2B terms agreement. B2B portal is protected by the
require_b2b_account decorator and shows a comprehensive dashboard with quotes, purchase
orders, invoices, sub-users, and spending. RFQ accepts up to 50 dynamic line items,
validates all SKUs in a single query, and collects all errors before returning. Quote
detail validates ownership, checks validity period, and handles accept (creates Order
and redirects to PO checkout) and decline actions. PO checkout validates credit limit
and existing overdue orders, creates Order and PurchaseOrder atomically, and dispatches
an invoice email. Contract pricing paginates at 50 and supports CSV export via
StreamingHttpResponse. Company account restricts to admin role or owner and handles
sub-user add, edit, and deactivation. Invoice history links to the invoice PDF view
which generates and caches the PDF for 24 hours. Tax exemption handles certificate
upload, validates file type and size, and dispatches a finance team notification.

### Context Processors and URL Configuration

A global context processor at public/context_processors.py injects into every template:
site_settings (from the cached get_site_settings), top_categories (active root
categories, cached 5 minutes), cart_item_count (from get_cart_item_count),
wishlist_count (for authenticated users), unread_notification_count (for authenticated
users), is_maintenance_mode, current_currency, current_region, active_flash_sale
(cached 30 seconds), active_theme (the current theme slug from SiteSettings), and
is_monitoring_enabled (a boolean from SiteSettings, true by default).

All URLs are registered in each app's urls.py with the storefront namespace following
the pattern storefront:app:action. The root urls.py includes all app URL configurations.

---

## PART THREE: VISITOR MONITORING SYSTEM

### Purpose

The monitoring system silently records every page visit made on both the customer-
facing storefront and the tenant's admin dashboard. It is implemented as Django
middleware on the recording side and as a set of read-only reporting views on the
viewing side. The tenant can see everything the system records about visitors to their
store. They cannot modify, delete, or suppress any record.

### New App: monitoring (inside public/)

Create a new Django app called monitoring inside the public folder. It has models.py,
middleware.py, views.py, urls.py, tasks.py, utils.py, and a templates/monitoring
directory.

### The PageVisit Model

The PageVisit model records one row per page load. It has the following fields: an auto
primary key, a nullable FK to User (null for anonymous), a session_key CharField storing
the Django session key, a visit_id UUIDField generated at middleware time and used to
correlate the asynchronous client beacon update, a path CharField storing the full
request path and query string, a page_name CharField storing the URL pattern name from
request.resolver_match.view_name or the raw path on 404, a page_category CharField
derived from the URL namespace (Storefront, Admin Dashboard, Checkout, Account, B2B,
Content, Support, etc.), a referrer CharField storing the HTTP Referer header truncated
to 500 characters, an ip_address GenericIPAddressField, a user_agent TextField, a
device_type CharField with choices Desktop/Mobile/Tablet derived from the user agent,
a browser CharField derived from the user agent (Chrome/Firefox/Safari/Edge/Other), a
country_code CharField storing the two-letter ISO country code derived from geolocation
(null if unavailable), a city CharField (null if unavailable), an is_bot BooleanField
derived from user agent pattern matching, an is_admin_visit BooleanField true when the
visit is to the tenant admin dashboard, a status_code IntegerField storing the HTTP
response status code, a time_on_page IntegerField storing seconds (initially null,
filled by client beacon), a scroll_depth IntegerField storing percentage 0-100
(initially null, filled by client beacon), an extra_data JSONField for additional event
data, a created_at auto timestamp, and an updated_at timestamp.

### The VisitorSession Model

The VisitorSession model groups individual PageVisit records into behavioural sessions.
A session is a continuous period of activity from a single session_key. It has: a
session_key CharField (unique per session), a nullable FK to User, a started_at
datetime, a last_seen_at datetime, a page_count PositiveIntegerField, a
total_time_on_site IntegerField in seconds, an entry_page CharField, an exit_page
CharField (updated on each new visit), a device_type CharField, a browser CharField,
a country_code CharField, an is_bot BooleanField, a tenant CharField, and timestamps.

A session is considered expired when the gap between last_seen_at and the new visit
exceeds 30 minutes. The record_page_visit Celery task handles session creation, update,
and expiry logic.

### The Middleware

The PageVisitMiddleware lives in monitoring/middleware.py and is added to the MIDDLEWARE
list in settings after SessionMiddleware and AuthenticationMiddleware. It operates in
the process_response phase. It immediately returns without recording if the path begins
with the STATIC_URL or MEDIA_URL prefix, or if the request is an AJAX request (unless
the path is the beacon endpoint), or if the response is a streaming response. For all
other requests it collects: the session key from request.session.session_key (creating
the session first if it does not exist yet), the user ID if request.user.is_authenticated
is true, the path, the query string, the Referer header, the IP from get_client_ip, the
User-Agent header, the view name from request.resolver_match.view_name or the raw path,
the page category derived from the view name namespace, whether this is an admin visit
from the URL namespace, and the response status code.

It then generates a visit_id as a UUID4. If the response is an HTML response (checked
via Content-Type containing text/html), it injects the visit_id into the response by
replacing a specific placeholder string MONITORING_VISIT_ID_PLACEHOLDER that the
base template places inside a meta tag in the HTML head. This replacement is done on
the response.content bytes after encoding to ensure it is always the correct type. It
dispatches the record_page_visit Celery task with all collected data and the generated
visit_id immediately without waiting for the result. It then returns the response.

The middleware never raises an exception. Every operation inside it is wrapped in a
broad try/except that logs at error level and returns the original response unchanged
if anything fails. Monitoring failures must never affect the user's experience.

### The Client-Side Beacon Script

Every theme's base template includes a small inline JavaScript block immediately before
the closing body tag. This script does the following. On page load it records
window.pageLoadTime as the current timestamp in milliseconds. It reads the monitoring
visit_id from a meta tag in the document head (the meta tag has the name
monitoring-visit-id and its content is the visit_id injected by the middleware). It
initialises scrollDepthMax as zero. It attaches a throttled scroll event listener that
computes the current scroll percentage as Math.round((window.scrollY + window.innerHeight)
/ document.body.scrollHeight * 100) clamped to 0-100 and updates scrollDepthMax if the
new value is greater. It attaches a handler to both the beforeunload event and the
Page Visibility API's visibilitychange event (firing when document.visibilityState
becomes hidden) that computes time_on_page as Math.round((Date.now() -
window.pageLoadTime) / 1000), assembles a FormData object containing the visit_id,
time_on_page, and scroll_depth, and sends it using navigator.sendBeacon if available
or a synchronous XMLHttpRequest as a fallback to the beacon endpoint URL. The script
is careful to fire only once even if both beforeunload and visibilitychange both fire
in the same session by setting a sent flag after the first beacon.

### The Beacon Endpoint

The beacon endpoint is a function-based view at the path /monitoring/beacon/ named
monitoring:beacon. It accepts POST only. It is CSRF-exempt via the csrf_exempt
decorator. It reads visit_id, time_on_page, and scroll_depth from the POST body. It
validates that visit_id is a valid UUID string. It validates that time_on_page is an
integer between 0 and 86400 (24 hours). It validates that scroll_depth is an integer
between 0 and 100. It then attempts to find the PageVisit record with this visit_id
and validates that the visit belongs to the current session key (request.session.session_key
equals the record's session_key). If all validation passes it dispatches the
update_visit_engagement Celery task with the validated data. It always returns a 204
No Content response. If validation fails it returns 400. It never raises an exception.

### The Celery Tasks

The record_page_visit task in monitoring/tasks.py receives all the visit metadata as
keyword arguments. It performs bot detection by checking the user_agent against a list
of known bot signatures (Googlebot, Bingbot, Slurp, DuckDuckBot, Baiduspider,
facebookexternalhit, Python-urllib, python-requests, curl, wget and common crawlers).
It performs device classification by checking for Mobile and Tablet keywords in the
user agent string. It performs browser detection by checking for Chrome, Firefox,
Safari, Edge, and Opera signatures. It performs geolocation by calling a utility
function that wraps the MaxMind GeoIP2 lookup or an external IP geolocation API in a
try/except, returning None for country_code and city if anything fails. It creates the
PageVisit record. It then handles the VisitorSession: if a session with this session_key
exists and its last_seen_at is within 30 minutes, it updates last_seen_at to now,
increments page_count, and updates exit_page. If no session exists or the last visit
was more than 30 minutes ago, it creates a new VisitorSession with started_at now,
page_count one, and entry_page set to the current path, and if an old session existed
it first finalises it by setting exit_page to its current exit_page value (which is
already the correct value from the last update). All database operations in this task
are in a transaction.atomic() block.

The update_visit_engagement task updates the PageVisit record's time_on_page and
scroll_depth and then calls VisitorSession.objects.filter(session_key=session_key)
.update(total_time_on_site=F('total_time_on_site') + time_on_page) using Django's F
expression for atomicity.

### Monitoring Reporting Views (Tenant-Accessible)

These views are registered in the tenant admin dashboard URL configuration under a
monitoring prefix and are protected by the tenant admin authentication decorator.

The monitoring dashboard view assembles a summary page for the current tenant. It
queries PageVisit records filtered to this tenant's session keys. It computes:
total visits for the last 24 hours, last 7 days, and last 30 days; total unique
session_key values in each period; the human vs bot split; the authenticated vs
anonymous split; the top 10 page_name values by count with their average time_on_page;
the top 10 page_name values by average time_on_page; the top 5 country_code values by
count; the device_type distribution as a dict; the browser distribution as a dict; and
an hourly visit count for the current day as a list of 24 integers. It also queries
VisitorSession for total sessions and the average session page_count and total_time_on_site.
All of this is assembled from ORM annotate, aggregate, and values queries. The entire
context is cached per tenant for 5 minutes at the key storefront:monitoring:dashboard:{tenant_id}.

The live visitors view shows VisitorSession records where last_seen_at is within the
last 5 minutes, filtered to is_bot false. For each it shows the current exit_page path,
device_type, country_code, whether a User FK is set, page_count, and the duration since
started_at. This view is not cached. Its dummy template includes a meta refresh of 30
seconds.

The page analytics view shows a paginated list of page_name values with their aggregate
statistics: total_visits, unique_sessions, auth_visits, anon_visits, avg_time_on_page,
median_time_on_page (computed by ordering and taking the midpoint of a queryset),
avg_scroll_depth, bot_count, and a list of the top 5 referrer values. It accepts a
path_filter query parameter for drilling into a specific page and a date range filter
defaulting to the last 30 days. It paginates at 25 page names.

The visitor detail view accepts a session_key parameter, validates it belongs to the
current tenant by checking at least one PageVisit record for this session_key has the
correct tenant value, and shows all PageVisit records for the session in chronological
order. For authenticated sessions it shows the user's display name only. It never shows
email, phone, address, or payment data.

The user visit history view accepts a user_id parameter, validates the user belongs to
the current tenant, and shows all VisitorSession records attributed to that user in
reverse chronological order paginated at 20, with a link to the visitor detail view
for each session.

All monitoring reporting views accept date range GET parameters (start_date and end_date
in ISO format) and a human_only toggle defaulting to true that excludes bot visits.
All views include an is_admin_visit toggle that defaults to showing both storefront and
admin visits with a filter to separate them.

---

## PART FOUR: THE FIVE-THEME SYSTEM

### Architecture

The project currently has one default theme. You will add four additional themes,
bringing the total to five. The five themes are: Default (the one that already exists,
slug: default), Classic (slug: classic), Modern (slug: modern), Boutique (slug:
boutique), and Bold (slug: bold).

Themes live in a themes directory at the top level of the Django project directory
alongside the main project folder and the public folder. Each theme has its own
subdirectory named by its slug. Inside each theme directory there are two subdirectories:
templates and static. The templates directory contains a complete set of Django templates
for all 122 storefront pages, mirroring the public app template structure exactly
(themes/classic/templates/home/homepage.html, themes/classic/templates/product/
product_detail.html, and so on for all pages across all apps). The static directory
contains the theme's CSS, JavaScript, fonts, and images, namespaced under the theme slug
to prevent collisions (themes/classic/static/classic/css/main.css, etc.).

The active theme is determined by the active_theme field on SiteSettings (a CharField
defaulting to default). A custom template loader at themes/loader.py reads this value
from a Redis cache keyed as storefront:active_theme with a 60-second TTL. On each
template load request it checks the active theme's template directory first, then falls
through to the standard app template directories. The loader subclasses Django's
filesystem loader. It is registered in TEMPLATES before the standard loaders in
settings.py. STATICFILES_DIRS includes the static directory of every theme. A post_save
signal on SiteSettings invalidates the active_theme cache key whenever the model is
saved.

### The Four New Themes

For each of the four new themes you will produce a complete implementation of all 122
storefront page templates plus a cohesive static asset set (CSS, JavaScript). The
design systems are described below. Every interactive element — cart updates, wishlist
toggles, variant selectors, flash sale countdown timers, image galleries, accordion FAQ,
product filters, shipping method selection, payment step rendering — must work using
vanilla JavaScript only. No external JavaScript frameworks or libraries beyond what is
already in the project. The monitoring beacon script must be present in each theme's
base template.

The Classic theme is built on a philosophy of trustworthiness, structure, and clarity.
Its navigation is a full-width horizontal bar with a mega-menu for categories that drops
into a multi-column grid on hover. The layout uses a conventional 12-column grid with a
clear maximum content width and generous left-right page margins. The colour palette is
white backgrounds with mid-grey section separators, a deep navy as the primary brand
accent used on buttons, links, prices, and active states, and a warm off-white for
secondary sections. Typography uses a classic serif typeface such as Playfair Display or
Georgia for all headings and a clean humanist sans-serif such as Lato or Source Sans Pro
for all body text, labels, and UI elements. Product cards are clean rectangles with a
defined border radius, a generous image area with a subtle hover shadow lift, the product
name in the heading typeface below the image, the price in navy, the compare-at price
struck through in grey if present, and an add-to-cart button that becomes visible on
card hover. The homepage hero is a single full-width image with a large serif headline
and a solid navy call-to-action button. Category pages use a fixed left sidebar filter
panel and a right-side product grid. Cart and checkout pages use a two-column layout
with the form on the left and the order summary on the right. The overall feeling is
established, reliable, and instantly legible.

The Modern theme is built on a philosophy of bold minimalism and editorial impact. Its
navigation is a fixed slim header with only the logo and a hamburger menu icon; the
hamburger opens a full-viewport overlay with large, spaced-out category names in a heavy
typeface. The layout uses wide gutters and aggressive asymmetry with intentional use of
negative space as a design element. The colour palette is a stark near-black (#0a0a0a)
for text and dark elements against pure white, with a single vivid accent — electric
indigo or neon coral — used sparingly on the most important interactive element of each
page. Typography uses a bold geometric sans-serif such as Space Grotesk or DM Sans at
large weights for all headings and a lighter weight of the same typeface for body text,
with generous letter-spacing on headings. Product cards are square with the product
image filling the entire card; the product name and price appear in a translucent dark
overlay that slides up from the bottom on hover, with a minimal circular quick-add icon.
The homepage hero uses a split layout: one half is a full-height image, the other half
is a large bold typographic statement with the primary call to action. Collections and
lookbooks are presented as magazine spreads with full-bleed photography. Checkout uses
a full-viewport step-by-step flow where each step takes over the entire screen with
a progress indicator at the top. The overall feeling is premium, editorial, and
intentionally modern.

The Boutique theme is built on a philosophy of elegance, exclusivity, and restraint.
Its navigation is ultra-minimal: the store logo is centred at the top of the page
flanked by a thin horizontal rule, and below it sits a single row of widely spaced
category links in a small uppercase light-weight typeface. The layout uses a narrow
centred column for text content and a wide full-bleed presentation for imagery, creating
constant visual breathing space. The colour palette is entirely warm neutrals: ivory
(#faf8f5) for backgrounds, warm taupe (#c9b99a) for borders and dividers, a muted rose
gold for all accent elements (buttons outlined rather than filled, hover states, active
indicators), and charcoal (#2d2d2d) for body text. Typography uses a refined serif for
all headings and subheadings — something like Cormorant Garamond or EB Garamond — and
an extremely thin sans-serif such as Raleway Light for all body text and labels, at
small sizes with generous line height. Product cards have no visible card border; each
product is presented as its image and below it the product name in the thin sans-serif
and the price in a subdued rose-adjacent tone. The homepage hero uses a large lifestyle
photograph with the brand statement as a single line of centred serif text at a small
but elegant size overlaid on the image. Collections are presented as single full-width
horizontal editorial strips. The overall feeling is aspirational, curated, and whisper-
quiet in its visual confidence.

The Bold theme is built on a philosophy of energy, density, and action. Its navigation
is a solid thick bar in the primary accent colour with white text, housing the logo,
all main category links, a search bar, and the cart count all in one line — everything
is visible immediately with no hiding behind menus. The layout is compact and information-
dense, using a tighter grid with minimal white space, strong rectangular borders on
containers, and bold typographic hierarchy. The colour palette is committed to high
energy: a vivid red or deep orange as the primary accent against white, with strong black
text and a yellow or lime used for attention badges (sale, new, best seller). Typography
uses a heavy condensed sans-serif such as Barlow Condensed Bold or Oswald Bold for all
headings and a regular weight of the same typeface for body text — this keeps the visual
system dense and strong. Product cards have thick 2-pixel borders, a prominently visible
badge system in the top corners for offers and new arrivals, and a large add-to-cart
button that is always visible below the product name without requiring hover. The
homepage hero is a grid of three to four large promotional banners side by side, each
with its own headline and call to action, presenting multiple campaigns simultaneously.
Category pages show five products per row on desktop with compact cards. The overall
feeling is a high-volume retail environment that drives action.

### Theme Preview Assets

Each new theme must include a preview_image in its static directory (a 1280x800 pixel
static image showing what the theme looks like) and a thumbnail_image (a 400x250 pixel
version). These are used in the theme management and marketplace interfaces.

---

## PART FIVE: THEME MANAGEMENT AND MARKETPLACE

### New App: platform_themes (platform level, outside public/)

The platform_themes app is a platform-level app, not a tenant-storefront app. It lives
outside the public folder alongside other platform-level apps. It owns the Theme data
model, the TenantThemeAccess model, the TenantActiveTheme model, the ThemeSwitchLog
model, the platform admin theme management views, and the tenant-facing theme
marketplace views.

### Models

The Theme model has: name, slug (matches the themes/ directory name), description
TextField, preview_image ImageField, thumbnail_image ImageField, is_active BooleanField
(controls marketplace visibility), is_free BooleanField (all tenants get free themes
without purchasing), price DecimalField, currency CharField defaulting to NGN, features
JSONField storing a list of feature bullet point strings shown in the marketplace,
created_at, updated_at.

The TenantThemeAccess model represents a tenant's right to use a theme. It has: a
tenant field (storing the tenant schema name or identifier from django-tenants), FK to
Theme, access_type CharField with choices Free and Purchased, purchase_date nullable
DateTimeField, purchase_price nullable DecimalField, payment_reference nullable
CharField, is_active BooleanField. The combination of tenant and theme is unique.

The TenantActiveTheme model stores which theme is currently active per tenant. It has:
tenant CharField (unique), FK to Theme. Updating this record triggers the theme switch.

The ThemeSwitchLog model records every theme switch for auditability. It has: tenant
CharField, FK to from_theme Theme (nullable for the first activation), FK to to_theme
Theme, switched_at DateTimeField, switched_by_user FK to User, reason CharField.

### Platform Admin Theme Management Views

These views live in platform_themes/views.py under a platform admin URL prefix and are
protected by the platform admin authentication mechanism. All are function-based views.

The theme list view shows all Theme records in a table with: name, slug, is_free, price,
is_active, the count of TenantThemeAccess records for each theme, and action links to
edit and view access records.

The theme create and edit view renders a form covering all Theme model fields. On valid
POST, when is_free is changed from false to true, a Celery task creates TenantThemeAccess
records of type Free for every active tenant who does not already have access. When is_free
is changed from true to false, existing Free access records are not revoked. The task
dispatches a notification email to newly granted tenants informing them of the new free
theme.

The theme access list view shows all TenantThemeAccess records for a specific theme
with tenant, access_type, purchase_date, and purchase_price. Manual grant and manual
revocation actions are available. On revocation, if the affected tenant's currently
active theme is the one being revoked, a Celery task switches their active theme to the
default theme and sends them a notification email explaining the change.

### Tenant Theme Marketplace Views

These views are part of the tenant's admin dashboard experience. They are protected by
the tenant admin authentication decorator. They are function-based views in
platform_themes/views.py under a tenant-admin URL prefix.

The theme marketplace index view shows all Theme records where is_active is true. For
each theme it shows: the thumbnail_image, name, a description excerpt (first 150
characters), and a status indicator. The status can be: Active (the current active
theme for this tenant, shown first always), Owned (the tenant has a valid
TenantThemeAccess record and can activate it), Available to Purchase (the theme is
paid and the tenant does not own it, showing the price), or Free (the theme is free and
the tenant can activate it immediately). The layout is a responsive grid of theme cards.
The currently active theme is always the first card regardless of sort order.

The theme detail view shows: the full-size preview_image, name, full description, the
features list rendered as bullet points, price or Free label, and a prominent primary
action button whose label depends on status: Currently Active (disabled), Activate This
Theme (for owned themes not currently active), Purchase For [price] (for paid themes
not owned), or Activate Free Theme (for free themes not activated). A back link
returns to the marketplace index.

The theme purchase view presents an order summary showing the theme name, description,
and price with currency. It renders a payment form using the platform's payment gateway
integration (the same payment service layer used by the storefront, but charging the
tenant rather than a storefront customer). On POST it validates payment details, calls
payment_service.create_intent() to initiate the charge, and redirects to a payment
callback handler. The callback handler on success creates a TenantThemeAccess record
with access_type Purchased, purchase_date now, purchase_price set to the Theme.price
at time of purchase, and the gateway reference. It dispatches a purchase receipt email
to the tenant's account email address as a Celery task. It dispatches a
theme_purchase_completed analytics event for platform revenue tracking. It redirects to
the theme detail view where the Activate button is now visible.

The theme activate view accepts POST with a theme_slug. It validates that the current
tenant has a valid is_active TenantThemeAccess record for this theme (or that the theme
is free and exists). If validation fails, it returns an error. If validation passes, it
opens a transaction.atomic() block in which it updates or creates the TenantActiveTheme
record to point to the new theme, updates the SiteSettings active_theme field to the
new theme's slug and saves it (triggering the post_save signal that invalidates the
Redis cache key for the template loader), and creates a ThemeSwitchLog record. It
dispatches a theme_switched analytics event. It redirects to the marketplace index with
a success message informing the tenant their new theme will be live within 60 seconds.

---

## PART SIX: TENANT REGISTRATION AND STORE SUBSCRIPTION FLOW

### Overview

This is the most commercially critical system in the entire platform. When a new
business owner discovers SabiStart and decides to create a store, they enter a carefully
designed multi-step journey. This journey begins with their account and progresses
through store plan selection with add-ons, payment, and finally subdomain setup. The
tenant does not receive access to their admin dashboard and cannot choose a subdomain
until they have completed a successful payment for at least the base store plan. The
subdomain is set up only after payment is confirmed. This is a hard business rule that
the system enforces without exception.

The entire registration and onboarding flow lives in a new app called onboarding at the
platform level, outside the public folder. It has its own models.py, views.py, urls.py,
tasks.py, utils.py, and templates/onboarding directory.

### Subscription Plan Architecture

The store subscription is not a simple flat monthly fee. It is structured as a base plan
plus optional add-ons that the tenant selects at registration and can modify later. The
base plan gives the tenant a working store. Each add-on extends the store's capabilities
in a specific dimension. This structure makes the pricing feel like a tier system to the
tenant (because higher tiers naturally include more add-ons by default) while remaining
individually configurable and transparent about what each component costs.

The StorePlan model represents the base monthly subscription. It has: name, slug,
description, monthly_price as a DecimalField, annual_price as a DecimalField (the
discounted annual equivalent), currency, a features_included JSONField listing what the
base plan includes (for example: 1 storefront, up to 500 products, unlimited orders,
email support, 3 staff accounts), a max_products IntegerField, a max_staff_accounts
IntegerField, a max_monthly_orders IntegerField or null for unlimited,
transaction_fee_percent as a DecimalField (for example 2.5% per order on entry plan),
is_active BooleanField, is_popular BooleanField (to show a Most Popular badge on the
pricing page), sort_order IntegerField, created_at, updated_at.

The StoreAddOn model represents an individual add-on feature that can be purchased
separately. It has: name, slug, description, icon (a short string like a font icon
class or SVG path reference), monthly_price DecimalField, annual_price DecimalField,
currency, category CharField with choices such as Features/Integrations/Marketing/
Analytics/Support/Themes, what_it_includes TextField describing in plain language what
the add-on provides, is_active BooleanField, is_popular BooleanField, sort_order
IntegerField, created_at, updated_at.

Add-ons that you must pre-define (the platform admin can add more later through the
management interface) are: Custom Domain (allows the tenant to map a custom domain
to their store instead of or alongside the subdomain), Advanced Analytics (gives the
tenant access to detailed analytics dashboards beyond basic visitor monitoring),
Email Marketing (integrates with an email service provider to enable campaign sending
from the dashboard), Abandoned Cart Recovery (enables the automated cart recovery
email flow), Priority Support (guarantees a response time SLA for support tickets),
B2B/Wholesale Module (unlocks all the B2B views described in Part Two), Loyalty Program
(enables the loyalty points and tier system for the storefront), Review Booster
(enables automated post-purchase review request emails and the review management
interface), Multi-Currency (enables the currency selector and automatic price conversion
on the storefront), Physical Store Management (enables the store locator, click-and-
collect, and physical store admin views), and Additional Theme (enables purchase of
premium themes beyond the default free theme).

The StorePlanBundle model represents a preset combination of a base plan plus certain
add-ons that together form a named tier. It has: name (for example Starter, Growth,
Professional, Enterprise), slug, description, FK to StorePlan as the base, M2M to
StoreAddOn as the included add-ons, monthly_total_price DecimalField, annual_total_price
DecimalField, is_active BooleanField, is_popular BooleanField, sort_order IntegerField,
and a savings_percent DecimalField showing how much cheaper this bundle is versus
buying the components individually. These bundles are what the tenant sees first on the
pricing/plan selection page — they look like tiers. The tenant can also click Customise
to pick a base plan and individual add-ons themselves if none of the preset bundles
fit their needs.

The TenantSubscription model records what a tenant is paying for. It has: tenant
CharField (the django-tenants schema name), FK to StorePlan, M2M to StoreAddOn through
TenantSubscriptionAddOn, billing_cycle CharField with choices Monthly and Annual,
status CharField with choices Trial/Active/PastDue/Cancelled/Suspended, current_period_start
DateTimeField, current_period_end DateTimeField, trial_ends_at nullable DateTimeField,
next_billing_date DateTimeField, gateway CharField, gateway_subscription_id CharField,
gateway_customer_id CharField, monthly_amount DecimalField (what they actually pay each
cycle), is_trial BooleanField, cancel_at_period_end BooleanField, cancelled_at nullable
DateTimeField, created_at, updated_at.

The TenantSubscriptionAddOn through model has: FK to TenantSubscription, FK to
StoreAddOn, added_at DateTimeField, monthly_price DecimalField (price at time of adding).

The TenantOnboardingSession model tracks where a registering tenant is in the
multi-step flow so they can resume if interrupted. It has: a UUID session_token as the
primary key, a nullable FK to User (set after step one), email CharField (set before
user creation to identify the session), step CharField with choices Step1AccountDetails/
Step2PlanSelection/Step3AddOnSelection/Step4ReviewAndPay/Step5SubdomainSetup/
Step6Complete, plan_data JSONField storing the selected StorePlan slug, add_on_data
JSONField storing the list of selected StoreAddOn slugs, billing_cycle_data CharField,
payment_reference CharField (the gateway reference after successful payment), is_complete
BooleanField, expires_at DateTimeField (sessions expire after 48 hours if incomplete),
created_at, updated_at.

### The Registration and Onboarding Views

All views in the onboarding app are function-based views. They are not tenant-specific
views. They run in the public schema (the platform level). They are accessible to anyone
who has not yet created a tenant.

The onboarding journey uses a session token stored in the Django session and in the URL
to track progress. On each step, the view reads the TenantOnboardingSession from the
database, validates that the session has not expired, validates that the current step is
the correct next step for this session (preventing step-skipping), and renders the step.
On valid POST, it updates the session's step field and data fields and redirects to the
next step.

Step One is the account creation step. Its URL is /register/ and its name is
onboarding:register. It renders a registration form with: first_name, last_name, email,
password, confirm_password, phone (optional), business_name, and agreement to platform
terms and privacy policy (required boolean). It also shows the onboarding progress
indicator at step 1 of 5. On GET, if the user is already authenticated and has no
complete TenantOnboardingSession, it pre-fills the form with their profile data and
creates a session token immediately. On POST it validates the form. If the email is
already registered to a platform user, it shows a specific message offering to log in
instead. If the email is new, it creates the User and CustomerProfile atomically (using
the same pattern as the storefront registration view — allauth for email verification
machinery, but a function-based view wrapper). It then creates a TenantOnboardingSession
with a new UUID token, this user's FK, the email, step set to Step2PlanSelection, and
expires_at set to 48 hours from now. It stores the session token in the Django session
as onboarding_session_token. It dispatches a welcome email as a Celery task. It
redirects to step two with the session token as a URL parameter for redundancy.

Step Two is the plan selection step. Its URL is /register/plans/<uuid:token>/ and its
name is onboarding:plans. It validates the TenantOnboardingSession by token and step.
On GET it loads all active StorePlanBundle records ordered by sort_order and all active
StorePlan and StoreAddOn records for the customisation path. It renders a pricing page
showing: a toggle between Monthly and Annual billing (annual typically offers a discount),
a grid of the preset bundle cards each showing the bundle name, a short description,
the monthly and annual price, a features-included list derived from both the base plan
and the bundled add-ons, an is_popular badge if the bundle has that flag, and a Choose
This Plan button. Below the bundle grid is a Customise Your Plan expandable section
that shows the base plans as a simpler comparison table and all available add-ons
grouped by category. This step does not require payment — it is selection only. On POST
it validates that the submitted plan_slug corresponds to an active StorePlan, that all
submitted add_on_slugs correspond to active StoreAddOn records, and that billing_cycle
is Monthly or Annual. It updates the TenantOnboardingSession with the plan_data,
add_on_data, and billing_cycle_data fields, advances the step to Step3AddOnSelection if
the tenant came from the customise path (otherwise skipping to Step4ReviewAndPay since
bundle selection implies add-ons are already determined), and redirects to the next step.

Step Three is the add-on customisation step. Its URL is /register/addons/<uuid:token>/
and its name is onboarding:addons. This step is shown when the tenant chose the
customise path rather than a preset bundle. If they chose a preset bundle, this step is
skipped. On GET it shows all active StoreAddOn records grouped by category. Each add-on
card shows the icon, name, description, price per month, what_it_includes text, and a
toggle switch. Add-ons included in the selected base plan bundle are pre-toggled. On
POST it validates the submitted add-on selection, updates the TenantOnboardingSession,
advances the step to Step4ReviewAndPay, and redirects.

Step Four is the review and pay step. Its URL is /register/checkout/<uuid:token>/ and
its name is onboarding:checkout. This is the payment step. On GET it assembles a
complete order summary: the selected StorePlan name and price, each selected StoreAddOn
name and price, the billing cycle, the total monthly or annual amount, and a clear
breakdown of what is included. It shows a payment form rendered using the payment
service layer's client-side initialisation (Stripe, Paystack, or Flutterwave — whichever
the platform uses for tenant billing). The form accepts card details or whatever payment
methods the gateway supports. It clearly states that this is a recurring monthly or
annual charge. On POST it validates the payment data, calls payment_service.create_subscription()
which creates a gateway-level recurring subscription charged to the submitted payment
method, and handles the gateway's synchronous response. On payment success it records
the gateway_subscription_id and payment_reference in the TenantOnboardingSession,
advances the step to Step5SubdomainSetup, and redirects to step five. On payment
failure it shows the specific payment error message from the gateway (for example
Your card was declined or Insufficient funds) and re-renders the payment form. The
payment form is not cleared on failure so the tenant does not have to re-enter their
details. On payment success a Celery task dispatches a payment confirmation email. This
step enforces idempotency: before processing payment it checks whether the session
already has a payment_reference (meaning the tenant already paid but was redirected
back due to a network error) and if so skips the payment step and redirects directly
to step five.

Step Five is the subdomain setup step. Its URL is /register/subdomain/<uuid:token>/
and its name is onboarding:subdomain. This is the first step that becomes available
only after successful payment. The view validates at the start that the
TenantOnboardingSession has a payment_reference set — if it does not, it redirects back
to step four with a message that payment must be completed first. This validation is
the system's enforcement of the business rule that subdomain access requires payment.
On GET it renders a form with a single subdomain field and a live availability checker.
The subdomain field accepts lowercase alphanumeric characters and hyphens only, between
3 and 50 characters, and must not start or end with a hyphen. Reserved subdomains (www,
api, admin, mail, ftp, and a configurable list from settings) are blocked. On keyup the
form makes an AJAX GET request to a availability check endpoint at /register/check-
subdomain/?subdomain=<value> which queries the django-tenants Tenant model to see
whether the subdomain is taken and returns JSON with available true or false and a
message. On POST the view validates the subdomain field with the same rules, checks
availability one final time in the database, and if clear, does the following inside a
single transaction.atomic() block: it calls the django-tenants Tenant creation function
to create the new schema (using django-tenants' TenantMixin.create_schema=True or
equivalent depending on the project's version), creates the Domain record linking the
subdomain to the new tenant schema, creates the TenantSubscription record linked to the
new tenant with the selected StorePlan and add-ons, creates TenantSubscriptionAddOn
records for each selected add-on, grants free themes to the tenant by creating
TenantThemeAccess records for all Theme records where is_free is true, creates the
initial SiteSettings singleton for the new tenant schema, runs the post-schema-setup
signals or management commands that the project uses to initialise a new tenant's data
(such as creating default categories, creating the default admin user for the tenant,
or whatever post_schema_sync signal handlers are registered), marks the
TenantOnboardingSession as is_complete true, stores the new tenant schema name and
subdomain in the session, and sets the step to Step6Complete. After the transaction
completes, it dispatches a Celery task that sends a detailed welcome email to the tenant
with their new store URL, login instructions, and a getting-started checklist. It
redirects to step six.

Step Six is the completion and welcome step. Its URL is /register/welcome/<uuid:token>/
and its name is onboarding:welcome. It validates the session is complete. It shows the
tenant's new store URL, their admin dashboard URL, their login credentials reminder, and
a checklist of recommended first steps (upload your logo, add your first product,
configure your payment gateway, invite a team member, and so on). Each checklist item
links to the relevant section of their new admin dashboard. It shows a large call-to-
action button labelled Go To Your Dashboard that links to the tenant's admin dashboard
URL. The monitoring system records this as an admin visit.

### Subdomain Availability Endpoint

The subdomain availability check endpoint is a function-based view at
/register/check-subdomain/ named onboarding:check-subdomain. It accepts GET only. It
reads the subdomain query parameter, validates its format (lowercase alphanumeric and
hyphens, 3-50 characters, not starting or ending with a hyphen, not in the reserved
list), queries the django-tenants Domain model for an existing domain matching
subdomain + platform domain suffix (for example .sabistart.com), and returns JSON with
the keys available (boolean), subdomain (the cleaned input), and message (a human-
readable status string such as mystore.sabistart.com is available or This subdomain is
already taken). It is rate-limited at 20 checks per IP per minute to prevent enumeration.

### Returning Tenant Login and Session Resume

A tenant who created an account in step one but did not complete the flow can resume
at any time by logging in. When a platform-level user logs in and is found to have an
incomplete, unexpired TenantOnboardingSession, the login success redirect goes to their
onboarding session's current step rather than the default post-login destination. This
is implemented in the login view by checking for an incomplete TenantOnboardingSession
after successful authentication.

### Plan and Add-On Management for Platform Admin

The platform admin needs views to manage StorePlan, StoreAddOn, and StorePlanBundle
records. These views live in the platform_themes app (since it already exists as a
platform-level app) or in a dedicated platform_billing app — choose whichever makes
more sense given the project structure. They are standard function-based views protected
by platform admin authentication.

The plan list view shows all StorePlan records in a table with sort controls, active
toggle actions, and edit links. The plan create and edit view renders a form for all
StorePlan fields. The add-on list view shows all StoreAddOn records grouped by category.
The add-on create and edit view renders a form for all StoreAddOn fields. The bundle
list view shows all StorePlanBundle records with their computed total prices and edit
links. The bundle create and edit view renders a form that lets the platform admin select
a base StorePlan and then check-toggle each available StoreAddOn to include in the
bundle; the view auto-computes the monthly_total_price, annual_total_price, and
savings_percent from the selected components in real time using a small piece of inline
JavaScript on the form page.

### Subscription Lifecycle Management

After the initial registration, tenants need to be able to manage their subscription from
within their admin dashboard. These views are tenant admin views in a billing section.

The billing overview view shows the tenant their current StorePlan name, their active
add-ons with prices, the billing cycle, the current_period_end date (next billing date),
the monthly or annual total amount, payment method on file (last4 and brand only), and
current status. A Manage Subscription button links to the subscription management view.

The subscription management view shows the current plan details and presents three
primary actions: Upgrade/Downgrade Plan (which leads to a plan selection flow showing
the other available bundles with the current plan highlighted, and allowing the tenant
to switch; downgrades take effect at period end, upgrades take effect immediately with
a prorated charge), Add or Remove Add-ons (which shows all available add-ons with the
currently active ones toggled, allowing toggles and saving with immediate effect and
prorated billing), and Change Billing Cycle (which allows switching between monthly and
annual with the appropriate price adjustment, effective at the next billing period).

The plan upgrade/downgrade view presents the plan selection grid again (same as onboarding
step two but with the current plan highlighted) and handles the change atomically:
updating the TenantSubscription record, calling payment_service.update_subscription()
to update the gateway subscription, dispatching confirmation and change-effective-date
emails as tasks, and redirecting back to the billing overview with a success message.

The add-on management view presents the add-on grid with current selections toggled and
handles additions and removals: updating TenantSubscriptionAddOn records, calling the
payment service to update the gateway subscription amount, dispatching a confirmation
email, and redirecting back to the billing overview.

The billing cycle change view handles the monthly-to-annual or annual-to-monthly switch
with appropriate gateway calls and a confirmation email.

The cancel subscription view validates the request (authenticated, has an active
TenantSubscription), shows a confirmation page explaining that cancellation takes effect
at the end of the current billing period (the store remains active until then), optionally
presents retention offers (such as a discount for staying), and on confirmed POST sets
cancel_at_period_end to true on TenantSubscription, calls
payment_service.cancel_subscription(at_period_end=True), dispatches a cancellation
confirmation email, and creates a cancellation reason record for platform analytics.

The payment history view shows all billing events for the tenant: successful charges,
failed charge attempts, and refunds. These are fetched from the gateway via the payment
service layer and cached for 5 minutes. Each event shows: date, amount, currency,
status, a description (which plan cycle or add-on change it covers), and a link to
download the invoice PDF if available.

The add payment method view handles updating the payment method on file. It uses the
gateway's setup flow (Stripe SetupIntent or equivalent) to securely collect new card
details without the platform ever touching the raw card number. On success it updates
the gateway customer's default payment method and stores only the last4 and brand
locally for display.

---

## PART SEVEN: DEPENDENCY SUMMARY

As you build each view, note missing models at the top of the relevant file using this
format: DEPENDENCY NEEDED: ModelName in app_path/models.py — fields: field descriptions.

Models that are very likely to need to be created as part of this build, because they
are referenced by multiple systems above and may not exist yet in the project, include:
PageVisit, VisitorSession, SearchLog, VisualSearchJob, CartRecoveryToken, UserSession,
NotificationPreference, StoreCreditTransaction, DataExportRequest, DataDeletionRequest,
FAQHelpfulVote, WarrantyClaim, ProductRecall, ProductConfiguration, StorePlan,
StoreAddOn, StorePlanBundle, TenantSubscription, TenantSubscriptionAddOn,
TenantOnboardingSession, Theme, TenantThemeAccess, TenantActiveTheme, ThemeSwitchLog.

Fields likely missing from existing models include: active_theme on SiteSettings,
is_gift_guide on Collection, view_count on FAQ, extra_data on PageVisit, and the
upsells M2M on Product.

The user_agents Python library is useful for device and browser detection. If not
in requirements, note as a dependency and implement a fallback using regex pattern
matching on the user agent string.

The geolocation system requires either a MaxMind GeoIP2 database accessed via
django.contrib.gis.geoip2 or an external API. Note as a dependency and wrap every
geolocation call in a try/except that returns null gracefully on any failure.

---

## PART EIGHT: OUTPUT ORDER AND EXPECTATIONS

Build everything in this order because each phase depends on the previous one being
in place.

First, create the shared public/utils.py with all shared helpers because every other
view depends on these functions.

Second, build the monitoring app completely — the PageVisit and VisitorSession models,
the middleware, the beacon endpoint, the Celery tasks, and the reporting views — because
the beacon script must be integrated into every theme's base template from the start.

Third, build the storefront view layer for all 122 pages across all apps in the public
folder, starting with the home app and working through category, product, search, cart,
checkout, account, promotions, content, store, support, legal, i18n, and b2b in that
order.

Fourth, build the theme architecture — the custom template loader, the themes directory
structure, and all five complete theme template sets (the default theme already existing
plus the four new ones: classic, modern, boutique, bold) — replacing the dummy
templates from step three with production UI for each theme.

Fifth, build the platform_themes app with the Theme, TenantThemeAccess,
TenantActiveTheme, and ThemeSwitchLog models, the platform admin theme management
views, and the tenant-facing theme marketplace and activation views.

Sixth, build the onboarding app with the StorePlan, StoreAddOn, StorePlanBundle,
TenantSubscription, TenantSubscriptionAddOn, and TenantOnboardingSession models, the
six-step registration flow, the subdomain availability endpoint, the session resume
logic, and all tenant subscription lifecycle management views.

Every view is a function-based view. Every write is in transaction.atomic(). Every
slow operation is a Celery task. No class-based views. No stub functions. No placeholder
comments. Every form is fully implemented with complete validation and error handling.
Every template in every theme is a complete production UI covering all 122 storefront
pages. Every monitoring, theme, and subscription view is a complete, working
implementation.

---

End of Prompt
Platform: SabiStart Enterprise Multi-Tenant E-Commerce SaaS
Target: Gemini Large Context Model
Version: 3.0 — Complete Unified Narrative Prompt
Covers: 122-page storefront views · Visitor monitoring · 5 themes (1 existing + 4 new)
        · Theme marketplace · 6-step tenant registration · Store subscription with add-ons
        · Subscription lifecycle management
Architecture: Function-based views throughout · django-tenants · Celery · Redis
