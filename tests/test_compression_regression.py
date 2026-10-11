"""Regression: scans carrying OCR must still have a real bilevel compression path."""
import fitz
from PIL import Image
from engine import convert, inspect_pdf

def test_scan_with_searchable_text_still_compressible(tmp_path):
    # Simulates an OCR-backed scanned page: large RGB raster plus selectable text.
    source = tmp_path / 'scan.pdf'
    image_path = tmp_path / 'scan.png'
    image = Image.effect_noise((1100, 1400), 20).point(lambda v: 235 + v // 13).convert('RGB')
    for row in range(40, 1300, 24):
        for x in range(80, 1000):
            image.putpixel((x, row), (25, 26, 27))
    image.save(image_path, 'PNG')
    doc = fitz.open()
    page = doc.new_page(width=550, height=700)
    page.insert_image(page.rect, filename=str(image_path))
    page.insert_text((60, 60), 'OCR text')
    doc.save(source, deflate=False)
    doc.close()
    assert inspect_pdf(source)['searchable']
    result_path = tmp_path / 'result.pdf'
    result = convert(source, result_path, mode='bw', dpi=150,
                     keep_smaller=False, preserve_ocr=False, workers=1)
    assert result['new_bytes'] < result['old_bytes'] * .6
    with fitz.open(result_path) as processed:
        assert len(processed) == 1
        assert processed[0].get_images()

def test_smart_preserves_searchable_text_for_explicit_opt_in(tmp_path):
    path = tmp_path / 'text.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 70), 'SELECTABLE TEXT')
        doc.save(path)
    output = tmp_path / 'out.pdf'
    result = convert(path, output, mode='smart', preserve_ocr=True, keep_smaller=False)
    assert result['mode'] == 'lossless'
    with fitz.open(output) as doc:
        assert 'SELECTABLE TEXT' in doc[0].get_text()
