# Platform Payment Gateway Field Guide

This is the field-by-field guide for the shared platform payment domain in `system.system_pay`.

It is written for three jobs:

1. configuring payment gateways in the platform dashboard
2. understanding what each shared model is for
3. knowing what to put in every field, with real examples

This guide covers the shared public-schema models in [models.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\models.py).

## Scope

These models are the platform-side payment control plane.

They power:

- platform gateway registry
- platform credentials
- webhook configuration
- payment settings
- commission rules
- public projection tables for tenant payment visibility

They are surfaced through:

- [views.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\views.py)
- [forms.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\forms.py)
- [services.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\services.py)
- [urls.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\urls.py)

## How To Read This Guide

Each model section includes:

- what the model is for
- how it is used in the platform
- every field
- two or more real-life examples for every field

## Shared Base Models

### `TimestampedModel`

Purpose:

- gives normal mutable records a created and updated timestamp

Fields:

- `created_at`
  Purpose: when the row was first created.
  Example 1: a Paystack gateway definition created on `2026-04-20 10:15`.
  Example 2: a tenant refund projection created during sync on `2026-04-20 18:42`.

- `updated_at`
  Purpose: when the row was last edited.
  Example 1: a Stripe credential updated after rotating the secret key.
  Example 2: a webhook config updated after changing the signature header.

### `AppendOnlyModel`

Purpose:

- base for immutable ledger-like rows
- blocks edits after creation

Fields:

- `created_at`
  Purpose: when the append-only event was recorded.
  Example 1: a future immutable payment event inserted after a webhook callback.
  Example 2: a future audit row inserted when a payout status changes.

## Enums

### `GatewayProvider`

Purpose:

- the canonical provider code list for supported gateways

Examples:

- `paystack` for a Nigeria-focused card and bank-transfer gateway
- `stripe` for a global card and recurring billing gateway
- `manual` for offline bank transfer instructions
- `crypto` for a wallet-based crypto checkout provider

### `PaymentMode`

Purpose:

- describes whether billing uses platform-owned credentials or tenant-owned credentials

Examples:

- `platform` when all tenant marketplace purchases use the platform Paystack account
- `direct` when a tenant processes orders with its own Flutterwave merchant account

### `TransactionStatus`

Purpose:

- normalized status values for projected transaction state

Examples:

- `success` after a hosted checkout is confirmed
- `failed` after a provider declines a charge
- `flagged` when a payment is held for fraud review
- `expired` when a virtual account payment window passes without settlement

## Model Reference

### `PaymentGatewayDefinition`

Purpose:

- this is the top-level registry row for a gateway provider
- it decides whether the platform knows about the provider and what the provider can do

Used by:

- platform gateway pages
- marketplace gateway selection
- onboarding billing gateway selection
- tenant payment-mode review screens

Fields:

- `id`
  Purpose: stable UUID primary key for the registry row.
  Example 1: the UUID for the main Paystack definition.
  Example 2: the UUID for a future Razorpay definition.

- `provider`
  Purpose: machine-readable provider code from `GatewayProvider`.
  Example 1: `paystack`.
  Example 2: `flutterwave`.

- `name`
  Purpose: human-readable gateway name shown in the UI.
  Example 1: `Paystack`.
  Example 2: `Flutterwave Standard Checkout`.

- `description`
  Purpose: short explanation of what the provider is best for.
  Example 1: `Strong for NGN card, transfer, and split-payment flows in West Africa.`
  Example 2: `Best for international card billing and subscriptions across multiple regions.`

- `logo_url`
  Purpose: brand image displayed in platform and tenant UI.
  Example 1: `https://assets.example.com/payments/paystack.svg`.
  Example 2: `https://cdn.company.com/gateways/stripe-mark.png`.

- `website_url`
  Purpose: public homepage for the provider.
  Example 1: `https://paystack.com`.
  Example 2: `https://stripe.com`.

- `documentation_url`
  Purpose: direct link to API docs for engineers or operators.
  Example 1: `https://paystack.com/docs`.
  Example 2: `https://docs.stripe.com/api`.

- `dashboard_url`
  Purpose: provider console URL for operators.
  Example 1: `https://dashboard.paystack.com`.
  Example 2: `https://dashboard.stripe.com`.

- `is_enabled`
  Purpose: whether the provider is active for platform usage.
  Example 1: `True` after the platform is ready to let tenants use Paystack.
  Example 2: `False` while Stripe is still in internal testing.

- `is_available_for_direct_mode`
  Purpose: whether tenants may configure this provider with their own credentials.
  Example 1: `True` for Flutterwave if tenants can bring their own merchant accounts.
  Example 2: `False` for a platform-only acquiring partner that tenants must not use directly.

- `requires_business_verification`
  Purpose: whether tenant direct-mode setup must pass KYB review.
  Example 1: `True` for Paystack direct-mode if settlement requires merchant verification.
  Example 2: `False` for a simple offline manual bank-transfer option.

- `supported_countries`
  Purpose: country codes where the provider is operational.
  Example 1: `["NG", "GH", "KE"]` for an African PSP rollout.
  Example 2: `["US", "GB", "DE", "FR"]` for a global Stripe setup.

