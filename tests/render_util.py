"""Narzędzia testowe: render strony fitz do PNG + porównanie w tolerancji.

Bez numpy — porównujemy surowe bajty pixmapy. Niska DPI (mały bufor, szybki
test), wystarczająca by wychwycić przesunięcia/zniknięcia użytków.
"""
from __future__ import annotations

import fitz

RENDER_DPI = 72


def render_page_png(doc: fitz.Document, page_index: int = 0, dpi: int = RENDER_DPI) -> bytes:
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return pix.tobytes("png")


def _samples(png_bytes: bytes) -> bytes:
    pix = fitz.Pixmap(png_bytes)
    return pix.samples


def fraction_differing(png_a: bytes, png_b: bytes, byte_threshold: int = 24) -> float:
    """Ułamek bajtów (pikseli gray) różniących się o więcej niż byte_threshold.

    Zwraca 1.0 gdy rozmiary buforów różne (twarda regresja geometrii).
    """
    a = _samples(png_a)
    b = _samples(png_b)
    if len(a) != len(b) or not a:
        return 1.0
    diff = sum(1 for x, y in zip(a, b) if abs(x - y) > byte_threshold)
    return diff / len(a)
