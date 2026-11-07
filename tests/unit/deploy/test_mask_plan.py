"""T-D83 / ADR-0098: plan-output masking filter and wiring. No network."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "terraform" / "scripts" / "mask_plan.py"

_spec = importlib.util.spec_from_file_location("mask_plan", SCRIPT)
assert _spec is not None and _spec.loader is not None
mask_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mask_plan)

# Obvious dummies; built by concatenation so detect-secrets has nothing to flag.
AGE = "AGE-SECRET-" + "KEY-1" + "DUMMY" * 6
TSKEY = "tskey-" + "auth-kDUMMY123CNTRL-DUMMYdummy456"
GHP = "ghp_" + "DUMMY" * 5
PAT = "github_pat_" + "DUMMY_dummy" * 3
SCW = "SCW" + "DUMMY0DUMMY0DUMMY"


@pytest.mark.parametrize("secret", [AGE, TSKEY, GHP, PAT, SCW])
def test_secret_shapes_are_masked(secret: str) -> None:
    line = f'  - "key={secret}" -> (known after apply)\n'
    out = mask_plan.mask_line(line)
    assert secret not in out
    assert "key=***" in out


def test_non_secret_lines_are_untouched() -> None:
    line = "  ~ resource scaleway_instance_server.app will be updated in-place\n"
    assert mask_plan.mask_line(line) == line


def test_several_secrets_on_one_line() -> None:
    out = mask_plan.mask_line(f"a={AGE} b={TSKEY} c={GHP}")
    assert out == "a=*** b=*** c=***"


def test_cli_filters_stdin() -> None:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no user input
        [sys.executable, "-I", str(SCRIPT)],
        input=f"before\n{AGE}\nafter\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout == "before\n***\nafter\n"


def test_workflow_pipes_plan_output_through_filter() -> None:
    wf = (ROOT / ".github" / "workflows" / "terraform.yml").read_text()
    assert "scripts/mask_plan.py" in wf
    assert "terraform plan -no-color -input=false -lock=false -out=plan.bin | tee" not in wf
    assert "::add-mask::" in wf


def test_justfile_has_safe_plan_recipe() -> None:
    assert "tf-plan-safe env:" in (ROOT / "justfile").read_text()