- `supported_currencies`
  Purpose: currencies allowed for this provider inside the platform.
  Example 1: `["NGN", "USD"]` for Paystack with domestic and limited cross-border use.
  Example 2: `["USD", "EUR", "GBP"]` for Stripe across western markets.

- `supports_recurring`
  Purpose: whether the provider supports recurring billing patterns.
  Example 1: `True` for Stripe subscriptions.
  Example 2: `False` for manual bank transfer.

- `supports_refunds`
  Purpose: whether the provider supports refund flows.
  Example 1: `True` for Paystack card charges.
  Example 2: `False` for a pure cash-on-delivery flow.

- `supports_partial_refunds`
  Purpose: whether part of a captured payment can be refunded.
  Example 1: `True` for Stripe order adjustments.
  Example 2: `False` for a provider that only supports full reversal.

- `supports_tokenization`
  Purpose: whether cards or payment methods can be stored/tokenized.
  Example 1: `True` for Stripe saved cards.
  Example 2: `False` for manual transfer.

- `supports_3ds`
  Purpose: whether the provider supports 3D Secure authentication.
  Example 1: `True` for a Visa card gateway in Europe.
  Example 2: `False` for offline bank transfer.

- `supports_split_payment`
  Purpose: whether the provider supports native split/subaccount payouts.
  Example 1: `True` for Paystack subaccounts.
  Example 2: `True` for Flutterwave split settlements.

- `supports_virtual_accounts`
  Purpose: whether the provider supports reserved or temporary bank accounts.
  Example 1: `True` for Paystack dedicated virtual accounts.
  Example 2: `False` for Stripe card-only deployment.

- `supports_authorization`
  Purpose: whether the gateway supports auth-now, capture-later flows.
  Example 1: `True` for hotel or rental-style delayed capture.
  Example 2: `False` for instant transfer flows.

- `min_transaction_amount`
  Purpose: minimum payment value allowed by the provider.
  Example 1: `100.00` NGN for a domestic minimum.
  Example 2: `1.00` USD for small digital purchases.

- `max_transaction_amount`
  Purpose: maximum payment value allowed by the provider or platform policy.
  Example 1: `5000000.00` NGN for large business invoices.
  Example 2: `25000.00` USD to reduce exposure during rollout.

- `settlement_days`
  Purpose: expected settlement delay in days.
  Example 1: `1` for next-day settlement.
  Example 2: `7` for a slower payout cycle in a higher-risk region.

- `settlement_note`
  Purpose: human note that explains settlement behavior.
  Example 1: `T+1 for local cards, T+2 for transfer settlements.`
  Example 2: `First payout held for compliance review before recurring weekly release.`

- `credential_schema`
  Purpose: JSON description of the keys/settings required to configure credentials.
  Example 1: `{"required":["public_key","secret_key","webhook_secret"]}`.
  Example 2: `{"required":["secret_key"],"optional":["merchant_id","passphrase"]}`.

- `webhook_events`
  Purpose: list of provider events the platform expects.
  Example 1: `["charge.success", "charge.failed", "transfer.success"]`.
  Example 2: `["payment_intent.succeeded", "charge.refunded", "charge.dispute.created"]`.

- `display_order`
  Purpose: ordering in platform and tenant gateway lists.
  Example 1: `1` for Paystack as the primary provider in Nigeria.
  Example 2: `20` for a backup provider shown lower in the list.

- `badge_label`
  Purpose: optional UI badge for marketing or operational highlighting.
  Example 1: `Recommended`.
  Example 2: `Beta`.

### `PlatformGatewayCredential`

Purpose:

- stores the platform-owned API credentials used in platform mode
- one gateway can have many credentials for test/live, multiple business accounts, or rotation

Fields:

- `id`
  Purpose: UUID primary key for the credential row.
  Example 1: a live Paystack key pair row.
  Example 2: a test Stripe key pair row.

- `gateway`
  Purpose: links the credential to a `PaymentGatewayDefinition`.
  Example 1: a credential attached to the Paystack definition.
  Example 2: a credential attached to the Stripe definition.

- `name`
  Purpose: operator-facing label for the credential.
  Example 1: `Paystack Live Main Account`.
  Example 2: `Stripe Test Sandbox - EU`.

- `environment`
  Purpose: whether the credential is test or live.
  Example 1: `test` during QA and onboarding rehearsal.
  Example 2: `live` after production cutover.

- `is_active`
  Purpose: whether this credential may be used by the platform.
  Example 1: `True` for the current production key.
  Example 2: `False` for a retired key kept only for audit reference.

- `priority`
  Purpose: selection order when more than one credential is active.
  Example 1: `100` for the main live account.
  Example 2: `10` for a fallback account used only when primary is disabled.

- `public_key`
  Purpose: client-side or publishable key when the provider uses one.
  Example 1: Stripe publishable key starting with `pk_live_`.
  Example 2: Paystack public key used for hosted widget initialization.

- `secret_key`
  Purpose: server-side secret used for protected API actions.
  Example 1: Paystack secret key used for charge verification.
  Example 2: Stripe secret key used for payment intent creation.

- `encryption_key`
  Purpose: extra cryptographic secret required by some providers.
  Example 1: Flutterwave encryption key for secure payload encryption.
  Example 2: blank value for providers that do not require a second crypto key.

