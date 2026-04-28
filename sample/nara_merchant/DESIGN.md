# Design System Specification: Editorial E-Commerce & SaaS

## 1. Overview & Creative North Star
The Creative North Star for this design system is **"The Digital Atelier."** 

Unlike generic e-commerce templates that rely on rigid grids and heavy borders, this system treats the interface as a high-end editorial spread. We are building a platform that feels like a premium concierge service for Nigerian entrepreneurs. The aesthetic moves away from "app-like" density toward "gallery-like" breathing room. 

We break the "template look" through:
*   **Intentional Asymmetry:** Using the `24 (8.5rem)` and `16 (5.5rem)` spacing tokens to create staggered content layouts that lead the eye.
*   **Tonal Depth:** Replacing 1px lines with subtle background shifts (`surface-container-low` vs `surface-container-lowest`).
*   **High-Contrast Scale:** Pairing massive `display-lg` headlines with micro-refined `label-sm` metadata to create an authoritative typographic hierarchy.

---

## 2. Colors & Surface Architecture

### The Palette
We use a sophisticated interplay of Deep Navy (`primary`) and Vibrant Coral (`secondary`) to balance professional trust with high-conversion energy.

*   **Primary:** `#0F172A` (Deep Navy) – Used for authoritative typography and primary CTAs.
*   **Secondary:** `#9D4300` / `#FD761A` (Vibrant Coral) – Reserved strictly for conversion points (Add to Cart, Buy Now) and critical notifications.
*   **Surface Hierarchy:**
    *   `surface`: `#F9F9F9` (The canvas)
    *   `surface-container-lowest`: `#FFFFFF` (The "Elevated" card or focal point)
    *   `surface-container-low`: `#F3F3F3` (Subtle sectioning)

### The "No-Line" Rule
**Standard 1px solid borders are strictly prohibited for sectioning.** 
Boundaries must be defined by background color shifts. To separate the Hero section from a Product Grid, transition from `surface` to `surface-container-low`. This creates a seamless, "liquid" flow that feels modern and expensive.

### Glass & Gradient Rule
To prevent the UI from feeling flat, use **Glassmorphism** for floating elements (e.g., sticky navigation or hovering "Quick View" buttons). 
*   **Formula:** `surface-container-lowest` at 80% opacity + 12px Backdrop Blur.
*   **Signature Textures:** For high-impact SaaS landing pages, use a subtle linear gradient on primary containers: `primary (#0F172A)` to `primary-container (#131B2E)`. This adds "soul" and prevents the navy from looking "dead" on OLED screens.

---

## 3. Typography: Editorial Authority

The system leverages a dual-font strategy: **Plus Jakarta Sans** for expressive headers and **Inter** for high-legibility utility.

*   **Display & Headlines (Plus Jakarta Sans):** These should be tracked slightly tighter (-2%) to feel "inked" and professional. Use `display-lg` for hero statements to command immediate attention.
*   **Titles & Body (Inter):** Inter handles the heavy lifting of SaaS data and product descriptions. Use `title-md` for product names and `body-md` for descriptions.
*   **The Nigerian Context:** Ensure the Naira symbol (₦) is always set in the same weight as the price value. Use `title-lg` for prices to ensure they are the second most visible element after the product image.

---

## 4. Elevation & Depth

### The Layering Principle
Depth is achieved by "stacking" surface tiers.
*   **Base:** `surface` (#F9F9F9)
*   **Section:** `surface-container-low` (#F3F3F3)
*   **Card/Interactive Element:** `surface-container-lowest` (#FFFFFF)

### Ambient Shadows
When an element must "float" (like a checkout modal or a mobile navigation menu), use a "Tuscan Shadow":
*   **Values:** `0px 20px 40px rgba(15, 23, 42, 0.06)`
*   **Color:** Never use pure black. Use a 6% opacity version of our `on-surface` (#1A1C1C) to mimic natural light.

### The "Ghost Border" Fallback
If an element (like a text input) requires a container on a white background, use the **Ghost Border**: 
*   Token: `outline-variant` at 15% opacity. It should be felt, not seen.

---

## 5. Components

### Buttons
*   **Primary:** `primary` background, `on-primary` text. Border radius: `md (0.75rem)`.
*   **Secondary (Conversion):** `secondary` background. Use this only for the "Final Action" in a flow (e.g., "Pay ₦25,000").
*   **Tertiary:** No background, `primary` text weight 600. Used for "Cancel" or "Learn More."

### Input Fields
*   **Styling:** `surface-container-low` background, no border. On focus, transition to a `ghost border` with a 1px `primary` bottom-stroke. This mimics high-end banking apps.

### Cards & Lists
*   **Constraint:** Forbid the use of divider lines between list items. Use `spacing-4 (1.4rem)` of vertical whitespace to separate items.
*   **Product Cards:** Use `lg (1rem)` border radius. The image should occupy 70% of the card height, with the price and title floating in a `surface-container-lowest` area below.

### Currency Display (Naira)
*   Always use a non-breaking space between ₦ and the value. 
*   **Style:** Bold the currency and value equally to denote financial transparency.

---

## 6. Do’s and Don’ts

### Do
*   **Do** use "Generous Whitespace." If you think there is enough space, add `spacing-2` more.
*   **Do** use Lucide icons in `outline` style with a 1.5px stroke width for a light, airy feel.
*   **Do** use `secondary` (Coral) for "Stock Low" or "Limited Offer" tags to drive SaaS urgency.

### Don’t
*   **Don’t** use 100% black (#000000). It breaks the premium "Digital Atelier" feel.
*   **Don’t** use shadows on cards that are resting on the background; use background color shifts instead.
*   **Don’t** use hard 90-degree corners. Everything must feel "soft-modern" with at least a `sm` radius.
*   **Don’t** crowd the Naira (₦) symbol. Give the price room to breathe as it is the ultimate conversion metric.