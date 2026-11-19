#!/usr/bin/env python3
"""H1 repro: static audit of .github/workflows + actions (T-Q18/H1).

Prints, from the workflow files and the recorded GitHub config (gh_api/*.json):
  1. triggers per workflow, and which can start from an arbitrary branch
  2. action pinning (every `uses:` must be a local path or a 40-hex SHA)
  3. `${{ }}` expressions interpolated directly into `run:` scripts
  4. job -> environment -> protection -> secret NAMES (the trust-boundary table)
  5. the prod-grade secrets reachable by an unapproved branch workflow
Usage: python3 workflow_audit.py   (read-only, no network)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
WF = ROOT / ".github" / "workflows"
ACT = ROOT / ".github" / "actions"
API = Path(__file__).parent / "gh_api"

SHA = re.compile(r"^[^@]+@[0-9a-f]{40}$")
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)
UNTRUSTED = re.compile(
    r"\b(inputs\.|github\.event\.|github\.head_ref|github\.ref_name|steps\.[\w-]+\.outputs\.|needs\.[\w-]+\.outputs\.)"
)
# secrets whose value would let the holder read/tamper prod data or reach prod infra
PROD_GRADE = {  # pragma: allowlist secret
    "LITESTREAM_AGE_IDENTITY": "age identity: decrypts the prod Litestream replica",  # pragma: allowlist secret
    "APP_SCW_SECRET_KEY": "Litestream app key: read/write/delete on the env bucket",  # pragma: allowlist secret
    "PROD_REPLICA_RO_SECRET_KEY": "restore-reader key: reads the PROD replica",  # pragma: allowlist secret
    "PROD_REPLICA_RO_ACCESS_KEY": "restore-reader key id",  # pragma: allowlist secret
    "TS_OAUTH_SECRET": "Tailscale OAuth (auth_keys write, tag:automation owns tag:ci/prod/drill)",  # pragma: allowlist secret
    "SCW_SECRET_KEY": "Scaleway CI key of that env",  # pragma: allowlist secret
    "GHCR_PULL_PAT": "GHCR read PAT",  # pragma: allowlist secret
    "DEPLOY_SSH_PRIVATE_KEY": "operator SSH key for the drill VM",  # pragma: allowlist secret
}


def load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text())
    if True in doc:  # PyYAML parses the key `on` as boolean True
        doc["on"] = doc.pop(True)
    return doc


def triggers(doc: dict) -> list[str]:
    on = doc.get("on")
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return list(on)
    return list((on or {}).keys())


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    wfs = {p.name: load(p) for p in sorted(WF.glob("*.yml"))}

    section("1. triggers")
    for name, doc in wfs.items():
        ev = triggers(doc)
        flags = []
        if "pull_request" in ev:
            flags.append("PR-branch (same-repo PRs get env secrets)")
        if "pull_request_target" in ev:
            flags.append("PULL_REQUEST_TARGET")
        if "workflow_dispatch" in ev:
            flags.append("dispatch from ANY branch (needs write)")
        if "workflow_run" in ev:
            flags.append("WORKFLOW_RUN")
        print(f"{name:34s} {','.join(ev):40s} {'; '.join(flags)}")

    section("2. unpinned `uses:` (empty = all pinned)")
    bad = 0
    files = list(WF.glob("*.yml")) + list(ACT.glob("*/action.yml"))
    for p in files:
        for m in re.finditer(r"^\s*-?\s*uses:\s*(\S+)", p.read_text(), re.M):
            ref = m.group(1)
            if ref.startswith("./") or SHA.match(ref):
                continue
            bad += 1
            print(f"UNPINNED {p.relative_to(ROOT)}: {ref}")
    print(f"unpinned count: {bad}; docker:// refs:",
          sum("docker://" in p.read_text() for p in files))

    section("3. expressions interpolated into run: scripts")
    for name, doc in wfs.items():
        for jid, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                run = step.get("run")
                if not run:
                    continue
                for expr in EXPR.findall(run):
                    tag = "UNTRUSTED-CONTEXT" if UNTRUSTED.search(expr) else "safe-context"
                    if tag == "UNTRUSTED-CONTEXT":
                        print(f"{name}:{jid}:{step.get('name') or step.get('id')}: {{{{{expr.strip()}}}}}")

    section("4. job -> environment -> protection -> secret names")
    envs = {e["name"]: e for e in json.loads((API / "environments.json").read_text())["environments"]}
    secret_names: dict[str, list[str]] = {}
    for f in API.glob("secrets_*.json"):
        env = f.stem.removeprefix("secrets_").replace("_", "-")
        secret_names[env] = [s["name"] for s in json.loads(f.read_text())["secrets"]]
    for env, e in envs.items():
        rules = [r["type"] for r in e["protection_rules"]]
        pol = e["deployment_branch_policy"]
        print(f"env {env:14s} reviewers={'required_reviewers' in rules!s:5s} "
              f"branch_policy={'custom' if pol else 'NONE (all branches)'}")
    print()
    binders: dict[str, set[str]] = {}
    for name, doc in wfs.items():
        for jid, job in (doc.get("jobs") or {}).items():
            env = job.get("environment")
            if env is None:
                continue
            raw = env["name"] if isinstance(env, dict) else env
            lits = set(re.findall(r"'([a-z-]+)'", str(raw))) or {str(raw)}
            if "inputs.env" in str(raw) or "matrix.env" in str(raw):
                lits |= {"prod", "drill"}
            for lit in lits:
                binders.setdefault(lit, set()).add(f"{name}:{jid}")
    for env, jobs in sorted(binders.items()):
        print(f"{env:14s} <- {', '.join(sorted(jobs))}")

    section("5. prod-grade secrets in environments with NO reviewers")
    for env, names in sorted(secret_names.items()):
        e = envs.get(env, {})
        gated = any(r["type"] == "required_reviewers" for r in e.get("protection_rules", []))
        hits = [n for n in names if n in PROD_GRADE]
        print(f"{env:14s} gated={gated!s:5s} branch_policy={'custom' if e.get('deployment_branch_policy') else 'none':6s} "
              f"prod-grade secrets: {len(hits)}")
        if not gated:
            for n in hits:
                print(f"    {n:28s} {PROD_GRADE[n]}")


if __name__ == "__main__":
    main()
