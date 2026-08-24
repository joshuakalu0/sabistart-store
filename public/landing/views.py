from django.shortcuts import render

from system.feature_marketplace.services import get_plan_groups


def landing_home(request):
    plan_groups = get_plan_groups(currency="NGN", current_only=True)
    return render(request, "landing/home.html", {"landing_plan_groups": plan_groups})


def landing_about(request):
    return render(request, "landing/about.html")


def landing_features(request):
    return render(request, "landing/features.html")


def landing_pricing(request):
    plan_groups = get_plan_groups(currency="NGN", current_only=True)
    return render(request, "landing/pricing.html", {"plan_groups": plan_groups})


def landing_contact(request):
    return render(request, "landing/contact.html")
