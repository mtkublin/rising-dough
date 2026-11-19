"""A-01 / C-03: JPY account (0 decimals) rendered via template '/ 100.0'."""

import re

from _web import USER_ID, fresh_conn, make_client

from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts

conn = fresh_conn()
accounts.create(conn, USER_ID, NewAccount(name="V1-Yen", currency="JPY", opening_balance=500_000, type="cash"))
conn.commit()
c, _ = make_client()
html = c.get("/today").text
print("stored balance: 500000 JPY (whole yen)")
print("'5,000.00' (100x too small) present on /today:", "5,000.00" in html, "| '500,000.00' present:", "500,000.00" in html)
print("V1-Yen on /today:", "V1-Yen" in html)
h2 = c.get("/accounts").text
i = h2.find("V1-Yen")
print("/accounts card snippet:", " ".join(re.sub(r"<[^>]+>", " ", h2[i:i+1500]).split())[:200])
print("/accounts has 5,000.00:", "5,000.00" in h2, "| 500,000.00:", "500,000.00" in h2)

import re as _re
txt = " ".join(_re.sub(r"<(script|style|svg)[^>]*>.*?</\\1>|<[^>]+>", " ", h2, flags=_re.S).split())
j = txt.find("V1-Yen")
print("card text:", txt[j:j+160])
