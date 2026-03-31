# Frontend Design Guidelines

Visual and interaction patterns for the Agentic PM frontend. Follow these rules when building or modifying any page or component.

---

## 1. Design Tokens

All colors, spacing, and typography are defined as CSS custom properties in `:root`. Never use hardcoded values — always reference tokens.

### Colors

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#101012` | Page background (warm charcoal) |
| `--bg-elevated` | `#18181C` | Cards, sidebar, elevated surfaces |
| `--surface` | `#1F1F25` | Inputs, chips, nested containers |
| `--surface-2` | `#26262E` | Hover states on surface elements |
| `--surface-3` | `#2E2E38` | Active/selected states |
| `--line` | `rgba(255,255,255,0.06)` | Default borders |
| `--line-strong` | `rgba(255,255,255,0.10)` | Emphasized borders |
| `--text` | `#A8A8B4` | Body text |
| `--text-bright` | `#EDEDF0` | Headings, strong values, emphasis |
| `--text-secondary` | `#75758A` | Labels, metadata, secondary info |
| `--muted` | `#5E5E72` | Placeholder text, disabled, section titles |
| `--brand` | `#3AAFA8` | Primary accent (teal/viridian) |
| `--brand-hover` | `#32998E` | Brand hover state |
| `--brand-glow` | `rgba(58,175,168,0.14)` | Brand tinted backgrounds |
| `--brand-subtle` | `rgba(58,175,168,0.06)` | Subtle brand tint |
| `--success` | `#4CAE6F` | Success states |
| `--danger` | `#D45454` | Errors, high-risk indicators |
| `--warning` | `#D4943A` | Warnings, at-risk indicators |

### Typography

- **UI font**: `var(--font)` — Sora. Geometric, distinctive, readable at small sizes. Used everywhere.
- **Monospace**: `var(--mono)` — IBM Plex Mono. **Only** for code blocks and code citations. Never for labels, values, timestamps, or badges.
- **Base size**: 13px body, 12px compact elements, 11px metadata, 10px micro labels.
- **Weights**: 400 (body), 500 (medium emphasis), 600 (section titles, labels), 700 (values, strong).
- **Letter-spacing**: -0.01em to -0.03em for headings (tighter = more confident). Default (0) for body. 0.06em+ for micro uppercase labels.

### Spacing & Radii

- `--radius`: 6px (default border-radius — precise, not bubbly)
- `--radius-lg`: 10px (cards, modals)
- Padding: 12-14px for cards, 6-10px for compact items, 4-8px for chips/badges
- Gaps: 6-10px between items, 4-6px for tight stacks
- `--t`: 120ms ease (default transition)

---

## 2. Page Structure

Every page follows the same vertical flow:

```
┌─ Summary Bar ────────────────────────────────────┐
│ stat | stat | stat | stat          [Action Button]│
└──────────────────────────────────────────────────┘
┌─ Toolbar / Tabs / Filters ───────────────────────┐
│ [select] [select] [search input]                  │
└──────────────────────────────────────────────────┘
┌─ Content ────────────────────────────────────────┐
│ Table / Cards / Detail panel                      │
└──────────────────────────────────────────────────┘
```

### Summary Bar

Use `.setup-summary-bar` at the top of every page. Contains inline stats separated by `.setup-summary-sep` dividers, and optionally an action button on the right.

```tsx
<div className="setup-summary-bar">
  <div className="setup-summary-stats">
    <span>{count} items</span>
    <span className="setup-summary-sep" />
    <span>{other} stat</span>
  </div>
  <button className="meetings-new-btn">
    <FontAwesomeIcon icon={faPlus} /> Action
  </button>
</div>
```

### Toolbar / Filters

Use `.meetings-toolbar` + `.meetings-filter-group` for filter rows. Selects and inputs sit in a horizontal flex row.

```tsx
<div className="meetings-toolbar">
  <div className="meetings-filter-group">
    <select>...</select>
    <input className="meetings-search" placeholder="Search..." />
  </div>
</div>
```

### Tabs

Use `.delivery-tabs` for tabbed content. Each tab is a `.delivery-tab` button with optional `.delivery-tab-count` badge. Active tab gets `.active` class.

