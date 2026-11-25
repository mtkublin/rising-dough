# Rising Dough — Sourdough

The design system of Rising Dough, a modern, minimalist and simple budget planner. One system, two themes: **light** (white and apricot, the default) and **dark** (near-black and oven orange). Both themes share every font, shape, component and token name; a screen switches theme by swapping colour values only.

The tokens are generated from the app's shipped stylesheet (`docs/design/rising-dough-frontend/static/css/tokens.css` in the Rising Dough repo). A token name here is the CSS custom property without `--`: `color-ground` is `var(--color-ground)`, `space-4` is `var(--space-4)`. Design with these names, never with raw values, so every board works in both themes.

## Principles

- **Simple.** Every key screen has two zones: a `color-bake` field with one big figure, and a `color-panel` below with the detail in mono.
- **Modern.** Big Unbounded figures, mono data and art made from type (ASCII loaves, block-character bars).
- **Minimalist.** Three colours do the work: `color-bake` for the hero, `color-now-fill` for the one current thing, `color-over` for overspend. Everything else is ink on ground.
- **Rising Dough, kept alive.** An ASCII loaf in `color-crumb` is printed into the bake field behind the hero number and gets denser as savings grow. Charts are rows of loaves; the current one is `color-now-fill`.

## Content fundamentals

- Two voices, split by font. Figures and headlines in Unbounded are wide, bold and confident: "842 zł", "Fresh out of the oven." Labels and data in Geist Mono are dry and lowercase: "left to spend", "rent 80%".
- Lead with the number, then what it means: "842 zł · ↑ 96 zł on october".
- Dough words for wins only ("proofing", "risen", "fresh out of the oven"). Never in warnings or errors.
- Bracketed labels for primary actions: "[ add expense ]".

## Visual foundations

**Colour.** `color-ground` everywhere; the `color-bake` field once per screen at the top, with `color-ink-deep` text and `color-crumb` ASCII behind it. The `color-panel` rises under it. `color-now-fill` marks one current thing per view (`color-now` when it is text). Every now-fill shape carries the 1px `color-now-edge` ring (`--ring-now`): it holds the shape at 3:1 or more in light and is invisible in dark. `color-over` marks overspend and is never an orange. `color-past` is for old loaves.

- Light: white ground, a slightly warmer panel, pale apricot bake, oven-orange now-fill, burnt-orange now text, deep-berry over. No lime.
- Dark: near-black ground, full oven-orange bake, lime now and now-fill, pink over.

**Type.** Unbounded 700 for every figure and headline (`mega`, `display`, `title` and the hero sizes): wide, geometric, tight negative tracking; keep it to short strings. Geist Mono for everything else: labels (`heading`), rows (`data`), sentences (`body`), timestamps (`caption`) and ASCII. Fonts are vendored files, not Google Fonts.

**Shape.** Soft outside, sharp inside. The bake field and panel use `radius-lg`; buttons, chips and loaf tops use `radius-pill`. Data rows and block cells are square (`radius-none`) with `color-rule` hairlines.

**Bars.** Over-time charts are loaves: domed `radius-pill` tops, `radius-sm` bases, past loaves in `color-past`, the current one in `color-now-fill`. Category progress is ten mono block cells (█ filled, ░ empty).

**Spacing and size.** A 4px base: `space-4` gutters, `space-6` bake field padding, `space-8` between the figure and the panel. Every touch target is at least `size-control` (44px).

**Motion.** Loaves rise from the baseline with a small overshoot, staggered 40ms. Reduced motion shows the final frame only.

## Iconography

Prefer mono text glyphs (↑ ↓ + − →). Icons, when needed, are a 1.5px outline set at 16–20px in `color-ink` on panel and `color-ink-deep` on bake.

## Logo

No logo yet. Set "Rising Dough" in Unbounded 700, tight tracking. The system label form is `RISING_DOUGH` in Geist Mono.

## Designing with this system

- Draw every screen, component and state twice, light and dark, side by side.
- Use token names only; a colour that is not a token is a new token request, not a hex in a board.
- Phone boards are 375 wide, tablet 1024, desktop 1440.
