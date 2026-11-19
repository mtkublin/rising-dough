#!/usr/bin/env python3
"""H1 repro: security.yml builds pip-audit args from the PR-controlled .security-allowlist.yml.

Extracts the real heredoc from security.yml, feeds it a crafted allowlist, and shows (a) the
resulting `run:` line after ${{ }} substitution and (b) GITHUB_OUTPUT newline injection.
Nothing is executed; the shell line is only printed.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
wf = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())
steps = wf["jobs"]["pip-audit"]["steps"]
build = next(s for s in steps if s.get("id") == "allowlist")["run"]
script = re.search(r"<<'PY'[^\n]*\n(.*?)\n\s*PY", build, re.S).group(1)
script = "\n".join(line[10:] if line.startswith(" " * 10) else line for line in script.splitlines())
run_line = next(s for s in steps if s.get("name") == "Run pip-audit")["run"]

ALLOWLISTS = {
    "benign ignore of a real CVE (D Q1: PR self-serves a pip-audit bypass)":
        "pip_audit:\n  - cve: PYSEC-2026-3552\n    reason: x\n",
    "shell metacharacters in cve":
        "pip_audit:\n  - cve: 'X; echo INJECTED-$(id -un)'\n    reason: x\n",
}
for label, text in ALLOWLISTS.items():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / ".security-allowlist.yml").write_text(text)
        out = subprocess.run([sys.executable, "-I", "-c", script], cwd=d, capture_output=True, text=True).stdout
    val = out.strip().split("=", 1)[1]
    print(f"[{label}]\n  GITHUB_OUTPUT: {out.strip()}")
    print("  shell line  :", run_line.strip().splitlines()[-1].replace("${{ steps.allowlist.outputs.ignore_args }}", val))

# newline in cve -> an extra GITHUB_OUTPUT key (output injection into later steps)
with tempfile.TemporaryDirectory() as d:
    (Path(d) / ".security-allowlist.yml").write_text('pip_audit:\n  - cve: "A\\nevil=1"\n')
    out = subprocess.run([sys.executable, "-I", "-c", script], cwd=d, capture_output=True, text=True).stdout
print("[newline in cve] GITHUB_OUTPUT lines:", out.strip().splitlines())
