from django.urls import reverse


def main_sidebar(prefix):
    return [
        ['Business Setting',
         {
             'dashboard': {
                 'name': 'Dashboard',
                 'url': reverse('dashboard:dashboard_home:home', kwargs={'prefix': prefix}),
                 'icon': 'home',
                 'active': True,
             },
             'business setup': {
                 'name': 'Business Setup',
                 'url': reverse('dashboard:dashboard_settings:general', kwargs={'prefix': prefix}),
                 'icon': 'settings',
                 'active': False,
             },
             'categories': {
                 'name': 'Categories',
                 'url': '#',
                 'icon': 'category',
                 'active': False,
                 'sub_menu': [
                     {
                        'name': 'List',
                        'url': reverse('dashboard:dashboard_categories:list', kwargs={'prefix': prefix}),
                        'icon': 'list',
                        'active': False,
                     },
                     {
                         'name': 'Add',
                         'url': reverse('dashboard:dashboard_categories:create', kwargs={'prefix': prefix}),
                         'icon': 'add',
                         'active': False,
                     },
                 ]
             },
             'tags': {
                 'name': 'Tags',
                 'url': '#',
                 'icon': 'local_offer',
                 'active': False,
                 'sub_menu': [
                     {
                        'name': 'List',
                        'url': reverse('dashboard:dashboard_categories:tag_list', kwargs={'prefix': prefix}),
                        'icon': 'list',
                        'active': False,
                     },
                     {
                         'name': 'Add',
                         'url': reverse('dashboard:dashboard_categories:tag_create', kwargs={'prefix': prefix}),
                         'icon': 'add',
                         'active': False,
                     },
                 ]
             },
             'brands': {
                 'name': 'Brands',
                 'url': '#',
                 'icon': 'storefront',
                 'active': False,
                 'sub_menu': [
                     {
                        'name': 'List',
                        'url': reverse('dashboard:dashboard_categories:brand_list', kwargs={'prefix': prefix}),
                        'icon': 'list',
                        'active': False,
                     },
                     {
                         'name': 'Add',
                         'url': reverse('dashboard:dashboard_categories:brand_create', kwargs={'prefix': prefix}),
                         'icon': 'add',
                         'active': False,
                     },
                 ]
             },
             'products': {
                 'name': 'Products',
                 'url': '#',
                 'icon': 'inventory_2',
                 'active': False,
                 'sub_menu': [
                     {
                         'name': 'List',
                         'url': reverse('dashboard:product_settings:product_list', kwargs={'prefix': prefix}),
                         'icon': 'list',
                         'active': False,
                     },
                     {
                         'name': 'Add',
                         'url': reverse('dashboard:product_settings:product_create', kwargs={'prefix': prefix}),
                         'icon': 'add',
                         'active': False,
                     },
                 ]
             },
             'attributes': {
                 'name': 'Attributes',
                 'url': '#',
                 'icon': 'filter_alt',
                 'active': False,
                 'sub_menu': [
                     {
                         'name': 'Attribute Groups',
                         'url': reverse('dashboard:product_settings:attribute_group_list', kwargs={'prefix': prefix}),
                         'icon': 'category',
                         'active': False,
                     },
                     {
                         'name': 'Attributes',
                         'url': reverse('dashboard:product_settings:attribute_list', kwargs={'prefix': prefix}),
                         'icon': 'tag',
                         'active': False,
                     },
                 ]
             },
             'system vat': {
                 'name': 'System Vat',
                 'url': '#',
                 'icon': 'receipt_long',
                 'active': False,
                 'sub_menu': [
                     {
                         'name': 'System Vat',
                         'url': '#',
                         'icon': 'receipt_long',
                         'active': False,
                     },
                 ]
             },
         }],]


def business_setup_sidebar(prefix):
    return [['Business Setting', 'Configure your store settings'], {
        'general': {
            'name': 'General',
            'url': reverse('dashboard:dashboard_settings:general', kwargs={'prefix': prefix}),
            'icon': 'settings',
            'active': True,
        },
        'branding': {
            'name': 'Branding',
            'url': reverse('dashboard:dashboard_settings:branding', kwargs={'prefix': prefix}),
            'icon': 'storefront',
            'active': False,
        },
        'seo': {
            'name': 'Seo',
            'url': reverse('dashboard:dashboard_settings:seo', kwargs={'prefix': prefix}),
            'icon': 'search',
            'active': False,
        },
        'payment': {
            'name': 'Payment',
            'url': reverse('dashboard:dashboard_settings:payment', kwargs={'prefix': prefix}),
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
    }]


def get_sidebar_with_active(page, prefix):
    sidebar = main_sidebar(prefix)
    for key, values in sidebar[0][1].items():
        clean_v = values['name'].lower()
        if clean_v == page:
            values['active'] = True
        else:
            values['active'] = False
    return sidebar


def get_sub_sidebar_with_active(page, prefix):
    sidebar = business_setup_sidebar(prefix)
    for key, values in sidebar[1].items():
        clean_v = values['name'].lower()
        if clean_v == page:
            values['active'] = True
        else:
            values['active'] = False
    return sidebar


def get_settings_sidebar(prefix):
    return business_setup_sidebar(prefix)
