# ADR-0153: Pillow as a Dev-Only Dependency for the Visual Compare Decode

- **Status**: Accepted (orchestrator, 2026-11-25; operator decision Q14, `docs/plans/ui-redesign/operator-decisions-2026-11-25.md`)
- **Date**: 2026-11-25
- **Amends**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (visual compare harness: "stdlib-only PNG diff, no Pillow; a stack change needs an ADR")
- **Related**: [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md), [ADR-0027](0027-frontend-toolchain-hardening.md)
- **Tasks**: T-UR42a

## Context

`tests/visual/handoff.py` compares page screenshots against the designer handoff PNGs. It decodes PNGs with a hand-written stdlib decoder (`_decode`: zlib plus a per-byte Python loop for the Sub, Average and Paeth filters). Filters Sub, Average and Paeth are inherently serial per byte, so large screenshots (full-page captures at 1440 px and wider) spend most of the compare time in Python loops. The operator decided (Q14, 2026-11-25) to add a dev-only dependency for the decode rather than keep the stdlib decoder.

## Decision

1. **Pillow** (`pillow>=10.4`) joins the `dev` dependency group in `pyproject.toml`. It is never a runtime dependency; `src/` does not import it, and the import-linter and purity contracts are unchanged.
2. Only `_decode` in `tests/visual/handoff.py` changes: it opens the file with `PIL.Image`, requires 8-bit RGB or RGBA (the layouts the stdlib decoder accepted; anything else still raises `ValueError`), and returns the same `(width, height, channels, raw bytes)` tuple. The diff mask, cluster scan, ratio and size-mismatch logic are untouched, so pixel-diff counts, ratios and the tolerance semantics are bit-identical. The `_png` writer in the same module stays as is (small, write-only).
3. **Why Pillow, not numpy**: the job is "decode a PNG to raw interleaved bytes". Pillow does that in C (libpng/zlib-ng bundled in the wheel) with one call (`Image.tobytes()`), and the downstream code already works on `bytes` (big-int XOR). numpy would also need a PNG decoder (it has none), so it would only help the diff step, which is not the bottleneck. Pillow is also needed by Playwright-adjacent tooling in later tasks (cropping, overlays) without another dependency. Size: the Pillow wheel is about 4 MB (about 12 MB installed); numpy is larger (about 16 MB wheel) and does not solve decode. Wheels: Pillow ships manylinux (x86_64, aarch64) and macOS (x86_64, arm64) wheels for CPython 3.12 (the dev platforms: Linux CI container and macOS).
4. Supply chain: Pillow is pinned by `uv.lock`; `pip-audit` already covers the dev group.

## Consequences

- Visual compare decode time drops (measurements in the T-UR42a commit message); behaviour is identical, pinned by `tests/visual/test_compare.py` and `tests/visual/test_reference_mapping.py`.
- One more dev dependency to keep patched. The stdlib decoder (about 60 lines) is deleted.
- `docs/requirements.md` section 3 lists the dev tooling; it gains Pillow.
