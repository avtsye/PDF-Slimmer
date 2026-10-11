"""Lossless JBIG2 encoder. Requires a local jbig2enc executable; no networking."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import fitz
from PIL import Image
from pikepdf import Pdf, Stream, Name, Dictionary

def encoder_path():
    ext = '.exe' if sys.platform == 'win32' else ''
    roots = [Path(getattr(sys, '_MEIPASS', Path(__file__).parent)),
             Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent]
    for root in roots:
        candidate = root / 'bin' / ('jbig2' + ext)
        if candidate.is_file():
            return str(candidate)
    return shutil.which('jbig2')

def available():
    return bool(encoder_path())

def encode_pdf(source, destination, *, dpi=200, threshold=190, progress=None, cancel=None):
    """Re-render each page to 1bpp then encode in *generic*, non-symbol JBIG2 mode.

    NB: Binarization itself is lossy relative to the color original.
    JBIG2 stage is pixel-lossless relative to those 1bpp pixels.
    Never use jbig2 -s (symbol clustering) or -a.
    """
    binary = encoder_path()
    if not binary:
        raise RuntimeError('Offline JBIG2 encoder not installed (bin/jbig2.exe). No download is attempted.')
    with fitz.open(str(source)) as original:
        if original.needs_pass:
            raise ValueError('Password-protected source')
        total = len(original)
        with Pdf.new() as pdf:
            for idx in range(total):
                if cancel is not None and cancel.is_set():
                    raise RuntimeError('Conversion cancelled')
                page = original[idx]
                width_pt, height_pt = page.rect.width, page.rect.height
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72),
                                      colorspace=fitz.csGRAY, alpha=False)
                gray = Image.frombytes('L',(pix.width,pix.height),pix.samples)
                mono = gray.point(lambda v: 255 if v >= threshold else 0, '1')
                with tempfile.TemporaryDirectory(prefix='jbig2-') as work:
                    pbm = Path(work) / 'page.pbm'
                    mono.save(pbm, format='PPM')
                    # -p: PDF compatible output; default generic region coding is lossless.
                    # Do NOT use -s: symbol substitution can corrupt characters.
                    result = subprocess.run([binary, '-p', str(pbm)],
                                            capture_output=True, timeout=300, check=False)
                mono.close()
                gray.close()
                if result.returncode or not result.stdout:
                    raise RuntimeError('jbig2enc failed: ' + result.stderr.decode(errors='replace')[-1000:])
                target_page = pdf.add_blank_page(page_size=(width_pt, height_pt))
                jbig_stream = Stream(pdf, result.stdout,
                                     Type=Name('/XObject'), Subtype=Name('/Image'),
                                     Width=pix.width, Height=pix.height,
                                     ColorSpace=Name('/DeviceGray'), BitsPerComponent=1,
                                     Filter=Name('/JBIG2Decode'))
                resources = Dictionary(XObject=Dictionary(Im0=jbig_stream))
                target_page.Resources = resources
                target_page.Contents = Stream(pdf,
                    f'q {width_pt} 0 0 {height_pt} 0 0 cm /Im0 Do Q'.encode('ascii'))
                if progress:
                    progress(idx+1,total)
            pdf.save(str(destination), compress_streams=True)
