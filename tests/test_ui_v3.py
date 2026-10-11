"""Smoke tests for the sole supported desktop interface."""
import ast
from pathlib import Path

def test_app_parses():
    ast.parse(Path("app.py").read_text(encoding="utf-8"))

def test_app_uses_compression_engine():
    src = Path("app.py").read_text(encoding="utf-8")
    assert "from engine import convert, inspect_pdf" in src
    for method in ("add_files", "add_folder", "settings", "preview", "start", "stop", "_worker", "_poll"):
        assert f"def {method}(" in src

def test_only_one_gui_entrypoint():
    assert Path("app.py").exists()
    assert not Path("app_v3.py").exists()
    assert not Path("app_win11.py").exists()
