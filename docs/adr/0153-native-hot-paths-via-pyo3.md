# ADR-0153: Native Hot Paths via PyO3, With the Python Implementation as the Oracle

- **Status**: Proposed (accepted once the T-SC13 pilot meets its acceptance criteria)
- **Date**: 2026-11-26
- **Amends**: `requirements.md` §3.1 (stack) once accepted
- **Relates to**: [ADR-0021](0021-functional-style-no-oop.md), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md) §3, [ADR-0123](0123-frontend-stays-server-rendered-no-spa-framework.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md), [ADR-0131](0131-mutation-testing-policy.md), [ADR-0151](0151-capacity-and-scaling-strategy-per-distribution-stage.md), [ADR-0152](0152-python-upgrade-and-native-arm64-dev-interpreter.md)
- **Plan**: [`docs/plans/scaling/tasks.md`](../plans/scaling/tasks.md) T-SC13, T-SC14

## Context

Per-host CPU is the first limit on one box (ADR-0151 §1). A full rewrite in Rust or C is rejected: the unit and service tests call Python, and the prevention regime (architecture guards, import-linter, `mypy --strict`, mutmut, allowlists; ADR-0130) is Python-only. What remains is porting individual **pure, CPU-bound** functions to Rust behind a Python interface.

Per-request data is small (one user's thousands of rows, a 365-day forecast, dozens of recurring rules), so the cost is likely spread across many small steps rather than concentrated in a few loops. Some layers are already native: SQLite, pydantic-core, AES-GCM through `cryptography` (OpenSSL), Argon2 through argon2-cffi. Native ports are therefore chosen from a profile, not by guess.

## Decision

1. **Scope**: only pure functions (no I/O, no clock, no settings; ADR-0021) whose share of request CPU in a py-spy profile under the T-SC05 load justifies the port. Data in, data out; no Rust code touches the DB, HTTP or templates.
2. **The Python implementation stays and is the oracle.** Each native function has a property test (Hypothesis) asserting equal output to the Python version over generated inputs, plus the existing tests run against the native path. Python stays the fallback when the extension is missing (dev convenience), selected in one place; production requires the native build (checked at startup).
3. **Packaging**: one Rust crate in the repo built with maturin into a wheel; built in the Docker image and in CI on the pinned Python (ADR-0152); `cargo fmt`, `clippy -D warnings` and `cargo test` join the pre-commit and CI stack. No `unsafe` outside PyO3 macros.
4. **Guards**: the Python facade module is the canonical owner and is registered in `tests/architecture/canonical_modules.toml`; banned-pattern and purity guards apply to the facade. Mutation testing (ADR-0131) keeps running on the Python oracle.
5. **Pilot: SVG charts** (`web/charts.py`, `web/chart_geometry.py`, about 1,150 lines; ADR-0123). Pure numbers to SVG text, so the oracle check is a byte-equal comparison. The pilot proves the toolchain end to end.
6. **Further candidates, in order, each only if the profile backs it**: recurring occurrence expansion (`services/recurring.pending_occurrences`, `domain/recurring_schedule.py`); forecast roll-ups (`services/forecast.py` day and month chains); the recurring formula evaluator (`services/recurring_formula.py`; first check whether caching the parsed form in Python is enough); after v4, a batch decrypt (`decrypt_many`) to cut one Python call per field per row against the ADR-0081 §3 budget.
7. **Not ported**: aggregates (small N, and they move to Python reductions in v4 anyway), Argon2 and AES (already native), JSON (responses are HTML).

## Consequences

- A Rust toolchain in CI and the image build (build time and image size increase; measured in the pilot).
- A second language to review; kept small by the pure-function scope and the oracle tests.
- CPU headroom per host grows where the profile says it matters, without touching the prevention regime.

## Alternatives considered

- **Full rewrite**: rejected, see Context.
- **minijinja (Rust Jinja engine)**: deferred (ADR-0151 §11). Custom filters, globals and dataclass attribute access call back into Python, so real gains may be far below benchmarks; revisited only with a benchmark of one heavy page.
- **Cython or mypyc**: viable for typed pure-Python modules with less toolchain change; to be compared in the pilot write-up if the PyO3 build cost is high.
