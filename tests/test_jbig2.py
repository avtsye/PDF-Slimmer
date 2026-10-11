"""Checks for the offline JBIG2 path (binary-dependent integration test is optional)."""
import pytest
import fitz
from pathlib import Path
from engine import MODES, convert
import jbig2_backend

def test_jbig2_is_an_explicit_mode():
    assert 'jbig2' in MODES

def test_jbig2_requires_local_encoder(tmp_path, monkeypatch):
    monkeypatch.setattr(jbig2_backend, 'encoder_path', lambda: None)
    source = tmp_path / 'source.pdf'
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(str(source))
    pdf.close()
    with pytest.raises(RuntimeError, match='Offline JBIG2 encoder'):
        convert(source, tmp_path / 'output.pdf', mode='jbig2', keep_smaller=False,
                preserve_ocr=False)
    assert source.exists()
    assert not (tmp_path / 'output.pdf').exists()
