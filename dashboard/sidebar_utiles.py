from django.db import connection

from sabistart.navigation import iter_tenant_navigation


def _apply_active_menu(sidebar, active_menu):
    if not active_menu:
        return sidebar

    for _, entries in sidebar:
        for key, values in entries.items():
            submenu_active = False
            for sub_item in values.get("sub_menu", []):
                is_active = sub_item.get("key") == active_menu
                sub_item["active"] = is_active
                submenu_active = submenu_active or is_active

            active_keys = set(values.get("active_keys", []))
            values["active"] = key == active_menu or submenu_active or active_menu in active_keys

    return sidebar


def _filter_sidebar_by_features(sidebar):
    schema_name = getattr(connection, "schema_name", "public")
    if schema_name == "public":
        return sidebar

    try:
        from dashboard.feature_marketplace.services import FeatureEntitlementEngine
    except Exception:
        return sidebar

    engine = FeatureEntitlementEngine(schema_name)
    filtered = []
    for title, entries in sidebar:
        next_entries = {}
        for key, values in entries.items():
            feature_code = values.get("feature_code")
            if feature_code and not engine.has_feature(feature_code):
                continue

            sub_menu = values.get("sub_menu")
            if sub_menu:
                values["sub_menu"] = [
                    item
                    for item in sub_menu
                    if not item.get("feature_code") or engine.has_feature(item["feature_code"])
                ]
                if not values["sub_menu"] and values.get("url") == "#":
                    continue

            next_entries[key] = values

        if next_entries:
            filtered.append([title, next_entries])
    return filtered


def _build_tenant_sidebar(prefix):
    sidebar = []
    for section in iter_tenant_navigation(prefix):
        entries = {}
        for item in section["items"]:
            entries[item["key"]] = {
                "name": item["name"],
                "url": item["url"],
                "icon": item["icon"],
                "active": False,
                "feature_code": item.get("feature_code"),
                "active_keys": item.get("active_keys", ()),
                "sub_menu": [
                    {
                        "name": child["name"],
                        "url": child["url"],
                        "icon": child["icon"],
                        "active": False,
                        "key": child["key"],
                        "feature_code": child.get("feature_code"),
                    }
                    for child in item.get("children", [])
                ],
            }
        if entries:
            sidebar.append([section["title"], entries])
    return sidebar


def main_sidebar(prefix, active_menu=None):
    sidebar = _build_tenant_sidebar(prefix)
    sidebar = _filter_sidebar_by_features(sidebar)
    return _apply_active_menu(sidebar, active_menu)


def business_setup_sidebar(prefix):
    return [['Business Setting', 'Configure your store settings'], {
        'general': {
            'name': 'General',
            'url': "#",
            'icon': 'settings',
            'active': True,
        },
        'branding': {
            'name': 'Branding',
            'url': "#",
            'icon': 'storefront',
            'active': False,
        },
        'seo': {
            'name': 'Seo',
            'url': "#",
            'icon': 'search',
            'active': False,
        },
        'payment': {
            'name': 'Payment',
            'url': "#",
            'icon': 'payment',
            'active': False,
        },
        'login': {
            'name': 'Login',
            'url': '#',
            'icon': 'login',
            'active': False,
        },
        'email': {
            'name': 'Email',
            'url': '#',
            'icon': 'email',
            'active': False,
        },
    }
    ]


def get_sidebar_with_active(page, prefix):
    sidebar = main_sidebar(prefix)
    for _, values in sidebar[0][1].items():
        clean_v = values['name'].lower()
        values['active'] = clean_v == page
    return sidebar


def get_sub_sidebar_with_active(page, prefix):
    sidebar = business_setup_sidebar(prefix)
    for _, values in sidebar[1].items():
        clean_v = values['name'].lower()
        values['active'] = clean_v == page
    return sidebar


def get_settings_sidebar(prefix):
    return business_setup_sidebar(prefix)
