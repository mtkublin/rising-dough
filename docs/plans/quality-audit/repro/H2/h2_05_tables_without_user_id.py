"""H2: list tables with no user_id column in a freshly migrated scratch DB, and which of those are
reachable for writes from non-admin routes. Run: uv run python docs/plans/quality-audit/repro/H2/h2_05_tables_without_user_id.py | grep -v '^{"event"'
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import fresh, q  # noqa: E402

fresh()
for (t,) in q("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by 1"):
    cols = [r[1] for r in q(f"pragma table_info({t})")]
    if "user_id" not in cols:
        print(f"{t:32s} no user_id | columns: {','.join(cols)[:100]}")
