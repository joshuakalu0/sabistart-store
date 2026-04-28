from django.urls import path
from . import views

app_name = 'b2b'

urlpatterns = [
    path('apply/', views.b2b_application_view, name='b2b_apply'),
    path('portal/', views.b2b_portal_view, name='b2b_portal'),
    path('rfq/', views.request_for_quote_view, name='b2b_rfq'),
    path('quotes/<uuid:quote_id>/', views.quote_detail_view, name='quote_detail'),
    path('checkout/po/', views.po_checkout_view, name='po_checkout'),
    path('pricing/', views.contract_pricing_view, name='contract_pricing'),
    path('company/', views.company_management_view, name='company_management'),
    path('invoices/', views.invoice_history_view, name='invoice_history'),
    path('tax-exemption/', views.tax_exemption_view, name='tax_exemption'),
]
