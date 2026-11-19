"""Read-only dump of rate-limit + audit rows in the drill DB. Run inside the app container:
   docker exec -i budget-planner-app python -I - < h4_xff_readback.py
Only rows created by the probe (identity contains an ip=...) are meaningful; emails are probe-only."""
import sqlite3

c = sqlite3.connect("file:/data/budget.db?mode=ro", uri=True)
tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print("tables:", [t for t in tabs if "rate" in t or "audit" in t])
for t in tabs:
    if "rate" in t:
        cols = [r[1] for r in c.execute(f"pragma table_info({t})")]
        print(t, cols)
        for r in c.execute(f"select * from {t} order by rowid desc limit 8"):
            print("  ", r)
cols = [r[1] for r in c.execute("pragma table_info(audit_log)")]
print("audit_log cols:", cols)
for r in c.execute("select * from audit_log order by rowid desc limit 5"):
    print("  ", tuple(str(x)[:90] for x in r))
