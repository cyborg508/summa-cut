from __future__ import annotations

from .models import JobSettings, LayoutResult, Placement, RectMM


def _fit_count(span_mm: float, item_mm: float, gap_mm: float) -> int:
    if item_mm <= 0 or span_mm <= 0:
        return 0
    step = item_mm + gap_mm
    if step <= 0:
        return 0
    return max(int((span_mm + gap_mm) // step), 0)


def _build_special_mode_placements(job: JobSettings, work_area: RectMM) -> tuple[list[Placement], int, int]:
    pattern = job.special_mode_pattern
    if pattern is None or not pattern.enabled or pattern.page_width_mm <= 0 or pattern.page_height_mm <= 0:
        return [], 0, 0
    if pattern.explicit_placements:
        rows = max((p.row for p in pattern.explicit_placements), default=-1) + 1
        cols = max((p.column for p in pattern.explicit_placements), default=-1) + 1
        return list(pattern.explicit_placements), rows, cols

    local_positions: dict[tuple[int, int], tuple[float, float]] = {}
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    for row in range(2):
        for col in range(2):
            x = col * pattern.page_width_mm + pattern.row_offsets_mm[row] + pattern.col_x_offsets_mm[col]
            y = row * pattern.page_height_mm + pattern.col_offsets_mm[col] + pattern.row_y_offsets_mm[row]
            local_positions[(row, col)] = (x, y)
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + pattern.page_width_mm)
            max_y = max(max_y, y + pattern.page_height_mm)

    normalized_positions = {
        key: (value[0] - min_x, value[1] - min_y)
        for key, value in local_positions.items()
    }
    block_width = max_x - min_x
    block_height = max_y - min_y
    if block_width <= 0 or block_height <= 0:
        return [], 0, 0

    row_delta_x = {
        row: normalized_positions[(row, 1)][0] - normalized_positions[(row, 0)][0]
        for row in range(2)
    }
    col_delta_y = {
        col: normalized_positions[(1, col)][1] - normalized_positions[(0, col)][1]
        for col in range(2)
    }
    row_repeat_x = {
        row: 2.0 * row_delta_x[row] if row_delta_x[row] > 0 else block_width
        for row in range(2)
    }
    col_repeat_y = {
        col: 2.0 * col_delta_y[col] if col_delta_y[col] > 0 else block_height
        for col in range(2)
    }

    def make_raw(rows: int, cols: int) -> list[Placement]:
        result: list[Placement] = []
        for row in range(rows):
            for col in range(cols):
                row_kind = row % 2
                col_kind = col % 2
                block_row = row // 2
                block_col = col // 2
                local_x, local_y = normalized_positions[(row_kind, col_kind)]
                x = local_x + block_col * row_repeat_x[row_kind]
                y = local_y + block_row * col_repeat_y[col_kind]
                result.append(Placement(x, y, pattern.page_width_mm, pattern.page_height_mm, 0, row, col, 0))
        return result

    def fits(rows: int, cols: int) -> tuple[bool, list[Placement]]:
        placements = make_raw(rows, cols)
        if not placements:
            return False, []
        min_x = min(p.x_mm for p in placements)
        min_y = min(p.y_mm for p in placements)
        max_x = max(p.x_mm + p.width_mm for p in placements)
        max_y = max(p.y_mm + p.height_mm for p in placements)
        width = max_x - min_x
        height = max_y - min_y
        if width > work_area.width_mm or height > work_area.height_mm:
            return False, []
        shift_x = work_area.x_mm + max((work_area.width_mm - width) / 2.0, 0.0) - min_x
        shift_y = work_area.y_mm + max((work_area.height_mm - height) / 2.0, 0.0) - min_y
        shifted = [Placement(p.x_mm + shift_x, p.y_mm + shift_y, p.width_mm, p.height_mm, p.rotation_deg, p.row, p.column, p.group) for p in placements]
        return True, shifted

    min_repeat_width = min(max(row_repeat_x.values()), block_width)
    min_repeat_height = min(max(col_repeat_y.values()), block_height)
    max_cols = max(int(work_area.width_mm // max(min_repeat_width, 1.0)) + 3, 1)
    max_rows = max(int(work_area.height_mm // max(min_repeat_height, 1.0)) + 3, 1)
    best: tuple[int, int, list[Placement]] = (0, 0, [])
    for rows in range(1, max_rows + 1):
        for cols in range(1, max_cols + 1):
            ok, placements = fits(rows, cols)
            if not ok:
                continue
            count = rows * cols
            if count > best[0] * best[1]:
                best = (rows, cols, placements)
    return best[2], best[0], best[1]


def _apply_montage_quantities(job: JobSettings, placements: list[Placement]) -> tuple[list[Placement], int, int]:
    requested_count = sum(max(item.quantity, 0) for item in job.montage_items)
    if requested_count <= 0:
        return placements, 0, 0

    limited = placements[:requested_count]
    cursor = 0
    for item_index, item in enumerate(job.montage_items):
        for _ in range(max(item.quantity, 0)):
            if cursor >= len(limited):
                return limited, requested_count, requested_count - len(limited)
            limited[cursor].montage_item_index = item_index
            cursor += 1
    return limited[:cursor], requested_count, max(requested_count - cursor, 0)


def compute_layout(job: JobSettings) -> LayoutResult:
    sheet = RectMM(0.0, 0.0, job.sheet_spec.width_mm, job.sheet_spec.height_mm)
    work_area = RectMM(
        x_mm=job.opos_spec.side_offset_mm,
        y_mm=job.opos_spec.top_offset_mm,
        width_mm=max(job.sheet_spec.width_mm - 2 * job.opos_spec.side_offset_mm, 0.0),
        height_mm=max(job.sheet_spec.height_mm - job.opos_spec.top_offset_mm - job.opos_spec.bottom_offset_mm, 0.0),
    )

    if job.special_mode_pattern and job.special_mode_pattern.enabled:
        placements, rows, cols = _build_special_mode_placements(job, work_area)
        capacity_count = len(placements)
        placements, requested_count, unplaced_count = _apply_montage_quantities(job, placements)
        return LayoutResult(
            placements=placements,
            count=len(placements),
            capacity_count=capacity_count,
            requested_count=requested_count,
            unplaced_count=unplaced_count,
            rows=rows,
            columns=cols,
            used_rotation=False,
            split_horizontal_groups=False,
            split_max_spread=False,
            removed_row_for_split=False,
            group_rows=0,
            manual_grid_enabled=False,
            work_area_rect=work_area,
            sheet_rect=sheet,
        )

    gap_mm = job.gap_mm if job.gap_enabled else 0.0
    variants: list[tuple[int, int, int, float, float, int, int, bool]] = []

    base_width_mm = job.item_spec.width_mm + gap_mm
    base_height_mm = job.item_spec.height_mm + gap_mm
    dims = [(base_width_mm, base_height_mm, 0)]
    if job.item_spec.rotation_allowed and base_width_mm != base_height_mm:
        dims.append((base_height_mm, base_width_mm, 90))

    for width_mm, height_mm, rotation_deg in dims:
        if job.split_horizontal_groups:
            if job.manual_grid_enabled:
                cols = job.manual_columns
                full_rows = job.manual_rows
            else:
                cols = _fit_count(work_area.width_mm, width_mm, 0.0)
                full_rows = _fit_count(work_area.height_mm, height_mm, 0.0)
            rows = full_rows
            removed_row = False
            if job.manual_grid_enabled and rows % 2 == 1:
                continue
            removed_row = rows % 2 == 1
            if removed_row:
                rows -= 1
            group_rows = rows // 2 if rows > 0 else 0
            count = cols * rows
            half_height = work_area.height_mm / 2.0
            fits = cols > 0 and group_rows > 0 and (cols * width_mm) <= work_area.width_mm and (group_rows * height_mm) <= half_height
        else:
            if job.manual_grid_enabled:
                cols = job.manual_columns
                rows = job.manual_rows
            else:
                cols = _fit_count(work_area.width_mm, width_mm, 0.0)
                rows = _fit_count(work_area.height_mm, height_mm, 0.0)
            count = cols * rows
            group_rows = 0
            removed_row = False
            fits = cols > 0 and rows > 0 and (cols * width_mm) <= work_area.width_mm and (rows * height_mm) <= work_area.height_mm
        if fits:
            variants.append((count, rows, cols, width_mm, height_mm, rotation_deg, group_rows, removed_row))

    count, rows, cols, item_w, item_h, rotation_deg, group_rows, removed_row = max(variants, key=lambda v: (v[0], -v[5])) if variants else (0, 0, 0, 0.0, 0.0, 0, 0, False)

    placements: list[Placement] = []
    if count > 0:
        if job.split_horizontal_groups:
            group_height = group_rows * item_h
            grid_width = cols * item_w
            start_x = work_area.x_mm + max((work_area.width_mm - grid_width) / 2.0, 0.0)
            if job.split_max_spread:
                top_start_y = work_area.y_mm
                bottom_start_y = work_area.y_mm + work_area.height_mm - group_height
            else:
                half_height = work_area.height_mm / 2.0
                top_half_y = work_area.y_mm
                bottom_half_y = work_area.y_mm + half_height
                top_start_y = top_half_y + max((half_height - group_height) / 2.0, 0.0)
                bottom_start_y = bottom_half_y + max((half_height - group_height) / 2.0, 0.0)

            for group_index, group_start_y in enumerate((top_start_y, bottom_start_y)):
                for row in range(group_rows):
                    for col in range(cols):
                        x = start_x + col * item_w
                        y = group_start_y + row * item_h
                        placements.append(Placement(x, y, item_w, item_h, rotation_deg, group_index * group_rows + row, col, group_index))
        else:
            grid_width = cols * item_w
            grid_height = rows * item_h
            start_x = work_area.x_mm + max((work_area.width_mm - grid_width) / 2.0, 0.0)
            start_y = work_area.y_mm + max((work_area.height_mm - grid_height) / 2.0, 0.0)
            for row in range(rows):
                for col in range(cols):
                    x = start_x + col * item_w
                    y = start_y + row * item_h
                    placements.append(Placement(x, y, item_w, item_h, rotation_deg, row, col, 0))

    capacity_count = len(placements)
    placements, requested_count, unplaced_count = _apply_montage_quantities(job, placements)
    return LayoutResult(
        placements=placements,
        count=len(placements),
        capacity_count=capacity_count,
        requested_count=requested_count,
        unplaced_count=unplaced_count,
        rows=rows,
        columns=cols,
        used_rotation=rotation_deg == 90,
        split_horizontal_groups=job.split_horizontal_groups,
        split_max_spread=job.split_max_spread,
        removed_row_for_split=removed_row,
        group_rows=group_rows,
        manual_grid_enabled=job.manual_grid_enabled,
        work_area_rect=work_area,
        sheet_rect=sheet,
    )
