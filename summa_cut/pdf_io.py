from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4
MM_PER_POINT = MM_PER_INCH / POINTS_PER_INCH


@dataclass
class PdfInfo:
    path: str
    name: str
    page_count: int
    page_sizes_mm: list[tuple[float, float]]
    page_content_sizes_mm: list[tuple[float, float]]
    page_content_boxes_pt: list[tuple[float, float, float, float]]


class PdfReadError(RuntimeError):
    pass


def points_to_mm(value: float) -> float:
    return value * MM_PER_POINT


def _page_content_bbox_pt(page: fitz.Page) -> fitz.Rect:
    rects = []
    for _kind, bbox in page.get_bboxlog():
        try:
            rect = fitz.Rect(bbox)
        except Exception:
            continue
        if rect.is_empty or rect.width <= 0 or rect.height <= 0:
            continue
        rects.append(rect)
    if not rects:
        return page.rect
    result = fitz.Rect(rects[0])
    for rect in rects[1:]:
        result |= rect
    return result & page.rect


def read_pdf_info(path: str) -> PdfInfo:
    pdf_path = Path(path)
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise PdfReadError(f"Nie udało się otworzyć PDF: {pdf_path.name}") from exc

    try:
        page_sizes_mm: list[tuple[float, float]] = []
        page_content_sizes_mm: list[tuple[float, float]] = []
        page_content_boxes_pt: list[tuple[float, float, float, float]] = []
        for page in doc:
            rect = page.rect
            content_bbox = _page_content_bbox_pt(page)
            page_sizes_mm.append((round(points_to_mm(rect.width), 2), round(points_to_mm(rect.height), 2)))
            page_content_sizes_mm.append((round(points_to_mm(content_bbox.width), 2), round(points_to_mm(content_bbox.height), 2)))
            page_content_boxes_pt.append((content_bbox.x0, content_bbox.y0, content_bbox.x1, content_bbox.y1))
        return PdfInfo(
            path=str(pdf_path),
            name=pdf_path.name,
            page_count=doc.page_count,
            page_sizes_mm=page_sizes_mm,
            page_content_sizes_mm=page_content_sizes_mm,
            page_content_boxes_pt=page_content_boxes_pt,
        )
    finally:
        doc.close()
