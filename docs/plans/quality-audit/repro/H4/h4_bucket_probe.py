"""H4: what can the DRILL's own S3 credentials LIST? Read-only; never reads objects.
Run on the drill host:
  AK=$(docker inspect budget-planner-litestream --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^SCW_ACCESS_KEY=//p')
  SK=...(same for SCW_SECRET_KEY)
  docker exec -i -e AK -e SK budget-planner-app python -I - < h4_bucket_probe.py
Output: bucket NAMES visible, and for each only the HTTP status of a ListObjectsV2 max-keys=1
(object keys of non-drill buckets are never printed)."""
import datetime, hashlib, hmac, os, re, urllib.request, urllib.error

AK, SK = os.environ["AK"], os.environ["SK"]
REGION, HOST = "pl-waw", "s3.pl-waw.scw.cloud"


def _h(k, m):
    return hmac.new(k, m.encode(), hashlib.sha256).digest()


def req(path="/", query="", host=HOST):
    t = datetime.datetime.now(datetime.timezone.utc)
    amz, d = t.strftime("%Y%m%dT%H%M%SZ"), t.strftime("%Y%m%d")
    ph = hashlib.sha256(b"").hexdigest()
    ch = f"host:{host}\nx-amz-content-sha256:{ph}\nx-amz-date:{amz}\n"
    sh = "host;x-amz-content-sha256;x-amz-date"
    cr = f"GET\n{path}\n{query}\n{ch}\n{sh}\n{ph}"
    scope = f"{d}/{REGION}/s3/aws4_request"
    sts = f"AWS4-HMAC-SHA256\n{amz}\n{scope}\n{hashlib.sha256(cr.encode()).hexdigest()}"
    k = _h(_h(_h(_h(("AWS4" + SK).encode(), d), REGION), "s3"), "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    auth = f"AWS4-HMAC-SHA256 Credential={AK}/{scope}, SignedHeaders={sh}, Signature={sig}"
    r = urllib.request.Request(f"https://{host}{path}" + (f"?{query}" if query else ""),
                               headers={"x-amz-date": amz, "x-amz-content-sha256": ph, "Authorization": auth})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


st, body = req("/")
print("ListBuckets status", st)
buckets = re.findall(r"<Name>([^<]+)</Name>", body) if st == 200 else []
print("buckets visible:", buckets)
for b in buckets:
    st, body = req("/", "list-type=2&max-keys=1&prefix=db%2F", host=f"{b}.{HOST}")
    n = len(re.findall(r"<Key>", body)) if st == 200 else "-"
    print(f"  LIST {b}: status={st} keys_in_page={n}")
