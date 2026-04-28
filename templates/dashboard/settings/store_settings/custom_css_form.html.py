{% load static %}
<!DOCTYPE html>
<html class="light" lang="en">
<head>
    <meta charset="utf-8"/>
    <meta content="width=device-width, initial-scale=1.0" name="viewport"/>
    <title>{{ title }} | Store Admin</title>
    <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
    <script id="tailwind-config">
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    colors: {
                        "primary": "#0053db",
                        "on-primary-fixed-variant": "#0050d4",
                        "background": "#f7f9fb",
                        "on-surface-variant": "#566166",
                        "on-error-container": "#752121",
                        "on-secondary-fixed": "#314055",
                        "secondary-dim": "#44546a",
                        "error-container": "#fe8983",
                        "on-secondary-container": "#435368",
                        "on-secondary": "#f7f9ff",
                        "surface-container-lowest": "#ffffff",
                        "on-primary-fixed": "#003798",
                        "surface": "#f7f9fb",
                        "on-surface": "#2a3439",
                        "error": "#9f403d",
                        "on-tertiary-fixed": "#3e3a54",
                        "on-primary": "#f8f7ff",
                        "primary-fixed-dim": "#c7d3ff",
                        "surface-container-highest": "#d9e4ea",
                        "on-tertiary-fixed-variant": "#5b5672",
                        "surface-container": "#e8eff3",
                        "inverse-primary": "#618bff",
                        "on-tertiary": "#fcf7ff",
                        "on-error": "#fff7f6",
                        "surface-dim": "#cfdce3",
                        "on-secondary-fixed-variant": "#4d5d73",
                        "tertiary-dim": "#54506b",
                        "secondary-fixed-dim": "#c5d6f0",
                        "tertiary-fixed-dim": "#d4cdee",
                        "outline": "#717c82",
                        "primary-fixed": "#dbe1ff",
                        "secondary-container": "#d3e4fe",
                        "surface-container-low": "#f0f4f7",
                        "surface-variant": "#d9e4ea",
                        "surface-tint": "#0053db",
                        "secondary-fixed": "#d3e4fe",
                        "error-dim": "#4e0309",
                        "tertiary-fixed": "#e3dbfd",
                        "tertiary-container": "#e3dbfd",
                        "tertiary": "#605c78",
                        "primary-container": "#dbe1ff",
                        "on-background": "#2a3439",
                        "surface-container-high": "#e1e9ee",
                        "on-tertiary-container": "#514d68",
                        "inverse-surface": "#0b0f10",
                        "surface-bright": "#f7f9fb",
                        "primary-dim": "#0048c1",
                        "outline-variant": "#a9b4b9",
                        "on-primary-container": "#0048bf",
                        "inverse-on-surface": "#9a9d9f",
                        "secondary": "#506076"
                    },
                    fontFamily: {
                        "headline": ["Manrope"],
                        "body": ["Inter"],
                        "label": ["Inter"]
                    },
                    borderRadius: { "DEFAULT": "0.125rem", "lg": "0.25rem", "xl": "0.5rem", "full": "0.75rem" },
                },
            },
        }
    </script>
    <style>
        .material-symbols-outlined {
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        }
        body { font-family: 'Inter', sans-serif; }
        h1, h2, h3 { font-family: 'Manrope', sans-serif; }
        .no-scrollbar::-webkit-scrollbar { display: none; }

        /* Form Error States */
        .form-field-error {
            border-bottom-color: #9f403d !important;
            background-color: #fef2f2 !important;
        }
        .error-message {
            color: #9f403d;
            font-size: 0.75rem;
            margin-top: 0.25rem;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }

        /* Toggle Switch Styling */
        .toggle-checkbox {
            opacity: 0;
            position: absolute;
        }

        /* Code Editor */
        .code-editor {
            font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.6;
        }
        .code-editor textarea {
            background: transparent;
            border: none;
            color: #e5e5e5;
            resize: none;
            width: 100%;
            height: 100%;
            outline: none;
        }

        /* Syntax Highlighting */
        .syntax-keyword { color: #c678dd; }
        .syntax-property { color: #61afef; }
        .syntax-value { color: #d19a66; }
        .syntax-selector { color: #e5c07b; }
        .syntax-comment { color: #5c6370; }
        .syntax-function { color: #98c379; }

        /* Validation Status */
        .validation-valid {
            border-color: #10B981 !important;
        }
        .validation-error {
            border-color: #9f403d !important;
        }

        /* Custom Pages Section */
        .custom-pages-section {
            transition: all 0.3s ease;
        }
        .custom-pages-section.disabled {
            opacity: 0.5;
            pointer-events: none;
        }
    </style>
</head>
<body class="bg-surface text-on-surface min-h-screen">

<!-- Django Messages Framework -->
{% if messages %}
<div class="fixed top-20 right-8 z-50 space-y-2">
    {% for message in messages %}
    <div class="flex items-center gap-3 px-6 py-4 rounded-lg shadow-lg" style="background-color: {% if message.tags == 'success' %}#10B981{% elif message.tags == 'error' %}#9f403d{% else %}#ffffff{% endif %}; color: {% if message.tags == 'error' %}#fff7f6{% else %}#2a3439{% endif %};">
        <span class="material-symbols-outlined text-sm">
            {% if message.tags == 'success' %}check_circle{% elif message.tags == 'error' %}error{% else %}info{% endif %}
        </span>
        <span class="font-medium text-sm">{{ message }}</span>
    </div>
    {% endfor %}
</div>
{% endif %}

<!-- TopAppBar -->
<header class="sticky top-0 z-50 w-full bg-white/80 dark:bg-slate-900/80 backdrop-blur-md shadow-sm shadow-slate-200/50 dark:shadow-none flex items-center justify-between px-8 py-4 max-w-full mx-auto">
    <div class="flex items-center gap-8">
        <span class="text-xl font-bold tracking-tighter text-slate-900 dark:text-slate-100">{{ title }}</span>
        <nav class="hidden md:flex gap-6 font-manrope text-sm font-medium tracking-tight">
            <a class="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 transition-colors active:scale-95 duration-200 ease-in-out" href="{% url 'custom_css_list' %}">Settings</a>
            <a class="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 transition-colors active:scale-95 duration-200 ease-in-out" href="#">Advanced</a>
            <a class="text-blue-700 dark:text-blue-400 border-b-2 border-blue-700 pb-1 active:scale-95 duration-200 ease-in-out" href="#">System</a>
        </nav>
    </div>
    <div class="flex items-center gap-4">
        <button type="button" class="px-4 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100/50 dark:hover:bg-slate-800/50 transition-colors rounded-lg active:scale-95 duration-200 ease-in-out" onclick="window.location.href='{% url 'custom_css_list' %}'">Discard</button>
        <button type="button" class="px-6 py-2 text-sm font-bold bg-primary text-on-primary rounded-lg shadow-sm hover:bg-primary-dim transition-all active:scale-95 duration-200 ease-in-out flex items-center gap-2" onclick="validateCSS()">
            <span class="material-symbols-outlined text-[18px]">code</span>
            Validate
        </button>
        <button type="submit" form="css-form" class="px-6 py-2 text-sm font-bold bg-primary text-on-primary rounded-lg shadow-sm hover:bg-primary-dim transition-all active:scale-95 duration-200 ease-in-out flex items-center gap-2">
            <span class="material-symbols-outlined text-[18px]">save</span>
            {% if is_edit %}Save Changes{% else %}Create Snippet{% endif %}
        </button>
        {% if is_edit %}
        <a href="{% url 'custom_css_preview' object.pk %}" class="px-5 py-2 text-primary font-medium hover:bg-surface-container-low transition-all active:scale-95 duration-200 ease-in-out flex items-center gap-2">
            <span class="material-symbols-outlined text-sm">visibility</span>
            Preview
        </a>
        <a href="{% url 'custom_css_duplicate' object.pk %}" class="px-5 py-2 text-primary font-medium hover:bg-surface-container-low transition-all active:scale-95 duration-200 ease-in-out flex items-center gap-2" onclick="return confirm('Create a copy of this CSS snippet?')">
            <span class="material-symbols-outlined text-sm">content_copy</span>
            Duplicate
        </a>
        {% endif %}
    </div>
</header>

<main class="max-w-7xl mx-auto px-8 py-12">
    <form id="css-form" method="post" action="{{ action_url }}" novalidate>
        {% csrf_token %}

        <!-- Page Title -->
        <div class="mb-16">
            <div class="flex items-center gap-2 text-on-surface-variant text-sm font-medium mb-2">
                <span>System</span>
                <span class="material-symbols-outlined text-[14px]">chevron_right</span>
                <span>Custom CSS Models</span>
            </div>
            <h1 class="text-5xl font-extrabold tracking-tighter text-on-surface">Global Stylesheet Editor</h1>
            <p class="text-on-surface-variant mt-2 text-lg">Manage technical overrides and device-specific rendering logic.</p>
            {% if is_edit %}
            <p class="text-xs text-on-surface-variant mt-4">
                <span class="material-symbols-outlined text-xs align-middle">code</span>
                {{ object.css_code|length|default:0 }} characters •
                <span class="material-symbols-outlined text-xs align-middle">layers</span>
                Load order: {{ object.load_order|default:0 }} •
                <span class="material-symbols-outlined text-xs align-middle">{% if object.is_active %}check_circle{% else %}cancel{% endif %}</span>
                {% if object.is_active %}Active{% else %}Inactive{% endif %}
            </p>
            {% endif %}
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-10">
            <!-- Left Column: Primary Editing Space -->
            <div class="lg:col-span-8 space-y-10">

                <!-- Section 1: CSS Identity -->
                <section class="bg-surface-container-low p-10 rounded-xl">
                    <h2 class="text-sm font-bold tracking-widest uppercase text-on-surface-variant mb-8">01. CSS Identity</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-on-surface-variant" for="{{ form.name.id_for_label }}">Stylesheet Name</label>
                            {{ form.name }}
                            {% if form.name.errors %}
                                {% for error in form.name.errors %}
                                    <p class="error-message">{{ error }}</p>
                                {% endfor %}
                            {% endif %}
                        </div>
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-on-surface-variant">Created By</label>
                            <div class="flex items-center gap-3 bg-surface-container-lowest px-4 py-3 rounded-lg border-b border-transparent">
                                <div class="w-6 h-6 rounded-full bg-primary-fixed flex items-center justify-center text-[10px] font-bold text-on-primary-fixed">
                                    {% if is_edit and object.created_by %}{{ object.created_by|slice:":2"|upper }}{% else %}AD{% endif %}
                                </div>
                                <span class="text-on-surface font-medium">{% if is_edit and object.created_by %}{{ object.created_by }}{% else %}Admin User{% endif %}</span>
                            </div>
                        </div>
                        <div class="md:col-span-2 space-y-2">
                            <label class="block text-sm font-medium text-on-surface-variant" for="{{ form.description.id_for_label }}">Description</label>
                            {{ form.description }}
                            <div class="flex justify-between mt-1">
                                <span class="text-[11px] text-on-surface-variant px-1 italic">Explain the purpose of these style overrides...</span>
                                <span class="text-[11px] font-bold char-counter" id="description-counter">{{ form.description.value|length|default:0 }} / 500</span>
                            </div>
                            {% if form.description.errors %}
                                {% for error in form.description.errors %}
                                    <p class="error-message">{{ error }}</p>
                                {% endfor %}
                            {% endif %}
                        </div>
                    </div>
                </section>

                <!-- Section 2: Code Editor -->
                <section class="bg-surface-container-low p-10 rounded-xl">
                    <div class="flex justify-between items-center mb-8">
                        <h2 class="text-sm font-bold tracking-widest uppercase text-on-surface-variant">02. Code Editor</h2>
                        <div class="flex gap-2">
                            <span class="px-2 py-1 bg-surface-container-highest text-[10px] font-bold rounded text-on-surface-variant">CSS</span>
                            <span class="px-2 py-1 bg-surface-container-highest text-[10px] font-bold rounded text-on-surface-variant">UTF-8</span>
                        </div>
                    </div>
                    <div class="relative bg-[#1e1e1e] rounded-xl overflow-hidden shadow-xl ring-1 ring-white/10" id="validation-container">
                        <div class="flex items-center gap-2 px-4 py-2 bg-[#2d2d2d] border-b border-[#3d3d3d]">
                            <div class="flex gap-1.5">
                                <div class="w-3 h-3 rounded-full bg-[#ff5f56]"></div>
                                <div class="w-3 h-3 rounded-full bg-[#ffbd2e]"></div>
                                <div class="w-3 h-3 rounded-full bg-[#27c93f]"></div>
                            </div>
                            <span class="text-[11px] font-mono text-slate-400 ml-4">{% if is_edit %}{{ object.name|slugify }}.css{% else %}custom_styles.css{% endif %}</span>
                            <span class="ml-auto text-[10px] font-bold" id="validation-status"></span>
                        </div>
                        <div class="flex font-mono text-sm leading-6 overflow-x-auto">
                            <div class="text-slate-500 pr-6 text-right select-none border-r border-slate-800 bg-[#1e1e1e] py-6" id="line-numbers">
                                01<br/>02<br/>03<br/>04<br/>05<br/>06<br/>07<br/>08<br/>09<br/>10<br/>11<br/>12<br/>13<br/>14<br/>15
                            </div>
                            <div class="code-editor flex-1 py-6 px-6">
                                <textarea id="css-code-editor" name="{{ form.css_code.name }}" spellcheck="false" placeholder="/* Enter your CSS code here (without &lt;style&gt; tags) */">{{ form.css_code.value|default:'/* Start writing your CSS here */' }}</textarea>
                            </div>
                        </div>
                        <!-- Hidden textarea for form submission -->
                        <textarea id="{{ form.css_code.id_for_label }}" name="{{ form.css_code.name }}" class="hidden">{{ form.css_code.value|default:'' }}</textarea>
                    </div>
                    {% if form.css_code.errors %}
                        {% for error in form.css_code.errors %}
                            <p class="error-message mt-2">{{ error }}</p>
                        {% endfor %}
                    {% endif %}
                    <div class="flex justify-between items-center mt-4">
                        <p class="text-xs text-on-surface-variant">⚠️ Warning: Incorrect CSS can break your theme. Test thoroughly before activating.</p>
                        <p class="text-xs font-bold" id="css-length-counter">{{ form.css_code.value|length|default:0 }} characters</p>
                    </div>
                </section>

                <!-- Section 3: Targeting -->
                <section class="bg-surface-container-low p-10 rounded-xl">
                    <h2 class="text-sm font-bold tracking-widest uppercase text-on-surface-variant mb-8">03. Targeting</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-10">
                        <div class="space-y-4">
                            <label class="block text-sm font-medium text-on-surface-variant" for="{{ form.apply_to.id_for_label }}">Apply To</label>
                            {{ form.apply_to }}
                            <p class="text-[11px] text-on-surface-variant px-1 italic">Select the scope of these CSS injections.</p>
                            {% if form.apply_to.errors %}
                                {% for error in form.apply_to.errors %}
                                    <p class="error-message">{{ error }}</p>
                                {% endfor %}
                            {% endif %}
                        </div>
                        <div class="space-y-4 custom-pages-section {% if form.apply_to.value != 'custom' %}disabled{% endif %}" id="custom-pages-section">
                            <label class="block text-sm font-medium text-on-surface-variant" for="{{ form.custom_pages.id_for_label }}">Custom Pages (Comma-separated IDs)</label>
                            {{ form.custom_pages }}
                            <p class="text-[11px] text-on-surface-variant px-1 italic">e.g., 1, 2, 3 (page IDs)</p>
                            {% if form.custom_pages.errors %}
                                {% for error in form.custom_pages.errors %}
                                    <p class="error-message">{{ error }}</p>
                                {% endfor %}
                            {% endif %}
                        </div>
                    </div>
                </section>
            </div>

            <!-- Right Column: Controls & Preview -->
            <aside class="lg:col-span-4 space-y-10">

                <!-- Section 4: Responsive & Device Targeting -->
                <div class="bg-surface-container-low p-8 rounded-xl">
                    <h2 class="text-sm font-bold tracking-widest uppercase text-on-surface-variant mb-6">04. Device Coverage</h2>
                    <div class="space-y-6">
                        <div class="flex items-center justify-between group">
                            <div class="flex items-center gap-3">
                                <span class="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">smartphone</span>
                                <span class="text-sm font-semibold text-on-surface">Mobile</span>
                            </div>
                            <label class="relative inline-flex items-center cursor-pointer">
                                {{ form.apply_to_mobile }}
                                <div class="w-10 h-5 bg-primary rounded-full relative" style="background-color: {% if form.apply_to_mobile.value %}#0053db{% else %}#d9e4ea{% endif %};">
                                    <div class="absolute w-3 h-3 bg-white rounded-full transition-all" style="{% if form.apply_to_mobile.value %}right: 4px;{% else %}left: 4px;{% endif %} top: 4px;"></div>
                                </div>
                            </label>
                        </div>
                        {% if form.apply_to_mobile.errors %}
                            {% for error in form.apply_to_mobile.errors %}
                                <p class="error-message">{{ error }}</p>
                            {% endfor %}
                        {% endif %}

                        <div class="flex items-center justify-between group">
                            <div class="flex items-center gap-3">
                                <span class="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">tablet</span>
                                <span class="text-sm font-semibold text-on-surface">Tablet</span>
                            </div>
                            <label class="relative inline-flex items-center cursor-pointer">
                                {{ form.apply_to_tablet }}
                                <div class="w-10 h-5 bg-primary rounded-full relative" style="background-color: {% if form.apply_to_tablet.value %}#0053db{% else %}#d9e4ea{% endif %};">
                                    <div class="absolute w-3 h-3 bg-white rounded-full transition-all" style="{% if form.apply_to_tablet.value %}right: 4px;{% else %}left: 4px;{% endif %} top: 4px;"></div>
                                </div>
                            </label>
                        </div>
                        {% if form.apply_to_tablet.errors %}
                            {% for error in form.apply_to_tablet.errors %}
                                <p class="error-message">{{ error }}</p>
                            {% endfor %}
                        {% endif %}

                        <div class="flex items-center justify-between group">
                            <div class="flex items-center gap-3">
                                <span class="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">desktop_windows</span>
                                <span class="text-sm font-semibold text-on-surface">Desktop</span>
                            </div>
                            <label class="relative inline-flex items-center cursor-pointer">
                                {{ form.apply_to_desktop }}
                                <div class="w-10 h-5 bg-primary rounded-full relative" style="background-color: {% if form.apply_to_desktop.value %}#0053db{% else %}#d9e4ea{% endif %};">
                                    <div class="absolute w-3 h-3 bg-white rounded-full transition-all" style="{% if form.apply_to_desktop.value %}right: 4px;{% else %}left: 4px;{% endif %} top: 4px;"></div>
                                </div>
                            </label>
                        </div>
                        {% if form.apply_to_desktop.errors %}
                            {% for error in form.apply_to_desktop.errors %}
                                <p class="error-message">{{ error }}</p>
                            {% endfor %}
                        {% endif %}
                    </div>
                </div>

                <!-- Section 5: Load Control -->
                <div class="bg-surface-container-low p-8 rounded-xl">
                    <h2 class="text-sm font-bold tracking-widest uppercase text-on-surface-variant mb-6">05. Execution</h2>
                    <div class="space-y-8">
                        <div class="space-y-3">
                            <label class="block text-sm font-medium text-on-surface-variant" for="{{ form.load_order.id_for_label }}">Load Order (Priority)</label>
                            <div class="flex items-center gap-4">
                                {{ form.load_order }}
                                <span class="text-xs text-on-surface-variant leading-tight">Higher numbers load last (overriding other styles).</span>
                            </div>
                            {% if form.load_order.errors %}
                                {% for error in form.load_order.errors %}
                                    <p class="error-message">{{ error }}</p>
                                {% endfor %}
                            {% endif %}
                        </div>
                        <hr class="border-surface-container-highest"/>
                        <div class="flex items-center justify-between">
                            <div class="space-y-0.5">
                                <span class="text-sm font-bold text-on-surface">Active Status</span>
                                <p class="text-[11px] text-on-surface-variant">Live on production</p>
                            </div>
                            <label class="relative inline-flex items-center cursor-pointer">
                                {{ form.is_active }}
                                <div class="w-12 h-6 bg-primary rounded-full relative" style="background-color: {% if form.is_active.value %}#0053db{% else %}#d9e4ea{% endif %};">
                                    <div class="absolute w-4 h-4 bg-white rounded-full transition-all" style="{% if form.is_active.value %}right: 4px;{% else %}left: 4px;{% endif %} top: 4px;"></div>
                                </div>
                            </label>
                        </div>
                        {% if form.is_active.errors %}
                            {% for error in form.is_active.errors %}
                                <p class="error-message">{{ error }}</p>
                            {% endfor %}
                        {% endif %}
                    </div>
                </div>

                <!-- Preview Panel -->
                <div class="bg-on-surface text-surface rounded-xl p-8 shadow-2xl relative overflow-hidden">
                    <div class="absolute top-0 right-0 p-4 opacity-10">
                        <span class="material-symbols-outlined text-6xl">visibility</span>
                    </div>
                    <h2 class="text-sm font-bold tracking-widest uppercase mb-6 opacity-60">Live Projection</h2>
                    <div class="space-y-4 font-mono text-[11px] leading-relaxed">
                        <div class="text-primary-fixed">/* Media Query Generation */</div>
                        <div id="media-query-preview">
                            <span class="syntax-keyword">@media</span> (max-width: <span class="syntax-value">768px</span>) {<br/>
                              <span class="syntax-comment">/* Mobile styles enabled */</span><br/>
                              [Wrapped Code Block]<br/>
                            }
                        </div>
                        <div class="mt-4" id="desktop-query-preview">
                            <span class="syntax-keyword">@media</span> (min-width: <span class="syntax-value">1024px</span>) {<br/>
                              <span class="syntax-comment">/* Desktop styles enabled */</span><br/>
                              [Wrapped Code Block]<br/>
                            }
                        </div>
                    </div>
                    <div class="mt-8 p-4 bg-white/5 rounded-lg border border-white/10">
                        <p class="text-xs leading-normal opacity-80">These styles will be injected into the <span class="font-mono text-primary-fixed">&lt;head&gt;</span> element of the target pages with an <span class="italic">!important</span> weight due to load priority <span id="load-order-preview">{{ form.load_order.value|default:0 }}</span>.</p>
                    </div>
                </div>

                {% if is_edit %}
                <div class="bg-surface-container-low p-8 rounded-xl">
                    <h2 class="text-sm font-bold tracking-widest uppercase text-on-surface-variant mb-6">Danger Zone</h2>
                    <a href="{% url 'custom_css_delete' object.pk %}" class="text-xs text-error font-bold hover:underline flex items-center gap-1" onclick="return confirm('Are you sure you want to delete this CSS snippet? This action cannot be undone.')">
                        <span class="material-symbols-outlined text-sm">delete</span>
                        Delete CSS Snippet
                    </a>
                </div>
                {% endif %}
            </aside>
        </div>
    </form>
</main>

<!-- Footer Space -->
<footer class="mt-20 border-t border-surface-container-highest py-12 text-center">
    <p class="text-on-surface-variant text-sm font-medium tracking-tight">Architectural Ledger © 2024. Advanced Django Model Interface.</p>
</footer>

<!-- JavaScript for Dynamic Interactions -->
<script>
    document.addEventListener('DOMContentLoaded', function() {
        // === Sync CSS Code Editor ===
        const cssEditor = document.getElementById('css-code-editor');
        const cssTextarea = document.getElementById('{{ form.css_code.id_for_label }}');
        const lineNumbers = document.getElementById('line-numbers');
        const cssLengthCounter = document.getElementById('css-length-counter');
        const validationStatus = document.getElementById('validation-status');
        const validationContainer = document.getElementById('validation-container');

        if (cssEditor && cssTextarea) {
            cssTextarea.value = cssEditor.value;

            cssEditor.addEventListener('input', function() {
                cssTextarea.value = this.value;
                updateLineNumbers();
                updateCSSLength();
                updateMediaQueryPreview();
            });

            cssEditor.addEventListener('scroll', function() {
                lineNumbers.scrollTop = this.scrollTop;
            });
        }

        // === Update Line Numbers ===
        function updateLineNumbers() {
            if (!cssEditor || !lineNumbers) return;

            const lines = cssEditor.value.split('\n').length;
            let lineNumbersHTML = '';
            for (let i = 1; i <= Math.max(lines, 15); i++) {
                lineNumbersHTML += (i < 10 ? '0' : '') + i + '<br/>';
            }
            lineNumbers.innerHTML = lineNumbersHTML;
        }

        // === Update CSS Length Counter ===
        function updateCSSLength() {
            if (cssEditor && cssLengthCounter) {
                cssLengthCounter.textContent = cssEditor.value.length + ' characters';
            }
        }

        // === Description Character Counter ===
        const descriptionInput = document.getElementById('{{ form.description.id_for_label }}');
        const descriptionCounter = document.getElementById('description-counter');

        if (descriptionInput && descriptionCounter) {
            descriptionCounter.textContent = descriptionInput.value.length + ' / 500';

            descriptionInput.addEventListener('input', function() {
                descriptionCounter.textContent = this.value.length + ' / 500';

                if (this.value.length > 450) {
                    descriptionCounter.classList.add('text-error');
                } else {
                    descriptionCounter.classList.remove('text-error');
                }
            });
        }

        // === Apply To Selection ===
        const applyToSelect = document.getElementById('{{ form.apply_to.id_for_label }}');
        const customPagesSection = document.getElementById('custom-pages-section');

        if (applyToSelect && customPagesSection) {
            applyToSelect.addEventListener('change', function() {
                if (this.value === 'custom') {
                    customPagesSection.classList.remove('disabled');
                } else {
                    customPagesSection.classList.add('disabled');
                }
                updateMediaQueryPreview();
            });
        }

        // === Device Targeting Toggles ===
        const deviceToggles = [
            document.getElementById('{{ form.apply_to_mobile.id_for_label }}'),
            document.getElementById('{{ form.apply_to_tablet.id_for_label }}'),
            document.getElementById('{{ form.apply_to_desktop.id_for_label }}')
        ];

        deviceToggles.forEach(function(toggle) {
            if (toggle) {
                toggle.addEventListener('change', function() {
                    const toggleDiv = this.parentElement.querySelector('div.w-10.h-5');
                    const toggleKnob = toggleDiv?.querySelector('div.absolute');

                    if (toggleDiv) {
                        toggleDiv.style.backgroundColor = this.checked ? '#0053db' : '#d9e4ea';
                    }
                    if (toggleKnob) {
                        toggleKnob.style.left = this.checked ? '' : '4px';
                        toggleKnob.style.right = this.checked ? '4px' : '';
                    }

                    updateMediaQueryPreview();
                    validateDeviceSelection();
                });
            }
        });

        // === Validate At Least One Device Selected ===
        function validateDeviceSelection() {
            const mobileChecked = document.getElementById('{{ form.apply_to_mobile.id_for_label }}')?.checked;
            const tabletChecked = document.getElementById('{{ form.apply_to_tablet.id_for_label }}')?.checked;
            const desktopChecked = document.getElementById('{{ form.apply_to_desktop.id_for_label }}')?.checked;

            if (!mobileChecked && !tabletChecked && !desktopChecked) {
                // Show error
                const mobileToggle = document.getElementById('{{ form.apply_to_mobile.id_for_label }}');
                if (mobileToggle) {
                    const errorMsg = document.createElement('p');
                    errorMsg.className = 'error-message';
                    errorMsg.textContent = 'CSS must be applied to at least one device type.';
                    mobileToggle.parentElement.parentElement.appendChild(errorMsg);
                }
            }
        }

        // === Load Order Preview ===
        const loadOrderInput = document.getElementById('{{ form.load_order.id_for_label }}');
        const loadOrderPreview = document.getElementById('load-order-preview');

        if (loadOrderInput && loadOrderPreview) {
            loadOrderPreview.textContent = loadOrderInput.value;

            loadOrderInput.addEventListener('input', function() {
                loadOrderPreview.textContent = this.value;
            });
        }

        // === Update Media Query Preview ===
        function updateMediaQueryPreview() {
            const mobileChecked = document.getElementById('{{ form.apply_to_mobile.id_for_label }}')?.checked;
            const tabletChecked = document.getElementById('{{ form.apply_to_tablet.id_for_label }}')?.checked;
            const desktopChecked = document.getElementById('{{ form.apply_to_desktop.id_for_label }}')?.checked;

            const mobilePreview = document.getElementById('media-query-preview');
            const desktopPreview = document.getElementById('desktop-query-preview');

            if (mobilePreview) {
                if (mobileChecked && !tabletChecked && !desktopChecked) {
                    mobilePreview.innerHTML = '<span class="syntax-keyword">@media</span> (max-width: <span class="syntax-value">767px</span>) {<br/>  <span class="syntax-comment">/* Mobile only */</span><br/>  [Wrapped Code Block]<br/>}';
                } else if (tabletChecked && !mobileChecked && !desktopChecked) {
                    mobilePreview.innerHTML = '<span class="syntax-keyword">@media</span> (min-width: <span class="syntax-value">768px</span>) and (max-width: <span class="syntax-value">1023px</span>) {<br/>  <span class="syntax-comment">/* Tablet only */</span><br/>  [Wrapped Code Block]<br/>}';
                } else if (desktopChecked && !mobileChecked && !tabletChecked) {
                    mobilePreview.innerHTML = '<span class="syntax-keyword">@media</span> (min-width: <span class="syntax-value">1024px</span>) {<br/>  <span class="syntax-comment">/* Desktop only */</span><br/>  [Wrapped Code Block]<br/>}';
                } else {
                    mobilePreview.innerHTML = '<span class="syntax-comment">/* All devices enabled - no media query wrapper */</span>';
                }
            }

            if (desktopPreview) {
                desktopPreview.style.display = (mobileChecked && tabletChecked && desktopChecked) ? 'none' : 'block';
            }
        }

        // === CSS Validation ===
        window.validateCSS = function() {
            if (!cssEditor) return;

            const cssCode = cssEditor.value;

            // Basic validation
            const openBraces = (cssCode.match(/{/g) || []).length;
            const closeBraces = (cssCode.match(/}/g) || []).length;

            // Security checks
            const dangerousPatterns = [
                {pattern: /<script/i, message: 'Script tags detected'},
                {pattern: /javascript:/i, message: 'JavaScript URLs detected'},
                {pattern: /expression\s*\(/i, message: 'CSS expressions detected'},
                {pattern: /@import/i, message: '@import rules detected'},
            ];

            let errors = [];
            let warnings = [];

            if (openBraces !== closeBraces) {
                errors.push(`Unbalanced braces: ${openBraces} open, ${closeBraces} close`);
            }

            dangerousPatterns.forEach(function(check) {
                if (check.pattern.test(cssCode)) {
                    errors.push(`Security violation: ${check.message}`);
                }
            });

            if (cssCode.length > 50000) {
                warnings.push(`Large CSS (${cssCode.length} chars) - may impact performance`);
            }

            // Update UI
            if (errors.length > 0) {
                validationContainer.classList.add('validation-error');
                validationContainer.classList.remove('validation-valid');
                validationStatus.innerHTML = '<span class="text-error font-bold">❌ ' + errors.length + ' error(s) found</span>';

                // Show errors
                errors.forEach(function(error) {
                    alert('⚠️ ' + error);
                });
            } else if (warnings.length > 0) {
                validationContainer.classList.add('validation-valid');
                validationStatus.innerHTML = '<span class="text-warning font-bold">⚠️ ' + warnings.length + ' warning(s)</span>';

                warnings.forEach(function(warning) {
                    console.warn('⚠️ ' + warning);
                });
            } else {
                validationContainer.classList.add('validation-valid');
                validationContainer.classList.remove('validation-error');
                validationStatus.innerHTML = '<span class="text-success font-bold">✓ Valid CSS</span>';
            }
        };

        // === Toggle Switches ===
        const toggleCheckboxes = document.querySelectorAll('input[type="checkbox"]');
        toggleCheckboxes.forEach(function(checkbox) {
            checkbox.classList.add('toggle-checkbox');
        });

        // === Initialize ===
        updateLineNumbers();
        updateCSSLength();
        updateMediaQueryPreview();

        // === Form Change Detection ===
        const form = document.getElementById('css-form');
        let formChanged = false;

        form.addEventListener('input', function() {
            formChanged = true;
        });

        window.addEventListener('beforeunload', function(e) {
            if (formChanged) {
                e.preventDefault();
                e.returnValue = '';
            }
        });

        // === Hide Messages After 5 Seconds ===
        setTimeout(function() {
            const messages = document.querySelectorAll('.fixed.top-20');
            messages.forEach(function(msg) {
                msg.style.opacity = '0';
                msg.style.transition = 'opacity 0.5s ease';
                setTimeout(function() {
                    msg.remove();
                }, 500);
            });
        }, 5000);
    });
</script>

</body>
</html>