- `webhook_secret`
  Purpose: secret used to validate signed webhook payloads.
  Example 1: Stripe webhook signing secret like `whsec_...`.
  Example 2: a Paystack HMAC verification secret stored for webhook checking.

- `extra_credentials`
  Purpose: JSON bucket for provider-specific settings not covered by top-level fields.
  Example 1: `{"merchant_id":"M12345","terminal_id":"TERM-01"}`.
  Example 2: `{"location_id":"LOC_ABC","account_region":"eu-west-1"}`.

- `account_id`
  Purpose: provider-side account identifier for the platform merchant.
  Example 1: Stripe connected account ID for the platform business.
  Example 2: Paystack business account reference from the PSP dashboard.

- `subaccount_code`
  Purpose: provider-side subaccount or master split code for platform commissions.
  Example 1: Paystack subaccount code used to receive a marketplace commission.
  Example 2: Flutterwave split configuration key for platform fee routing.

- `daily_transaction_limit`
  Purpose: optional per-day usage ceiling for operational risk control.
  Example 1: `500` transactions/day during provider rollout.
  Example 2: `5000` transactions/day after scaling up.

- `monthly_volume_limit`
  Purpose: optional monthly money-volume ceiling for the credential.
  Example 1: `10000000.00` NGN during pilot stage.
  Example 2: `250000.00` USD for a new international account.

- `supported_countries`
  Purpose: narrower country list for this specific credential.
  Example 1: `["NG"]` for a Nigeria-only merchant account.
  Example 2: `["US", "CA"]` for a North America-only Stripe account.

- `default_currency`
  Purpose: default currency this credential expects or prefers.
  Example 1: `NGN` for a local acquiring account.
  Example 2: `USD` for a global card processor account.

- `last_used_at`
  Purpose: last time this credential was used in a payment operation.
  Example 1: updated after an onboarding payment session.
  Example 2: updated after a feature marketplace hosted checkout initialization.

- `last_health_check_at`
  Purpose: timestamp of the last credential health validation.
  Example 1: after a nightly credential verification task.
  Example 2: after a staff-triggered health check during gateway troubleshooting.

- `is_healthy`
  Purpose: whether the credential is currently safe to expose for checkout.
  Example 1: `True` when verification succeeds and the provider account is normal.
  Example 2: `False` after revoked keys or failed API auth.

- `health_note`
  Purpose: operator-readable health explanation.
  Example 1: `Health check passed against live verification endpoint.`
  Example 2: `Provider returned unauthorized; rotate secret key.`

### `GatewayWebhookConfig`

Purpose:

- configures the inbound webhook endpoint behavior for one provider

Fields:

- `id`
  Purpose: UUID primary key for the webhook config.
  Example 1: the config row for Paystack webhooks.
  Example 2: the config row for Stripe webhooks.

- `gateway`
  Purpose: one-to-one link to the provider definition.
  Example 1: webhook config for the Paystack definition.
  Example 2: webhook config for the Stripe definition.

- `webhook_url`
  Purpose: full public endpoint the provider should call.
  Example 1: `https://platform.example.com/platform/payments/webhooks/marketplace/paystack/`.
  Example 2: `https://app.sabistart.com/platform/payments/webhooks/marketplace/stripe/`.

- `signature_header`
  Purpose: HTTP header that carries the webhook signature.
  Example 1: `x-paystack-signature`.
  Example 2: `Stripe-Signature`.

- `signature_algorithm`
  Purpose: algorithm used to verify incoming signatures.
  Example 1: `hmac_sha256` for Stripe-style signatures.
  Example 2: `hmac_sha512` for a provider that signs with SHA-512.

- `ip_whitelist`
  Purpose: optional list of trusted source IPs.
  Example 1: `["52.31.139.75","52.49.173.169"]` for provider webhook IPs.
  Example 2: `[]` when signature validation is the only enforcement.

- `is_active`
  Purpose: whether the platform should treat this webhook route as active.
  Example 1: `True` in production after provider setup.
  Example 2: `False` while rotating webhook settings.

- `last_received_at`
  Purpose: timestamp of the most recent received webhook.
  Example 1: the moment a successful charge event arrives.
  Example 2: the moment a dispute event is posted by the provider.

- `total_events_received`
  Purpose: running counter of webhook volume.
  Example 1: `1200` after a month of charge events.
  Example 2: `5` in a fresh sandbox environment.

### `PlatformPaymentSetting`

Purpose:

- singleton-style global payment behavior for the whole platform

Fields:

- `name`
  Purpose: singleton label, usually `default`.
  Example 1: `default` for the primary live config.
  Example 2: `staging` if you temporarily keep a separate staging-only setting row.

- `default_currency`
  Purpose: platform default billing currency.
  Example 1: `NGN` for a Nigeria-first deployment.
  Example 2: `USD` for a global SaaS launch.

- `supported_currencies`
  Purpose: list of currencies allowed by platform policy.
  Example 1: `["NGN","USD"]`.
  Example 2: `["USD","EUR","GBP"]`.

- `allow_multi_currency`
  Purpose: whether the platform may offer multiple currencies at once.
  Example 1: `True` when tenants can bill in NGN and USD.
  Example 2: `False` when the platform temporarily standardizes on one currency.

