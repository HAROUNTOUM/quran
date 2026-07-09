# Hafez Design System — Single Source of Truth

Date: 2026-07-04

Canonical reference for the platform's visual language. Every screen, component, drawer, and workspace must use these tokens and component recipes.

---

## 1. Color tokens

Source of truth: the `tailwind.config` block in `templates/base.html`. **Never introduce raw hex outside this scale.**

### Primary — emerald (brand)
| Token | Hex | Use |
|-------|-----|-----|
| primary-50 | `#ecfdf5` | tint backgrounds (chips, hovered nav) |
| primary-100 | `#d1fae5` | subtle fills |
| primary-500 | `#10b981` | gradients, accents |
| primary-600 | `#059669` | **primary buttons, links, active nav** |
| primary-700 | `#047857` | button hover, gradients |
| primary-800/900 | `#065f46` / `#064e3b` | sidebar gradient depth |

### Accent — amber
`accent-500 #f59e0b` / `accent-600 #d97706` — review/attention actions, "murajaa" chips.

### Semantic (Tailwind defaults)
| Meaning | Classes |
|---------|---------|
| Success / present / memorized | `green-*` |
| Warning / pending / acceptable | `amber-*` |
| Danger / absent / weak | `red-*` |
| Info / online / upcoming | `blue-*` |
| Mastered | `cyan-*` |
| Neutral text | `gray-800` body, `gray-500` secondary, `gray-400` muted |
| Borders | `gray-100` (cards), `gray-200` (inputs) |

---

## 2. Typography

- **Family:** `Tajawal` (Google Fonts, weights 300/400/500/700/800/900), RTL.
- **Scale:**
  | Role | Classes |
  |------|---------|
  | Page heading | `text-lg font-bold text-gray-800` |
  | Section title | `text-sm font-semibold text-gray-700` |
  | Body | `text-sm text-gray-600` |
  | Meta / caption | `text-xs text-gray-400` |
  | Stat number | `text-2xl font-bold` (semantic color) |
  | Micro label | `text-[10px]` tracking-wider for nav group titles |

---

## 3. Spacing, radius, elevation

- **Radius:** cards & panels `rounded-2xl`; controls `rounded-xl`; small chips `rounded-lg`.
- **Card:** `bg-white rounded-2xl border border-gray-100 p-5`. No shadow at rest; `hover:shadow-md` for clickable.
- **Spacing:** card padding `p-5`, gaps `gap-3/gap-4`, section rhythm `mb-6`.
- **Elevation:** flat by default; `shadow-md` hover, `shadow-xl` dropdowns, `shadow-2xl` toasts.

---

## 4. Shared components (`templates/dashboard/components/`)

Build once, reuse everywhere. Each is a pure `{% include %}` partial.

### `page_toolbar.html`
Compact page header: title + optional subtitle on left, actions slot on right.

```
{% include "dashboard/components/page_toolbar.html" with title="..." subtitle="..." actions="..." %}
```

### `tab_bar.html`
Horizontal workspace tabs. Takes `tabs` list: `[{label, url, active, badge?}]`.

```
{% include "dashboard/components/tab_bar.html" with tabs=tabs %}
```

### `status_chip.html`
One chip renderer keyed by status `value` (→ semantic tone) with an optional
`tone` override (`success|info|warning|danger|neutral`) and `label`. Uses
**literal** Tailwind classes per tone — never build class names dynamically
(`bg-{{ c }}-50`), the CDN won't generate them.

```
{% include "dashboard/components/status_chip.html" with value=obj.status label=obj.get_status_display %}
```

### `data_table.html`
Table shell with client-side search (Alpine), sticky header, empty state, optional bulk-select. Rows passed as context.

```
{% include "dashboard/components/data_table.html" with columns=columns rows=rows include_toolbar=True %}
```

### `metric_strip.html`
Responsive grid row wrapping `stat_card.html`. Takes `metrics` list + `cols`.

```
{% include "dashboard/components/metric_strip.html" with metrics=metrics cols=4 %}
```

### `drawer.html`
Right-side slide-over (Alpine). Listens for `@open-drawer` custom event with `{url, title}`. Loads content via fetch.

```
{% include "dashboard/components/drawer.html" with title="التفاصيل" %}
```

### `filter_bar.html`
Sticky pill filters row. Takes `filters` list: `[{url, label, active, count?}]`.

```
{% include "dashboard/components/filter_bar.html" with filters=filters %}
```

### `form_field.html`
Label + help + error + control wrapper. Replaces copy-pasted input class strings.

```
{% include "dashboard/components/form_field.html" with label="الاسم" field=form.name required=True %}
```

### `skeleton.html`, `error_state.html`, `empty_state.html`
Loading/error/empty triad. `empty_state.html` lives in `partials/`; skeleton and error_state in `components/`.

---

## 5. Component recipes (canonical class strings)

**Primary button:** `py-2.5 px-5 bg-primary-600 text-white text-sm font-medium rounded-xl hover:bg-primary-700 transition-colors`
**Secondary button:** `py-2.5 px-5 bg-gray-100 text-gray-600 text-sm font-medium rounded-xl hover:bg-gray-200 transition-colors`
**Input:** `w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500`
**Status chip:** `px-2.5 py-1 rounded-lg text-xs font-medium` + semantic `bg-*-50 text-*-700`
**Card:** `bg-white rounded-2xl border border-gray-100 p-5`
**Table header:** `bg-gray-50 text-gray-500 text-xs`
**Table cell:** `px-4 py-3 text-sm`

---

## 6. Enforcement rules

1. No raw hex, ad-hoc spacing, or one-off radii — only the tokens above.
2. New UI reuses a shared component before inventing markup.
3. One icon set (Heroicons outline), one font (Tajawal), one card style.
4. Every list has an empty state; every destructive action a confirm modal.
5. Sidebar entries name **task workspaces**, not database models.
