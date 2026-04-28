"""Shared storefront theme package.

Theme templates and assets live in this central directory and are never copied per
tenant. The custom loader in ``themes.loader`` resolves the active theme at request
time and serves files directly from here.
"""
