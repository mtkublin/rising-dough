#!/usr/bin/env bash
# Re-run every Track A differential invariant on the scratch DB (/tmp/audit-A.sqlite).
# Each script re-copies data/demo.sqlite over the scratch DB first; prod is never touched.
set -u
cd "$(dirname "$0")/../../../../.."
mkdir -p docs/plans/quality-audit/repro/A/output
for f in docs/plans/quality-audit/repro/A/inv_*.py; do
  name="$(basename "$f" .py)"
  uv run python "$f" 2>&1 | grep -v -i -e 'warn' -e 'validated_self' -e 'HTTP Request' \
    > "docs/plans/quality-audit/repro/A/output/${name}.txt"
done
