# Vendored test tooling (T-Q300, ADR-0027 amendment 2026-11-23)

- `axe.min.js`: [axe-core](https://github.com/dequelabs/axe-core) **4.10.3**, byte-identical to
  `axe.min.js` in the npm tarball `axe-core@4.10.3` (`npm pack axe-core@4.10.3`). License MPL-2.0
  (`axe-core.LICENSE`). Used only by `tests/e2e/test_axe_sweep.py`; never served by the app, never
  fetched from a CDN at runtime. To upgrade: repack the new version, replace both files, update
  this README and the ADR-0027 amendment, and review new violations as triage tasks.
