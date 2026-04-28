"""
dashboard/payments_tenant/__init__.py
Tenant-facing payment management dashboard.

Covers all 29 tenant-schema payment models including:
  - TenantPaymentProfile, TenantGatewayMode, TenantGatewayCredential, SupportedCurrency
  - Transactions, Refunds, Disputes, DisputeEvidence
  - TenantBalance, TenantBalanceTransaction (append-only ledger)
  - TenantBankAccount, PayoutRequest
  - FraudRule (tenant-specific), BlocklistEntry (tenant-specific), FraudAssessment
  - ReconciliationReport, ReconciliationEntry
"""
