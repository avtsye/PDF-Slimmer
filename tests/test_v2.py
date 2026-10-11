from pathlib import Path
import fitz
import pytest
from engine import convert, inspect_pdf, Cancelled, PRESETS

def source_pdf(p):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((70, 80), 'Searchable text')
    doc.save(str(p))
    doc.close()

def test_lossless_text_is_preserved(tmp_path):
    source = tmp_path / 'source.pdf'
    source_pdf(source)
    result = tmp_path / 'result.pdf'
    meta = convert(source, result, mode='lossless', keep_smaller=False)
    with fitz.open(str(result)) as pdf:
        assert 'Searchable text' in pdf[0].get_text()
    assert meta['pages'] == 1

def test_smart_digital_avoids_raster(tmp_path):
    source = tmp_path / 'source.pdf'
    source_pdf(source)
    result = tmp_path / 'result.pdf'
    meta = convert(source, result, mode='smart', keep_smaller=False)
    assert meta['mode'] == 'lossless'
    with fitz.open(str(result)) as pdf:
        assert pdf[0].get_text().strip()

def test_presets_have_supported_modes():
    for entry in PRESETS.values():
        assert entry['mode'] in ('smart', 'lossless', 'gray', 'bw', 'bw-clean')
        assert 100 <= entry['dpi'] <= 400

def test_source_is_never_overwritten(tmp_path):
    source = tmp_path / 'source.pdf'
    source_pdf(source)
    before = source.read_bytes()
    convert(source, tmp_path / 'out.pdf', 'bw', dpi=150, keep_smaller=False)
    assert source.read_bytes() == before
