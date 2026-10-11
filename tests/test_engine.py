import fitz
import pytest
from engine import convert, inspect_pdf

def make_pdf(path):
    doc = fitz.open()
    for i in range(2):
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), f'Test page {i + 1}')
        page.draw_rect(fitz.Rect(50, 100, 560, 600), color=(1, 0, 0), fill=(1, 0.5, 0))
    doc.save(path)
    doc.close()

def test_bilevel_preserves_page_count(tmp_path):
    original = tmp_path / 'original.pdf'
    make_pdf(original)
    dest = tmp_path / 'result.pdf'
    output = convert(original, dest, 'bw', 150, keep_smaller=False)
    assert output['pages'] == 2
    assert inspect_pdf(dest)['pages'] == 2
    assert original.exists()
    with fitz.open(str(dest)) as doc:
        assert all(page.get_images() for page in doc)

def test_auto_retains_smaller_original(tmp_path):
    src = tmp_path / 'small.pdf'
    make_pdf(src)
    dest = tmp_path / 'output.pdf'
    result = convert(src, dest, 'bw', 300, keep_smaller=True)
    assert result['new_bytes'] <= result['old_bytes']

def test_protect_input(tmp_path):
    src = tmp_path / 'in.pdf'
    make_pdf(src)
    with pytest.raises(ValueError):
        convert(src, src)

def test_invalid_mode(tmp_path):
    src = tmp_path / 'in.pdf'
    make_pdf(src)
    with pytest.raises(ValueError):
        convert(src, tmp_path / 'out.pdf', mode='foo')
