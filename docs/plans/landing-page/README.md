# Public Landing Page

> **What**: a static landing page on `https://rising-dough.eu` (product info + a button into the app); the app stays on its own subdomain.
> **Decision**: [ADR-0151](../../adr/0151-public-landing-page-on-the-root-domain.md) (Proposed). Requirements: [`docs/requirements.md` §13](../../requirements.md#13-public-landing-page-added-2026-11-26).
> **Tasks**: [`tasks.md`](tasks.md) (T-LP01…T-LP07).

## Open operator decisions

| # | Question | Options | Recommendation | Blocks |
|---|---|---|---|---|
| D1 | Host (ADR-0151 §6.1) | Scaleway Object Storage website (operator preference) or GitHub Pages | GitHub Pages if a public repo is acceptable; else Scaleway bucket + Edge Services on `www.` once its price is known. Note: a bucket website alone cannot serve HTTPS on the root domain. | T-LP03, T-LP04 |
| D2 | App subdomain (ADR-0151 §6.2) | keep `budget.` or move to `app.` | `app.` in the same release window as the landing page, or `budget.` for good; never later | T-LP06 |

## When

- T-LP01 (facts for D1) can start now.
- T-LP02 (design) waits for PR #59 (design gate, ADR-0154 / ADR-0155) to merge, which itself waits for `ui/sourdough` (PR #54).
- T-LP03…T-LP05 after D1 and T-LP02.
- T-LP06 only if D2 = `app.`, best in the same window as T-LP05.

```
T-LP01 ─ D1 ─┐
PR #59 ─ T-LP02 ─┴─ T-LP03 ─ T-LP04 ─ T-LP05
                          D2 = app. ─ T-LP06 (same window as T-LP05)
T-LP07 closes the plan
```

## Cost

| Item | Cost |
|---|---|
| Domain, Scaleway DNS records, Let's Encrypt | already paid / free |
| GitHub Pages, public repo | free |
| GitHub Pages, private repo | paid GitHub plan |
| Scaleway bucket storage | cents per month |
| Scaleway Edge Services (needed for HTTPS on a custom domain) | monthly plan, price to check at T-LP01 |
| Prod Caddy proxying the bucket (stopgap) | free |
