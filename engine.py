"""PDF-Slimmer 2: safe and bounded-memory PDF conversion."""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import fitz
from PIL import Image, ImageOps, ImageFilter

MODES = ('smart', 'lossless', 'gray', 'bw', 'bw-clean')
PRESETS = {
    'small': {'mode': 'bw-clean', 'dpi': 150},
    'balanced': {'mode': 'smart', 'dpi': 200},
    'quality': {'mode': 'smart', 'dpi': 300},
    'lossless': {'mode': 'lossless', 'dpi': 300},
}
class Cancelled(Exception):
    pass

def inspect_pdf(path):
    p = Path(path)
    with fitz.open(str(p)) as pdf:
        if pdf.needs_pass:
            raise ValueError('Encrypted PDFs are not supported')
        if not len(pdf):
            raise ValueError('Empty PDF')
        sampled = list(range(min(3, len(pdf))))
        searchable = any(bool(pdf[i].get_text().strip()) for i in sampled)
        images = sum(len(pdf[i].get_images()) for i in sampled)
        return {'pages': len(pdf), 'bytes': p.stat().st_size, 'searchable': searchable,
                'has_images': bool(images), 'digital': searchable and not images}

def _find_ghostscript():
    return next((v for n in ('gswin64c', 'gswin32c', 'gs') if (v := shutil.which(n))), None)

def _ghostscript(source, target, gray=False):
    gs = _find_ghostscript()
    if not gs:
        raise RuntimeError('Install Ghostscript and add it to PATH for grayscale/optimized mode')
    cmd = [gs, '-dSAFER', '-dBATCH', '-dNOPAUSE', '-sDEVICE=pdfwrite',
           '-dCompatibilityLevel=1.6', '-dDetectDuplicateImages=true',
           '-dCompressFonts=true', '-dAutoRotatePages=/None']
    if gray:
        cmd.extend(['-sColorConversionStrategy=Gray', '-dProcessColorModel=/DeviceGray'])
    cmd.extend([f'-sOutputFile={target}', str(source)])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    if proc.returncode:
        raise RuntimeError('Ghostscript: ' + (proc.stderr or proc.stdout)[-1200:])

def _render_page(job):
    source, idx, dpi, clean, threshold, folder = job
    with fitz.open(str(source)) as pdf:
        page = pdf[idx]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72),
                              colorspace=fitz.csGRAY, alpha=False)
        width, height = page.rect.width, page.rect.height
        image = Image.frombytes('L', (pix.width, pix.height), pix.samples)
        if clean:
            image = ImageOps.autocontrast(image, cutoff=1)
            image = image.filter(ImageFilter.MedianFilter(3))
        mono = image.point(lambda x: 255 if x >= threshold else 0, mode='1')
        page_pdf = Path(folder) / f'{idx:07d}.pdf'
        mono.save(str(page_pdf), format='PDF', resolution=float(dpi))
        mono.close()
        image.close()
        return idx, str(page_pdf), width, height

def _bilevel(source, output, dpi, clean=False, workers=1, threshold=190,
             progress=None, cancel=None):
    with fitz.open(str(source)) as pdf:
        page_count = len(pdf)
    with tempfile.TemporaryDirectory(prefix='pdfslimmer-pages-') as tmp:
        tasks = [(str(source), i, dpi, clean, threshold, tmp) for i in range(page_count)]
        results = {}
        if workers > 1:
            with ProcessPoolExecutor(max_workers=min(workers, 8)) as pool:
                futures = {pool.submit(_render_page, t): t[1] for t in tasks}
                try:
                    for f in as_completed(futures):
                        if cancel and cancel.is_set():
                            raise Cancelled('Conversion cancelled')
                        idx, page_path, w, h = f.result()
                        results[idx] = (page_path, w, h)
                        if progress: progress(len(results), page_count)
                except BaseException:
                    for f in futures: f.cancel()
                    raise
        else:
            for t in tasks:
                if cancel and cancel.is_set():
                    raise Cancelled('Conversion cancelled')
                idx, page_path, w, h = _render_page(t)
                results[idx] = (page_path, w, h)
                if progress: progress(len(results), page_count)
        out = fitz.open()
        try:
            for idx in range(page_count):
                page_path, w, h = results[idx]
                with fitz.open(page_path) as part:
                    out.insert_pdf(part)
            out.save(str(output), garbage=4, deflate=True)
        finally:
            out.close()

def _ocr(input_path, output_path, language='heb+eng'):
    exe = shutil.which('ocrmypdf')
    if not exe:
        raise RuntimeError('OCRmyPDF is not installed; install it and language packs to enable OCR')
    cmd = [exe, '--force-ocr', '-l', language, '--optimize', '1',
           str(input_path), str(output_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=14400)
    if proc.returncode:
        raise RuntimeError('OCRmyPDF: ' + (proc.stderr or proc.stdout)[-1200:])

def convert(source, destination, mode='smart', dpi=200, keep_smaller=True,
            progress=None, workers=1, preserve_ocr=True, cancel=None,
            threshold=190, use_jbig2=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Source and destination must differ')
    if source.suffix.lower() != '.pdf' or destination.suffix.lower() != '.pdf':
        raise ValueError('PDF files only')
    if mode not in MODES:
        raise ValueError('Invalid mode')
    if not 100 <= dpi <= 400 or not 0 <= threshold <= 255:
        raise ValueError('Invalid DPI/threshold')
    info = inspect_pdf(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pdfslimmer-', dir=str(destination.parent)) as work:
        temp = Path(work) / 'candidate.pdf'
        selected = mode
        if mode == 'smart':
            selected = 'lossless' if info['digital'] or (preserve_ocr and info['searchable']) else 'bw'
        if selected == 'lossless':
            with fitz.open(str(source)) as doc:
                doc.save(str(temp), garbage=4, deflate=True, clean=False)
        elif selected == 'gray':
            _ghostscript(source, temp, gray=True)
        else:
            base = Path(work) / 'rendered.pdf'
            _bilevel(source, base, dpi, selected == 'bw-clean', workers, threshold, progress, cancel)
            if preserve_ocr and info['searchable']:
                _ocr(base, temp)
            else:
                shutil.copy2(base, temp)
        if cancel and cancel.is_set():
            raise Cancelled('Conversion cancelled')
        with fitz.open(str(temp)) as doc:
            if len(doc) != info['pages']:
                raise RuntimeError('Page count mismatch')
        candidate_bytes = temp.stat().st_size
        original_kept = bool(keep_smaller and candidate_bytes >= info['bytes'])
        final_path = source if original_kept else temp
        # Stage copy to avoid destroying a pre-existing destination on copy failures.
        staging = Path(work) / 'publish.pdf'
        shutil.copy2(final_path, staging)
        os.replace(staging, destination)
        return {'source': str(source), 'destination': str(destination),
                'pages': info['pages'], 'old_bytes': info['bytes'],
                'new_bytes': destination.stat().st_size,
                'candidate_bytes': candidate_bytes, 'original_kept': original_kept,
                'mode': selected, 'text_layer_may_be_lost':
                    selected in ('bw', 'bw-clean') and not (preserve_ocr and info['searchable'])}
