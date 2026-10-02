<!-- impeccable:design-schema 1 -->
# OmniDome Design System & Visual Language

Guided by the **Impeccable Design Standard** (Paul Bakaus). Used by designers, developers, and AI agents for all frontend engineering across OmniDome web applications, customer portals, and technician mobile interfaces.

---

## 1. Visual World: "Obsidian Telecom"
A high-precision, dark-mode-first telecommunications control room aesthetic inspired by high-reliability infrastructure consoles, Bloomberg terminals, and modern fiber telemetry hubs.

### Color Palette
Avoid generic "AI slop" gradients (e.g. purple-to-blue `from-indigo-500` or raw gray-on-black). Every color is intentionally tinted:

- **Surface & Backgrounds**:
  - `bg-background`: Deep Obsidian Black (`#0a0d14` / hsl(222, 47%, 6%))
  - `bg-card`: Muted Slate-Carbon (`#111726` / hsl(222, 40%, 10%))
  - `border-border`: Subtly tinted blue-slate border (`#1e293b` / hsl(217, 33%, 17%))
- **Primary Telecom Accent**:
  - `text-primary` / `bg-primary`: High-luminance Cyan (`#06b6d4` / hsl(189, 94%, 43%)) representing fiber-optic light.
- **Secondary Accents**:
  - **Network Health / Online**: Vivid Emerald (`#10b981` / hsl(160, 84%, 39%))
  - **Faults / Alarms / Churn**: Warm Crimson (`#ef4444` / hsl(0, 84%, 60%))
  - **Pending / In Review / Feasibility**: Solar Amber (`#f59e0b` / hsl(38, 92%, 50%))
  - **VIP / Enterprise Tier**: Royal Cobalt (`#3b82f6` / hsl(217, 91%, 60%))

---

## 2. Typography & Hierarchy
- **Display Headings**: Clean, high-impact Sans with tight tracking (`tracking-tight font-semibold`).
- **Data & Telemetry Values**: High-contrast tabular numbers, metrics, and currency (`font-mono`, `text-foreground`).
- **Body & Captions**: Crisp Slate (`text-muted-foreground` / hsl(215, 20%, 65%)). Never pure `#888888` gray on colored backgrounds.

---

## 3. Layout, Elevation & Card Rhythm
- **No Nested Cards**: Do not nest a bordered card inside another bordered card. Use flat dividers (`border-t border-border/40`), tinted row backgrounds, or open whitespace.
- **Visual Rhythm**: Use consistent vertical cadence (`space-y-6` for pages, `gap-4` for grids).
- **Subtle Elevation**: Ambient edge highlights (`shadow-sm`, border highlight on hover `hover:border-primary/40`).

---

## 4. Impeccable Anti-Pattern Rules (Enforced by CLI & Agent)
1. **No Generic AI Color Tells**: Never use `from-indigo-500 to-purple-600` or generic cyan-purple glow tiles.
2. **No Gray Text on Colored Tiles**: When rendering status badges or alert banners, use matched tinted text with low-opacity backgrounds (`bg-emerald-500/10 text-emerald-400`).
3. **No Decorative Icon Tiles on Every Header**: Use icons only when they clarify actionability or domain identity.
4. **No Jittery Transitions**: Use predictable transitions (`transition-colors duration-150 ease-out`). Avoid bounce or elastic easing.
5. **Full Mobile Adaptation**: Every desktop multi-column grid must cleanly reflow on mobile screens (`grid-cols-1 md:grid-cols-2 lg:grid-cols-4`).
