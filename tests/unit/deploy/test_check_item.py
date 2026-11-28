"""Executable Definition of Done for orchestrated items (T-Q326, ADR-0150 §4). No git."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("check_item", ROOT / "scripts/ci/check_item.py")
assert _spec is not None and _spec.loader is not None
check_item = importlib.util.module_from_spec(_spec)
sys.modules["check_item"] = check_item
_spec.loader.exec_module(check_item)


def test_branch_without_commits_fails() -> None:
    assert check_item.check_ahead(0).line() == (
        "FAIL ahead: the item branch has no commits beyond the work branch"
    )
    assert check_item.check_ahead(3).line() == "PASS ahead: 3 commit(s)"


def test_unowned_file_fails_and_names_it() -> None:
    changed = ["src/a.py", "tests/unit/test_a.py", "src/b.py"]
    finding = check_item.check_owned(changed, ["src/a.py", "tests/unit/*"])
    assert finding.line() == "FAIL owned: not owned: src/b.py"


def test_missing_owned_list_only_warns() -> None:
    assert check_item.check_owned(["src/a.py"], []).level == "WARN"


def test_hotspot_needs_a_literal_owned_path() -> None:
    changed = ["docs/CHANGELOG.md", "docs/plans/v3/tasks.md", "src/a.py"]
    broad = check_item.check_hotspots(changed, ["docs/*", "src/a.py"])
    assert broad.line() == (
        "FAIL hotspots: scribe-owned, not listed literally in --owned: "
        "docs/CHANGELOG.md, docs/plans/v3/tasks.md"
    )
    literal = check_item.check_hotspots(changed, changed)
    assert literal.line() == "PASS hotspots"


def test_subjects_must_carry_the_item_id() -> None:
    ok = ["feat(T-Q326): add check", "fix(T-Q326b)!: tighten", "docs(T-Q326, ADR-0150): note"]
    assert check_item.check_subjects(ok, "T-Q326").level == "PASS"
    bad = check_item.check_subjects(["feat(T-Q327): other item", "wip"], "T-Q326")
    assert bad.line() == "FAIL subjects: not '<type>(T-Q326): ...': feat(T-Q327): other item | wip"


def test_allowlist_total_sums_counts_across_tables() -> None:
    text = """guard = "sql_sites"

[[entry]]
path = "a.py"
count = 2

[[entry]]
path = "b.py"

