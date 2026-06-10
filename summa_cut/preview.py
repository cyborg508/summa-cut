from __future__ import annotations

import fitz
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap

from .models import JobSettings, LayoutResult
from .opos import get_opos_positions
from .pdf_io import MM_PER_POINT

POINTS_PER_MM = 1.0 / MM_PER_POINT
MONTAGE_COLORS = [
    QColor("#27ae60"),
    QColor("#d35400"),
    QColor("#8e44ad"),
    QColor("#2980b9"),
    QColor("#c0392b"),
    QColor("#16a085"),
]


def render_pdf_page_to_pixmap(doc: fitz.Document, max_width: int = 900, max_height: int = 1100) -> QPixmap:
    page = doc[0]
    scale = min(
        max_width / max(page.rect.width, 1),
        max_height / max(page.rect.height, 1),
    )
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)


def render_source_tile(
    doc: fitz.Document,
    page_index: int,
    clip_bbox_pt: tuple[float, float, float, float] | None = None,
    max_px: int = 280,
) -> QPixmap:
    """Rasteryzuje RAZ obszar zawartości strony źródłowej do miniatury (kafla).

    Kafel jest potem „stemplowany" N razy w podglądzie (QPainter), zamiast budować
    pełny PDF wyjściowy przy każdej zmianie — to czyni podgląd O(1) względem
    liczby użytków.
    """
    page = doc[page_index]
    clip = fitz.Rect(clip_bbox_pt) if clip_bbox_pt else page.rect
    if clip.is_empty or clip.is_infinite:
        clip = page.rect
    scale = max_px / max(clip.width, clip.height, 1.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)


def render_layout_preview(
    job: JobSettings,
    layout: LayoutResult,
    width_px: int = 900,
    height_px: int = 900,
    tiles: dict[int, QPixmap] | None = None,
) -> QPixmap:
    pixmap = QPixmap(width_px, height_px)
    pixmap.fill(QColor("white"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    sheet = layout.sheet_rect
    if sheet.width_mm <= 0 or sheet.height_mm <= 0:
        painter.end()
        return pixmap

    margin = 20
    scale = min((width_px - 2 * margin) / sheet.width_mm, (height_px - 2 * margin) / sheet.height_mm)
    offset_x = (width_px - sheet.width_mm * scale) / 2
    offset_y = (height_px - sheet.height_mm * scale) / 2

    def tx(x_mm: float) -> float:
        return offset_x + x_mm * scale

    def ty(y_mm: float) -> float:
        return offset_y + y_mm * scale

    painter.setPen(QPen(QColor("#222222"), 2))
    painter.drawRect(tx(0), ty(0), sheet.width_mm * scale, sheet.height_mm * scale)

    work = layout.work_area_rect
    painter.setPen(QPen(QColor("#2f80ed"), 1))
    painter.drawRect(tx(work.x_mm), ty(work.y_mm), work.width_mm * scale, work.height_mm * scale)

    default_color = QColor("#27ae60")
    for placement in layout.placements:
        px = tx(placement.x_mm)
        py = ty(placement.y_mm)
        pw = placement.width_mm * scale
        ph = placement.height_mm * scale
        tile = tiles.get(placement.montage_item_index) if tiles else None
        if tile is not None and not tile.isNull():
            target = QRectF(px, py, pw, ph)
            src_rect = QRectF(tile.rect())
            if placement.rotation_deg == 90:
                painter.save()
                painter.translate(px + pw / 2.0, py + ph / 2.0)
                painter.rotate(90)
                painter.drawPixmap(QRectF(-ph / 2.0, -pw / 2.0, ph, pw), tile, src_rect)
                painter.restore()
            else:
                painter.drawPixmap(target, tile, src_rect)
            painter.setPen(QPen(QColor("#9aa0a6"), 1))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRect(px, py, pw, ph)
        else:
            color = default_color
            if job.montage_items:
                color = MONTAGE_COLORS[placement.montage_item_index % len(MONTAGE_COLORS)]
            painter.setPen(QPen(color, 1))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRect(px, py, pw, ph)

    painter.setPen(QPen(QColor("#000000"), 1))
    painter.setBrush(QColor("#000000"))
    mark_mm = 2.0
    for x_mm, y_mm in get_opos_positions(job):
        x = tx(x_mm - mark_mm / 2.0)
        y = ty(y_mm - mark_mm / 2.0)
        painter.drawRect(x, y, mark_mm * scale, mark_mm * scale)

    painter.end()
    return pixmap
