# Probe record: T-UR04g dialog macro gaps (hero placeholder, typing race, action hx attrs, field_error, budget hero sign)

Task: T-UR04g, branch wi/ui/sourdough/UR04g. ADR-0027, ADR-0107, ADR-0130 section 7, ADR-0150.
Method: integration tests plus Playwright e2e against a scratch live server (temp DB; data/budget.sqlite not touched). The multi-viewport
visual sweep (1440/1024/375, light and dark) is left to the visual-auditor the orchestrator sends into this worktree.

## Probes run

| Probe | Result |
|---|---|
| New entry, JPY account: hero placeholder | "0" (PLN and EUR keep "0.00"); integration `test_hero_placeholder_follows_the_currency_exponent` |
| Typing during a held hero refresh (account switched to JPY, "1234" typed, refresh released) | the amount stays "1234", unit JPY, placeholder "0", saved amount stored as 1234; e2e `test_amount_typed_during_the_hero_refresh_is_kept_and_stored`; the test fails (empty amount) when the restore handler is disabled |
| Hero refresh answers HTTP 500 | the unit shows an em dash; e2e `test_failed_hero_refresh_marks_the_unit_stale` |
| Formula slot trigger | `keyup changed delay:400ms from:#formula-slot` plus change; refresh uses `hx-sync="closest form:drop"` |
| Budget hero, remaining -567822 PLN | "−5,678.22" with U+2212 (`test_budget_hero_prints_a_negative_left_with_the_display_minus`) |
| Category dialog 422 | name/direction/color error paragraphs from `field_error`, id `field-<name>-error` (existing settings e2e journey passes) |
| Parity of existing dialog callers | dev variants and handoff skeleton tests unchanged and green; action hx-include/hx-vals absent unless given |

## Left

Visual sweep at three widths and both themes (new-entry PLN/EUR/JPY, formula typing, budget tab negative hero, category 422).