- `automatic_payout_review`
  Purpose: whether payout requests enter a review path by default.
  Example 1: `True` for tighter manual finance control.
  Example 2: `False` when a mature platform auto-clears low-risk payouts.

- `default_payout_schedule`
  Purpose: default payout rhythm.
  Example 1: `manual` for new tenants needing finance approval.
  Example 2: `weekly` for stable merchants on a routine release cycle.

- `default_payout_hold_days`
  Purpose: number of days funds are held before payout.
  Example 1: `1` for next-day release after successful settlement.
  Example 2: `7` for fraud-buffer holding on new stores.

- `default_minimum_payout_amount`
  Purpose: smallest payout the platform allows.
  Example 1: `1000.00` NGN to avoid too many tiny transfers.
  Example 2: `50.00` USD for international payout efficiency.

- `default_gateway_timeout_minutes`
  Purpose: timeout window for payment session or provider response policy.
  Example 1: `30` minutes for a checkout reference to remain actionable.
  Example 2: `5` minutes for a stricter fast-fail card-init flow.

- `enable_direct_mode_reviews`
  Purpose: whether tenant direct-mode gateways require platform review.
  Example 1: `True` so staff approve each tenant’s own gateway setup.
  Example 2: `False` if direct-mode is self-service in a future product tier.

- `enable_platform_refund_tools`
  Purpose: whether platform staff can use refund operations from the console.
  Example 1: `True` when support teams handle refund escalations.
  Example 2: `False` when all refunds must stay tenant-side.

- `enable_platform_dispute_tools`
  Purpose: whether platform staff can manage dispute-related actions.
  Example 1: `True` when a central risk team helps tenants with chargebacks.
  Example 2: `False` when disputes are handled only in tenant operations.

- `metadata`
  Purpose: freeform JSON for future platform-level payment settings.
  Example 1: `{"risk_threshold":"medium","default_region":"west-africa"}`.
  Example 2: `{"provider_rollout":{"stripe":true,"paypal":false}}`.

### `PlatformCommissionRule`

Purpose:

- stores the platform’s fee policy for gateway processing

Fields:

- `id`
  Purpose: UUID primary key.
  Example 1: the default NGN commission rule.
  Example 2: a premium-plan USD commission rule.

- `name`
  Purpose: human-readable name for staff.
  Example 1: `Default NGN Marketplace Fee`.
  Example 2: `Growth Plan USD Reduced Fee`.

- `gateway`
  Purpose: optional gateway-specific scope.
  Example 1: tied to Paystack only.
  Example 2: blank to apply to all gateways.

- `subscription_plan`
  Purpose: optional plan code or segment this rule applies to.
  Example 1: `starter`.
  Example 2: `growth`.

- `country_code`
  Purpose: optional country-specific scope.
  Example 1: `NG` for Nigeria-specific fee rules.
  Example 2: `US` for United States merchants.

- `currency`
  Purpose: optional currency-specific scope.
  Example 1: `NGN`.
  Example 2: `USD`.

- `percentage_rate`
  Purpose: percentage fee charged by the platform.
  Example 1: `2.5000` meaning 2.5%.
  Example 2: `1.2500` for a discounted enterprise rate.

- `flat_fee`
  Purpose: flat amount added to every processed payment.
  Example 1: `100.00` NGN per payout-eligible order.
  Example 2: `0.30` USD per transaction.

- `cap_amount`
  Purpose: maximum fee allowed after calculations.
  Example 1: `2000.00` NGN to cap large-order fees.
  Example 2: blank when there is no cap.

- `minimum_fee`
  Purpose: smallest fee that can be charged.
  Example 1: `50.00` NGN for low-value transactions.
  Example 2: `0.50` USD for micro-transactions.

- `priority`
  Purpose: rule ordering, with higher-priority rules applied first in practice.
  Example 1: `100` for a VIP-plan override.
  Example 2: `0` for the generic fallback rule.

- `is_active`
  Purpose: whether the rule is currently in force.
  Example 1: `True` for the current live commission policy.
  Example 2: `False` for a retired promo fee structure.

- `notes`
  Purpose: operational explanation of why the rule exists.
  Example 1: `Reduced rate negotiated for enterprise merchants above 50M NGN monthly GMV.`
  Example 2: `Temporary promo fee for Q4 onboarding campaign.`

### `TenantPaymentSnapshot`

Purpose:

- public read model summarizing one tenant’s payment state
- used for fast platform visibility without querying every tenant schema on each page load

Fields:

- `id`
  Purpose: UUID primary key.
  Example 1: snapshot row for `shop_akure`.
  Example 2: snapshot row for `demo-fashion`.

- `shop`
  Purpose: foreign key to the tenant `Shop`.
  Example 1: links to the `Joshua Fashion` shop row.
  Example 2: links to the `Electro Hub` shop row.

- `schema_name`
  Purpose: tenant schema identifier.
  Example 1: `joshuafashion`.
  Example 2: `electrohub`.

- `business_name`
  Purpose: display name pulled from the tenant payment profile.
  Example 1: `Joshua Fashion Store`.
  Example 2: `Electro Hub Lagos`.

- `account_status`
  Purpose: normalized payment account state.
  Example 1: `active`.
  Example 2: `restricted`.

