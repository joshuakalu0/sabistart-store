from django.contrib import messages
from django.shortcuts import redirect

from public.storefront.forms import RegionSelectionForm
from public.storefront.services import build_breadcrumbs, render_info_page


def region_selector_view(request):
    form = RegionSelectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.session["region_preference"] = form.cleaned_data["region"]
        request.session["language_preference"] = form.cleaned_data.get("language", "en")
        request.session.modified = True
        messages.success(request, "Region preference updated.")
        return redirect("i18n:region_selector")
    return render_info_page(
        request,
        title="Select Region",
        body="Capture storefront region and language preferences in a tenant-safe session.",
        form=form,
        form_action=request.path,
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Region", ""))},
    )


def geo_redirect_view(request):
    return render_info_page(
        request,
        title="Geo Redirect",
        body="Geo-based redirection is represented as a themed shell until IP-based region detection is introduced.",
        extra_context={"breadcrumbs": build_breadcrumbs(("Home", "/"), ("Geo Redirect", ""))},
    )


def set_language_view(request):
    language = request.POST.get("language") or request.GET.get("language")
    if language:
        request.session["language_preference"] = language
        request.session.modified = True
        messages.success(request, "Language preference updated.")
    return redirect(request.META.get("HTTP_REFERER", "/"))
