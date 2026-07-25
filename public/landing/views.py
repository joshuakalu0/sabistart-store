from django.shortcuts import render


def landing_home(request):
    return render(request, "landing/home.html")


def landing_about(request):
    return render(request, "landing/about.html")


def landing_features(request):
    return render(request, "landing/features.html")


def landing_pricing(request):
    return render(request, "landing/pricing.html")


def landing_contact(request):
    return render(request, "landing/contact.html")
