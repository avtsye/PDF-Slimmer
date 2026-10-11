"""Smoke tests for the new interface without requiring a graphical display."""
import ast
from pathlib import Path

def test_v3_interface_parses():
    ast.parse(Path("app_v3.py").read_text(encoding="utf-8"))

def test_v3_keeps_old_interface_and_engine():
    assert Path("app.py").is_file()
    assert Path("engine.py").is_file()

def test_new_interface_has_required_actions():
    source = Path("app_v3.py").read_text(encoding="utf-8")
    for method in ("add_files", "add_folder", "clear", "preview", "start_run",
                   "cancel_run", "_poll", "_update_result_panel", "_settings"):
        assert f"def {method}(" in source
