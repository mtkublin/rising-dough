import sqlite3
from decimal import Decimal
from budget_planner.domain.money import to_minor_units
c=sqlite3.connect(":memory:")
c.execute("create table t(id integer primary key, a integer)")
for label,v in [("id=2**63",2**63),("amount 1e17 major->minor",to_minor_units(Decimal("1e17"),"PLN"))]:
    try: c.execute("select * from t where id=?" if label.startswith("id") else "insert into t(a) values(?)",(v,)); print(label,"ok",v)
    except Exception as e: print(label,type(e).__name__,e)