- `kyb_status`
  Purpose: KYB verification state.
  Example 1: `verified`.
  Example 2: `under_review`.

- `payout_enabled`
  Purpose: whether the tenant may currently receive payouts.
  Example 1: `True` for a verified merchant.
  Example 2: `False` for a merchant still under compliance review.

- `default_currency`
  Purpose: tenant’s primary payment currency.
  Example 1: `NGN`.
  Example 2: `USD`.

- `available_balance`
  Purpose: amount ready to withdraw or settle.
  Example 1: `125000.00` NGN ready for payout.
  Example 2: `820.50` USD ready after reserve release.

- `pending_balance`
  Purpose: amount not yet matured for payout.
  Example 1: `42000.00` NGN from fresh settlements.
  Example 2: `150.00` USD from newly captured orders.

- `reserved_balance`
  Purpose: funds held for risk, refunds, or disputes.
  Example 1: `10000.00` NGN held for potential chargeback exposure.
  Example 2: `250.00` USD held because of an active dispute.

- `total_transaction_count`
  Purpose: total transaction count in the projection.
  Example 1: `340`.
  Example 2: `12`.

- `total_transaction_volume`
  Purpose: total money volume for indexed transactions.
  Example 1: `5600000.00` NGN.
  Example 2: `18000.00` USD.

- `gateway_count`
  Purpose: number of configured gateways for the tenant.
  Example 1: `2` for Paystack and manual transfer.
  Example 2: `1` for Stripe only.

- `active_gateway_count`
  Purpose: number of active configured gateways.
  Example 1: `1` when only Paystack is active and bank transfer is disabled.
  Example 2: `2` when both card and manual transfer are live.

- `direct_gateway_count`
  Purpose: number of tenant-owned direct-mode gateways.
  Example 1: `1` when the merchant uses its own Flutterwave account.
  Example 2: `0` when everything goes through platform mode.

- `platform_gateway_count`
  Purpose: number of platform-mode gateways.
  Example 1: `1` when tenant uses platform Paystack.
  Example 2: `2` when platform Stripe and manual transfer are available.

- `last_transaction_at`
  Purpose: timestamp of most recent transaction activity.
  Example 1: latest checkout completed at `2026-04-20 15:20`.
  Example 2: blank for a brand-new tenant with no payment history.

- `health_status`
  Purpose: roll-up health signal for the tenant payment setup.
  Example 1: `healthy`.
  Example 2: `warning`.

- `notes`
  Purpose: optional operator notes or sync notes.
  Example 1: `Merchant awaiting KYB document resubmission.`
  Example 2: `Snapshot created before tenant payment profile existed.`

- `last_synced_at`
  Purpose: timestamp of the last projection refresh.
  Example 1: set by `sync_payment_projections`.
  Example 2: set after a targeted tenant snapshot refresh from the platform detail page.

### `TenantGatewaySnapshot`

Purpose:

- public read model for one tenant/provider combination

Fields:

- `id`
  Purpose: UUID primary key.
  Example 1: Paystack snapshot for `joshuafashion`.
  Example 2: Flutterwave snapshot for `demoelectronics`.

- `shop`
  Purpose: owning tenant shop.
  Example 1: `Joshua Fashion Store`.
  Example 2: `Demo Electronics`.

- `schema_name`
  Purpose: tenant schema name.
  Example 1: `joshuafashion`.
  Example 2: `demoelectronics`.

- `gateway`
  Purpose: optional link to the shared gateway definition.
  Example 1: linked to the Paystack registry row.
  Example 2: blank if the historical provider record was removed but snapshot kept.

- `gateway_provider`
  Purpose: provider code for filtering and reporting.
  Example 1: `paystack`.
  Example 2: `manual`.

- `gateway_name`
  Purpose: display name shown to platform staff.
  Example 1: `Paystack`.
  Example 2: `Manual Bank Transfer`.

- `mode`
  Purpose: platform or direct mode.
  Example 1: `platform` for shared platform credentials.
  Example 2: `direct` for tenant-owned credentials.

- `status`
  Purpose: operational status of this tenant gateway setup.
  Example 1: `active`.
  Example 2: `suspended`.

- `currency`
  Purpose: primary currency for this tenant gateway snapshot.
  Example 1: `NGN`.
  Example 2: `USD`.

- `is_default`
  Purpose: whether this is the default checkout gateway for the tenant.
  Example 1: `True` for the main Paystack checkout route.
  Example 2: `False` for a backup manual bank-transfer option.

- `is_healthy`
  Purpose: quick health signal for the tenant gateway setup.
  Example 1: `True` when active and behaving normally.
  Example 2: `False` when suspended or missing a valid credential.

- `transaction_count`
  Purpose: transactions processed through this provider for the tenant.
  Example 1: `220` Paystack transactions.
  Example 2: `17` manual transfer confirmations.

- `transaction_volume`
  Purpose: money volume processed through this provider for the tenant.
  Example 1: `3400000.00` NGN.
  Example 2: `950.00` USD.

- `last_transaction_at`
  Purpose: most recent transaction timestamp for this provider.
  Example 1: the last successful Paystack checkout.
  Example 2: blank for a newly configured gateway with no live use yet.

