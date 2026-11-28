"""Guard (D10-A, ADR-0147): the visual harness's fixed one-time password never reaches production.

``frozen_server.py`` overrides ``get_token_source`` for the visual server only. Production wiring
must stay the CSPRNG adapter and nothing under ``src/`` may know the board's sample.
"""

from __future__ import annotations

from pathlib import Path

from budget_planner.adapters.entropy import SecretsTokenSource
from budget_planner.web import deps
from budget_planner.web.app import app
from tests.visual.frozen_server import HANDOFF_ONE_TIME_PASSWORD

SRC = Path(__file__).resolve().parents[2] / "src"


def test_default_token_source_is_the_csprng() -> None:
    assert isinstance(deps.get_token_source(), SecretsTokenSource)


def test_production_app_has_no_token_override() -> None:
    assert deps.get_token_source not in app.dependency_overrides


def test_fixed_source_is_not_in_src() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if HANDOFF_ONE_TIME_PASSWORD in path.read_text(encoding="utf-8")
        or "_HandoffTokens" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
