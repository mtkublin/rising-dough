#!/usr/bin/env bash
# Regenerates docs/plans/quality-audit/inventory/*.txt (T-Q14b). Read-only on src/, stdlib-only, deterministic.
# Run from the repository root: bash docs/plans/quality-audit/repro/inventory/run_all.sh
set -euo pipefail
cd "$(dirname "$0")"
for s in p01_dry p02_functional p03_immutability p04_p07_effects_clock p05_p06_web_repo p08_money \
         p09_p10_p11_imports_size_suppress p12_templates p13_other summary; do
  python3 "$s.py"
done
echo "inventory regenerated in docs/plans/quality-audit/inventory/"
