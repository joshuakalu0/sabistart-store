from __future__ import annotations

from django import forms


BASE_INPUT = (
    "block w-full rounded-2xl border border-slate-200/90 bg-slate-50 px-4 py-3 text-sm "
    "font-medium text-slate-900 shadow-sm shadow-slate-200/40 outline-none transition "
    "placeholder:text-slate-400 hover:border-slate-300 hover:bg-white "
    "focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-500/10 "
)
# BASE_INPUT = (
#     "block w-full rounded-2xl border border-slate-200/90 bg-slate-50 px-4 py-3 text-sm "
#     "font-medium text-slate-900 shadow-sm shadow-slate-200/40 outline-none transition "
#     "placeholder:text-slate-400 hover:border-slate-300 hover:bg-white "
#     "focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-500/10 "
#     "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 "
#     "dark:placeholder:text-slate-500 dark:hover:border-slate-600 dark:hover:bg-slate-900"
# )
BASE_TEXTAREA = BASE_INPUT + " min-h-[120px] resize-y"
BASE_SELECT = (
    "block w-full rounded-2xl border border-slate-200/90 bg-slate-50 px-4 py-3 text-sm "
    "font-medium text-slate-900 shadow-sm shadow-slate-200/40 outline-none transition "
    "hover:border-slate-300 hover:bg-white focus:border-blue-500 focus:bg-white "
    "focus:ring-4 focus:ring-blue-500/10  "

)
# BASE_SELECT = (
#     "block w-full rounded-2xl border border-slate-200/90 bg-slate-50 px-4 py-3 text-sm "
#     "font-medium text-slate-900 shadow-sm shadow-slate-200/40 outline-none transition "
#     "hover:border-slate-300 hover:bg-white focus:border-blue-500 focus:bg-white "
#     "focus:ring-4 focus:ring-blue-500/10 dark:border-slate-700 dark:bg-slate-900 "
#     "dark:text-slate-100 dark:hover:border-slate-600 dark:hover:bg-slate-900"
# )
BASE_CHECKBOX = (
    "h-4 w-4 rounded border-slate-300 bg-white text-blue-600 shadow-sm "
    "focus:ring-2 focus:ring-blue-500/20"
)
BASE_COLOR = (
    "h-12 w-full rounded-2xl border border-slate-200/90 bg-slate-50 px-2 py-2 shadow-sm "
    "shadow-slate-200/40 outline-none transition hover:border-slate-300 hover:bg-white "
    "focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-500/10 "
)
# BASE_COLOR = (
#     "h-12 w-full rounded-2xl border border-slate-200/90 bg-slate-50 px-2 py-2 shadow-sm "
#     "shadow-slate-200/40 outline-none transition hover:border-slate-300 hover:bg-white "
#     "focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-500/10 "
#     "dark:border-slate-700 dark:bg-slate-900"
# )
BASE_HELP = "mt-1 text-xs text-slate-500 "
# BASE_HELP = "mt-1 text-xs text-slate-500 dark:text-slate-400"
BASE_ERROR = "mt-1 text-xs font-medium text-rose-600 "
# BASE_ERROR = "mt-1 text-xs font-medium text-rose-600 dark:text-rose-300"


def merge_classes(attrs: dict, classes: str) -> dict:
    merged = dict(attrs or {})
    current = merged.get("class", "").strip()
    merged["class"] = f"{current} {classes}".strip() if current else classes
    return merged


def style_field(field: forms.Field) -> forms.Field:
    widget = field.widget
    attrs = widget.attrs

    if isinstance(widget, forms.Textarea):
        widget.attrs = merge_classes(attrs, BASE_TEXTAREA)
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
        widget.attrs = merge_classes(attrs, BASE_SELECT)
    elif isinstance(widget, (forms.CheckboxInput,)):
        widget.attrs = merge_classes(attrs, BASE_CHECKBOX)
    elif getattr(widget, "input_type", "") == "color":
        widget.attrs = merge_classes(attrs, BASE_COLOR)
    elif isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
        widget.attrs = merge_classes(attrs, "space-y-3")
    else:
        widget.attrs = merge_classes(attrs, BASE_INPUT)

    return field


def style_form_fields(form: forms.BaseForm) -> forms.BaseForm:
    for field in form.fields.values():
        style_field(field)
    return form


class TailwindFormMixin:
    """
    Apply shared Tailwind widget classes to every field automatically.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)
