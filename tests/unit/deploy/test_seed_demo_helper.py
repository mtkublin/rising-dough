"""T-Q306(c) / ADR-0149 section 4: the drill-only `seed-demo` host helper."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (ROOT / "terraform/cloud-init/bin/seed-demo.tpl").read_text()
USER_DATA = (ROOT / "terraform/modules/compute/user_data.tf").read_text()
MAIN_TF = (ROOT / "terraform/main.tf").read_text()
RENDER_TEST = (ROOT / "terraform/tests/render.tftest.hcl").read_text()


def _body() -> str:
    return SCRIPT[SCRIPT.index("set -Eeuo pipefail") :]


def _main_calls() -> list[str]:
    main = _body().split("main() {", 1)[1]
    return re.findall(r"^\s{2}([a-z_]+)(?: |$)", main, flags=re.M)


def test_strict_mode() -> None:
    assert "set -Eeuo pipefail" in SCRIPT


def test_step_order_in_main() -> None:
    calls = _main_calls()
    order = [
        "preflight",
        "stop_stack",
        "move_local_db_aside",
        "install_demo_db",
        "verify_and_chown",
        "start_stack_and_wait",
    ]
    idx = [calls.index(name) for name in order]
    assert idx == sorted(idx)


def test_stops_app_and_litestream_before_anything_is_moved() -> None:
    stop = _body().split("stop_stack() {", 1)[1].split("\n}", 1)[0]
    assert stop.index("compose stop app") < stop.index("compose stop litestream")


def test_integrity_check_must_be_ok_and_precedes_chown_and_start() -> None:
    verify = _body().split("verify_and_chown() {", 1)[1].split("\n}", 1)[0]
    assert "PRAGMA integrity_check" in verify
    assert '[[ "$${result}" == "ok" ]] || die' in verify
    assert verify.index("die") < verify.index("chown")
    assert "readonly APP_UID=10001" in SCRIPT
    assert 'chown "$${APP_UID}:$${APP_UID}"' in verify


def test_litestream_starts_before_app_then_waits_for_ready() -> None:
    start = _body().split("start_stack_and_wait() {", 1)[1].split("\n}", 1)[0]
    assert start.index("up -d litestream") < start.index("up -d app")
    assert '"$${status}" == "ready"' in start
    assert '"$${db}" == "ok"' in start
    assert "--resolve" in start
    assert " -k" not in start
    assert 'die "/ready did not report' in start


def test_requires_one_absolute_regular_file_argument() -> None:
    pre = _body().split("preflight() {", 1)[1].split("\n}", 1)[0]
    assert '"$#" -eq 1' in pre
    assert "must be absolute" in pre
    assert "! -L" in pre


def test_never_touches_prod_replica_or_credentials() -> None:
    code = "\n".join(ln for ln in SCRIPT.splitlines() if not ln.lstrip().startswith("#"))
    for forbidden in (
        "restore-source",
        "RESTORE_",
        "AGE-SECRET",
        "litestream restore",
        "s3://",
        "source_bucket",
    ):
        assert forbidden not in code


def test_hostname_and_compose_dir_are_template_variables() -> None:
    assert "READY_HOST='${hostname}'" in SCRIPT
    assert "COMPOSE_DIR='${compose_dir}'" in SCRIPT


def test_rendered_only_when_seed_helper_enabled() -> None:
    start = USER_DATA.index("seed-demo.tpl")
    assert "var.enable_seed_helper ?" in USER_DATA[start - 120 : start]
    managed = USER_DATA[USER_DATA.index("var.enable_seed_helper ? [") :]
    entry = managed.split("\n", 2)[1]
    assert "/usr/local/bin/seed-demo" in entry
    assert 'mode = "0755"' in entry


def test_seed_helper_is_drill_only_and_independent_of_restore_key() -> None:
    lines = [ln for ln in MAIN_TF.splitlines() if "enable_seed_helper" in ln]
    assert len(lines) == 1
    assert 'var.env == "drill"' in lines[0]
    assert "scw_access_key_restore" not in lines[0]


def test_render_tftest_asserts_drill_present_and_prod_absent() -> None:
    assert 'run "seed_demo_installed_on_drill"' in RENDER_TEST
    assert 'run "seed_demo_absent_on_prod"' in RENDER_TEST