[[permanent]]
path = "c.py"
count = 3
reason = "x"
"""
    assert check_item.allowlist_total(text) == 6
    assert check_item.allowlist_total("") == 0


def test_risen_allowlist_fails_and_shrunk_one_passes() -> None:
    risen = check_item.check_allowlists({"tests/architecture/allowlists/purity.toml": (4, 5)})
    assert risen.line() == "FAIL allowlists: rose: tests/architecture/allowlists/purity.toml 4->5"
    shrunk = check_item.check_allowlists({"tests/architecture/allowlists/purity.toml": (4, 2)})
    assert shrunk.line() == (
        "PASS allowlists: shrank: tests/architecture/allowlists/purity.toml 4->2"
    )


def test_template_change_without_audit_record_fails() -> None:
    template, css = (
        "src/budget_planner/web/templates/home.html",
        "src/budget_planner/web/static/rd/css/app.bundle.css",
    )
    changed = [template, css]
    missing = check_item.check_audit(changed, [])
    assert missing.level == "FAIL"
    assert missing.detail.endswith(f"{template}, {css}")
    assert check_item.check_audit(changed, ["docs/audits/2026-11-24-t-x.md"]).level == "PASS"
    no_frontend = check_item.check_audit(["src/a.py"], [])
    assert no_frontend.line() == "PASS audit: no template or CSS change"


DIFF = """diff --git a/src/budget_planner/services/x.py b/src/budget_planner/services/x.py
--- a/src/budget_planner/services/x.py
+++ b/src/budget_planner/services/x.py
@@ -0,0 +1,4 @@
+def month_window(d):
+    return d  # type: ignore[no-any-return]  # reason
+async def load_rows():
+class Row:
diff --git a/tests/unit/test_x.py b/tests/unit/test_x.py
--- /dev/null
+++ b/tests/unit/test_x.py
@@ -0,0 +1 @@
+def test_month_window():  # noqa: D103
diff --git a/src/gone.py b/src/gone.py
--- a/src/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-def removed():
"""


def test_added_lines_track_the_file_and_skip_deletions() -> None:
    lines = check_item.added_lines(DIFF)
    assert lines[0] == ("src/budget_planner/services/x.py", "def month_window(d):")
    assert lines[-1] == ("tests/unit/test_x.py", "def test_month_window():  # noqa: D103")
    assert len(lines) == 5


def test_suppressions_are_listed_as_warnings() -> None:
    found = [f.line() for f in check_item.suppression_findings(check_item.added_lines(DIFF))]
    assert found == [
        "WARN suppression: src/budget_planner/services/x.py: "
        "return d  # type: ignore[no-any-return]  # reason",
        "WARN suppression: tests/unit/test_x.py: def test_month_window():  # noqa: D103",
    ]


def test_new_src_definitions_flag_canonical_concepts() -> None:
    found = [f.line() for f in check_item.definition_findings(check_item.added_lines(DIFF))]
    assert found == [
        "WARN new-def: src/budget_planner/services/x.py: month_window"
        " (canonical concept: check the Canonical modules table)",
        "WARN new-def: src/budget_planner/services/x.py: load_rows",
        "WARN new-def: src/budget_planner/services/x.py: Row",
    ]


def test_work_branch_is_never_double_prefixed() -> None:
    assert check_item.resolve_work("wi/ui/sourdough/QCI1", "QCI1") == "ui/sourdough"
    assert check_item.resolve_work("ui/sourdough", "QCI1") == "ui/sourdough"
    assert check_item.resolve_work("main", "QCI1", "wi/main/QCI1") == "main"
    assert check_item.resolve_work("wi/x/OTHER", "QCI1") == "wi/x/OTHER"


def test_hotspots_flag_allows_listed_scribe_files_and_reports_them() -> None:
    changed = ["docs/CHANGELOG.md", "docs/plans/v3/tasks.md"]
    only = check_item.check_hotspots(changed, [], ["docs/CHANGELOG.md"])
    assert only.line() == (
        "FAIL hotspots: scribe-owned, not listed literally in --owned: docs/plans/v3/tasks.md"
    )
    both = check_item.check_hotspots(changed, [], ["docs/CHANGELOG.md", "docs/plans/*/tasks.md"])
    assert both.line() == (
        "PASS hotspots: allowed via --hotspots: docs/CHANGELOG.md, docs/plans/v3/tasks.md"
    )


def test_allowlist_total_can_skip_the_framework_section() -> None:
    text = '[[entry]]\npath = "a"\n\n[[framework]]\npath = "b"\ncount = 2\n'
    assert check_item.allowlist_total(text) == 3
    assert check_item.allowlist_total(text, skip="framework") == 1


def test_framework_row_growth_fails_unless_allowed() -> None:
    path = "tests/architecture/allowlists/functional_first.toml"
    totals, framework = {path: (4, 6)}, {path: (1, 3)}
    failing = check_item.check_allowlists(totals, framework)
    assert failing.line() == f"FAIL allowlists: rose: {path} 4->6"
    warned = check_item.check_allowlists(totals, framework, allow_framework=True)
    assert warned.line() == f"WARN allowlists: framework rows added: {path} 1->3"


def test_allowed_framework_flag_does_not_hide_other_growth() -> None:
    path = "tests/architecture/allowlists/functional_first.toml"
    finding = check_item.check_allowlists({path: (4, 7)}, {path: (1, 3)}, allow_framework=True)
    assert finding.line() == f"FAIL allowlists: rose: {path} 3->4"
