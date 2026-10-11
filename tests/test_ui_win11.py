"""Source-level checks: GUI does not modify the compression engine."""
import ast
from pathlib import Path

def test_new_interface_syntax():
    ast.parse(Path("app_win11.py").read_text(encoding="utf-8"))

def test_engine_integration():
    src = Path("app_win11.py").read_text(encoding="utf-8")
    assert "from engine import convert, inspect_pdf" in src
    for method in ("add_files", "add_folder", "settings", "preview", "start", "stop", "_worker", "_poll"):
        assert f"def {method}(" in src

def test_previous_interfaces_remain():
    assert Path("app.py").is_file()
    assert Path("app_v3.py").is_file()