- `notes`
  Purpose: review notes or health notes.
  Example 1: `Approved for direct mode after KYB review.`
  Example 2: `Suspended after repeated webhook verification failures.`

- `last_synced_at`
  Purpose: last time this snapshot row was rebuilt.
  Example 1: nightly projection sync.
  Example 2: manual refresh after gateway approval.

### `PlatformTransactionIndex`

Purpose:

- public projection row for fast transaction search/filtering

Fields:

- `id`
  Purpose: UUID primary key of the projection row.
  Example 1: row for a successful marketplace checkout.
  Example 2: row for a flagged tenant storefront order payment.

- `shop`
  Purpose: related tenant shop.
  Example 1: `Joshua Fashion Store`.
  Example 2: `Electro Hub`.

- `schema_name`
  Purpose: tenant schema for fast filtering.
  Example 1: `joshuafashion`.
  Example 2: `electrohub`.

- `transaction_id`
  Purpose: original tenant transaction UUID.
  Example 1: UUID from a successful payment intent conversion.
  Example 2: UUID from a failed direct-mode transaction.

- `internal_reference`
  Purpose: platform or tenant-generated internal reference.
  Example 1: `TXN-20260420-0012`.
  Example 2: `feat_akd92k_checkout`.

- `order_id`
  Purpose: related order UUID if there is an order.
  Example 1: linked storefront order UUID.
  Example 2: blank for a pure feature-purchase flow without storefront order linkage.

- `order_number`
  Purpose: human-readable order number.
  Example 1: `ORD-10458`.
  Example 2: blank for a non-order marketplace transaction.

- `gateway_transaction_id`
  Purpose: provider-side transaction ID.
  Example 1: a Stripe payment intent ID.
  Example 2: a Paystack transaction integer/string reference.

- `gateway_reference`
  Purpose: provider reference exposed during verification.
  Example 1: `psk_live_9d1...`.
  Example 2: `pi_3Q...`.

- `amount`
  Purpose: charged amount.
  Example 1: `25000.00` NGN.
  Example 2: `49.99` USD.

- `currency`
  Purpose: transaction currency.
  Example 1: `NGN`.
  Example 2: `USD`.

- `status`
  Purpose: normalized transaction status.
  Example 1: `success`.
  Example 2: `failed`.

- `payment_mode`
  Purpose: whether the transaction used platform or direct mode.
  Example 1: `platform`.
  Example 2: `direct`.

- `gateway_provider`
  Purpose: provider used for the transaction.
  Example 1: `paystack`.
  Example 2: `stripe`.

- `customer_email`
  Purpose: customer email for search and support.
  Example 1: `buyer@example.com`.
  Example 2: `procurement@company.com`.

- `customer_name`
  Purpose: customer display name.
  Example 1: `Ada Okafor`.
  Example 2: `Brighton Retail Ltd`.

- `payment_method_type`
  Purpose: payment method channel used.
  Example 1: `card`.
  Example 2: `bank_transfer`.

- `paid_at`
  Purpose: actual payment completion timestamp.
  Example 1: when the PSP confirms success.
  Example 2: blank if the transaction never completed.

- `created_at_source`
  Purpose: original tenant-transaction creation time.
  Example 1: checkout session started at `2026-04-20 09:01`.
  Example 2: refundable order payment created at `2026-04-19 14:42`.

- `is_flagged`
  Purpose: fraud or manual review marker.
  Example 1: `True` for an unusually large card payment.
  Example 2: `False` for a normal small order.

- `metadata`
  Purpose: extra source details from the tenant transaction snapshot.
  Example 1: `{"channel":"storefront","risk_score":"high"}`.
  Example 2: `{"channel":"marketplace","feature_code":"max_products"}`.

- `last_synced_at`
  Purpose: last projection refresh time.
  Example 1: full projection rebuild timestamp.
  Example 2: targeted resync after a webhook correction.

### `PlatformPayoutIndex`

Purpose:

- public projection of tenant payout requests for platform review

Fields:

- `id`
  Purpose: UUID primary key.
  Example 1: a pending NGN payout request.
  Example 2: a completed USD payout request.

- `shop`
  Purpose: related tenant shop.
  Example 1: `Joshua Fashion Store`.
  Example 2: `Electro Hub`.

- `schema_name`
  Purpose: tenant schema.
  Example 1: `joshuafashion`.
  Example 2: `electrohub`.

- `payout_request_id`
  Purpose: original tenant payout request UUID.
  Example 1: the payout row created after a withdrawal request.
  Example 2: the payout row created during scheduled settlement batching.

- `payout_reference`
  Purpose: human-readable or internal payout reference.
  Example 1: `PO-2026-0419-001`.
  Example 2: `WDRAW-7C10`.

- `amount`
  Purpose: payout amount.
  Example 1: `150000.00` NGN.
  Example 2: `1200.00` USD.

- `currency`
  Purpose: payout currency.
  Example 1: `NGN`.
  Example 2: `USD`.

- `status`
  Purpose: payout lifecycle status.
  Example 1: `pending_approval`.
  Example 2: `completed`.

- `bank_name`
  Purpose: receiving bank name.
  Example 1: `Guaranty Trust Bank`.
  Example 2: `Chase Bank`.

