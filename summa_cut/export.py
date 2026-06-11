from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
import pikepdf

from .models import JobSettings, LayoutResult, MontageItem, Placement
from .opos import get_opos_positions
from .pdf_io import MM_PER_POINT

POINTS_PER_MM = 1.0 / MM_PER_POINT


@dataclass
class OutputDocs:
    print_doc: fitz.Document
    cut_doc: fitz.Document


def mm_to_pt(value_mm: float) -> float:
    return value_mm * POINTS_PER_MM


def _rect_mm_to_pt(x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> fitz.Rect:
    return fitz.Rect(mm_to_pt(x_mm), mm_to_pt(y_mm), mm_to_pt(x_mm + w_mm), mm_to_pt(y_mm + h_mm))


def _draw_opos(page: fitz.Page, job: JobSettings) -> None:
    mark_mm = 2.0
    half_mark_mm = mark_mm / 2.0
    shape = page.new_shape()
    for x_mm, y_mm in get_opos_positions(job):
        rect = _rect_mm_to_pt(x_mm - half_mark_mm, y_mm - half_mark_mm, mark_mm, mark_mm)
        shape.draw_rect(rect)
    shape.finish(color=(0, 0, 0), fill=(0, 0, 0), width=1)
    shape.commit()


def _centered_clip_rect_pt(
    page_rect_pt: fitz.Rect,
    content_bbox_pt: tuple[float, float, float, float],
    clip_width_mm: float,
    clip_height_mm: float,
    rotation_deg: int,
) -> fitz.Rect:
    clip_w_pt = mm_to_pt(clip_width_mm)
    clip_h_pt = mm_to_pt(clip_height_mm)
    if rotation_deg == 90:
        clip_w_pt, clip_h_pt = clip_h_pt, clip_w_pt
    content_rect = fitz.Rect(content_bbox_pt)
    cx = (content_rect.x0 + content_rect.x1) / 2.0
    cy = (content_rect.y0 + content_rect.y1) / 2.0
    x0 = max(page_rect_pt.x0, cx - clip_w_pt / 2.0)
    y0 = max(page_rect_pt.y0, cy - clip_h_pt / 2.0)
    x1 = min(page_rect_pt.x1, x0 + clip_w_pt)
    y1 = min(page_rect_pt.y1, y0 + clip_h_pt)
    x0 = max(page_rect_pt.x0, x1 - clip_w_pt)
    y0 = max(page_rect_pt.y0, y1 - clip_h_pt)
    return fitz.Rect(x0, y0, x1, y1)


class _SourceCache:
    """Otwiera każdy plik źródłowy najwyżej raz w obrębie jednego eksportu.

    Dawniej `_place_pdf_page` wołało `fitz.open()` per placement, co przy setkach
    użytków dawało setki otwarć tego samego PDF-a — główne wąskie gardło podglądu
    (np. 117 użytków = 236 otwarć ≈ 6,4 s). Teraz otwieramy raz i reużywamy.
    """

    def __init__(self) -> None:
        self._docs: dict[str, fitz.Document] = {}

    def get(self, path: str) -> fitz.Document:
        doc = self._docs.get(path)
        if doc is None:
            doc = fitz.open(path)
            self._docs[path] = doc
        return doc

    def close(self) -> None:
        for doc in self._docs.values():
            doc.close()
        self._docs.clear()


def _resolve_print_source(job: JobSettings, placement: Placement) -> tuple[str, int, tuple[float, float, float, float]]:
    if job.montage_items:
        item: MontageItem = job.montage_items[min(max(placement.montage_item_index, 0), len(job.montage_items) - 1)]
        return item.print_page.pdf_path, item.print_page.page_index, item.print_content_bbox_pt
    return job.print_page.pdf_path, job.print_page.page_index, job.print_content_bbox_pt


def _resolve_cut_source(job: JobSettings, placement: Placement) -> tuple[str, int, tuple[float, float, float, float]]:
    if job.montage_items:
        item: MontageItem = job.montage_items[min(max(placement.montage_item_index, 0), len(job.montage_items) - 1)]
        return item.cut_page.pdf_path, item.cut_page.page_index, item.cut_content_bbox_pt
    return job.cut_page.pdf_path, job.cut_page.page_index, job.cut_content_bbox_pt


def _placement_signature(
    source_path: str,
    page_index: int,
    content_bbox_pt: tuple[float, float, float, float],
    placement: Placement,
    use_full_page: bool,
) -> tuple:
    """Klucz identyczności RYSUNKU komórki — bez pozycji (x,y/group/index).

    Dwa użytki o tej samej sygnaturze rysują piksel w piksel to samo, więc
    stempel renderujemy raz i tylko przesuwamy."""
    return (
        source_path,
        page_index,
        content_bbox_pt,
        round(placement.width_mm, 4),
        round(placement.height_mm, 4),
        placement.rotation_deg,
        use_full_page,
    )


def _render_cell_stamp(
    src: fitz.Document,
    page_index: int,
    content_bbox_pt: tuple[float, float, float, float],
    width_mm: float,
    height_mm: float,
    rotation_deg: int,
    use_full_page: bool,
) -> bytes:
    """Jednostronicowy PDF rozmiaru komórki z osadzonym źródłem w (0,0).

    Używa istniejącej ścieżki show_pdf_page (identyczny render jak dawniej),
    ale TYLKO raz na unikalną sygnaturę."""
    cell_w_pt = mm_to_pt(width_mm)
    cell_h_pt = mm_to_pt(height_mm)
    src_page = src[page_index]
    clip_rect = src_page.rect if use_full_page else _centered_clip_rect_pt(
        src_page.rect, content_bbox_pt, width_mm, height_mm, rotation_deg,
    )
    with fitz.open() as stamp:
        page = stamp.new_page(width=cell_w_pt, height=cell_h_pt)
        page.show_pdf_page(
            fitz.Rect(0, 0, cell_w_pt, cell_h_pt),
            src, page_index, rotate=rotation_deg, clip=clip_rect,
        )
        return stamp.tobytes()


def _stamp_placements_pikepdf(
    base_pdf_bytes: bytes,
    sheet_height_mm: float,
    stamp_bytes_by_sig: dict[tuple, bytes],
    placements_with_sig: list[tuple[Placement, tuple]],
) -> bytes:
    """Na stronę bazową (krata/puste, bez OPOS) nakłada stemple przez overlay.

    Konwersja układu współrzędnych: nasze mm mają origin w LEWYM-GÓRNYM rogu,
    PDF w LEWYM-DOLNYM → odbicie osi Y."""
    sheet_h_pt = mm_to_pt(sheet_height_mm)
    base = pikepdf.Pdf.open(BytesIO(base_pdf_bytes))
    target_page = base.pages[0]
    stamp_pdfs: dict[tuple, pikepdf.Pdf] = {}
    try:
        for placement, sig in placements_with_sig:
            sp = stamp_pdfs.get(sig)
            if sp is None:
                sp = pikepdf.Pdf.open(BytesIO(stamp_bytes_by_sig[sig]))
                stamp_pdfs[sig] = sp
            x0 = mm_to_pt(placement.x_mm)
            w = mm_to_pt(placement.width_mm)
            h = mm_to_pt(placement.height_mm)
            y_top = mm_to_pt(placement.y_mm)
            lly = sheet_h_pt - (y_top + h)
            rect = pikepdf.Rectangle(x0, lly, x0 + w, lly + h)
            target_page.add_overlay(sp.pages[0], rect)
        out = BytesIO()
        base.save(out)
        return out.getvalue()
    finally:
        for sp in stamp_pdfs.values():
            sp.close()
        base.close()


def _draw_generated_cut_grid(page: fitz.Page, layout: LayoutResult) -> None:
    if not layout.placements:
        return
    overshoot_mm = 1.0

    shape = page.new_shape()
    groups = sorted({placement.group for placement in layout.placements})
    for group in groups:
        group_placements = [placement for placement in layout.placements if placement.group == group]
        x_positions = sorted({placement.x_mm for placement in group_placements} | {placement.x_mm + placement.width_mm for placement in group_placements})
        y_positions = sorted({placement.y_mm for placement in group_placements} | {placement.y_mm + placement.height_mm for placement in group_placements})
        min_x = min(x_positions)
        max_x = max(x_positions)
        min_y = min(y_positions)
        max_y = max(y_positions)

        for x_mm in x_positions:
            shape.draw_line(
                fitz.Point(mm_to_pt(x_mm), mm_to_pt(min_y - overshoot_mm)),
                fitz.Point(mm_to_pt(x_mm), mm_to_pt(max_y + overshoot_mm)),
            )
        for y_mm in y_positions:
            shape.draw_line(
                fitz.Point(mm_to_pt(min_x - overshoot_mm), mm_to_pt(y_mm)),
                fitz.Point(mm_to_pt(max_x + overshoot_mm), mm_to_pt(y_mm)),
            )
    shape.finish(color=(0, 0, 0), width=1)
    shape.commit()


def generate_output_docs(job: JobSettings, layout: LayoutResult) -> OutputDocs:
    page_rect = _rect_mm_to_pt(0, 0, job.sheet_spec.width_mm, job.sheet_spec.height_mm)
    use_special = bool(job.special_mode_pattern and job.special_mode_pattern.enabled)

    # 1) BAZA (fitz): puste strony; na wykrojniku krata gdy gapless. Bez OPOS.
    with fitz.open() as print_base, fitz.open() as cut_base:
        print_base.new_page(width=page_rect.width, height=page_rect.height)
        cut_base_page = cut_base.new_page(width=page_rect.width, height=page_rect.height)
        if job.generate_cut_grid:
            _draw_generated_cut_grid(cut_base_page, layout)
        print_base_bytes = print_base.tobytes()
        cut_base_bytes = cut_base.tobytes()

    # 2) Render unikalnych stempli RAZ + lista (placement, sygnatura).
    sources = _SourceCache()
    print_stamps: dict[tuple, bytes] = {}
    cut_stamps: dict[tuple, bytes] = {}
    print_list: list[tuple[Placement, tuple]] = []
    cut_list: list[tuple[Placement, tuple]] = []
    try:
        for placement in layout.placements:
            p_path, p_idx, p_bbox = _resolve_print_source(job, placement)
            sig = _placement_signature(p_path, p_idx, p_bbox, placement, use_special)
            if sig not in print_stamps:
                print_stamps[sig] = _render_cell_stamp(
                    sources.get(p_path), p_idx, p_bbox,
                    placement.width_mm, placement.height_mm,
                    placement.rotation_deg, use_special,
                )
            print_list.append((placement, sig))

            if not job.generate_cut_grid:
                c_path, c_idx, c_bbox = _resolve_cut_source(job, placement)
                csig = _placement_signature(c_path, c_idx, c_bbox, placement, use_special)
                if csig not in cut_stamps:
                    cut_stamps[csig] = _render_cell_stamp(
                        sources.get(c_path), c_idx, c_bbox,
                        placement.width_mm, placement.height_mm,
                        placement.rotation_deg, use_special,
                    )
                cut_list.append((placement, csig))
    finally:
        sources.close()

    # 3) Montaż stempli (pikepdf).
    print_bytes = _stamp_placements_pikepdf(
        print_base_bytes, job.sheet_spec.height_mm, print_stamps, print_list,
    )
    if job.generate_cut_grid:
        cut_bytes = cut_base_bytes
    else:
        cut_bytes = _stamp_placements_pikepdf(
            cut_base_bytes, job.sheet_spec.height_mm, cut_stamps, cut_list,
        )

    # 4) OPOS na wierzchu (fitz).
    print_doc = fitz.open("pdf", print_bytes)
    cut_doc = fitz.open("pdf", cut_bytes)
    _draw_opos(print_doc[0], job)
    _draw_opos(cut_doc[0], job)
    return OutputDocs(print_doc=print_doc, cut_doc=cut_doc)


def save_output_docs(output_docs: OutputDocs, target_dir: str | Path, base_name: str = "wynik") -> tuple[Path, Path]:
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    safe_base_name = Path(base_name).stem or "wynik"
    print_path = target / f'{safe_base_name}_druk.pdf'
    cut_path = target / f'{safe_base_name}_wykrojnik.pdf'
    output_docs.print_doc.save(print_path)
    output_docs.cut_doc.save(cut_path)
    return print_path, cut_path
