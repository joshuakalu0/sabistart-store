from django.urls import path
from . import views

app_name = 'promotions'

urlpatterns = [
    path('coupons/', views.coupon_landing_view, name='coupon_landing'),
    path('loyalty/info/', views.loyalty_info_view, name='loyalty_info'),
    path('referrals/join/', views.referral_landing_view, name='referral_landing'),
    path('gift-cards/', views.gift_card_buy_view, name='gift_card_buy'),
    path('gift-cards/balance/', views.gift_card_balance_view, name='gift_card_balance'),
    path('newsletter/', views.newsletter_signup_view, name='newsletter_signup'),
    path('competitions/', views.competition_list_view, name='competition_list'),
    path('campaigns/<slug:campaign_slug>/', views.campaign_landing_view, name='campaign_landing'),
]