- `bank_account_masked`
  Purpose: safe masked account number.
  Example 1: `******1234`.
  Example 2: `****6789`.

- `gateway_provider`
  Purpose: provider or transfer rail used.
  Example 1: `paystack`.
  Example 2: `manual`.

- `gateway_transfer_reference`
  Purpose: provider-side transfer reference.
  Example 1: transfer code from Paystack transfers.
  Example 2: bank transfer batch ID from a payout processor.

- `requested_at`
  Purpose: when the payout was requested.
  Example 1: merchant clicked withdraw at `2026-04-20 12:30`.
  Example 2: scheduled weekly payout generated automatically at midnight.

- `approved_at`
  Purpose: when platform finance approved the payout.
  Example 1: manual approval by finance staff.
  Example 2: blank if still waiting review.

- `completed_at`
  Purpose: when the payout was completed.
  Example 1: provider confirms transfer success.
  Example 2: blank while transfer is still processing.

- `metadata`
  Purpose: extra payout context.
  Example 1: `{"request_type":"manual_withdrawal"}`.
  Example 2: `{"request_type":"scheduled_settlement","batch":"APR-W4"}`.

- `last_synced_at`
  Purpose: last projection update time.
  Example 1: nightly sync timestamp.
  Example 2: manual resync after payout approval.

### `PlatformRefundIndex`

Purpose:

- public projection of refunds for platform review and search

Fields:

- `id`
  Purpose: UUID primary key.
  Example 1: row for a customer return refund.
  Example 2: row for a failed-order goodwill refund.

- `shop`
  Purpose: related tenant shop.
  Example 1: `Joshua Fashion Store`.
  Example 2: `Electro Hub`.

- `schema_name`
  Purpose: tenant schema.
  Example 1: `joshuafashion`.
  Example 2: `electrohub`.

- `refund_id`
  Purpose: original tenant refund UUID.
  Example 1: refund object from tenant payment records.
  Example 2: partial refund object created after order adjustment.

- `refund_reference`
  Purpose: human or system refund reference.
  Example 1: `RFD-2026-0041`.
  Example 2: `refund_9832fd`.

- `transaction_reference`
  Purpose: source payment reference being refunded.
  Example 1: `TXN-20260418-0091`.
  Example 2: `feat_sub_renewal_002`.

- `order_number`
  Purpose: related order number when applicable.
  Example 1: `ORD-10458`.
  Example 2: blank for a non-order digital charge.

- `amount`
  Purpose: refund amount.
  Example 1: `5000.00` NGN partial refund.
  Example 2: `49.99` USD full refund.

- `currency`
  Purpose: refund currency.
  Example 1: `NGN`.
  Example 2: `USD`.

- `status`
  Purpose: refund state.
  Example 1: `processing`.
  Example 2: `completed`.

- `reason`
  Purpose: refund reason label.
  Example 1: `customer_request`.
  Example 2: `item_unavailable`.

- `requested_at`
  Purpose: when the refund was initiated.
  Example 1: customer service created the refund at noon.
  Example 2: automatic refund started after stock validation failure.

- `completed_at`
  Purpose: when the refund finished.
  Example 1: provider confirms settlement reversal.
  Example 2: blank while waiting PSP completion.

- `metadata`
  Purpose: extra provider or operational details.
  Example 1: `{"gateway_refund_id":"RF_12345"}`.
  Example 2: `{"initiated_by":"support_team","partial":true}`.

- `last_synced_at`
  Purpose: last time the projection row was refreshed.
  Example 1: nightly sync.
  Example 2: manual sync after provider callback arrives late.

### `PlatformDisputeIndex`

Purpose:

- public projection of chargebacks and disputes for platform monitoring

Fields:

- `id`
  Purpose: UUID primary key.
  Example 1: row for a cardholder fraud claim.
  Example 2: row for a product-not-received dispute.

- `shop`
  Purpose: related tenant shop.
  Example 1: `Joshua Fashion Store`.
  Example 2: `Electro Hub`.

- `schema_name`
  Purpose: tenant schema.
  Example 1: `joshuafashion`.
  Example 2: `electrohub`.

- `dispute_id`
  Purpose: original tenant dispute UUID.
  Example 1: tenant dispute row from the payment app.
  Example 2: chargeback object projected after webhook sync.

- `dispute_reference`
  Purpose: internal or provider dispute reference.
  Example 1: `DSP-2026-0003`.
  Example 2: provider case code like `cb_93822`.

- `transaction_reference`
  Purpose: reference of the challenged transaction.
  Example 1: `TXN-20260414-0030`.
  Example 2: `ORDPAY-5092`.

- `amount`
  Purpose: amount under dispute.
  Example 1: `25000.00` NGN.
  Example 2: `120.00` USD.

- `currency`
  Purpose: dispute currency.
  Example 1: `NGN`.
  Example 2: `USD`.

- `status`
  Purpose: current dispute status.
  Example 1: `needs_evidence`.
  Example 2: `won`.

- `reason`
  Purpose: dispute reason label.
  Example 1: `fraud`.
  Example 2: `product_not_received`.

- `opened_at`
  Purpose: when the dispute opened.
  Example 1: the timestamp from the gateway dispute webhook.
  Example 2: the timestamp finance created a manual imported dispute row.

