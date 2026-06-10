from dataclasses import dataclass, field


@dataclass
class InputFile:
    path: str
    name: str
    page_count: int
    page_sizes_mm: list[tuple[float, float]] = field(default_factory=list)
    page_content_sizes_mm: list[tuple[float, float]] = field(default_factory=list)
    page_content_boxes_pt: list[tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class SelectedPage:
    pdf_path: str
    page_index: int


@dataclass
class MontageItem:
    label: str
    print_page: SelectedPage
    cut_page: SelectedPage
    print_page_size_mm: tuple[float, float]
    cut_page_size_mm: tuple[float, float]
    print_content_size_mm: tuple[float, float]
    cut_content_size_mm: tuple[float, float]
    print_content_bbox_pt: tuple[float, float, float, float]
    cut_content_bbox_pt: tuple[float, float, float, float]
    quantity: int = 1


@dataclass
class SheetSpec:
    width_mm: float = 330.0
    height_mm: float = 480.0


@dataclass
class ItemSpec:
    width_mm: float = 0.0
    height_mm: float = 0.0
    rotation_allowed: bool = False


@dataclass
class OposSpec:
    side_offset_mm: float = 10.0
    bottom_offset_mm: float = 10.0
    top_offset_mm: float = 40.0


@dataclass
class SpecialModePattern:
    enabled: bool = False
    print_pdf_path: str = ""
    cut_pdf_path: str = ""
    page_width_mm: float = 0.0
    page_height_mm: float = 0.0
    row_offsets_mm: list[float] = field(default_factory=lambda: [0.0, 0.0])
    col_offsets_mm: list[float] = field(default_factory=lambda: [0.0, 0.0])
    col_x_offsets_mm: list[float] = field(default_factory=lambda: [0.0, 0.0])
    row_y_offsets_mm: list[float] = field(default_factory=lambda: [0.0, 0.0])
    explicit_placements: list["Placement"] = field(default_factory=list)


@dataclass
class JobSettings:
    print_page: SelectedPage
    cut_page: SelectedPage
    print_page_size_mm: tuple[float, float]
    cut_page_size_mm: tuple[float, float]
    print_content_size_mm: tuple[float, float]
    cut_content_size_mm: tuple[float, float]
    print_content_bbox_pt: tuple[float, float, float, float]
    cut_content_bbox_pt: tuple[float, float, float, float]
    sheet_spec: SheetSpec
    item_spec: ItemSpec
    gap_enabled: bool
    gap_mm: float
    generate_cut_grid: bool = False
    split_horizontal_groups: bool = False
    split_max_spread: bool = False
    manual_grid_enabled: bool = False
    manual_columns: int = 0
    manual_rows: int = 0
    montage_items: list[MontageItem] = field(default_factory=list)
    opos_spec: OposSpec = field(default_factory=OposSpec)
    special_mode_pattern: SpecialModePattern | None = None


@dataclass
class RectMM:
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float


@dataclass
class Placement:
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotation_deg: int
    row: int
    column: int
    group: int = 0
    montage_item_index: int = 0


@dataclass
class LayoutResult:
    placements: list[Placement] = field(default_factory=list)
    count: int = 0
    capacity_count: int = 0
    requested_count: int = 0
    unplaced_count: int = 0
    rows: int = 0
    columns: int = 0
    used_rotation: bool = False
    split_horizontal_groups: bool = False
    split_max_spread: bool = False
    removed_row_for_split: bool = False
    group_rows: int = 0
    manual_grid_enabled: bool = False
    work_area_rect: RectMM = field(default_factory=lambda: RectMM(0.0, 0.0, 0.0, 0.0))
    sheet_rect: RectMM = field(default_factory=lambda: RectMM(0.0, 0.0, 0.0, 0.0))


@dataclass
class AppState:
    input_files_count: int = 0
    selected_print_page: str = "—"
    selected_cut_page: str = "—"
    estimated_items: int = 0
