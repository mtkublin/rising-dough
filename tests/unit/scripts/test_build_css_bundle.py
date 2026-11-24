"""build_css_bundle: order, layers, nested-import rejection, --check (ADR-0107 §3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "scripts" / "build_css_bundle.py"
    spec = importlib.util.spec_from_file_location("build_css_bundle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle = _load()

ENTRY = """@layer a, b;

@import url("one.css") layer(a);
@import url("sub/two.css") layer(b);
@import url("three.css") layer(a);
"""


def _tree(tmp_path: Path, entry: str = ENTRY) -> Path:
    (tmp_path / "sub").mkdir()
    (tmp_path / "main.css").write_text(entry)
    (tmp_path / "one.css").write_text(".rd-one { color: red; }\n")
    (tmp_path / "sub/two.css").write_text(".rd-two { color: blue; }\n")
    (tmp_path / "three.css").write_text(".rd-three { color: green; }\n")
    return tmp_path


def test_order_and_layers_kept(tmp_path: Path) -> None:
    out = bundle.build_dir(_tree(tmp_path))
    assert out.index("@layer a, b;") < out.index("@layer a {")
    blocks = [
        ("a", ".rd-one { color: red; }"),
        ("b", ".rd-two { color: blue; }"),
        ("a", ".rd-three { color: green; }"),
    ]
    pos = 0
    for layer, rule in blocks:
        chunk = f"@layer {layer} {{\n{rule}\n}}\n"
        pos = out.index(chunk, pos) + len(chunk)
    assert "@import" not in out


def test_deterministic(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert bundle.build_dir(root) == bundle.build_dir(root)


def test_nested_import_rejected(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "one.css").write_text('@import url("x.css");\n')
    with pytest.raises(bundle.BundleError, match="nested"):
        bundle.build_dir(root)


def test_unsupported_import_form_rejected(tmp_path: Path) -> None:
    root = _tree(tmp_path, '@import "one.css";\n')
    with pytest.raises(bundle.BundleError, match="unsupported"):
        bundle.build_dir(root)


def test_check_stale_then_fresh(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    args = ["--css-dir", str(root)]
    assert bundle.main([*args, "--check"]) == 1  # no bundle yet
    assert bundle.main(args) == 0
    assert bundle.main([*args, "--check"]) == 0
    (root / "one.css").write_text(".rd-one { color: pink; }\n")
    assert bundle.main([*args, "--check"]) == 1