- `evidence_deadline`
  Purpose: last date to submit evidence.
  Example 1: `2026-04-27 23:59`.
  Example 2: blank if provider has not supplied a deadline yet.

- `resolved_at`
  Purpose: when the dispute was finally resolved.
  Example 1: the date the provider marks the merchant as winner.
  Example 2: blank while the dispute is still active.

- `metadata`
  Purpose: dispute-specific extra details.
  Example 1: `{"gateway_dispute_id":"dp_8821","card_last4":"4242"}`.
  Example 2: `{"evidence_submitted":true,"case_owner":"risk_team"}`.

- `last_synced_at`
  Purpose: last projection update timestamp.
  Example 1: updated after every dispute sync run.
  Example 2: updated after a manual platform refresh for one tenant.

## Real Setup Sequence For A New Gateway

If you want to add a provider in the platform system, work through these records in order:

1. create `PaymentGatewayDefinition`
2. create one or more `PlatformGatewayCredential`
3. create `GatewayWebhookConfig`
4. verify `PlatformPaymentSetting` supports the currencies and payout behavior you want
5. create or adjust `PlatformCommissionRule` if the new gateway changes fee structure
6. run [sync_payment_projections.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\management\commands\sync_payment_projections.py) after live activity starts

## Quick Configuration Examples

### Example A: Paystack for Nigeria marketplace billing

- `PaymentGatewayDefinition.provider = "paystack"`
- `PaymentGatewayDefinition.supported_countries = ["NG"]`
- `PaymentGatewayDefinition.supported_currencies = ["NGN"]`
- `PaymentGatewayDefinition.supports_split_payment = True`
- `PlatformGatewayCredential.environment = "live"`
- `PlatformGatewayCredential.default_currency = "NGN"`
- `GatewayWebhookConfig.signature_header = "x-paystack-signature"`
- `PlatformPaymentSetting.default_currency = "NGN"`

### Example B: Stripe for international feature billing

- `PaymentGatewayDefinition.provider = "stripe"`
- `PaymentGatewayDefinition.supported_countries = ["US","GB","DE"]`
- `PaymentGatewayDefinition.supported_currencies = ["USD","EUR","GBP"]`
- `PaymentGatewayDefinition.supports_recurring = True`
- `PlatformGatewayCredential.environment = "test"` during rollout, then `live`
- `PlatformGatewayCredential.webhook_secret = "whsec_..."`
- `GatewayWebhookConfig.signature_header = "Stripe-Signature"`
- `PlatformCommissionRule.currency = "USD"`

## Operational Checks

Run these when setting up or changing a gateway:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py sync_payment_projections
```

Then verify:

- `/platform/payments/gateways/`
- `/platform/payments/gateways/<gateway_id>/`
- `/platform/payments/settings/`
- `/platform/payments/tenants/`
- `/platform/payments/transactions/`

## Code References

- Shared models: [models.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\models.py)
- Shared forms: [forms.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\forms.py)
- Platform pages: [views.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\views.py)
- Projection sync and actions: [services.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\services.py)
- Utility helpers: [utils.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\utils.py)
- URL map: [urls.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\urls.py)
- Sync command: [sync_payment_projections.py](C:\Users\user\Desktop\build\backend\sabistart-store\system\system_pay\management\commands\sync_payment_projections.py)




i need you to work on a few this
1. on the platform, i don`t like the form color, it totally looks terrible, but input and labels look very bad
2. on the payment management page, all the forms are in one place, i need thhis done properly, the each should be in there one page and have a can be edited, and also it should be inherit so i don`t try to manage a paystack payemnt and have to start add paystack as name again and all thos stuff i that should be got from the patrent
3. on the tenent dashbaord, on the pages on  Store Operations sidebar group, if i open some of the page, it looks different with its own nav and no sidebar, it does ing=herit the dashboard look, also fix that
4. on the add on, the form input there look very bad AND IF I CLICK ON CONTINUE TO CHECKOUT It does to add error page
[20/Apr/2026 10:26:33] "GET /dashboard/admin/marketplace/features/max_pos_locations/ HTTP/1.1" 200 47210
preview_purchase() got an unexpected keyword argument 'gateway_provider' +++++
Not Found: /dashboard/admin/marketplace/checkout/
[20/Apr/2026 10:26:39] "GET /dashboard/admin/marketplace/checkout/?currency=NGN&billing_cycle=monthly&quantity=1&coupon_code=&gateway_provider=&feature_code=max_pos_locations&bundle_slug= HTTP/1.1" 404 28133
[20/Apr/2026 10:26:39] "POST /__monitoring/beacon/ HTTP/1.1" 200 81
preview_purchase() got an unexpected keyword argument 'gateway_provider' +++++
Not Found: /dashboard/admin/marketplace/checkout/
[20/Apr/2026 10:50:16] "GET /dashboard/admin/marketplace/checkout/?currency=NGN&billing_cycle=monthly&quantity=1&coupon_code=&gateway_provider=&feature_code=max_pos_locations&bundle_slug= HTTP/1.1" 404 28133
[20/Apr/2026 10:50:17] "POST /__monitoring/beacon/ HTTP/1.1" 200 81

fix that as well
