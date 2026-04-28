from django.urls import path

from dashboard.payments_tenant.views.balance import (
    balance_list,
    balance_transaction_list,
    commission_entry_list,
    saved_payment_method_list,
)
from dashboard.payments_tenant.views.fraud import (
    blocklist_create,
    blocklist_delete,
    blocklist_list,
    fraud_assessment_list,
    fraud_rule_create,
    fraud_rule_delete,
    fraud_rule_edit,
    fraud_rule_list,
)
from dashboard.payments_tenant.views.payouts import (
    bank_account_create,
    bank_account_delete,
    bank_account_list,
    payout_request_cancel,
    payout_request_create,
    payout_request_detail,
    payout_request_list,
)
from dashboard.payments_tenant.views.profile import (
    analytics_view,
    credential_create,
    credential_edit,
    credential_list,
    gateway_mode_detail,
    gateway_mode_list,
    gateway_mode_set_default,
    gateway_mode_switch,
    profile_edit,
    supported_currency_create,
    supported_currency_delete,
    supported_currency_edit,
    supported_currency_list,
    tenant_home,
)
from dashboard.payments_tenant.views.reconciliation import (
    tenant_reconciliation_detail,
    tenant_reconciliation_list,
)
from dashboard.payments_tenant.views.refunds_disputes import (
    dispute_detail,
    dispute_evidence_create,
    dispute_list,
    refund_create,
    refund_detail,
    refund_list,
)
from dashboard.payments_tenant.views.transactions import (
    payment_intent_list,
    transaction_detail,
    transaction_flag,
    transaction_list,
)

app_name = "payments_tenant"

urlpatterns = [
    path("", tenant_home, name="tenant_home"),
    path("analytics/", analytics_view, name="analytics"),
    path("settings/", profile_edit, name="profile_edit"),

    path("gateways/", gateway_mode_list, name="gateway_mode_list"),
    path("gateways/<uuid:pk>/", gateway_mode_detail, name="gateway_mode_detail"),
    path("gateways/<uuid:pk>/switch/", gateway_mode_switch, name="gateway_mode_switch"),
    path("gateways/<uuid:pk>/set-default/", gateway_mode_set_default, name="gateway_mode_set_default"),
    path("gateways/<uuid:gateway_pk>/credentials/", credential_list, name="credential_list"),
    path("gateways/<uuid:gateway_pk>/credentials/add/", credential_create, name="credential_create"),
    path("gateways/<uuid:gateway_pk>/credentials/<uuid:pk>/edit/", credential_edit, name="credential_edit"),

    path("currencies/", supported_currency_list, name="supported_currency_list"),
    path("currencies/add/", supported_currency_create, name="supported_currency_create"),
    path("currencies/<uuid:pk>/edit/", supported_currency_edit, name="supported_currency_edit"),
    path("currencies/<uuid:pk>/delete/", supported_currency_delete, name="supported_currency_delete"),

    path("payment-intents/", payment_intent_list, name="payment_intent_list"),
    path("transactions/", transaction_list, name="transaction_list"),
    path("transactions/<uuid:pk>/", transaction_detail, name="transaction_detail"),
    path("transactions/<uuid:pk>/flag/", transaction_flag, name="transaction_flag"),

    path("refunds/", refund_list, name="refund_list"),
    path("refunds/<uuid:pk>/", refund_detail, name="refund_detail"),
    path("transactions/<uuid:transaction_pk>/refund/", refund_create, name="refund_create"),

    path("disputes/", dispute_list, name="dispute_list"),
    path("disputes/<uuid:pk>/", dispute_detail, name="dispute_detail"),
    path("disputes/<uuid:dispute_pk>/evidence/add/", dispute_evidence_create, name="dispute_evidence_create"),

    path("balance/", balance_list, name="balance_list"),
    path("balance/ledger/", balance_transaction_list, name="balance_transaction_list"),
    path("balance/commissions/", commission_entry_list, name="commission_entry_list"),
    path("balance/saved-methods/", saved_payment_method_list, name="saved_payment_method_list"),

    path("bank-accounts/", bank_account_list, name="bank_account_list"),
    path("bank-accounts/add/", bank_account_create, name="bank_account_create"),
    path("bank-accounts/<uuid:pk>/delete/", bank_account_delete, name="bank_account_delete"),

    path("payouts/", payout_request_list, name="payout_request_list"),
    path("payouts/request/", payout_request_create, name="payout_request_create"),
    path("payouts/<uuid:pk>/", payout_request_detail, name="payout_request_detail"),
    path("payouts/<uuid:pk>/cancel/", payout_request_cancel, name="payout_request_cancel"),

    path("fraud/rules/", fraud_rule_list, name="fraud_rule_list"),
    path("fraud/rules/add/", fraud_rule_create, name="fraud_rule_create"),
    path("fraud/rules/<uuid:pk>/edit/", fraud_rule_edit, name="fraud_rule_edit"),
    path("fraud/rules/<uuid:pk>/delete/", fraud_rule_delete, name="fraud_rule_delete"),
    path("fraud/blocklist/", blocklist_list, name="blocklist_list"),
    path("fraud/blocklist/add/", blocklist_create, name="blocklist_create"),
    path("fraud/blocklist/<uuid:pk>/delete/", blocklist_delete, name="blocklist_delete"),
    path("fraud/assessments/", fraud_assessment_list, name="fraud_assessment_list"),

    path("reconciliation/", tenant_reconciliation_list, name="tenant_reconciliation_list"),
    path("reconciliation/<uuid:pk>/", tenant_reconciliation_detail, name="tenant_reconciliation_detail"),
]
