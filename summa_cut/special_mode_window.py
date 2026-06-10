from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import fitz

from .pdf_io import PdfReadError, read_pdf_info
from .models import Placement, RectMM


POINTS_PER_MM = 72.0 / 25.4


@dataclass
class PreparedSpecialModeDocs:
    print_pdf_path: Path
    cut_pdf_path: Path
    preview: QPixmap
    page_size_pt: tuple[float, float]
    temp_work_dir: Path


@dataclass
class PreparedMontagePair:
    print_pdf_path: Path
    cut_pdf_path: Path
    page_size_pt: tuple[float, float]
    preview: QPixmap



def qpath_to_pdf_clip_commands(path: QPainterPath, page: fitz.Page, offset_x: float = 0.0, offset_y: float = 0.0) -> str:
    pdf_matrix = page.transformation_matrix
    commands: list[str] = ["q"]
    for polygon in path.toFillPolygons():
        if polygon.isEmpty():
            continue
        first_qp = polygon[0]
        first = fitz.Point(first_qp.x() - offset_x, first_qp.y() - offset_y) * pdf_matrix
        commands.append(f"{first.x:.3f} {first.y:.3f} m")
        for idx in range(1, polygon.count()):
            point = polygon[idx]
            mapped = fitz.Point(point.x() - offset_x, point.y() - offset_y) * pdf_matrix
            commands.append(f"{mapped.x:.3f} {mapped.y:.3f} l")
        commands.append("h")
    commands.append("W n")
    commands.append("/fzFrm0 Do")
    commands.append("Q")
    return "\n".join(commands)


def save_vector_trim_pdf(
    output_path: Path,
    source_doc: fitz.Document,
    source_page_index: int,
    clip_path: QPainterPath,
    page_rect: fitz.Rect,
) -> tuple[float, float]:
    bounds = clip_path.boundingRect()
    if bounds.isEmpty():
        raise ValueError("Obrys wykrojnika po dodaniu spadu jest pusty.")
    out_doc = fitz.open()
    out_page = out_doc.new_page(width=bounds.width(), height=bounds.height())
    target_rect = fitz.Rect(-bounds.x(), -bounds.y(), page_rect.width - bounds.x(), page_rect.height - bounds.y())
    out_page.show_pdf_page(target_rect, source_doc, source_page_index)
    content_xrefs = out_page.get_contents()
    if not content_xrefs:
        raise ValueError("Nie udało się utworzyć treści strony wynikowej PDF.")
    clip_stream = qpath_to_pdf_clip_commands(clip_path, out_page, bounds.x(), bounds.y()).encode("ascii")
    out_doc.update_stream(content_xrefs[0], clip_stream)
    out_doc.save(str(output_path))
    out_doc.close()
    return bounds.width(), bounds.height()


def render_preview_from_pdf(pdf_path: Path, max_width: int = 1200) -> QPixmap:
    preview_doc = fitz.open(str(pdf_path))
    try:
        page = preview_doc[0]
        scale = max_width / max(page.rect.width, 1)
        preview_pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
        result = QImage(
            preview_pix.samples,
            preview_pix.width,
            preview_pix.height,
            preview_pix.stride,
            QImage.Format.Format_RGBA8888,
        ).copy()
        return QPixmap.fromImage(result)
    finally:
        preview_doc.close()


