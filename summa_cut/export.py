from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

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


def _place_pdf_page(
    target_page: fitz.Page,
    source_path: str,
    source_page_index: int,
    content_bbox_pt: tuple[float, float, float, float],
    placement: Placement,
    use_full_page: bool = False,
) -> None:
    src = fitz.open(source_path)
    try:
        src_page = src[source_page_index]
        clip_rect = src_page.rect if use_full_page else _centered_clip_rect_pt(
            src_page.rect,
            content_bbox_pt,
            placement.width_mm,
            placement.height_mm,
            placement.rotation_deg,
        )
        rect = _rect_mm_to_pt(
            placement.x_mm,
            placement.y_mm,
            placement.width_mm,
            placement.height_mm,
        )
        target_page.show_pdf_page(rect, src, source_page_index, rotate=placement.rotation_deg, clip=clip_rect)
    finally:
        src.close()


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
    print_doc = fitz.open()
    cut_doc = fitz.open()
    print_page = print_doc.new_page(width=page_rect.width, height=page_rect.height)
    cut_page = cut_doc.new_page(width=page_rect.width, height=page_rect.height)

    use_special = bool(job.special_mode_pattern and job.special_mode_pattern.enabled)
    for placement in layout.placements:
        print_path, print_page_index, print_bbox = _resolve_print_source(job, placement)
        _place_pdf_page(
            print_page,
            print_path,
            print_page_index,
            print_bbox,
            placement,
            use_full_page=use_special,
        )
        if not job.generate_cut_grid:
            cut_path, cut_page_index, cut_bbox = _resolve_cut_source(job, placement)
            _place_pdf_page(
                cut_page,
                cut_path,
                cut_page_index,
                cut_bbox,
                placement,
                use_full_page=use_special,
            )

    if job.generate_cut_grid:
        _draw_generated_cut_grid(cut_page, layout)

    _draw_opos(print_page, job)
    _draw_opos(cut_page, job)
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
