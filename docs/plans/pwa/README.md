# Installable Web App (PWA)

> **What**: Rising Dough installs on iOS and Android as a PWA (home-screen icon, standalone window, branded offline page). No native or store app.
> **Decision**: [ADR-0151](../../adr/0151-installable-pwa-as-the-mobile-app.md) (Proposed; options A to E compared there). Requirements: [`docs/requirements.md` §16](../../requirements.md#16-installable-web-app-pwa-added-2026-11-27).
> **Tasks**: [`tasks.md`](tasks.md) (T-PWA01…T-PWA05).

## Open operator decisions

| # | Question | Options | Recommendation | Blocks |
|---|---|---|---|---|
| D1 | Accept ADR-0151 | PWA (A); WebView shell (B); store wrap (C); cross-platform native (D); two native apps (E) | A now; C on Android later only if a Play Store listing is wanted | all |
| D2 | `short_name` under the icon | "Dough" or "Rising Dough" | "Dough" (iOS cuts labels at about 12 characters) | T-PWA01 |

## When

- After the redesign release (`ui/sourdough`, PR #54): the base layout, offline page and icons come from it.
- T-PWA03 (install hint) also waits for the design gate (PR #59).
- Normal release path (ADR-0099); no migration, no Terraform change.
