"""PDF-Slimmer compression engine. No source file is overwritten."""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import fitz
from PIL import Image, ImageOps, ImageFilter

MODES = ('gray', 'bw', 'bw-clean')

def inspect_pdf(path):
    p = Path(path)
    with fitz.open(str(p)) as pdf:
        if pdf.needs_pass:
            raise ValueError('Password-protected PDFs are not supported.')
        return {'pages': len(pdf), 'bytes': p.stat().st_size,
                'searchable': any(bool(pdf[i].get_text().strip()) for i in range(min(5, len(pdf))))}

def gs_location():
    for name in ('gs', 'gswin64c', 'gswin32c'):
        found = shutil.which(name)
        if found:
            return found
    return None

def _gray(input_path, temp_output):
    gs = gs_location()
    if not gs:
        raise RuntimeError('Ghostscript is required for grayscale PDF mode. Install it and add it to PATH.')
    cmd = [gs, '-dSAFER', '-dBATCH', '-dNOPAUSE', '-sDEVICE=pdfwrite',
           '-sColorConversionStrategy=Gray', '-dProcessColorModel=/DeviceGray',
           '-dCompatibilityLevel=1.6', '-dDetectDuplicateImages=true',
           '-dCompressFonts=true', '-dAutoRotatePages=/None',
           f'-sOutputFile={temp_output}', str(input_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode:
        raise RuntimeError('Ghostscript failed: ' + (result.stderr or result.stdout)[-1500:])

def _raster(input_path, temp_output, dpi, clean, progress=None):
    pages = []
    try:
        with fitz.open(str(input_path)) as pdf:
            if not len(pdf):
                raise ValueError('The PDF is empty.')
            for index, page in enumerate(pdf):
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), colorspace=fitz.csGRAY, alpha=False)
                im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
                if clean:
                    im = ImageOps.autocontrast(im, cutoff=1)
                    im = im.filter(ImageFilter.MedianFilter(3))
                mono = im.point(lambda v: 255 if v >= (175 if clean else 190) else 0, mode='1')
                mono.info['dpi'] = (dpi, dpi)
                pages.append(mono)
                if progress:
                    progress(index+1, len(pdf))
        pages[0].save(temp_output, format='PDF', save_all=True, append_images=pages[1:],
                      resolution=float(dpi))
    finally:
        for page in pages:
            page.close()

def convert(source, destination, mode='bw', dpi=200, keep_smaller=True, progress=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Source and destination must differ.')
    if source.suffix.lower() != '.pdf' or destination.suffix.lower() != '.pdf':
        raise ValueError('Both source and destination must be PDF files.')
    if mode not in MODES:
        raise ValueError('Invalid conversion mode.')
    if not 100 <= dpi <= 400:
        raise ValueError('DPI must be between 100 and 400.')
    info = inspect_pdf(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix='.pdf', dir=destination.parent)
    os.close(fd)
    temp = Path(tmp)
    try:
        if mode == 'gray':
            _gray(source, temp)
        else:
            _raster(source, temp, dpi, mode == 'bw-clean', progress)
        with fitz.open(str(temp)) as result_pdf:
            if len(result_pdf) != info['pages']:
                raise RuntimeError('Page count changed unexpectedly.')
        candidate_size = temp.stat().st_size
        used_original = bool(keep_smaller and candidate_size >= info['bytes'])
        if used_original:
            shutil.copy2(source, temp)
        os.replace(temp, destination)
        return {'source': str(source), 'destination': str(destination),
                'old_bytes': info['bytes'], 'new_bytes': destination.stat().st_size,
                'candidate_bytes': candidate_size, 'original_kept': used_original,
                'pages': info['pages'], 'mode': mode, 'text_layer_may_be_lost': mode != 'gray'}
    finally:
        temp.unlink(missing_ok=True)
