#!/usr/bin/env bash
# Extract the caddy binary from prod's digest-pinned image (ADR-0027 amendment 2026-11-24).
# Usage: fetch_caddy.sh <image-ref e.g. caddy:2.8@sha256:...> <output-path>
# The perf job runs inside the Playwright container (no docker daemon), so the image is read from
# the registry API. Every manifest and blob is verified against its sha256 digest before use.
set -euo pipefail

ref="$1"
out="$2"
digest="${ref##*@}"
repo="library/${ref%%:*}"
registry="https://registry-1.docker.io/v2/${repo}"
accept="application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

token="$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${repo}:pull" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"

fetch() { # <manifest-or-blob path> <dest>
  curl -fsSL -H "Authorization: Bearer ${token}" -H "Accept: ${accept}" -o "$2" "${registry}/$1"
}
verify() { # <file> <sha256:hex>
  echo "${2#sha256:}  $1" | sha256sum -c --quiet -
}

fetch "manifests/${digest}" "$work/m.json"
verify "$work/m.json" "$digest"
platform_digest="$(python3 - "$work/m.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
for e in m.get("manifests", []):
    p = e.get("platform", {})
    if p.get("os") == "linux" and p.get("architecture") == "amd64":
        print(e["digest"])
        break
PY
)"
if [ -n "$platform_digest" ]; then
  fetch "manifests/${platform_digest}" "$work/m.json"
  verify "$work/m.json" "$platform_digest"
fi
layers="$(python3 -c 'import json,sys; print(*[l["digest"] for l in json.load(open(sys.argv[1]))["layers"]])' "$work/m.json")"

for layer in $layers; do
  fetch "blobs/${layer}" "$work/layer.tgz"
  verify "$work/layer.tgz" "$layer"
  if tar -tzf "$work/layer.tgz" | grep -qx 'usr/bin/caddy'; then
    tar -xzf "$work/layer.tgz" -C "$work" usr/bin/caddy
    install -m 0755 "$work/usr/bin/caddy" "$out"
    echo "caddy extracted from ${ref} layer ${layer} -> ${out}"
    exit 0
  fi
done
echo "usr/bin/caddy not found in ${ref}" >&2
exit 1
