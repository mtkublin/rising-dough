#!/usr/bin/env python3
"""H1 repro: static checks on gate integrity, signing identity and permission inheritance.

1. drill-gate-skip.yml: file list source vs status target SHA (TOCTOU), and absence of any
   head-SHA comparison.
2. Prod cosign identity regexp (terraform/modules/compute/user_data.tf) vs SANs a branch build
   would carry (reusable build.yml run from drill.yml on an arbitrary branch).
3. ruleset required checks: any integration_id pinning?
4. release.yml top-level permissions inherited by the called ci.yml job (no permissions block).
5. rollback target validation: does anything require the sha to be on main?
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
API = Path(__file__).parent / "gh_api"
skip = (ROOT / ".github/workflows/drill-gate-skip.yml").read_text()

print("== 1. drill-gate-skip: verdict inputs")
print("file list source :", re.findall(r'gh api --paginate "([^"]+)"', skip))
print("status target    :", re.findall(r"SHA: (\$\{\{[^}]+\}\})", skip))
print("compares head sha with live PR head?:",
      bool(re.search(r"pulls/\$\{PR\}\"? *--jq '?\.head\.sha|head\.sha.*(==|!=)", skip)))

print("\n== 2. cosign identity")
tf = (ROOT / "terraform/modules/compute/user_data.tf").read_text()
rx = re.search(r'identity_regexp = "([^"]+)"', tf).group(1).replace("\\\\", "\\")
rx = rx.replace("${var.github_owner}", "mtkublin").replace("${var.github_repo}", "rising-dough")
print("identity_regexp:", rx)
for ref in ("refs/heads/main", "refs/tags/v3.0.5", "refs/heads/attacker/evil-branch"):
    san = f"https://github.com/mtkublin/rising-dough/.github/workflows/build.yml@{ref}"
    print(f"  SAN ...build.yml@{ref:34s} accepted={bool(re.match(rx, san))}")

print("\n== 3. ruleset required checks")
rs = json.loads((API / "ruleset_protect_main.json").read_text())
for rule in rs["rules"]:
    if rule["type"] == "required_status_checks":
        for c in rule["parameters"]["required_status_checks"]:
            print("  ", c, "-> pinned to an app:", "integration_id" in c)
    if rule["type"] == "pull_request":
        print("   required_approving_review_count =", rule["parameters"]["required_approving_review_count"],
              "code_owner_review =", rule["parameters"]["require_code_owner_review"])
print("   bypass_actors =", rs["bypass_actors"], "| CODEOWNERS present:",
      any((ROOT / p).exists() for p in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")))

print("\n== 4. release.yml -> ci.yml permissions")
rel = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
print("release top-level permissions:", rel["permissions"])
print("ci.yml permissions block (workflow/job):", ci.get("permissions"), ci["jobs"]["ci"].get("permissions"))
print("release job `ci` permissions override  :", rel["jobs"]["ci"].get("permissions"))

print("\n== 5. rollback target validation")
rg = (ROOT / "scripts/ci/ref_guard.py").read_text()
print("ref_guard rollback-target checks ancestry of main?:", "is_ancestor" in rg.split("def resolve_rollback_target")[1].split("def check_ref")[0])
b = yaml.safe_load((ROOT / ".github/workflows/build.yml").read_text())
tags = [m for m in re.findall(r"type=raw,value=[^\n]+", (ROOT / ".github/workflows/build.yml").read_text())]
print("build.yml tags pushed for ANY ref (drill gate builds):", tags[0])
