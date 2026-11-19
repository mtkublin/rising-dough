"""CI rules for Terraform-declared host state: `scripts/ci/host_release.py` (T-D129, ADR-0111)."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("host_release", ROOT / "scripts/ci/host_release.py")
assert _spec is not None
assert _spec.loader is not None
hr = importlib.util.module_from_spec(_spec)
sys.modules["host_release"] = hr
_spec.loader.exec_module(hr)

A = "sha-aaaaaaa@sha256:" + "a" * 64
B = "sha-bbbbbbb@sha256:" + "b" * 64
C = "v1.2.3@sha256:" + "c" * 64
FULL_A = "ghcr.io/o/budget-planner:" + A


# --- refs -------------------------------------------------------------------


def test_release_records_current_as_previous() -> None:
    assert hr.resolve_refs(new=B, current=A, current_previous="") == hr.Refs(B, A)


def test_rerun_of_same_release_keeps_recorded_previous() -> None:
    assert hr.resolve_refs(new=B, current=B, current_previous=A) == hr.Refs(B, A)


def test_first_apply_has_no_previous() -> None:
    assert hr.resolve_refs(new=A, current="", current_previous="") == hr.Refs(A, "")


def test_plan_without_new_ref_keeps_state() -> None:
    assert hr.resolve_refs(new="", current=B, current_previous=A) == hr.Refs(B, A)


def test_plan_only_falls_back_to_placeholder() -> None:
    assert hr.resolve_refs(new="", current="", current_previous="", plan_only=True) == hr.Refs(
        hr.PLACEHOLDER, ""
    )


def test_plan_without_any_ref_is_refused() -> None:
    with pytest.raises(hr.ReleaseError, match="no image ref"):
        hr.resolve_refs(new="", current="", current_previous="")


def test_rollback_swaps_to_recorded_previous() -> None:
    assert hr.resolve_refs(new="", current=B, current_previous=A, rollback=True) == hr.Refs(A, B)


def test_rollback_to_explicit_target() -> None:
    assert hr.resolve_refs(new=C, current=B, current_previous=A, rollback=True) == hr.Refs(C, B)


@pytest.mark.parametrize(("current", "previous"), [(B, ""), (A, A)])
def test_rollback_without_usable_target_is_refused(current: str, previous: str) -> None:
    with pytest.raises(hr.ReleaseError, match="rollback"):
        hr.resolve_refs(new="", current=current, current_previous=previous, rollback=True)


def test_destroy_never_needs_a_real_ref() -> None:
    assert hr.resolve_refs(new="", current="", current_previous="", destroy=True) == hr.Refs(
        hr.PLACEHOLDER, ""
    )
    assert hr.resolve_refs(new="", current=A, current_previous=B, destroy=True) == hr.Refs(A, "")


@pytest.mark.parametrize(
    "bad",
    [
        "sha-1234567",
        "main",
        "sha-1@sha256:" + "a" * 63,
        "x y@sha256:" + "a" * 64,
        "-x@sha256:" + "a" * 64,
    ],
)
def test_refs_must_be_digest_pinned(bad: str) -> None:
    with pytest.raises(hr.ReleaseError, match="sha256"):
        hr.resolve_refs(new=bad, current="", current_previous="")


def test_refs_cli_prints_github_output_lines(capsys: pytest.CaptureFixture[str]) -> None:
    rc = hr.main(["refs", "--new", B, "--current", A])

    assert rc == 0
    assert capsys.readouterr().out == f"ref={B}\nprevious={A}\n"


def test_refs_cli_refuses_with_annotation(capsys: pytest.CaptureFixture[str]) -> None:
    assert hr.main(["refs"]) == 1
    assert capsys.readouterr().err.startswith("::error::")


# --- wait -------------------------------------------------------------------


def _status(**over: object) -> dict[str, object]:
    return {"generation": "g2", "state": "ok", "running_ref": FULL_A, "error": ""} | over


def test_converged_requires_generation_state_and_running_ref() -> None:
    assert hr.converged(_status(), "g2", FULL_A)
    assert not hr.converged(None, "g2", FULL_A)
    assert not hr.converged(_status(generation="g1"), "g2", FULL_A)
    assert not hr.converged(_status(state="applying"), "g2", FULL_A)
    assert not hr.converged(_status(running_ref="other"), "g2", FULL_A)


def test_converged_raises_when_this_generation_failed() -> None:
    with pytest.raises(hr.ReleaseError, match="cosign_verify"):
        hr.converged(_status(state="failed", error="cosign_verify"), "g2", FULL_A)
    assert not hr.converged(_status(generation="g1", state="failed"), "g2", FULL_A)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_wait_polls_until_converged() -> None:
    answers: list[Mapping[str, object] | None] = [None, _status(generation="g1"), _status()]
    clock = _Clock()

    def fetch(_url: str) -> Mapping[str, object] | None:
        return answers.pop(0)

    result = hr.wait_converged(
        fetch, "https://h/s", "g2", FULL_A, timeout=60, interval=10, clock=clock, sleep=clock.sleep
    )

    assert result["generation"] == "g2"
    assert clock.now == 20


def test_wait_times_out_with_last_status() -> None:
    clock = _Clock()

    with pytest.raises(hr.ReleaseError, match="did not converge"):
        hr.wait_converged(
            lambda _url: _status(state="applying"),
            "https://h/s",
            "g2",
            FULL_A,
            timeout=30,
            interval=10,
            clock=clock,
            sleep=clock.sleep,
        )


def test_wait_cli(capsys: pytest.CaptureFixture[str]) -> None:
    rc = hr.main(
        ["wait", "--url", "https://h/s", "--generation", "g2", "--ref", FULL_A],
        fetch=lambda _url: _status(),
    )

    assert rc == 0
    assert "converged" in capsys.readouterr().out


def test_fetch_status_requires_https() -> None:
    with pytest.raises(hr.ReleaseError, match="https"):
        hr.fetch_status("http://h/s")


# --- resolve-ref (T-D133) ---------------------------------------------------

DIGEST_A = "sha256:" + "a" * 64


def test_resolve_ref_joins_tag_and_digest() -> None:
    seen: list[str] = []

    def inspect(image_tag: str) -> str:
        seen.append(image_tag)
        return f'"{DIGEST_A}"\n'

    assert hr.resolve_ref("ghcr.io/o/budget-planner", "v1.2.3", inspect) == f"v1.2.3@{DIGEST_A}"
    assert seen == ["ghcr.io/o/budget-planner:v1.2.3"]


def test_resolve_ref_rejects_non_digest_output() -> None:
    with pytest.raises(hr.ReleaseError, match="sha256 digest"):
        hr.resolve_ref("ghcr.io/o/x", "main", lambda _t: "null")


def test_resolve_ref_rejects_bad_tag() -> None:
    with pytest.raises(hr.ReleaseError, match="not valid"):
        hr.resolve_ref("ghcr.io/o/x", "a b", lambda _t: DIGEST_A)


def test_resolve_ref_cli_prints_output_line(capsys: pytest.CaptureFixture[str]) -> None:
    rc = hr.main(
        ["resolve-ref", "--image", "ghcr.io/o/x", "--tag", "sha-abc1234"],
        inspect=lambda _t: DIGEST_A,
    )

    assert rc == 0
    assert capsys.readouterr().out == f"ref=sha-abc1234@{DIGEST_A}\n"


def test_resolve_ref_cli_reports_failure(capsys: pytest.CaptureFixture[str]) -> None:
    def boom(_t: str) -> str:
        raise hr.ReleaseError("cannot inspect")

    rc = hr.main(["resolve-ref", "--image", "i", "--tag", "main"], inspect=boom)

    assert rc == 1
    assert "cannot inspect" in capsys.readouterr().err


# --- VM replacement (T-D156, ADR-0127) --------------------------------------

RESTORED = {
    "result": "restored",
    "generation": "2901fbd3873a6696",  # pragma: allowlist secret
    "at": "t",
}


def test_require_restore_needs_a_restored_report() -> None:
    assert hr.converged(_status(restore=RESTORED), "g2", FULL_A, require_restore=True)
    # Not converged yet: no verdict on the restore.
    assert not hr.converged(
        _status(state="applying", restore=None), "g2", FULL_A, require_restore=True
    )


@pytest.mark.parametrize(
    "restore",
    [None, {"result": "empty"}, {"result": "skipped-db-present"}, "restored", {}],
)
def test_require_restore_fails_fast_when_converged_without_restore(restore: object) -> None:
    with pytest.raises(hr.ReleaseError, match="did not restore"):
        hr.converged(_status(restore=restore), "g2", FULL_A, require_restore=True)


def test_without_require_restore_the_report_is_ignored() -> None:
    assert hr.converged(_status(restore={"result": "empty"}), "g2", FULL_A)


def test_wait_cli_passes_require_restore(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["wait", "--url", "https://h/s", "--generation", "g2", "--ref", FULL_A]

    assert hr.main([*args, "--require-restore"], fetch=lambda _u: _status()) == 1
    assert "did not restore" in capsys.readouterr().err
    assert hr.main([*args, "--require-restore"], fetch=lambda _u: _status(restore=RESTORED)) == 0


def _plan(*changes: tuple[str, list[str]]) -> dict[str, object]:
    return {
        "resource_changes": [
            {"address": addr, "change": {"actions": actions}} for addr, actions in changes
        ]
    }


SERVER = "module.compute.scaleway_instance_server.app"


@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        (["delete", "create"], True),
        (["create", "delete"], True),  # create_before_destroy
        (["update"], False),
        (["no-op"], False),
        (["create"], False),  # first-ever apply
        (["delete"], False),  # destroy
    ],
)
def test_server_replaced(actions: list[str], expected: bool) -> None:
    plan = _plan(("tailscale_tailnet_key.vm", ["delete", "create"]), (SERVER, actions))
    assert hr.server_replaced(plan) is expected


def test_server_replaced_false_when_server_absent_and_other_resources_replaced() -> None:
    assert hr.server_replaced(_plan(("tailscale_tailnet_key.vm", ["delete", "create"]))) is False


def test_server_replaced_rejects_malformed_plans() -> None:
    with pytest.raises(hr.ReleaseError, match="resource_changes"):
        hr.server_replaced({})
    with pytest.raises(hr.ReleaseError, match="actions"):
        hr.server_replaced({"resource_changes": [{"address": SERVER, "change": {}}]})


def test_server_address_matches_terraform() -> None:
    assert hr.SERVER_ADDRESS == SERVER
    assert 'module "compute"' in (ROOT / "terraform" / "main.tf").read_text()
    compute = (ROOT / "terraform" / "modules" / "compute" / "main.tf").read_text()
    assert 'resource "scaleway_instance_server" "app"' in compute


OLD_ID = "pl-waw-2/0e39bbe5-f2e5-4991-9740-1c3c8022b232"


def _with_prior(plan: dict[str, object], server_id: object = OLD_ID) -> dict[str, object]:
    server = {
        "address": SERVER,
        "values": {
            "id": server_id,
            "user_data": {"bp-config": "TOPSECRET"},
        },  # pragma: allowlist secret
    }
    child = {"address": "module.compute", "resources": [server]}
    return {**plan, "prior_state": {"values": {"root_module": {"child_modules": [child]}}}}


def test_replaced_cli_prints_only_the_output_lines(capsys: pytest.CaptureFixture[str]) -> None:
    plan = _with_prior(_plan((SERVER, ["delete", "create"])))
    plan["variables"] = {"cookie_secret": {"value": "TOPSECRET"}}  # pragma: allowlist secret
    rc = hr.main(["replaced"], stdin=lambda: json.dumps(plan))

    out = capsys.readouterr()
    assert rc == 0
    # T-D157: the drain target, and nothing else of the plan.
    assert out.out == f"replaced=true\nserver_id={OLD_ID}\n"
    assert "TOPSECRET" not in out.out + out.err


def test_replaced_cli_in_place_prints_no_server_id(capsys: pytest.CaptureFixture[str]) -> None:
    rc = hr.main(["replaced"], stdin=lambda: json.dumps(_plan((SERVER, ["update"]))))

    assert rc == 0
    assert capsys.readouterr().out == "replaced=false\n"


@pytest.mark.parametrize("bad", ["not-an-id", "pl-waw-2/../x", 5, None])
def test_prior_server_id_must_be_zone_and_uuid(bad: object) -> None:
    with pytest.raises(hr.ReleaseError, match="zone"):
        hr.prior_server_id(_with_prior(_plan(), bad))


def test_prior_server_id_missing_is_refused() -> None:
    with pytest.raises(hr.ReleaseError, match="prior_state"):
        hr.prior_server_id(_plan())
    empty: dict[str, object] = {"prior_state": {"values": {"root_module": {"resources": []}}}}
    with pytest.raises(hr.ReleaseError, match="not in the prior state"):
        hr.prior_server_id(empty)


# --- drain (T-D157, ADR-0127 amendment) --------------------------------------

REQ = "44513330068-1"


def _drained(**over: object) -> dict[str, object]:
    return {"state": "drained", "drain": {"request": REQ, "at": "t"}} | over


def test_drained_needs_the_same_request() -> None:
    assert hr.drained(_drained(), REQ)
    assert not hr.drained(None, REQ)
    assert not hr.drained(_status(), REQ)
    assert not hr.drained(_drained(drain={"request": "other"}), REQ)
    assert not hr.drained(_drained(drain=None), REQ)


def test_drain_failure_fails_fast_but_other_failures_wait() -> None:
    mine = {"request": REQ, "at": ""}
    with pytest.raises(hr.ReleaseError, match="drain_litestream"):
        hr.drained(_status(state="failed", error="drain_litestream", drain=mine), REQ)
    # A failed config generation is not a drain verdict.
    assert not hr.drained(_status(state="failed", error="compose"), REQ)
    # Review finding: a stale failure from another request keeps waiting.
    old = {"request": "1-1", "at": ""}
    assert not hr.drained(_status(state="failed", error="drain_litestream", drain=old), REQ)


def test_wait_drained_polls_then_times_out() -> None:
    clock = _Clock()
    answers: list[Mapping[str, object] | None] = [_status(), _drained()]
    assert (
        hr.wait_drained(
            lambda _u: answers.pop(0),
            "https://h/s",
            REQ,
            timeout=60,
            interval=5,
            clock=clock,
            sleep=clock.sleep,
        )["state"]
        == "drained"
    )
    with pytest.raises(hr.ReleaseError, match="did not drain"):
        hr.wait_drained(
            lambda _u: _status(),
            "https://h/s",
            REQ,
            timeout=10,
            interval=5,
            clock=clock,
            sleep=clock.sleep,
        )


def test_wait_drained_rejects_bad_request_ids() -> None:
    with pytest.raises(hr.ReleaseError, match="request id"):
        hr.wait_drained(lambda _u: None, "https://h/s", "a b;rm", timeout=1, interval=1)


def test_wait_drained_cli(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["wait-drained", "--url", "https://h/s", "--request", REQ]
    assert hr.main(args, fetch=lambda _u: _drained()) == 0
    assert "drained" in capsys.readouterr().out


# --- drain-capable (T-D158, ADR-0127 amendment 2) --------------------------


@pytest.mark.parametrize("drain", [None, {"request": REQ, "at": ""}])
def test_drain_capable_accepts_any_drain_field(drain: object) -> None:
    hr.drain_capable(_status(drain=drain))


def test_drain_capable_refuses_a_pre_t_d157_agent() -> None:
    # The v3.0.5 agent's status (release run 44539030541): no `drain` field.
    with pytest.raises(hr.ReleaseError, match="cannot drain"):
        hr.drain_capable(_status())


def test_wait_status_retries_then_times_out() -> None:
    clock = _Clock()
    answers: list[Mapping[str, object] | None] = [None, _status()]
    got = hr.wait_status(
        lambda _u: answers.pop(0),
        "https://h/s",
        timeout=60,
        interval=5,
        clock=clock,
        sleep=clock.sleep,
    )
    assert got["state"] == "ok"
    with pytest.raises(hr.ReleaseError, match="no host status"):
        hr.wait_status(
            lambda _u: None,
            "https://h/s",
            timeout=10,
            interval=5,
            clock=clock,
            sleep=clock.sleep,
        )


def test_drain_capable_cli(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["drain-capable", "--url", "https://h/s"]
    assert hr.main(args, fetch=lambda _u: _status(drain=None)) == 0
    assert "can drain" in capsys.readouterr().out
    assert hr.main(args, fetch=lambda _u: _status()) == 1
    assert "::error::host agent cannot drain" in capsys.readouterr().err


def test_replaced_cli_never_echoes_bad_input(capsys: pytest.CaptureFixture[str]) -> None:
    rc = hr.main(["replaced"], stdin=lambda: "not json TOPSECRET")

    out = capsys.readouterr()
    assert rc == 1
    assert "TOPSECRET" not in out.out + out.err
    assert "::error::" in out.err
