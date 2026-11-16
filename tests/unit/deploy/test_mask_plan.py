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


# --- T-D85: heredoc redaction + secret-named keys ---------------------------

REMOVAL = """\
      ~ user_data                        = {
          - "cloud-init"            = <<-EOT
                #cloud-config
                write_files:
                  - content: |
                      BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD: "dummy-pw"  # pragma: allowlist secret
                      plain: dummy-value
            EOT
        } -> (known after apply)
"""


def _run(text: str) -> str:
    return "".join(mask_plan.mask_lines(text.splitlines(keepends=True)))


def test_prior_value_cloud_init_heredoc_is_redacted() -> None:
    out = _run(REMOVAL)
    assert "dummy" not in out
    assert "#cloud-config" not in out
    assert '- "cloud-init"            = <<-EOT\n' in out
    assert "(redacted by mask_plan.py: 5 lines)" in out
    assert "            EOT\n" in out
    assert "} -> (known after apply)" in out


def test_added_heredoc_is_redacted() -> None:
    text = "  + cloud_init = <<EOT\n    secret-ish body\nEOT\n  + other = 1\n"
    out = _run(text)
    assert "secret-ish body" not in out
    assert "(redacted by mask_plan.py: 1 lines)" in out
    assert out.endswith("EOT\n  + other = 1\n")


@pytest.mark.parametrize("key", ["user_data", "user-data", '"user-data"', "~ cloud_init"])
def test_key_variants_are_redacted(key: str) -> None:
    out = _run(f"{key} = <<-EOT\nbody\nEOT\n")
    assert "body" not in out


def test_other_delimiter_word_and_nesting() -> None:
    text = (
        "      + user_data = {\n"
        '          + "cloud-init" = <<-CONFIG\n'
        "                EOT\n"
        "                inner line\n"
        "            CONFIG\n"
        "        }\n"
    )
    out = _run(text)
    assert "inner line" not in out
    assert "(redacted by mask_plan.py: 2 lines)" in out
    assert "            CONFIG\n        }\n" in out


def test_non_cloud_init_heredoc_is_left_alone() -> None:
    text = '  + policy = <<-EOT\n      {"Version": "2012-10-17"}\n    EOT\n'
    assert _run(text) == text


def test_patterns_still_masked_in_normal_lines() -> None:
    assert _run(f"x = {AGE}\n") == "x = ***\n"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('ADMIN_INITIAL_PASSWORD: "abc"\n', 'ADMIN_INITIAL_PASSWORD: "***"\n'),
        ("      cookie_secret: abc\n", '      cookie_secret: "***"\n'),
        ("S3_SECRET_KEY=abc\n", "S3_SECRET_KEY=***\n"),
        ("access_key = abc\n", "access_key = ***\n"),
        ("TS_AUTHKEY=abc\n", "TS_AUTHKEY=***\n"),
        ("age_identity: abc\n", 'age_identity: "***"\n'),
        ("GH_TOKEN=abc", "GH_TOKEN=***"),
    ],
)
def test_secret_named_keys_are_masked(line: str, expected: str) -> None:
    assert mask_plan.mask_line(line) == expected


@pytest.mark.parametrize("line", ["lock_passwd: false\n", "name: monkey\n", "PASSWORD_POLICY:\n"])
def test_unrelated_keys_are_untouched(line: str) -> None:
    assert mask_plan.mask_line(line) == line


def test_unterminated_heredoc_redacts_to_eof() -> None:
    out = _run("  + cloud_init = <<-EOT\n    a\n    b\n")
    assert out.endswith("(redacted by mask_plan.py: 2 lines)\n")
    assert "    a" not in out
