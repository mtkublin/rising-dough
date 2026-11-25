# Operator QA decisions, 2026-11-25 (ui/sourdough)

Answered by the operator in the end-of-run QA, 2026-11-25. Binding for the rest of the run; ADR amendments land with the items that apply them.

- Q21 contract-test edits (UR08b 6, UR14 6): APPROVED all 12. Remote session applies them via an implementer, then UR08b and UR14 merge.
- Q26 UR09b drops HX-Refresh after edit save (OOB refresher instead): ACCEPTED. UR09b merges as is.
- Q22 own user row has no row menu: ACCEPTED (ADR-0134 §11).
- Q29 offline outside forms: offline banner only. Suppress the assertive network flash while the offline banner shows; the flash test edit is approved to assert the banner text.
- Q25 stored formula cycle: the amount shows 0.00 with a visible "formula cycle" warning, and changing such a rule is disallowed. My reading: any save that would keep or create a cycle is rejected with the cycle error, so the only allowed edit is one that removes it. Confirm the wording in the ADR.
- Q12 unknown routes: HTML 404 page for browsers (Accept: text/html), JSON 404 for API clients. Update tests/contract/test_errors.py:55-58 to pin both.
- Q15 (F5) unknown or foreign account delete: 404, no toast, the same for unknown and foreign accounts. Update the contract test_accounts.py:383.
- Q13 /budget contract tests: port them to the /plan budget tab at T-UR15, keeping the behaviour pins; /budget redirects to /plan.
- Q1 csrf.js and vendored htmx-2.0.11.min.js: KEEP both. Add keep rows in removal.md and an ADR-0107 §2 amendment naming them. Relocated to `rd/js` by UR15d (ADR-0107 §2 amendment); vendored htmx unchanged.
- Q2 ci.yml shallow checkout: the operator worried about history weight. Measured 1,726 commits, 49 MiB packed. Decision: `fetch-depth: 0` plus `filter: blob:none` (commits and trees only) on the guard job's checkout. This is a CI workflow change that the operator approved here.
- Q14 visual compare speed: ADD a dev-only dependency (Pillow or numpy, whichever suits the decode job better), with an ADR.
- Q16 ADR-0152: CONFIRMED by the operator; note the confirmation in the ADR.
- Q27 /setup copy ("Set up Rising Dough", "Let's get the first loaf in.", "[ create account ]"): KEEP.
- Q28 /setup token in the access log: REDACT the query string for /setup (the path stays logged; the token never reaches the logs).
- Q30 UR21 deviations: ACCEPT both. Signing in automatically lands on /today, and /setup shares the login per-IP rate-limit bucket.
- Q10 (T-UR21a) prod setup-token hash: a GitHub `prod` environment secret, declared in ci_environments.toml, passed by Terraform into the instance env (ADR-0100, ADR-0111). The operator adds the secret value.
- Q9 (T-UR18) invite email: NO-GO for v1. The switch stays off and admins copy the invite link by hand; the code stays. Record this in an ADR-0134 amendment.
- Q11 (T-UR17) release: the remote session stops at a ready PR (CI, e2e and drill-gate green; PR #54 marked ready only with the operator's go, per the human contract). It does NOT dispatch an explore drill; the operator dispatches it and clicks through.
- Design-parity group: FOLLOW THE HANDOFF wherever the app differs. That covers Q3 overlay placeholder, Q4 budget-row bar labels, Q5 empty/future values, Q6 22nd picker entry, Q17 topbar email placement, Q18 the 422 summary box (handoff has none), Q19 category palette names/hex, Q23 "THIS DEVICE", Q24 "Enter an amount above 0.00", and the seed/handoff data mismatches (23 upcoming rows, no header email, chip colours, afford-it states, accounts--empty). Where the handoff is silent (Q7, the "no budget" aria label), keep the current wording. Pinned contract tests that conflict (e.g. "This device" case, 422 summary) may be edited under this decision; it counts as operator approval of those edits.
- Q8 panel.css:45 stylelint deviation (orchestrator call, not asked): keep the vendored CSS byte-identical and keep the one-line config override in rd/.stylelintrc.json, consistent with "follow the handoff".
- Q20 FX rates table: BUILD NOW in v1. New task for the remote session after T-UR15, per the handoff's derived screen.
- Q29 detail: the e2e test_network_failure_shows_flash may be edited to assert the offline banner outside forms (approved above).
