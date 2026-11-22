# Audit 2026-11-21: plan year view crawl (T-D-UT07-1)

Scope: no template or CSS change; crawler change only (`tests/e2e/test_crawl.py`, `crawl_inventory.json`).

Routes checked on a seeded scratch DB (the crawler's seed), Chromium:

| Route | 375 | 1024 | 1440 |
|---|---|---|---|
| `/plan?tab=year` | scrollWidth 375 = clientWidth 375 | 1024 = 1024 | 1440 = 1440 |
| `/budget/yearly` (bare htmx fragment) | 2000 vs 375 | 2000 vs 1024 | 2000 vs 1440 |

Finding: the reported 2000px scroll comes from loading the fragment on its own, without the page layout. Users open `/plan?tab=year`, which has no page-level horizontal scroll, no overflowing elements, no console errors, no failed requests, no duplicate ids (crawl diagnostics at 375 and 1440). T-D-UT07-1 is a crawler artefact, resolved by crawling the host page.

Behaviour contract (Step 3b): no template change, nothing to check.