def render_overlay_preview_from_pdfs(print_pdf_path: Path, cut_pdf_path: Path, max_width: int = 1200) -> QPixmap:
    print_pixmap = render_preview_from_pdf(print_pdf_path, max_width=max_width)
    cut_pixmap = render_preview_from_pdf(cut_pdf_path, max_width=max_width)
    if print_pixmap.isNull():
        return cut_pixmap
    result = QPixmap(print_pixmap.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawPixmap(0, 0, print_pixmap)
    painter.setOpacity(0.95)
    painter.drawPixmap(0, 0, cut_pixmap)
    painter.end()
    return result


def cut_page_to_qpath(page: fitz.Page) -> QPainterPath:
    path = QPainterPath()
    for drawing in page.get_drawings():
        current_started = False
        current_point = None
        for item in drawing.get("items", []):
            op = item[0]
            if op == "re":
                rect = item[1]
                path.addRect(rect.x0, rect.y0, rect.width, rect.height)
                current_started = False
                current_point = None
            elif op == "l":
                p1, p2 = item[1], item[2]
                if not current_started or current_point != (p1.x, p1.y):
                    path.moveTo(p1.x, p1.y)
                path.lineTo(p2.x, p2.y)
                current_started = True
                current_point = (p2.x, p2.y)
            elif op == "c":
                p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                if not current_started or current_point != (p1.x, p1.y):
                    path.moveTo(p1.x, p1.y)
                path.cubicTo(p2.x, p2.y, p3.x, p3.y, p4.x, p4.y)
                current_started = True
                current_point = (p4.x, p4.y)
        if drawing.get("closePath"):
            path.closeSubpath()
    return path.simplified()


def get_first_page_drawings_bounds(pdf_path: Path) -> fitz.Rect:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        rects = [fitz.Rect(d["rect"]) for d in page.get_drawings() if fitz.Rect(d["rect"]).is_valid]
        if not rects:
            return fitz.Rect(page.rect)
        bounds = fitz.Rect(rects[0])
        for rect in rects[1:]:
            bounds |= rect
        return bounds
    finally:
        doc.close()


def prepare_special_mode_docs(
    print_pdf_path: str,
    print_page_index: int,
    cut_pdf_path: str,
    cut_page_index: int,
    bleed_mm: float,
    temp_work_dir: Path | None = None,
) -> PreparedSpecialModeDocs:
    print_doc = fitz.open(print_pdf_path)
    cut_doc = fitz.open(cut_pdf_path)
    try:
        print_page = print_doc[print_page_index]
        cut_page = cut_doc[cut_page_index]
        cut_path = cut_page_to_qpath(cut_page)
        if cut_path.isEmpty():
            raise ValueError("Nie udało się znaleźć wektorowego obrysu wykrojnika na wybranej stronie.")
        bleed_pt = bleed_mm * POINTS_PER_MM
        stroker = QPainterPathStroker()
        stroker.setWidth(bleed_pt * 2.0)
        expanded_path = cut_path.united(stroker.createStroke(cut_path)).simplified()
        work_dir = temp_work_dir or Path(tempfile.mkdtemp(prefix="summa-cut-special-"))
        work_dir.mkdir(parents=True, exist_ok=True)
        out_print = work_dir / "tryb-specjalny-druk-temp.pdf"
        out_cut = work_dir / "tryb-specjalny-wykrojnik-temp.pdf"
        page_size = save_vector_trim_pdf(out_print, print_doc, print_page_index, expanded_path, print_page.rect)
        save_vector_trim_pdf(out_cut, cut_doc, cut_page_index, expanded_path, cut_page.rect)
        preview = render_overlay_preview_from_pdfs(out_print, out_cut, max_width=1200)
        return PreparedSpecialModeDocs(out_print, out_cut, preview, page_size, work_dir)
    finally:
        print_doc.close()
        cut_doc.close()


def build_special_mode_explicit_placements(
    page_width_mm: float,
    page_height_mm: float,
    row_offsets_mm: list[float],
    col_offsets_mm: list[float],
    col_x_offsets_mm: list[float],
    row_y_offsets_mm: list[float],
    work_area: RectMM,
) -> tuple[list[Placement], int, int]:
    local_positions: dict[tuple[int, int], tuple[float, float]] = {}
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    for row in range(2):
        for col in range(2):
            x = col * page_width_mm + row_offsets_mm[row] + col_x_offsets_mm[col]
            y = row * page_height_mm + col_offsets_mm[col] + row_y_offsets_mm[row]
            local_positions[(row, col)] = (x, y)
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + page_width_mm)
            max_y = max(max_y, y + page_height_mm)

    normalized = {key: (value[0] - min_x, value[1] - min_y) for key, value in local_positions.items()}
    base_x_by_row = {
        row: normalized[(row, 0)][0]
        for row in range(2)
    }
    step_x_by_row = {
        row: max(normalized[(row, 1)][0] - normalized[(row, 0)][0], 0.001)
        for row in range(2)
    }
    base_y_by_col = {
        col: normalized[(0, col)][1]
        for col in range(2)
    }
    step_y_by_col = {
        col: max(normalized[(1, col)][1] - normalized[(0, col)][1], 0.001)
        for col in range(2)
    }

    def make_raw(rows: int, cols: int) -> list[Placement]:
        out: list[Placement] = []
        for row in range(rows):
            row_kind = row % 2
            for col in range(cols):
                col_kind = col % 2
                x = base_x_by_row[row_kind] + col * step_x_by_row[row_kind]
                y = base_y_by_col[col_kind] + row * step_y_by_col[col_kind]
                out.append(Placement(x, y, page_width_mm, page_height_mm, 0, row, col, 0))
        return out

    def fit_variant(rows: int, cols: int) -> tuple[bool, list[Placement]]:
        placements = make_raw(rows, cols)
        if not placements:
            return False, []
        min_px = min(p.x_mm for p in placements)
        min_py = min(p.y_mm for p in placements)
        max_px = max(p.x_mm + p.width_mm for p in placements)
        max_py = max(p.y_mm + p.height_mm for p in placements)
        width = max_px - min_px
        height = max_py - min_py
        if width > work_area.width_mm or height > work_area.height_mm:
            return False, []
        shift_x = work_area.x_mm + max((work_area.width_mm - width) / 2.0, 0.0) - min_px
        shift_y = work_area.y_mm + max((work_area.height_mm - height) / 2.0, 0.0) - min_py
        shifted = [Placement(p.x_mm + shift_x, p.y_mm + shift_y, p.width_mm, p.height_mm, p.rotation_deg, p.row, p.column, p.group) for p in placements]
        return True, shifted

    max_cols = max(int(work_area.width_mm // max(page_width_mm, 1.0)) + 4, 1)
    max_rows = max(int(work_area.height_mm // max(page_height_mm, 1.0)) + 4, 1)
    best_rows = best_cols = 0
    best: list[Placement] = []
    for rows in range(1, max_rows + 1):
        for cols in range(1, max_cols + 1):
            ok, placements = fit_variant(rows, cols)
            if not ok:
                continue
            if len(placements) > len(best):
                best = placements
                best_rows = rows
                best_cols = cols
    return best, best_rows, best_cols


def build_montage_placements_pt(
    page_size_pt: tuple[float, float],
    row_offsets_pt: list[float],
    col_offsets_pt: list[float],
    col_x_offsets_pt: list[float],
    row_y_offsets_pt: list[float],
) -> list[fitz.Rect]:
    page_width_pt, page_height_pt = page_size_pt
    return [
        fitz.Rect(0 + row_offsets_pt[0] + col_x_offsets_pt[0], 0 + col_offsets_pt[0] + row_y_offsets_pt[0], page_width_pt + row_offsets_pt[0] + col_x_offsets_pt[0], page_height_pt + col_offsets_pt[0] + row_y_offsets_pt[0]),
        fitz.Rect(page_width_pt + row_offsets_pt[0] + col_x_offsets_pt[1], 0 + col_offsets_pt[1] + row_y_offsets_pt[0], page_width_pt * 2.0 + row_offsets_pt[0] + col_x_offsets_pt[1], page_height_pt + col_offsets_pt[1] + row_y_offsets_pt[0]),
        fitz.Rect(0 + row_offsets_pt[1] + col_x_offsets_pt[0], page_height_pt + col_offsets_pt[0] + row_y_offsets_pt[1], page_width_pt + row_offsets_pt[1] + col_x_offsets_pt[0], page_height_pt * 2.0 + col_offsets_pt[0] + row_y_offsets_pt[1]),
        fitz.Rect(page_width_pt + row_offsets_pt[1] + col_x_offsets_pt[1], page_height_pt + col_offsets_pt[1] + row_y_offsets_pt[1], page_width_pt * 2.0 + row_offsets_pt[1] + col_x_offsets_pt[1], page_height_pt * 2.0 + col_offsets_pt[1] + row_y_offsets_pt[1]),
    ]


def save_montage_pair_pdfs(
    source_print_trim_pdf: Path,
    source_cut_trim_pdf: Path,
    page_size_pt: tuple[float, float],
    row_offsets_pt: list[float],
    col_offsets_pt: list[float],
    col_x_offsets_pt: list[float],
    row_y_offsets_pt: list[float],
    output_dir: Path,
    work_area_size_pt: tuple[float, float] | None = None,
) -> PreparedMontagePair:
    placements = build_montage_placements_pt(page_size_pt, row_offsets_pt, col_offsets_pt, col_x_offsets_pt, row_y_offsets_pt)
    local_bounds = get_first_page_drawings_bounds(source_cut_trim_pdf)
    local_center_x = (local_bounds.x0 + local_bounds.x1) / 2.0
    local_center_y = (local_bounds.y0 + local_bounds.y1) / 2.0

    if work_area_size_pt is not None and len(placements) >= 4:
        first_col = sorted([placements[0], placements[2]], key=lambda r: (r.y0 + r.y1) / 2.0)
        tile1, tile2 = first_col
        center1_y = tile1.y0 + local_center_y
        center2_y = tile2.y0 + local_center_y
        dy = center2_y - center1_y
        if dy > 0:
            work_w_pt, work_h_pt = work_area_size_pt
            last_rect = tile2
            next_template = tile1
            while True:
                width = next_template.width
                height = next_template.height
                x0 = next_template.x0
                last_center_y = last_rect.y0 + local_center_y
                next_center_y = last_center_y + dy
                candidate = fitz.Rect(
                    x0,
                    next_center_y - local_center_y,
                    x0 + width,
                    next_center_y - local_center_y + height,
                )
                candidate_bbox = fitz.Rect(
                    candidate.x0 + local_bounds.x0,
                    candidate.y0 + local_bounds.y0,
                    candidate.x0 + local_bounds.x1,
                    candidate.y0 + local_bounds.y1,
                )
                if candidate_bbox.x0 < 0 or candidate_bbox.y0 < 0 or candidate_bbox.x1 > work_w_pt or candidate_bbox.y1 > work_h_pt:
                    break
                placements.append(candidate)
                last_rect = candidate
                next_template = tile2 if next_template is tile1 else tile1

    min_x = min(rect.x0 for rect in placements)
    min_y = min(rect.y0 for rect in placements)
    max_x = max(rect.x1 for rect in placements)
    max_y = max(rect.y1 for rect in placements)
    out_size = (max_x - min_x, max_y - min_y)

    output_dir.mkdir(parents=True, exist_ok=True)
    print_out = output_dir / "tryb-specjalny-montaz-druk.pdf"
    cut_out = output_dir / "tryb-specjalny-montaz-wykrojnik.pdf"

    def render_one(source_pdf: Path, out_pdf: Path) -> None:
        src = fitz.open(str(source_pdf))
        try:
            out = fitz.open()
            try:
                page = out.new_page(width=out_size[0], height=out_size[1])
                shifted_rects: list[fitz.Rect] = []
                for rect in placements:
                    shifted = fitz.Rect(rect.x0 - min_x, rect.y0 - min_y, rect.x1 - min_x, rect.y1 - min_y)
                    shifted_rects.append(shifted)
                    page.show_pdf_page(shifted, src, 0)

                shape = page.new_shape()
                for rect in shifted_rects:
                    bbox = fitz.Rect(
                        rect.x0 + local_bounds.x0,
                        rect.y0 + local_bounds.y0,
                        rect.x0 + local_bounds.x1,
                        rect.y0 + local_bounds.y1,
                    )
                    cx = (bbox.x0 + bbox.x1) / 2.0
                    cy = (bbox.y0 + bbox.y1) / 2.0
                    shape.draw_line(fitz.Point(cx, bbox.y0), fitz.Point(cx, bbox.y1))
                    shape.draw_line(fitz.Point(bbox.x0, cy), fitz.Point(bbox.x1, cy))
                shape.finish(color=(1, 0, 0), width=0.5)
                shape.commit()

                out.save(str(out_pdf))
            finally:
                out.close()
        finally:
            src.close()

    render_one(source_print_trim_pdf, print_out)
    render_one(source_cut_trim_pdf, cut_out)
    preview = render_overlay_preview_from_pdfs(print_out, cut_out, max_width=1200)
    return PreparedMontagePair(print_out, cut_out, out_size, preview)



class MontageEditorWidget(QWidget):
    changed = Signal()
    preview_rows = 3
    preview_cols = 3

    def __init__(self) -> None:
        super().__init__()
        self.base_pixmap: QPixmap | None = None
        self.work_area_mm: RectMM | None = None
        self.page_width_pt = 0.0
        self.page_height_pt = 0.0
        self.row_offsets_pt = [0.0, 0.0]  # poziome przesunięcie rzędów
        self.col_offsets_pt = [0.0, 0.0]  # pionowe przesunięcie kolumn
        self.col_x_offsets_pt = [0.0, 0.0]  # poziome przesunięcie kolumn (Shift)
        self.row_y_offsets_pt = [0.0, 0.0]  # pionowe przesunięcie rzędów (Shift)
        self.drag_tile: tuple[int, int] | None = None
        self.last_mouse_pos = None
        self.setMinimumSize(700, 520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#ffffff; border:1px solid #ccc;")

    def clear(self) -> None:
        self.base_pixmap = None
        self.work_area_mm = None
        self.page_width_pt = 0.0
        self.page_height_pt = 0.0
        self.row_offsets_pt = [0.0, 0.0]
        self.col_offsets_pt = [0.0, 0.0]
        self.col_x_offsets_pt = [0.0, 0.0]
        self.row_y_offsets_pt = [0.0, 0.0]
        self.drag_tile = None
        self.last_mouse_pos = None
        self.update()

    def set_document(self, pixmap: QPixmap, page_width_pt: float, page_height_pt: float, work_area_mm: RectMM | None = None) -> None:
        self.base_pixmap = pixmap
        self.work_area_mm = work_area_mm
        self.page_width_pt = page_width_pt
        self.page_height_pt = page_height_pt
        self.row_offsets_pt = [0.0, 0.0]
        self.col_offsets_pt = [0.0, 0.0]
        self.col_x_offsets_pt = [0.0, 0.0]
        self.row_y_offsets_pt = [0.0, 0.0]
        self.update()
        self.changed.emit()

    def get_offsets_pt(self) -> tuple[list[float], list[float], list[float], list[float]]:
        return (
            self.row_offsets_pt[:],
            self.col_offsets_pt[:],
            self.col_x_offsets_pt[:],
            self.row_y_offsets_pt[:],
        )

    def set_offsets_pt(
        self,
        row_offsets_pt: list[float],
        col_offsets_pt: list[float],
        col_x_offsets_pt: list[float],
        row_y_offsets_pt: list[float],
    ) -> None:
        self.row_offsets_pt = list(row_offsets_pt[:2]) if row_offsets_pt else [0.0, 0.0]
        self.col_offsets_pt = list(col_offsets_pt[:2]) if col_offsets_pt else [0.0, 0.0]
        self.col_x_offsets_pt = list(col_x_offsets_pt[:2]) if col_x_offsets_pt else [0.0, 0.0]
        self.row_y_offsets_pt = list(row_y_offsets_pt[:2]) if row_y_offsets_pt else [0.0, 0.0]
        while len(self.row_offsets_pt) < 2:
            self.row_offsets_pt.append(0.0)
        while len(self.col_offsets_pt) < 2:
            self.col_offsets_pt.append(0.0)
        while len(self.col_x_offsets_pt) < 2:
            self.col_x_offsets_pt.append(0.0)
        while len(self.row_y_offsets_pt) < 2:
            self.row_y_offsets_pt.append(0.0)
        self.update()
        self.changed.emit()

    def _preview_row_base_index(self, row: int) -> int:
        return 0 if row in (0, 2) else 1

    def _preview_col_base_index(self, col: int) -> int:
        return 0 if col in (0, 2) else 1

    def _preview_tile_origin_pt(self, row: int, col: int) -> tuple[float, float]:
        row_base = self._preview_row_base_index(row)
        col_base = self._preview_col_base_index(col)

        first_x = self.row_offsets_pt[row_base] + self.col_x_offsets_pt[0]
        second_x = self.page_width_pt + self.row_offsets_pt[row_base] + self.col_x_offsets_pt[1]
        if col == 0:
            x_pt = first_x
        elif col == 1:
            x_pt = second_x
        else:
            x_pt = second_x + (second_x - first_x)

        first_y = self.col_offsets_pt[col_base] + self.row_y_offsets_pt[0]
        second_y = self.page_height_pt + self.col_offsets_pt[col_base] + self.row_y_offsets_pt[1]
        if row == 0:
            y_pt = first_y
        elif row == 1:
            y_pt = second_y
        else:
            y_pt = second_y + (second_y - first_y)

        return x_pt, y_pt

    def get_explicit_placements_mm(self) -> tuple[list[Placement], int, int]:
        if self.work_area_mm is None:
            placements = [Placement(col * self.page_width_pt / POINTS_PER_MM, row * self.page_height_pt / POINTS_PER_MM, self.page_width_pt / POINTS_PER_MM, self.page_height_pt / POINTS_PER_MM, 0, row, col, 0) for row in range(2) for col in range(2)]
            return placements, 2, 2
        return build_special_mode_explicit_placements(
            self.page_width_pt / POINTS_PER_MM,
            self.page_height_pt / POINTS_PER_MM,
            [v / POINTS_PER_MM for v in self.row_offsets_pt],
            [v / POINTS_PER_MM for v in self.col_offsets_pt],
            [v / POINTS_PER_MM for v in self.col_x_offsets_pt],
            [v / POINTS_PER_MM for v in self.row_y_offsets_pt],
            self.work_area_mm,
        )

    def _layout_metrics(self) -> tuple[float, float, float, float, float]:
        if self.page_width_pt <= 0 or self.page_height_pt <= 0:
            return 20.0, 20.0, 1.0, 0.0, 0.0
        tile_positions = []
        for row in range(self.preview_rows):
            for col in range(self.preview_cols):
                x_pt, y_pt = self._preview_tile_origin_pt(row, col)
                tile_positions.append((x_pt, y_pt, x_pt + self.page_width_pt, y_pt + self.page_height_pt))
        min_x = min(pos[0] for pos in tile_positions)
        max_x = max(pos[2] for pos in tile_positions)
        min_y = min(pos[1] for pos in tile_positions)
        max_y = max(pos[3] for pos in tile_positions)
        width = max_x - min_x
        height = max_y - min_y
        margin = 28.0
        scale = min(
            max((self.width() - 2 * margin) / max(width, 1.0), 0.05),
            max((self.height() - 2 * margin) / max(height, 1.0), 0.05),
        )
        offset_x = (self.width() - width * scale) / 2.0 - min_x * scale
        offset_y = (self.height() - height * scale) / 2.0 - min_y * scale
        return offset_x, offset_y, scale, width, height

    def _tile_rects_px(self) -> list[tuple[int, int, QRectF]]:
        from PySide6.QtCore import QRectF

        if self.base_pixmap is None or self.page_width_pt <= 0 or self.page_height_pt <= 0:
            return []
        offset_x, offset_y, scale, _, _ = self._layout_metrics()
        rects: list[tuple[int, int, QRectF]] = []
        for row in range(self.preview_rows):
            for col in range(self.preview_cols):
                x_pt, y_pt = self._preview_tile_origin_pt(row, col)
                rect = QRectF(
                    offset_x + x_pt * scale,
                    offset_y + y_pt * scale,
                    self.page_width_pt * scale,
                    self.page_height_pt * scale,
                )
                rects.append((row, col, rect))
        return rects

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        cell = 24
        for y in range(0, self.height(), cell):
            for x in range(0, self.width(), cell):
                color = QColor("#f2f2f2") if ((x // cell) + (y // cell)) % 2 == 0 else QColor("#e3e3e3")
                painter.fillRect(x, y, cell, cell, color)
        if self.base_pixmap is None:
            painter.setPen(QColor("#444"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Po wygenerowaniu tutaj pojawi się edytor montażu 3×3 (wynik dalej liczony z bazowego 2×2).")
            painter.end()
            return

        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        for row, col, rect in self._tile_rects_px():
            painter.drawPixmap(rect.toRect(), self.base_pixmap)
            pen = QPen(QColor("#2f80ed" if row % 2 == 0 else "#27ae60"), 2)
            painter.setPen(pen)
            painter.drawRect(rect)
            center_x = rect.center().x()
            center_y = rect.center().y()
            painter.setPen(QPen(QColor("#c0392b"), 1, Qt.DashLine))
            painter.drawLine(int(center_x), int(rect.top()), int(center_x), int(rect.bottom()))
            painter.drawLine(int(rect.left()), int(center_y), int(rect.right()), int(center_y))
            painter.setPen(QColor("#111"))
            painter.drawText(rect.adjusted(8, 8, -8, -8), Qt.AlignTop | Qt.AlignLeft, f"R{row + 1} / K{col + 1}")

        painter.setPen(QPen(QColor("#888"), 1, Qt.DashLine))
        painter.drawText(self.rect().adjusted(12, 12, -12, -12), Qt.AlignBottom | Qt.AlignLeft,
                         "Przeciągnij kafelek: normalnie poziomo=rząd, pionowo=kolumna; z Shiftem poziomo=kolumna, pionowo=rząd.")
        painter.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.drag_tile = None
        for row, col, rect in self._tile_rects_px():
            if rect.contains(event.position()):
                self.drag_tile = (row, col)
                self.last_mouse_pos = event.position()
                break
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.drag_tile is None or self.last_mouse_pos is None or self.base_pixmap is None:
            super().mouseMoveEvent(event)
            return
        dx = event.position().x() - self.last_mouse_pos.x()
        dy = event.position().y() - self.last_mouse_pos.y()
        _, _, scale, _, _ = self._layout_metrics()
        row = self.drag_tile[0]
        col = self.drag_tile[1]
        row_index = self._preview_row_base_index(row)
        col_index = self._preview_col_base_index(col)
        if event.modifiers() & Qt.ShiftModifier:
            self.col_x_offsets_pt[col_index] += dx / max(scale, 0.001)
            self.row_y_offsets_pt[row_index] += dy / max(scale, 0.001)
        else:
            self.row_offsets_pt[row_index] += dx / max(scale, 0.001)
            self.col_offsets_pt[col_index] += dy / max(scale, 0.001)
        self.last_mouse_pos = event.position()
        self.update()
        self.changed.emit()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self.drag_tile = None
        self.last_mouse_pos = None
        super().mouseReleaseEvent(event)


class MontageEditorWindow(QDialog):
    def __init__(self, parent: QWidget | None, pixmap: QPixmap, page_size_pt: tuple[float, float], save_callback=None, finish_callback=None, finish_label: str = "Zakończ") -> None:
        super().__init__(parent)
        self.save_callback = save_callback
        self.finish_callback = finish_callback
        self.setWindowTitle("summa-cut — Edytor montażu 3×3")
        self.resize(1400, 1000)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setModal(False)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        info = QLabel(
            "Przeciągaj kafelki myszką. Widok pokazuje 3×3, ale wynik dalej liczony jest z bazowego wzoru 2×2. Normalnie: poziomo przesuwasz rząd, pionowo kolumnę. Z Shiftem: poziomo przesuwasz kolumnę, pionowo rząd."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.editor_widget = MontageEditorWidget()
        self.editor_widget.setMinimumSize(1200, 800)
        self.editor_widget.set_document(pixmap, page_size_pt[0], page_size_pt[1])

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)
        scroll.setWidget(self.editor_widget)
        layout.addWidget(scroll, 1)

        row = QHBoxLayout()
        if self.save_callback is not None:
            save_btn = QPushButton("Zapisz montaż 2×2 PDF (2 strony)")
            save_btn.clicked.connect(self.save_callback)
            row.addWidget(save_btn)
        row.addStretch(1)
        if self.finish_callback is not None:
            finish_btn = QPushButton(finish_label)
            finish_btn.clicked.connect(self.finish_callback)
            row.addWidget(finish_btn)
        if self.finish_callback is None:
            close_btn = QPushButton("Zamknij")
            close_btn.clicked.connect(self.close)
            row.addWidget(close_btn)
        layout.addLayout(row)

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(central)

    def get_offsets_pt(self) -> tuple[list[float], list[float], list[float], list[float]]:
        return self.editor_widget.get_offsets_pt()

    def set_offsets_pt(
        self,
        row_offsets_pt: list[float],
        col_offsets_pt: list[float],
        col_x_offsets_pt: list[float],
        row_y_offsets_pt: list[float],
    ) -> None:
        self.editor_widget.set_offsets_pt(row_offsets_pt, col_offsets_pt, col_x_offsets_pt, row_y_offsets_pt)

    def get_explicit_placements_mm(self) -> tuple[list[Placement], int, int]:
        return self.editor_widget.get_explicit_placements_mm()


class SpecialModeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.source_pdf_path: str = ""
        self.trimmed_print_pdf_path: Path | None = None
        self.trimmed_cut_pdf_path: Path | None = None
        self.trimmed_page_size_pt: tuple[float, float] | None = None
        self.temp_work_dir: Path | None = None
        self.editor_window: MontageEditorWindow | None = None
        self.setWindowTitle("summa-cut — Tryb specjalny")
        self.resize(980, 720)
        self._build_ui()
        self._refresh_summary()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_input_group())
        root.addWidget(self._build_options_group())
        root.addWidget(self._build_preview_group(), 1)
        root.addWidget(self._build_summary_group(), 1)
        root.addWidget(self._build_actions_group())

        self.setCentralWidget(central)
        status = QStatusBar()
        status.showMessage("Szkielet trybu specjalnego gotowy")
        self.setStatusBar(status)

    def _build_input_group(self) -> QGroupBox:
        box = QGroupBox("Plik wejściowy")
        layout = QFormLayout(box)

        self.source_pdf_edit = QLineEdit()
        self.source_pdf_edit.setReadOnly(True)
        source_btn = QPushButton("Wybierz PDF 2-stronicowy")
        source_btn.clicked.connect(self._pick_source_pdf)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_pdf_edit, 1)
        source_row.addWidget(source_btn)
        layout.addRow("PDF źródłowy:", source_row)

        hint = QLabel("Założenie na teraz: strona 1 = druk, strona 2 = wykrojnik.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#444;")
        layout.addRow(hint)
        return box

    def _build_options_group(self) -> QGroupBox:
        box = QGroupBox("Założenia prototypu")
        layout = QFormLayout(box)

        self.bleed_mm = QSpinBox()
        self.bleed_mm.setRange(0, 20)
        self.bleed_mm.setValue(2)
        self.bleed_mm.setSuffix(" mm")
        self.bleed_mm.setKeyboardTracking(False)
        self.bleed_mm.valueChanged.connect(self._refresh_summary)

        self.output_dir_edit = QLineEdit(str(Path.home() / "summa-cut-special-output"))
        output_btn = QPushButton("Wybierz katalog")
        output_btn.clicked.connect(self._pick_output_dir)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir_edit, 1)
        output_row.addWidget(output_btn)

        layout.addRow("Spad dodawany do kształtu:", self.bleed_mm)
        layout.addRow("Katalog wynikowy:", output_row)
        return box

    def _build_preview_group(self) -> QGroupBox:
        box = QGroupBox("Podgląd druku z nałożonym obrysem wykrojnika")
        layout = QVBoxLayout(box)
        self.preview_label = QLabel("Podgląd pojedynczego przytrimowanego druku z obrysem pojawi się po obróbce.")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setWordWrap(True)
        self.preview_label.setMinimumSize(640, 420)
        self.preview_label.setStyleSheet("background:#ffffff; border:1px solid #ccc; padding:8px;")
        layout.addWidget(self.preview_label)

        hint = QLabel("Edytor montażu 2×2 otwiera się teraz w osobnym dużym oknie.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#444;")
        layout.addWidget(hint)
        return box

    def _build_summary_group(self) -> QGroupBox:
        box = QGroupBox("Opis / stan")
        layout = QVBoxLayout(box)
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary)
        hint = QLabel(
            "Ten prototyp ma sprawdzić osobno, czy da się przyciąć druk do kształtu wykrojnika + spad, "
            "zanim logika trafi do głównego programu summa-cut."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#444;")
        layout.addWidget(hint)
        return box

    def _build_actions_group(self) -> QGroupBox:
        box = QGroupBox("Akcje")
        layout = QHBoxLayout(box)
        self.inspect_btn = QPushButton("Sprawdź wejście")
        self.inspect_btn.clicked.connect(self._inspect_inputs)
        self.generate_btn = QPushButton("Generuj prototyp (na razie szkic)")
        self.generate_btn.clicked.connect(self._generate_prototype)
        self.generate_montage_btn = QPushButton("Przygotuj edytor 2×2")
        self.generate_montage_btn.clicked.connect(self._generate_2x2_montage)
        self.save_montage_btn = QPushButton("Zapisz montaż 2×2 PDF (2 strony)")
        self.save_montage_btn.clicked.connect(self._save_current_montage)
        layout.addWidget(self.inspect_btn)
        layout.addWidget(self.generate_btn)
        layout.addWidget(self.generate_montage_btn)
        layout.addWidget(self.save_montage_btn)
        return box

    def _set_preview_pixmap(self, pixmap: QPixmap | None, fallback_text: str) -> None:
        if pixmap is None:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(fallback_text)
            return
        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)
        self.preview_label.resize(pixmap.size())

    def _current_offsets(self) -> tuple[list[float], list[float], list[float], list[float]]:
        if self.editor_window is not None:
            return self.editor_window.get_offsets_pt()
        return [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]

    def _open_editor_window(self, preview: QPixmap, page_size: tuple[float, float]) -> None:
        if self.editor_window is not None:
            self.editor_window.close()
        self.editor_window = MontageEditorWindow(self, preview, page_size, self._save_current_montage)
        self.editor_window.editor_widget.changed.connect(self._refresh_summary)
        self.editor_window.destroyed.connect(lambda *_: setattr(self, "editor_window", None))
        self.editor_window.show()
        self.editor_window.raise_()
        self.editor_window.activateWindow()
        self.editor_window.showMaximized()

    def _pick_source_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Wybierz PDF 2-stronicowy", "", "PDF files (*.pdf)")
        if not path:
            return
        self.source_pdf_path = path
        self.source_pdf_edit.setText(path)
        self._refresh_summary()

    def _pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Wybierz katalog wynikowy", self.output_dir_edit.text())
        if not path:
            return
        self.output_dir_edit.setText(path)
        self._refresh_summary()

    def _inspect_inputs(self) -> None:
        if not self.source_pdf_path:
            QMessageBox.information(self, "Tryb specjalny", "Najpierw wybierz PDF 2-stronicowy.")
            return
        try:
            info = read_pdf_info(self.source_pdf_path)
        except PdfReadError as exc:
            QMessageBox.warning(self, "Błąd PDF", str(exc))
            return
        if info.page_count < 2:
            QMessageBox.warning(self, "Tryb specjalny", "Wybrany PDF musi mieć co najmniej 2 strony: 1 = druk, 2 = wykrojnik.")
            return

        self.statusBar().showMessage("Sprawdzono plik wejściowy")
        self.summary.setPlainText(
            "\n".join([
                "Tryb specjalny — inspekcja wejścia",
                "",
                f"PDF źródłowy: {info.name}",
                f"  strony: {info.page_count}",
                "",
                "Strona 1 = druk",
                f"  rozmiar strony: {info.page_sizes_mm[0][0]:.2f} × {info.page_sizes_mm[0][1]:.2f} mm",
                f"  bbox zawartości: {info.page_content_sizes_mm[0][0]:.2f} × {info.page_content_sizes_mm[0][1]:.2f} mm",
                "",
                "Strona 2 = wykrojnik",
                f"  rozmiar strony: {info.page_sizes_mm[1][0]:.2f} × {info.page_sizes_mm[1][1]:.2f} mm",
                f"  bbox zawartości: {info.page_content_sizes_mm[1][0]:.2f} × {info.page_content_sizes_mm[1][1]:.2f} mm",
                "",
                f"Planowany spad: {self.bleed_mm.value()} mm",
                f"Katalog wynikowy: {self.output_dir_edit.text()}",
                "",
                "Następny etap implementacji:",
                "1. wyciągnięcie rzeczywistego obrysu wykrojnika z 2. strony PDF,",
                "2. offset obrysu o spad,",
                "3. przycięcie druku z 1. strony do tego kształtu,",
                "4. zapis próbnego PDF testowego.",
            ])
        )

    def _render_page_image(self, doc: fitz.Document, page_index: int, max_width: int = 1200) -> tuple[QImage, fitz.Page, float, float]:
        page = doc[page_index]
        scale = max_width / max(page.rect.width, 1)
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        return image, page, scale, scale

    def _qpath_to_pdf_clip_commands(self, path: QPainterPath, page: fitz.Page, offset_x: float = 0.0, offset_y: float = 0.0) -> str:
        pdf_matrix = page.transformation_matrix
        commands: list[str] = ["q"]
        for polygon in path.toFillPolygons():
            if polygon.isEmpty():
                continue
            first_qp = polygon[0]
            first = fitz.Point(first_qp.x() - offset_x, first_qp.y() - offset_y) * pdf_matrix
            commands.append(f"{first.x:.3f} {first.y:.3f} m")
            for idx in range(1, polygon.count()):
                point = polygon[idx]
                mapped = fitz.Point(point.x() - offset_x, point.y() - offset_y) * pdf_matrix
                commands.append(f"{mapped.x:.3f} {mapped.y:.3f} l")
            commands.append("h")
        commands.append("W n")
        commands.append("/fzFrm0 Do")
        commands.append("Q")
        return "\n".join(commands)

    def _save_vector_trim_pdf(
        self,
        output_path: Path,
        source_doc: fitz.Document,
        source_page_index: int,
        clip_path: QPainterPath,
        page_rect: fitz.Rect,
    ) -> tuple[float, float]:
        bounds = clip_path.boundingRect()
        if bounds.isEmpty():
            raise ValueError("Obrys wykrojnika po dodaniu spadu jest pusty.")
        out_doc = fitz.open()
        out_page = out_doc.new_page(width=bounds.width(), height=bounds.height())
        target_rect = fitz.Rect(-bounds.x(), -bounds.y(), page_rect.width - bounds.x(), page_rect.height - bounds.y())
        out_page.show_pdf_page(target_rect, source_doc, source_page_index)
        content_xrefs = out_page.get_contents()
        if not content_xrefs:
            raise ValueError("Nie udało się utworzyć treści strony wynikowej PDF.")
        clip_stream = self._qpath_to_pdf_clip_commands(clip_path, out_page, bounds.x(), bounds.y()).encode("ascii")
        out_doc.update_stream(content_xrefs[0], clip_stream)
        out_doc.save(str(output_path))
        out_doc.close()
        return bounds.width(), bounds.height()

    def _build_montage_placements(
        self,
        page_rect: fitz.Rect,
        row_offsets_pt: list[float],
        col_offsets_pt: list[float],
        col_x_offsets_pt: list[float],
        row_y_offsets_pt: list[float],
    ) -> list[fitz.Rect]:
        return [
            fitz.Rect(0 + row_offsets_pt[0] + col_x_offsets_pt[0], 0 + col_offsets_pt[0] + row_y_offsets_pt[0], page_rect.width + row_offsets_pt[0] + col_x_offsets_pt[0], page_rect.height + col_offsets_pt[0] + row_y_offsets_pt[0]),
            fitz.Rect(page_rect.width + row_offsets_pt[0] + col_x_offsets_pt[1], 0 + col_offsets_pt[1] + row_y_offsets_pt[0], page_rect.width * 2.0 + row_offsets_pt[0] + col_x_offsets_pt[1], page_rect.height + col_offsets_pt[1] + row_y_offsets_pt[0]),
            fitz.Rect(0 + row_offsets_pt[1] + col_x_offsets_pt[0], page_rect.height + col_offsets_pt[0] + row_y_offsets_pt[1], page_rect.width + row_offsets_pt[1] + col_x_offsets_pt[0], page_rect.height * 2.0 + col_offsets_pt[0] + row_y_offsets_pt[1]),
            fitz.Rect(page_rect.width + row_offsets_pt[1] + col_x_offsets_pt[1], page_rect.height + col_offsets_pt[1] + row_y_offsets_pt[1], page_rect.width * 2.0 + row_offsets_pt[1] + col_x_offsets_pt[1], page_rect.height * 2.0 + col_offsets_pt[1] + row_y_offsets_pt[1]),
        ]

    def _save_2x2_montage_pdf(
        self,
        output_path: Path,
        source_print_trim_pdf: Path,
        source_cut_trim_pdf: Path,
        row_offsets_pt: list[float],
        col_offsets_pt: list[float],
        col_x_offsets_pt: list[float],
        row_y_offsets_pt: list[float],
    ) -> None:
        print_doc = fitz.open(str(source_print_trim_pdf))
        cut_doc = fitz.open(str(source_cut_trim_pdf))
        try:
            page_rect = print_doc[0].rect
            placements = self._build_montage_placements(page_rect, row_offsets_pt, col_offsets_pt, col_x_offsets_pt, row_y_offsets_pt)
            min_x = min(rect.x0 for rect in placements)
            min_y = min(rect.y0 for rect in placements)
            max_x = max(rect.x1 for rect in placements)
            max_y = max(rect.y1 for rect in placements)
            out_doc = fitz.open()
            try:
                out_print_page = out_doc.new_page(width=max_x - min_x, height=max_y - min_y)
                for rect in placements:
                    shifted = fitz.Rect(rect.x0 - min_x, rect.y0 - min_y, rect.x1 - min_x, rect.y1 - min_y)
                    out_print_page.show_pdf_page(shifted, print_doc, 0)
                out_cut_page = out_doc.new_page(width=max_x - min_x, height=max_y - min_y)
                out_cut_page = out_doc[-1]
                for rect in placements:
                    shifted = fitz.Rect(rect.x0 - min_x, rect.y0 - min_y, rect.x1 - min_x, rect.y1 - min_y)
                    out_cut_page.show_pdf_page(shifted, cut_doc, 0)
                out_doc.save(str(output_path))
            finally:
                out_doc.close()
        finally:
            print_doc.close()
            cut_doc.close()

    def _render_preview_from_pdf(self, pdf_path: Path, max_width: int = 1200) -> QPixmap:
        preview_doc = fitz.open(str(pdf_path))
        try:
            page = preview_doc[0]
            scale = max_width / max(page.rect.width, 1)
            preview_pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
            result = QImage(
                preview_pix.samples,
                preview_pix.width,
                preview_pix.height,
                preview_pix.stride,
                QImage.Format.Format_RGBA8888,
            ).copy()
            return QPixmap.fromImage(result)
        finally:
            preview_doc.close()

    def _render_overlay_preview_from_pdfs(self, print_pdf_path: Path, cut_pdf_path: Path, max_width: int = 1200) -> QPixmap:
        print_pixmap = self._render_preview_from_pdf(print_pdf_path, max_width=max_width)
        cut_pixmap = self._render_preview_from_pdf(cut_pdf_path, max_width=max_width)
        if print_pixmap.isNull():
            return cut_pixmap
        result = QPixmap(print_pixmap.size())
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, print_pixmap)
        painter.setOpacity(0.95)
        painter.drawPixmap(0, 0, cut_pixmap)
        painter.end()
        return result

    def _cut_page_to_qpath(self, page: fitz.Page) -> QPainterPath:
        path = QPainterPath()
        for drawing in page.get_drawings():
            current_started = False
            current_point = None
            for item in drawing.get("items", []):
                op = item[0]
                if op == "re":
                    rect = item[1]
                    path.addRect(rect.x0, rect.y0, rect.width, rect.height)
                    current_started = False
                    current_point = None
                elif op == "l":
                    p1, p2 = item[1], item[2]
                    if not current_started or current_point != (p1.x, p1.y):
                        path.moveTo(p1.x, p1.y)
                    path.lineTo(p2.x, p2.y)
                    current_started = True
                    current_point = (p2.x, p2.y)
                elif op == "c":
                    p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                    if not current_started or current_point != (p1.x, p1.y):
                        path.moveTo(p1.x, p1.y)
                    path.cubicTo(p2.x, p2.y, p3.x, p3.y, p4.x, p4.y)
                    current_started = True
                    current_point = (p4.x, p4.y)
            if drawing.get("closePath"):
                path.closeSubpath()
        return path.simplified()

    def _build_trimmed_pdf(self) -> tuple[Path, Path, QPixmap, tuple[float, float]]:
        if not self.source_pdf_path:
            raise ValueError("Najpierw wybierz PDF 2-stronicowy.")
        info = read_pdf_info(self.source_pdf_path)
        if info.page_count < 2:
            raise ValueError("PDF musi mieć co najmniej 2 strony: 1 = druk, 2 = wykrojnik.")

        doc = fitz.open(self.source_pdf_path)
        try:
            print_page = doc[0]
            cut_page = doc[1]
            cut_path = self._cut_page_to_qpath(cut_page)
            if cut_path.isEmpty():
                raise ValueError("Nie udało się znaleźć wektorowego obrysu wykrojnika na stronie 2.")

            bleed_pt = self.bleed_mm.value() * 72.0 / 25.4
            stroker = QPainterPathStroker()
            stroker.setWidth(bleed_pt * 2.0)
            expanded_path = cut_path.united(stroker.createStroke(cut_path)).simplified()

            if self.temp_work_dir is None:
                self.temp_work_dir = Path(tempfile.mkdtemp(prefix="summa-cut-special-"))
            self.temp_work_dir.mkdir(parents=True, exist_ok=True)
            print_pdf_path = self.temp_work_dir / "tryb-specjalny-druk-temp.pdf"
            cut_pdf_path = self.temp_work_dir / "tryb-specjalny-wykrojnik-temp.pdf"
            page_size = self._save_vector_trim_pdf(print_pdf_path, doc, 0, expanded_path, print_page.rect)
            self._save_vector_trim_pdf(cut_pdf_path, doc, 1, expanded_path, cut_page.rect)
            preview = self._render_overlay_preview_from_pdfs(print_pdf_path, cut_pdf_path, max_width=1200)
            self.trimmed_print_pdf_path = print_pdf_path
            self.trimmed_cut_pdf_path = cut_pdf_path
            self.trimmed_page_size_pt = page_size
            return print_pdf_path, cut_pdf_path, preview, page_size
        finally:
            doc.close()

    def _generate_prototype(self) -> None:
        try:
            print_pdf_path, cut_pdf_path, preview, page_size = self._build_trimmed_pdf()
            self._set_preview_pixmap(preview, "Brak podglądu")
            self.statusBar().showMessage("Wygenerowano tymczasowe przytrimowane PDF-y druku i wykrojnika do dalszej obróbki.")
            self.summary.append("\nWygenerowano tymczasowe przytrimowane PDF-y do dalszej obróbki.")
        except (PdfReadError, ValueError) as exc:
            if self.editor_window is not None:
                self.editor_window.close()
            self._set_preview_pixmap(None, f"Nie udało się wygenerować wyniku.\n\n{exc}")
            QMessageBox.warning(self, "Tryb specjalny", str(exc))

    def _generate_2x2_montage(self) -> None:
        try:
            print_pdf_path, cut_pdf_path, preview, page_size = self._build_trimmed_pdf()
            self._set_preview_pixmap(preview, "Brak podglądu")
            self._open_editor_window(preview, page_size)
            self.statusBar().showMessage("Otworzono duży edytor montażu 2×2 na bazie druku z nałożonym obrysem wykrojnika.")
            self.summary.append("\nPrzygotowano edytor 2×2 na bazie:")
            self.summary.append("tymczasowego przytrimowanego druku z nałożonym obrysem wykrojnika")
        except Exception as exc:
            if self.editor_window is not None:
                self.editor_window.close()
            self._set_preview_pixmap(None, f"Nie udało się wygenerować montażu 2×2.\n\n{exc}")
            QMessageBox.warning(self, "Tryb specjalny", str(exc))

    def _save_current_montage(self) -> None:
        if self.trimmed_print_pdf_path is None or self.trimmed_cut_pdf_path is None or self.trimmed_page_size_pt is None:
            QMessageBox.information(self, "Tryb specjalny", "Najpierw przygotuj edytor 2×2.")
            return
        row_offsets_pt, col_offsets_pt, col_x_offsets_pt, row_y_offsets_pt = self._current_offsets()
        out_dir = Path(self.output_dir_edit.text())
        out_dir.mkdir(parents=True, exist_ok=True)
        default_path = out_dir / "tryb-specjalny-montaz-2x2.pdf"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz montaż 2×2 PDF (2 strony)",
            str(default_path),
            "PDF files (*.pdf)",
        )
        if not save_path:
            return
        montage_pdf_path = Path(save_path)
        if montage_pdf_path.suffix.lower() != ".pdf":
            montage_pdf_path = montage_pdf_path.with_suffix(".pdf")
        try:
            montage_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_2x2_montage_pdf(
                montage_pdf_path,
                self.trimmed_print_pdf_path,
                self.trimmed_cut_pdf_path,
                row_offsets_pt,
                col_offsets_pt,
                col_x_offsets_pt,
                row_y_offsets_pt,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Błąd zapisu", f"Nie udało się zapisać montażu PDF.\n\n{exc}")
            return
        self.output_dir_edit.setText(str(montage_pdf_path.parent))
        self.statusBar().showMessage(f"Zapisano montaż 2×2: {montage_pdf_path}")
        self.summary.append("\nZapisano montaż 2×2:")
        self.summary.append(str(montage_pdf_path))
        QMessageBox.information(self, "Tryb specjalny", f"Zapisano PDF:\n{montage_pdf_path}")

    def _refresh_summary(self) -> None:
        source_name = Path(self.source_pdf_path).name if self.source_pdf_path else "[nie wybrano]"
        row_offsets_pt, col_offsets_pt, col_x_offsets_pt, row_y_offsets_pt = self._current_offsets()
        self.summary.setPlainText(
            "\n".join([
                "Tryb specjalny — szkic modułu testowego",
                "",
                f"PDF źródłowy: {source_name}",
                "Założenie: strona 1 = druk, strona 2 = wykrojnik",
                f"Spad: {self.bleed_mm.value()} mm",
                f"Katalog wynikowy: {self.output_dir_edit.text()}",
                f"Rząd 1 przesunięcie poziome: {row_offsets_pt[0]:.1f} pt",
                f"Rząd 2 przesunięcie poziome: {row_offsets_pt[1]:.1f} pt",
                f"Kolumna 1 przesunięcie pionowe: {col_offsets_pt[0]:.1f} pt",
                f"Kolumna 2 przesunięcie pionowe: {col_offsets_pt[1]:.1f} pt",
                f"Kolumna 1 przesunięcie poziome (Shift): {col_x_offsets_pt[0]:.1f} pt",
                f"Kolumna 2 przesunięcie poziome (Shift): {col_x_offsets_pt[1]:.1f} pt",
                f"Rząd 1 przesunięcie pionowe (Shift): {row_y_offsets_pt[0]:.1f} pt",
                f"Rząd 2 przesunięcie pionowe (Shift): {row_y_offsets_pt[1]:.1f} pt",
                "",
                "Cel tego modułu:",
                "- sprawdzić, czy trimowanie druku do kształtu wykrojnika + spad jest wykonalne,",
                "- dopracować to poza głównym GUI,",
                "- potem włączyć jako moduł do summa-cut.",
                "",
                "Edytor 2×2:",
                "- najpierw przygotuj przytrimowany PDF,",
                "- pliki pomocnicze druku i wykrojnika są tymczasowe,",
                "- potem przeciągaj kafelki myszką,",
                "- ruch poziomy przesuwa cały rząd lewo/prawo,",
                "- ruch pionowy przesuwa całą kolumnę góra/dół,",
                "- z wciśniętym Shift: poziomo przesuwa całą kolumnę, a pionowo cały rząd,",
                "- na końcu zapisz jeden wynikowy PDF montażu 2×2 (strona 1 = druk, strona 2 = wykrojnik).",
            ])
        )
