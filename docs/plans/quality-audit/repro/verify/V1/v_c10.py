"""A-08 / C-10 / A-19: boundary inputs -> HTTP status."""

from _web import fresh_conn, make_client

fresh_conn().close()
c, _ = make_client()
cases = [
    ("GET", "/budget?year=abc", None),
    ("GET", "/budget?year=99999&month=1", None),
    ("GET", "/today/afford?amount=nan", None),
    ("GET", "/today/afford?amount=inf", None),
    ("GET", "/today/afford?amount=1e999", None),
    ("GET", "/today/afford?amount=1e300", None),
    ("POST", "/accounts/1/reconcile", {"actual_balance": "NaN"}),
    ("POST", "/accounts/1/reconcile", {"actual_balance": "Infinity"}),
    ("POST", "/accounts/1/reconcile", {"actual_balance": "1e400"}),
    ("POST", "/accounts", {"name": "x", "currency": "PLN", "opening_balance": "NaN"}),
    ("POST", "/accounts", {"name": "x", "currency": "PLN", "opening_balance": "1e30"}),
    ("GET", "/plan?year=99999", None),
    ("GET", "/ledger?page_size=1000000", None),
]
for m, url, data in cases:
    r = c.get(url) if m == "GET" else c.post(url, data=data)
    print(f"{m:4s} {url:32s} {str(data or ''):55s} -> {r.status_code}")
