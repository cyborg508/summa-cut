from __future__ import annotations

import math

from .models import JobSettings

MAX_OPOS_SPACING_MM = 500.0


def _segment_points(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    x1, y1 = start
    x2, y2 = end
    length = math.hypot(x2 - x1, y2 - y1)
    intervals = max(1, math.ceil(length / MAX_OPOS_SPACING_MM))
    return [
        (x1 + (x2 - x1) * i / intervals, y1 + (y2 - y1) * i / intervals)
        for i in range(intervals + 1)
    ]


def get_opos_positions(job: JobSettings) -> list[tuple[float, float]]:
    sheet_w = job.sheet_spec.width_mm
    sheet_h = job.sheet_spec.height_mm
    side = job.opos_spec.side_offset_mm
    top = job.opos_spec.top_offset_mm
    bottom = job.opos_spec.bottom_offset_mm

    top_left = (side, top)
    top_right = (sheet_w - side, top)
    bottom_left = (side, sheet_h - bottom)
    bottom_right = (sheet_w - side, sheet_h - bottom)

    ordered_points: list[tuple[float, float]] = []
    for start, end, split in (
        (top_left, top_right, False),
        (top_right, bottom_right, True),
        (bottom_right, bottom_left, False),
        (bottom_left, top_left, True),
    ):
        points = _segment_points(start, end) if split else [start, end]
        if ordered_points:
            points = points[1:]
        ordered_points.extend(points)

    unique_points: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for x_mm, y_mm in ordered_points:
        key = (round(x_mm, 6), round(y_mm, 6))
        if key in seen:
            continue
        seen.add(key)
        unique_points.append((x_mm, y_mm))
    return unique_points