```tsx
<div className="delivery-tabs">
  <button className={`delivery-tab ${active ? "active" : ""}`}>
    Label <span className="delivery-tab-count">{n}</span>
  </button>
  <button className="meetings-new-btn delivery-tab-action">
    <FontAwesomeIcon icon={faPlus} /> Action
  </button>
</div>
```

---

## 3. Tables

Always use `simple-table compact-table` for data tables. Wrap in `.simple-table-wrap` for horizontal scroll on small screens.

```tsx
<div className="simple-table-wrap">
  <table className="simple-table compact-table">
    <thead><tr><th>...</th></tr></thead>
    <tbody><tr><td>...</td></tr></tbody>
  </table>
</div>
```

- Header text: uppercase, 10px, `--muted`, letter-spacing 0.06em
- Row padding: 8px vertical, hover background `--surface`
- Selected rows: class `row-selected` (brand-tinted left border + background)
- Primary column values wrapped in `<strong>` for `--text-bright` color

---

## 4. Modals

All modals use the same structure:

```tsx
<div className="modal-overlay" role="dialog" aria-modal="true">
  <div className="modal-card settings-modal-card">
    <div className="modal-head">
      <h3>Title</h3>
      <div className="modal-head-actions">
        <button>Save</button>
        <button className="ghost docs-action-btn" onClick={onClose} title="Close">X</button>
      </div>
    </div>
    <div className="form-grid">
      <label>Field <input /></label>
      <label className="full-span">Wide field <textarea /></label>
    </div>
  </div>
</div>
```

- `.modal-card` default width: `min(480px, 100%)`
- `.settings-modal-card` for wider forms: `min(960px, 100%)`
- `.form-grid` is a 2-column CSS grid; use `.full-span` or `.wide` for spanning both columns
- Modal overlay: semi-transparent black backdrop with centered card
- Use an icon-only `X` close button in the modal header, with `ghost docs-action-btn`
- Put primary modal actions next to the close button in the header when the workflow benefits from immediate save/confirm actions

---

## 5. Chips & Badges

### Status chips

```tsx
<span className="chip small">status_label</span>
```

Small uppercase text in a subtle bordered pill. Used for entity types, statuses, source types.

### Kind badges

For deliverable/milestone type indicators:

```tsx
<span className="dashboard-kind deliverable">D</span>
<span className="dashboard-kind milestone">MS</span>
```

22px square rounded badge with colored background.

### Count badges

```tsx
<span className="delivery-tab-count">{n}</span>
<span className="docs-version-count">{n}</span>
```

Tiny (10px) bold text in a subtle background pill. Used in tabs, section headers.

### Status indicators (documents)

```tsx
<span className="doc-status doc-indexed">indexed</span>
<span className="doc-status doc-failed">failed</span>
<span className="doc-status doc-uploaded">uploaded</span>
```

Colored uppercase micro text (10px). Green for indexed, red for failed, brand for uploaded.

---

## 6. Icon Patterns

### Source/type icons

Small 22px rounded squares with tinted backgrounds:

```tsx
<span className="meetings-source-icon">
  <FontAwesomeIcon icon={faFileLines} />
</span>
```

Default: brand-tinted. Use inline styles or modifier classes for variants (green, red).

### KPI chip icons

20px rounded squares with brand background:

```tsx
<span className="dashboard-kpi-chip-icon">
  <FontAwesomeIcon icon={faLayerGroup} />
</span>
```

### Action buttons (icon-only)

```tsx
<button className="ghost docs-action-btn" title="Reindex">
  <FontAwesomeIcon icon={faRotate} />
</button>
```

26px square, transparent background, hover shows brand tint.

---

## 7. Action Buttons

### Primary action button (in summary bar)

```tsx
<button className="meetings-new-btn">
  <FontAwesomeIcon icon={faPlus} /> Label
</button>
```

Brand-bordered, brand-tinted background, 12px font, inline-flex with icon + text.

### Ghost button

Default `.ghost` class: transparent background, muted text, hover reveals background.

### Collapsible toggle

```tsx
<button className={`meetings-assistant-toggle ${open ? "open" : ""}`}>
  <FontAwesomeIcon icon={faRobot} />
  <span>Label</span>
  <FontAwesomeIcon icon={faChevronDown} className="meetings-toggle-chevron" />
</button>
```

Bordered, muted text, brand-tinted on hover/open, chevron rotates 180deg when open.

---

## 8. Detail / Expandable Panels

Used for meeting content, version history, etc. Always bordered + rounded, with a head and scrollable body:

```tsx
<div className="meetings-detail-section">
  <div className="meetings-detail-head">
    <div className="meetings-detail-info">...</div>
    <button className="meetings-assistant-toggle">...</button>
  </div>
  <div className="meetings-content-scroll">
    <pre className="meetings-content-text">{content}</pre>
  </div>
</div>
```

- `max-height` set to keep content above the fold (e.g., `calc(100vh - 460px)`)
- `overflow-y: auto` for scrollbar
- Animation: `dropdown-in` (0.15s ease) on reveal

---

## 9. Alerts

Used in the dashboard Attention section:

```tsx
<div className="dashboard-alert error">
  <FontAwesomeIcon icon={faExclamationTriangle} />
  <div>
    <strong>Code</strong>
    <p>Description</p>
  </div>
</div>
```

- Flex layout with icon + content
- Left border colored by severity: `.error` (red), `.warning` (yellow), `.ok` (green)
- Icon color matches the severity
- Stack alerts with 4px gap

---

## 10. Side Column Stats

For compact stat blocks in sidebars or narrow columns:

```tsx
<div className="dashboard-side-stats three">
  <div className="dashboard-side-stat">
    <FontAwesomeIcon icon={faFileLines} />
    <strong>{n}</strong>
    <span>label</span>
  </div>
</div>
```

- Grid of 2 or 3 columns (use `.three` modifier for 3)
- Each stat: bordered surface box, flex row, icon + bold value + muted label
- Add `.danger` or `.warning` class for colored emphasis

---

## 11. Layout Rules

### Single-column flow

Most pages (Meetings, Documents, Delivery) use a **single-column** layout: summary bar → toolbar → content. No side-by-side splits for primary content.

### Two-column grid (Dashboard only)

Dashboard uses a `1.7fr / 0.9fr` grid with main column + side column. The side column contains compact stat cards, reporting dates, and partner load.

### Three-column grid (Assistant only)

The assistant uses `200px / 1fr / 260px`: thread sidebar + chat area + context sidebar. The chat area is height-constrained to `calc(100vh - 160px)` with internal scroll.

### Responsive breakpoints

- `1280px`: collapse grids to single column, wrap flex strips
- `768px`: collapse form grids, stack summary bars, wrap all flex containers

---

## 12. Animation

- **Transitions**: 120ms ease (`var(--t)`) for hover/focus states
- **Dropdown reveal**: `dropdown-in` keyframe (opacity 0→1, translateY -6px→0, 0.15s ease)
- **Chat messages**: `chat-msg-in` keyframe (opacity 0→1, translateY 8px→0, 0.25s ease)
- **Typing indicator**: `chat-typing-bounce` (translateY 0→-4px, infinite 0.6s)
- **No excessive animation**: one animation per element max. Prefer CSS transitions over keyframes for interactive states.

---

## 13. Do / Don't

### Do

- Use summary bars on every page for at-a-glance stats
- Use `simple-table compact-table` for all data tables
- Keep padding tight: 6-14px, never more than 16px
- Use `--text-bright` for primary values, `--text-secondary` for labels
- Use chips (`.chip.small`) for inline status/type labels
- Use modals for create/edit forms, not inline panels
- Constrain scrollable areas with `max-height` + `overflow-y: auto`
- Use `setup-summary-sep` dividers between inline stats

### Don't

- Don't use JetBrains Mono for anything except code blocks
- Don't use side-by-side column layouts for content areas (except Dashboard and Assistant)
- Don't use large icons (keep to 9-14px in UI elements)
- Don't add excessive padding or margins — density is intentional
- Don't use grid layouts where flex suffices (stat rows, filter bars, chip strips)
- Don't create custom table markup (divs with grid) — use `<table>` elements
- Don't use `min-height` on scrollable containers — use `height`/`max-height`
- Don't add borders heavier than 1px (except 3px left border on alerts)
