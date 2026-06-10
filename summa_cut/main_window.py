from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .export import OutputDocs, generate_output_docs, save_output_docs
from .layout import compute_layout
from .models import AppState, InputFile, ItemSpec, JobSettings, MontageItem, SelectedPage, SheetSpec, SpecialModePattern, Placement, RectMM
from .pdf_io import PdfReadError, read_pdf_info
from .preview import render_layout_preview, render_pdf_page_to_pixmap
from .settings import load_settings, save_settings
from .special_mode_window import MontageEditorWindow, PreparedSpecialModeDocs, build_special_mode_explicit_placements, prepare_special_mode_docs


def _normalize_offset_list(values: list[float] | tuple[float, ...] | None) -> list[float]:
    result = [float(v) for v in (values or [])[:2]]
    while len(result) < 2:
        result.append(0.0)
    return result


class PdfDropListWidget(QListWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def _extract_pdf_paths(self, event) -> list[str]:
        paths: list[str] = []
        if not event.mimeData().hasUrls():
            return paths
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if path.lower().endswith(".pdf"):
                    paths.append(path)
        return paths

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._extract_pdf_paths(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._extract_pdf_paths(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._extract_pdf_paths(event)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.state = AppState()
        self.input_files: list[InputFile] = []
        self.montage_items: list[MontageItem] = []
        self.current_output_docs: OutputDocs | None = None
        self.current_layout = None
        self.special_mode_pattern: SpecialModePattern | None = None
        self.special_mode_prepared: PreparedSpecialModeDocs | None = None
        self.special_mode_editor: MontageEditorWindow | None = None
        self.preview_refresh_timer = QTimer(self)
        self.preview_refresh_timer.setSingleShot(True)
        self.preview_refresh_timer.timeout.connect(self._refresh_live_preview)
        self.setWindowTitle("summa-cut")
        self.resize(1180, 760)
        self._build_ui()
        self._apply_settings()
        self._wire_signals()
        self._update_selection_controls()
        self._update_summary()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        left_col.addWidget(self._build_files_group())
        left_col.addWidget(self._build_selection_group())
        left_col.addWidget(self._build_sheet_group())
        left_col.addWidget(self._build_item_group())
        left_col.addWidget(self._build_layout_group())
        left_col.addStretch(1)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        right_col.addWidget(self._build_preview_group(), 1)
        right_col.addWidget(self._build_actions_group())

        root.addLayout(left_col, 0)
        root.addLayout(right_col, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        status.showMessage("Gotowe do startu projektu summa-cut")
        self.setStatusBar(status)

    def _build_files_group(self) -> QGroupBox:
        box = QGroupBox("Pliki wejściowe")
        layout = QVBoxLayout(box)
        self.files_list = PdfDropListWidget()
        self.files_list.setMinimumHeight(140)
        self.files_list.setToolTip("Możesz też przeciągnąć tutaj pliki PDF")
        layout.addWidget(self.files_list)

        row = QHBoxLayout()
        open_btn = QPushButton("Otwórz PDF")
        open_btn.clicked.connect(self._open_pdf)
        remove_selected_btn = QPushButton("Usuń zaznaczone")
        remove_selected_btn.clicked.connect(self._remove_selected_files)
        clear_btn = QPushButton("Wyczyść")
        clear_btn.clicked.connect(self._clear_files)
        row.addWidget(open_btn)
        row.addWidget(remove_selected_btn)
        row.addWidget(clear_btn)
        layout.addLayout(row)
        return box

    def _build_selection_group(self) -> QGroupBox:
        box = QGroupBox("Wybór stron")
        layout = QFormLayout(box)

        self.print_file_combo = QComboBox()
        self.print_page_combo = QComboBox()
        self.cut_file_combo = QComboBox()
        self.cut_page_combo = QComboBox()
        self.print_selection_info = QLabel("Brak wyboru")
        self.cut_selection_info = QLabel("Brak wyboru")
        self.print_selection_info.setWordWrap(True)
        self.cut_selection_info.setWordWrap(True)
        self.print_selection_info.setStyleSheet("color:#444;")
        self.cut_selection_info.setStyleSheet("color:#444;")

        layout.addRow("Plik druku:", self.print_file_combo)
        layout.addRow("Strona druku:", self.print_page_combo)
        layout.addRow("Wybrany druk:", self.print_selection_info)

        self.montage_qty = QSpinBox()
        self.montage_qty.setRange(1, 10000)
        self.montage_qty.setValue(1)
        self.montage_qty.setKeyboardTracking(False)
        self.add_montage_item_btn = QPushButton("Dodaj do montażu")
        self.add_montage_item_btn.clicked.connect(self._add_selected_print_to_montage)
        montage_add_row = QWidget()
        montage_add_layout = QHBoxLayout(montage_add_row)
        montage_add_layout.setContentsMargins(0, 0, 0, 0)
        montage_add_layout.addWidget(QLabel("Ilość:"))
        montage_add_layout.addWidget(self.montage_qty)
        montage_add_layout.addWidget(self.add_montage_item_btn)
        montage_add_layout.addStretch(1)
        layout.addRow("Montaż mieszany:", montage_add_row)

        self.montage_table = QTableWidget(0, 4)
        self.montage_table.setHorizontalHeaderLabels(["Druk", "Wykrojnik", "Strony", "Ilość"])
        self.montage_table.verticalHeader().setVisible(False)
        self.montage_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.montage_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.montage_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.montage_table.setMinimumHeight(120)
        self.montage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.montage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.montage_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.montage_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addRow(self.montage_table)

        montage_actions = QWidget()
        montage_actions_layout = QHBoxLayout(montage_actions)
        montage_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.remove_montage_item_btn = QPushButton("Usuń pozycję")
        self.remove_montage_item_btn.clicked.connect(self._remove_selected_montage_item)
        self.clear_montage_btn = QPushButton("Wyczyść montaż")
        self.clear_montage_btn.clicked.connect(self._clear_montage_items)
        montage_actions_layout.addWidget(self.remove_montage_item_btn)
        montage_actions_layout.addWidget(self.clear_montage_btn)
        montage_actions_layout.addStretch(1)
        layout.addRow(montage_actions)

        self.montage_info = QLabel("Lista montażu pusta: program zachowuje się jak dotąd i powiela jeden wybrany duet druk + wykrojnik.")
        self.montage_info.setWordWrap(True)
        self.montage_info.setStyleSheet("color:#444;")
        layout.addRow("Status montażu:", self.montage_info)
        layout.addRow(QLabel(""))
        layout.addRow("Plik wykrojnika:", self.cut_file_combo)
        layout.addRow("Strona wykrojnika:", self.cut_page_combo)
        layout.addRow("Wybrany wykrojnik:", self.cut_selection_info)

        hint = QLabel("Wybory są niezależne. Domyślnie po wczytaniu PDF ustawiana jest strona 1 jako druk i strona 2 jako wykrojnik (jeśli plik ma co najmniej 2 strony). W montażu mieszanym każda dodana pozycja zapamiętuje własny duet druk + wykrojnik.")
        hint.setWordWrap(True)
        layout.addRow(hint)
        return box

    def _build_sheet_group(self) -> QGroupBox:
        box = QGroupBox("Format arkusza")
        layout = QFormLayout(box)
        self.sheet_width = QSpinBox()
        self.sheet_width.setRange(1, 5000)
        self.sheet_width.setSuffix(" mm")
        self.sheet_width.setKeyboardTracking(False)
        self.sheet_height = QSpinBox()
        self.sheet_height.setRange(1, 5000)
        self.sheet_height.setSuffix(" mm")
        self.sheet_height.setKeyboardTracking(False)
        layout.addRow("Szerokość:", self.sheet_width)
        layout.addRow("Wysokość:", self.sheet_height)
        return box

    def _build_item_group(self) -> QGroupBox:
        box = QGroupBox("Rozmiar użytku")
        layout = QFormLayout(box)
        self.item_width = QSpinBox()
        self.item_width.setRange(0, 5000)
        self.item_width.setSuffix(" mm")
        self.item_width.setKeyboardTracking(False)
        self.item_height = QSpinBox()
        self.item_height.setRange(0, 5000)
        self.item_height.setSuffix(" mm")
        self.item_height.setKeyboardTracking(False)
        self.fill_bbox_btn = QPushButton("Pobierz bounding box z wybranej strony druku")
        self.fill_bbox_btn.clicked.connect(self._fill_item_size_from_print_page)
        layout.addRow("Szerokość:", self.item_width)
        layout.addRow("Wysokość:", self.item_height)
        layout.addRow(self.fill_bbox_btn)
        return box

    def _build_layout_group(self) -> QGroupBox:
        box = QGroupBox("Układ")
        layout = QVBoxLayout(box)

        self.mode_with_gap = QRadioButton("Tryb z odstępami — wykrojnik z PDF")
        self.mode_without_gap = QRadioButton("Tryb bez odstępów — wykrojnik generowany automatycznie")
        self.mode_with_gap.setChecked(True)
        layout.addWidget(self.mode_with_gap)
        layout.addWidget(self.mode_without_gap)

        self.gap_row_widget = QWidget()
        gap_row = QHBoxLayout(self.gap_row_widget)
        gap_row.setContentsMargins(0, 0, 0, 0)
        self.gap_label = QLabel("Odstęp:")
        self.gap_mm = QSpinBox()
        self.gap_mm.setRange(0, 100)
        self.gap_mm.setSuffix(" mm")
        self.gap_mm.setKeyboardTracking(False)
        gap_row.addWidget(self.gap_label)
        gap_row.addWidget(self.gap_mm)
        gap_row.addStretch(1)
        layout.addWidget(self.gap_row_widget)

        self.rotation_allowed = QCheckBox("Zezwól na obrót 90°")
        layout.addWidget(self.rotation_allowed)

        self.split_horizontal_groups = QCheckBox("Podziel na 2 grupy w poziomie")
        self.split_horizontal_groups.setToolTip(
            "Dzieli układ na dwie równe grupy ustawione lewa/prawa. "
            "Jeśli liczba rzędów wyjdzie nieparzysta, ostatni rząd zostanie pominięty."
        )
        layout.addWidget(self.split_horizontal_groups)

        self.split_max_spread = QCheckBox("Maksymalne rozsunięcie")
        self.split_max_spread.setToolTip(
            "Przy podziale na 2 grupy rozsuwa górną i dolną część maksymalnie do granic pola OPOS."
        )
        layout.addWidget(self.split_max_spread)

        self.manual_grid_enabled = QCheckBox("Tryb manualny siatki")
        layout.addWidget(self.manual_grid_enabled)

        self.manual_grid_row_widget = QWidget()
        manual_row = QHBoxLayout(self.manual_grid_row_widget)
        manual_row.setContentsMargins(0, 0, 0, 0)
        self.manual_columns_label = QLabel("Kolumny:")
        self.manual_columns = QSpinBox()
        self.manual_columns.setRange(1, 100)
        self.manual_columns.setKeyboardTracking(False)
        self.manual_rows_label = QLabel("Rzędy:")
        self.manual_rows = QSpinBox()
        self.manual_rows.setRange(1, 100)
        self.manual_rows.setKeyboardTracking(False)
        manual_row.addWidget(self.manual_columns_label)
        manual_row.addWidget(self.manual_columns)
        manual_row.addSpacing(12)
        manual_row.addWidget(self.manual_rows_label)
        manual_row.addWidget(self.manual_rows)
        manual_row.addStretch(1)
        layout.addWidget(self.manual_grid_row_widget)
        return box

    def _build_preview_group(self) -> QGroupBox:
        box = QGroupBox("Podgląd / status projektu")
        layout = QVBoxLayout(box)

        self.preview_tabs = QTabWidget()
        self.print_preview_label = self._make_preview_label("Podgląd druku pojawi się po ustawieniu poprawnych parametrów.")
        self.cut_preview_label = self._make_preview_label("Podgląd wykrojnika pojawi się po ustawieniu poprawnych parametrów.")
        self.sheet_preview_label = self._make_preview_label("Podgląd arkusza pojawi się po ustawieniu poprawnych parametrów.")

        self.print_preview_area = self._wrap_preview_widget(self.print_preview_label)
        self.cut_preview_area = self._wrap_preview_widget(self.cut_preview_label)
        self.sheet_preview_area = self._wrap_preview_widget(self.sheet_preview_label)

        self.preview_tabs.addTab(self.print_preview_area, "Podgląd druku")
        self.preview_tabs.addTab(self.cut_preview_area, "Podgląd wykrojnika")
        self.preview_tabs.addTab(self.sheet_preview_area, "Podgląd arkusza")
        layout.addWidget(self.preview_tabs, 1)

        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.summary_label.setWordWrap(True)
        self.summary_label.setMaximumHeight(150)
        self.summary_label.setStyleSheet("background:#f5f5f5; border:1px solid #ccc; padding:12px;")
        layout.addWidget(self.summary_label)
        return box

    def _build_actions_group(self) -> QGroupBox:
        box = QGroupBox("Akcje")
        layout = QHBoxLayout(box)
        self.generate_btn = QPushButton("Generuj układ")
        self.generate_btn.clicked.connect(self._generate_layout)
        self.save_btn = QPushButton("Zapisz oba PDF")
        self.save_btn.clicked.connect(self._save_both_pdfs)
        self.special_mode_btn = QPushButton("Tryb specjalny")
        self.special_mode_btn.clicked.connect(self._open_special_mode_editor)
        layout.addWidget(self.generate_btn)
        layout.addWidget(self.special_mode_btn)
        layout.addWidget(self.save_btn)
        return box

    def _make_preview_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setMinimumSize(320, 480)
        label.setStyleSheet("background:#ffffff; border:1px solid #ccc; padding:8px;")
        return label

    def _wrap_preview_widget(self, widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(False)
        area.setAlignment(Qt.AlignCenter)
        area.setWidget(widget)
        return area

    def _set_preview_pixmap(self, label: QLabel, pixmap: QPixmap | None, fallback_text: str) -> None:
        if pixmap is None:
            label.setPixmap(QPixmap())
            label.setText(fallback_text)
            return
        label.setText("")
        label.setPixmap(pixmap)
        label.resize(pixmap.size())

    def _preview_target_size(self, area: QScrollArea, default_width: int = 900, default_height: int = 1100) -> tuple[int, int]:
        viewport = area.viewport().size()
        width = max(viewport.width() - 24, 300)
        height = max(viewport.height() - 24, 400)
        return width or default_width, height or default_height

    def _suggest_output_base_name(self) -> str:
        if self.montage_items:
            first_name = Path(self.montage_items[0].label).stem or "montaz"
            first_name = re.sub(r"^\d+\.\s*", "", first_name)
            first_name = re.sub(r"\s+", " ", first_name).strip()
            return f"{first_name}_mix"
        print_file_index = self.print_file_combo.currentIndex()
        if print_file_index < 0 or print_file_index >= len(self.input_files):
            return "wynik"
        base_name = Path(self.input_files[print_file_index].name).stem or "wynik"
        base_name = re.sub(r"^\d+\.\s*", "", base_name)
        base_name = re.sub(r"\s+", " ", base_name).strip()
        return base_name or "wynik"

    def _apply_settings(self) -> None:
        self.sheet_width.setValue(int(self.settings.get("sheet_width_mm", 330)))
        self.sheet_height.setValue(int(self.settings.get("sheet_height_mm", 480)))
        self.item_width.setValue(int(self.settings.get("item_width_mm", 0)))
        self.item_height.setValue(int(self.settings.get("item_height_mm", 0)))
        mode_with_gap = bool(self.settings.get("mode_with_gap", self.settings.get("gap_enabled", True)))
        self.mode_with_gap.setChecked(mode_with_gap)
        self.mode_without_gap.setChecked(not mode_with_gap)
        self.gap_mm.setValue(int(self.settings.get("gap_mm", 3)))
        self.rotation_allowed.setChecked(bool(self.settings.get("rotation_allowed", True)))
        self.split_horizontal_groups.setChecked(bool(self.settings.get("split_horizontal_groups", False)))
        self.split_max_spread.setChecked(bool(self.settings.get("split_max_spread", False)))
        self.manual_grid_enabled.setChecked(bool(self.settings.get("manual_grid_enabled", False)))
        self.manual_columns.setValue(int(self.settings.get("manual_columns", 1)))
        self.manual_rows.setValue(int(self.settings.get("manual_rows", 1)))
        self._update_mode_controls()

    def _save_ui_settings(self) -> None:
        self.settings.update({
            "sheet_width_mm": self.sheet_width.value(),
            "sheet_height_mm": self.sheet_height.value(),
            "item_width_mm": self.item_width.value(),
            "item_height_mm": self.item_height.value(),
            "mode_with_gap": self.mode_with_gap.isChecked(),
            "gap_mm": self.gap_mm.value(),
            "rotation_allowed": self.rotation_allowed.isChecked(),
            "split_horizontal_groups": self.split_horizontal_groups.isChecked(),
            "split_max_spread": self.split_max_spread.isChecked(),
            "manual_grid_enabled": self.manual_grid_enabled.isChecked(),
            "manual_columns": self.manual_columns.value(),
            "manual_rows": self.manual_rows.value(),
            "last_output_dir": self.settings.get("last_output_dir", str(Path.home())),
        })
        save_settings(self.settings)

    def _make_special_mode_state(
        self,
        job: JobSettings,
        row_offsets_pt: list[float],
        col_offsets_pt: list[float],
        col_x_offsets_pt: list[float],
        row_y_offsets_pt: list[float],
    ) -> dict:
        return {
            "print_pdf_path": job.print_page.pdf_path,
            "print_page_index": job.print_page.page_index,
            "cut_pdf_path": job.cut_page.pdf_path,
            "cut_page_index": job.cut_page.page_index,
            "bleed_mm": float(job.gap_mm),
            "row_offsets_pt": _normalize_offset_list(row_offsets_pt),
            "col_offsets_pt": _normalize_offset_list(col_offsets_pt),
            "col_x_offsets_pt": _normalize_offset_list(col_x_offsets_pt),
            "row_y_offsets_pt": _normalize_offset_list(row_y_offsets_pt),
        }

    def _matching_special_mode_state(self, job: JobSettings) -> dict | None:
        state = self.settings.get("special_mode_state")
        if not isinstance(state, dict):
            return None
        if state.get("print_pdf_path") != job.print_page.pdf_path:
            return None
        if int(state.get("print_page_index", -1)) != job.print_page.page_index:
            return None
        if state.get("cut_pdf_path") != job.cut_page.pdf_path:
            return None
        if int(state.get("cut_page_index", -1)) != job.cut_page.page_index:
            return None
        if abs(float(state.get("bleed_mm", -1.0)) - float(job.gap_mm)) > 1e-6:
            return None
        return state

    def _persist_special_mode_editor_state(self, job: JobSettings | None = None) -> None:
        if self.special_mode_editor is None:
            return
        active_job = job
        if active_job is None:
            try:
                active_job = self._build_job_settings()
            except Exception:
                return
        row_offsets_pt, col_offsets_pt, col_x_offsets_pt, row_y_offsets_pt = self.special_mode_editor.get_offsets_pt()
        self.settings["special_mode_state"] = self._make_special_mode_state(
            active_job,
            row_offsets_pt,
            col_offsets_pt,
            col_x_offsets_pt,
            row_y_offsets_pt,
        )
        self._save_ui_settings()

    def _wire_signals(self) -> None:
        self.sheet_width.valueChanged.connect(self._schedule_preview_refresh)
        self.sheet_height.valueChanged.connect(self._schedule_preview_refresh)
        self.item_width.valueChanged.connect(self._schedule_preview_refresh)
        self.item_height.valueChanged.connect(self._schedule_preview_refresh)
        self.mode_with_gap.toggled.connect(self._update_mode_controls)
        self.mode_with_gap.toggled.connect(self._schedule_preview_refresh)
        self.mode_without_gap.toggled.connect(self._update_mode_controls)
        self.mode_without_gap.toggled.connect(self._schedule_preview_refresh)
        self.gap_mm.valueChanged.connect(self._schedule_preview_refresh)
        self.rotation_allowed.toggled.connect(self._schedule_preview_refresh)
        self.split_horizontal_groups.toggled.connect(self._schedule_preview_refresh)
        self.split_horizontal_groups.toggled.connect(self._update_mode_controls)
        self.split_max_spread.toggled.connect(self._schedule_preview_refresh)
        self.manual_grid_enabled.toggled.connect(self._update_mode_controls)
        self.manual_grid_enabled.toggled.connect(self._schedule_preview_refresh)
        self.manual_columns.valueChanged.connect(self._schedule_preview_refresh)
        self.manual_rows.valueChanged.connect(self._schedule_preview_refresh)
        self.print_file_combo.currentIndexChanged.connect(self._on_print_file_changed)
        self.cut_file_combo.currentIndexChanged.connect(self._on_cut_file_changed)
        self.print_page_combo.currentIndexChanged.connect(self._refresh_selection_labels)
        self.print_page_combo.currentIndexChanged.connect(self._schedule_preview_refresh)
        self.cut_page_combo.currentIndexChanged.connect(self._refresh_selection_labels)
        self.cut_page_combo.currentIndexChanged.connect(self._schedule_preview_refresh)
        self.files_list.files_dropped.connect(self._add_pdf_files)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._persist_special_mode_editor_state()
        self._save_ui_settings()
        self._close_current_output_docs()
        super().closeEvent(event)

    def _open_pdf(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Wybierz PDF", "", "PDF files (*.pdf)")
        if not paths:
            return
        self._add_pdf_files(paths)

    def _add_pdf_files(self, paths: list[str]) -> None:
        self._clear_special_mode_pattern()
        added = 0
        for path in paths:
            if any(existing.path == path for existing in self.input_files):
                continue
            try:
                info = read_pdf_info(path)
            except PdfReadError as exc:
                QMessageBox.warning(self, "Błąd PDF", str(exc))
                continue

            item = InputFile(
                path=info.path,
                name=info.name,
                page_count=info.page_count,
                page_sizes_mm=info.page_sizes_mm,
                page_content_sizes_mm=info.page_content_sizes_mm,
                page_content_boxes_pt=info.page_content_boxes_pt,
            )
            self.input_files.append(item)
            self.files_list.addItem(self._format_file_item_text(item))
            added += 1

        self.state.input_files_count = len(self.input_files)
        self._update_selection_controls()
        if added:
            self.statusBar().showMessage(f"Wczytano {added} plik(ów) PDF")
        else:
            self.statusBar().showMessage("Nie dodano nowych plików PDF")
        self._schedule_preview_refresh()

    def _build_montage_item_from_selection(self) -> MontageItem:
        print_file_index = self.print_file_combo.currentIndex()
        print_page_index = self.print_page_combo.currentIndex()
        cut_file_index = self.cut_file_combo.currentIndex()
        cut_page_index = self.cut_page_combo.currentIndex()
        if print_file_index < 0 or print_page_index < 0 or print_file_index >= len(self.input_files):
            raise ValueError("Najpierw wybierz plik i stronę druku.")
        if self.mode_with_gap.isChecked():
            if cut_file_index < 0 or cut_page_index < 0 or cut_file_index >= len(self.input_files):
                raise ValueError("Przy montażu mieszanym najpierw wybierz też plik i stronę wykrojnika.")
        else:
            cut_file_index = print_file_index
            cut_page_index = print_page_index

        print_file = self.input_files[print_file_index]
        cut_file = self.input_files[cut_file_index]
        return MontageItem(
            label=print_file.name,
            print_page=SelectedPage(print_file.path, print_page_index),
            cut_page=SelectedPage(cut_file.path, cut_page_index),
            print_page_size_mm=print_file.page_sizes_mm[print_page_index],
            cut_page_size_mm=cut_file.page_sizes_mm[cut_page_index],
            print_content_size_mm=print_file.page_content_sizes_mm[print_page_index],
            cut_content_size_mm=cut_file.page_content_sizes_mm[cut_page_index],
            print_content_bbox_pt=print_file.page_content_boxes_pt[print_page_index],
            cut_content_bbox_pt=cut_file.page_content_boxes_pt[cut_page_index],
            quantity=int(self.montage_qty.value()),
        )

    def _refresh_montage_table(self) -> None:
        self.montage_table.setColumnCount(4)
        self.montage_table.setHorizontalHeaderLabels(["Druk", "Wykrojnik", "Strony", "Ilość"])
        self.montage_table.setRowCount(len(self.montage_items))
        for row, item in enumerate(self.montage_items):
            cut_label = Path(item.cut_page.pdf_path).name
            page_text = f"D {item.print_page.page_index + 1} / W {item.cut_page.page_index + 1}"
            qty_text = str(item.quantity)
            for column, value in enumerate((item.label, cut_label, page_text, qty_text)):
                table_item = QTableWidgetItem(value)
                if column == 3:
                    table_item.setTextAlignment(Qt.AlignCenter)
                self.montage_table.setItem(row, column, table_item)
        self.remove_montage_item_btn.setEnabled(bool(self.montage_items))
        self.clear_montage_btn.setEnabled(bool(self.montage_items))
        self.special_mode_btn.setEnabled(self.mode_with_gap.isChecked() and bool(self.input_files) and not self.montage_items)
        if not self.montage_items:
            self.montage_info.setText("Lista montażu pusta: program zachowuje się jak dotąd i powiela jeden wybrany duet druk + wykrojnik.")
            return
        total = sum(item.quantity for item in self.montage_items)
        self.montage_info.setText(
            f"Pozycji: {len(self.montage_items)} | razem sztuk: {total}. "
            "Każda pozycja pamięta własny druk i własny wykrojnik; wspólny rozmiar bierze się z pól Użytek."
        )

    def _add_selected_print_to_montage(self) -> None:
        self._clear_special_mode_pattern()
        try:
            new_item = self._build_montage_item_from_selection()
        except Exception as exc:
            QMessageBox.warning(self, "summa-cut", str(exc))
            return

        if self.item_width.value() <= 0 or self.item_height.value() <= 0:
            self.item_width.setValue(round(new_item.print_content_size_mm[0]))
            self.item_height.setValue(round(new_item.print_content_size_mm[1]))

        for existing in self.montage_items:
            if (
                existing.print_page.pdf_path == new_item.print_page.pdf_path
                and existing.print_page.page_index == new_item.print_page.page_index
                and existing.cut_page.pdf_path == new_item.cut_page.pdf_path
                and existing.cut_page.page_index == new_item.cut_page.page_index
            ):
                existing.quantity += new_item.quantity
                self._refresh_montage_table()
                self.statusBar().showMessage("Zwiększono ilość istniejącej pozycji montażu")
                self._schedule_preview_refresh()
                return

        self.montage_items.append(new_item)
        self._refresh_montage_table()
        self.statusBar().showMessage("Dodano pozycję do montażu mieszanego")
        self._schedule_preview_refresh()

    def _remove_selected_montage_item(self) -> None:
        rows = sorted({index.row() for index in self.montage_table.selectedIndexes()}, reverse=True)
        if not rows:
            self.statusBar().showMessage("Nie zaznaczono pozycji montażu do usunięcia")
            return
        for row in rows:
            if 0 <= row < len(self.montage_items):
                del self.montage_items[row]
        self._refresh_montage_table()
        self.statusBar().showMessage("Usunięto pozycję z listy montażu")
        self._schedule_preview_refresh()

    def _clear_montage_items(self) -> None:
        if not self.montage_items:
            return
        self.montage_items.clear()
        self._refresh_montage_table()
        self.statusBar().showMessage("Wyczyszczono listę montażu")
        self._schedule_preview_refresh()

    def _sync_montage_items_with_input_files(self) -> None:
        existing_paths = {file.path for file in self.input_files}
        before = len(self.montage_items)
        self.montage_items = [
            item
            for item in self.montage_items
            if item.print_page.pdf_path in existing_paths and item.cut_page.pdf_path in existing_paths
        ]
        if len(self.montage_items) != before:
            self.statusBar().showMessage("Usunięto z montażu pozycje wskazujące na skasowane pliki")
        self._refresh_montage_table()

    def _remove_selected_files(self) -> None:
        self._clear_special_mode_pattern()
        selected_rows = sorted({index.row() for index in self.files_list.selectedIndexes()}, reverse=True)
        if not selected_rows:
            self.statusBar().showMessage("Nie zaznaczono plików do usunięcia")
            return
        for row in selected_rows:
            if 0 <= row < len(self.input_files):
                del self.input_files[row]
            item = self.files_list.takeItem(row)
            del item
        self.state.input_files_count = len(self.input_files)
        self._sync_montage_items_with_input_files()
        self._update_selection_controls()
        self.statusBar().showMessage(f"Usunięto {len(selected_rows)} zaznaczony(ch) plik(ów)")
        self._schedule_preview_refresh()

    def _clear_files(self) -> None:
        self._clear_special_mode_pattern()
        self.input_files.clear()
        self.montage_items.clear()
        self.files_list.clear()
        self.state.input_files_count = 0
        self._refresh_montage_table()
        self._update_selection_controls()
        self.statusBar().showMessage("Wyczyszczono listę plików")
        self._schedule_preview_refresh()

    def _update_selection_controls(self) -> None:
        prev_print_file = self.print_file_combo.currentIndex()
        prev_cut_file = self.cut_file_combo.currentIndex()
        prev_print_page = self.print_page_combo.currentIndex()
        prev_cut_page = self.cut_page_combo.currentIndex()

        self.print_file_combo.blockSignals(True)
        self.cut_file_combo.blockSignals(True)

        self.print_file_combo.clear()
        self.cut_file_combo.clear()

        for file in self.input_files:
            label = f"{file.name} ({file.page_count} str.)"
            self.print_file_combo.addItem(label)
            self.cut_file_combo.addItem(label)

        has_files = bool(self.input_files)
        print_index = -1
        cut_index = -1
        if has_files:
            print_index = min(max(prev_print_file, 0), len(self.input_files) - 1)
            cut_index = min(prev_cut_file, len(self.input_files) - 1) if prev_cut_file >= 0 else print_index
            self.print_file_combo.setCurrentIndex(print_index)
            self.cut_file_combo.setCurrentIndex(cut_index)

        self.print_file_combo.blockSignals(False)
        self.cut_file_combo.blockSignals(False)

        default_cut_page = 0
        if has_files and 0 <= cut_index < len(self.input_files) and self.input_files[cut_index].page_count > 1:
            default_cut_page = 1
        self._on_print_file_changed(0 if prev_print_page < 0 else max(prev_print_page, 0), schedule_refresh=False)
        self._on_cut_file_changed(default_cut_page if prev_cut_page < 0 else max(prev_cut_page, 0), schedule_refresh=False)

        self.print_file_combo.setEnabled(has_files)
        self.print_page_combo.setEnabled(has_files)
        self.fill_bbox_btn.setEnabled(has_files)
        self.montage_qty.setEnabled(has_files)
        self.add_montage_item_btn.setEnabled(has_files)
        self._refresh_montage_table()
        self._update_mode_controls()

    def _populate_pages_combo(self, combo: QComboBox, file_index: int, selected_page_index: int = 0) -> None:
        combo.blockSignals(True)
        combo.clear()
        if 0 <= file_index < len(self.input_files):
            file = self.input_files[file_index]
            for idx, (w_mm, h_mm) in enumerate(file.page_sizes_mm, start=1):
                combo.addItem(f"Strona {idx} — {w_mm:.2f} × {h_mm:.2f} mm")
            if file.page_count:
                combo.setCurrentIndex(min(selected_page_index, file.page_count - 1))
        combo.blockSignals(False)

    def _on_print_file_changed(self, selected_page_index: int | None = None, schedule_refresh: bool = True) -> None:
        self._clear_special_mode_pattern()
        page_index = self.print_page_combo.currentIndex() if selected_page_index is None else selected_page_index
        self._populate_pages_combo(self.print_page_combo, self.print_file_combo.currentIndex(), max(page_index, 0))
        self._refresh_selection_labels()
        if schedule_refresh:
            self._schedule_preview_refresh()
        else:
            self._update_summary()

    def _on_cut_file_changed(self, selected_page_index: int | None = None, schedule_refresh: bool = True) -> None:
        self._clear_special_mode_pattern()
        page_index = self.cut_page_combo.currentIndex() if selected_page_index is None else selected_page_index
        self._populate_pages_combo(self.cut_page_combo, self.cut_file_combo.currentIndex(), max(page_index, 0))
        self._refresh_selection_labels()
        if schedule_refresh:
            self._schedule_preview_refresh()
        else:
            self._update_summary()

    def _fill_item_size_from_print_page(self) -> None:
        file_index = self.print_file_combo.currentIndex()
        page_index = self.print_page_combo.currentIndex()
        if file_index < 0 or page_index < 0 or file_index >= len(self.input_files):
            QMessageBox.information(self, "summa-cut", "Najpierw wybierz plik i stronę druku.")
            return
        width_mm, height_mm = self.input_files[file_index].page_content_sizes_mm[page_index]
        self.item_width.setValue(round(width_mm))
        self.item_height.setValue(round(height_mm))
        self.statusBar().showMessage("Ustawiono rozmiar użytku z bounding box wybranej strony druku")
        self._update_summary()

    def _format_file_item_text(self, item: InputFile) -> str:
        if item.page_sizes_mm:
            w_mm, h_mm = item.page_sizes_mm[0]
            return f"{item.name} — {item.page_count} str. — 1s: {w_mm:.2f} × {h_mm:.2f} mm"
        return f"{item.name} — {item.page_count} str."

    def _selected_page_text(self, file_combo: QComboBox, page_combo: QComboBox) -> str:
        file_index = file_combo.currentIndex()
        page_index = page_combo.currentIndex()
        if file_index < 0 or page_index < 0 or file_index >= len(self.input_files):
            return "Brak"
        file = self.input_files[file_index]
        return f"{file.name} / strona {page_index + 1}"

    def _refresh_selection_labels(self) -> None:
        self.print_selection_info.setText(self._selected_page_text(self.print_file_combo, self.print_page_combo))
        if self.mode_without_gap.isChecked():
            self.cut_selection_info.setText("Generowany automatycznie z rozmiaru użytku")
        else:
            self.cut_selection_info.setText(self._selected_page_text(self.cut_file_combo, self.cut_page_combo))

    def _update_mode_controls(self) -> None:
        with_gap = self.mode_with_gap.isChecked()
        if not with_gap and self.special_mode_pattern and self.special_mode_pattern.enabled:
            self._clear_special_mode_pattern()
        self.gap_row_widget.setVisible(with_gap)
        self.gap_label.setEnabled(with_gap)
        self.gap_mm.setEnabled(with_gap)
        split_enabled = self.split_horizontal_groups.isChecked()
        self.split_max_spread.setVisible(split_enabled)
        self.split_max_spread.setEnabled(split_enabled)
        manual = self.manual_grid_enabled.isChecked()
        self.manual_grid_row_widget.setVisible(manual)
        self.manual_columns_label.setEnabled(manual)
        self.manual_columns.setEnabled(manual)
        self.manual_rows_label.setEnabled(manual)
        self.manual_rows.setEnabled(manual)
        self.cut_file_combo.setEnabled(with_gap and bool(self.input_files))
        self.cut_page_combo.setEnabled(with_gap and bool(self.input_files))
        self.special_mode_btn.setEnabled(with_gap and bool(self.input_files) and not self.montage_items)
        self._refresh_selection_labels()

    def _pt_to_mm(self, value_pt: float) -> float:
        return value_pt * 25.4 / 72.0

    def _open_special_mode_editor(self) -> None:
        if self.montage_items:
            QMessageBox.information(self, "summa-cut", "Tryb specjalny jest na razie dostępny tylko dla jednego pliku druku, bez listy montażowej.")
            return
        if self.mode_without_gap.isChecked():
            self.mode_with_gap.setChecked(True)
            self.statusBar().showMessage("Przełączono na tryb z odstępami, żeby otworzyć tryb specjalny")
        try:
            job = self._build_job_settings()
        except Exception as exc:
            QMessageBox.warning(self, "summa-cut", str(exc))
            return
        if not self.mode_with_gap.isChecked():
            QMessageBox.information(self, "summa-cut", "Tryb specjalny działa tylko w trybie z odstępami / z wykrojnikiem z PDF.")
            return
        try:
            self.special_mode_prepared = prepare_special_mode_docs(
                job.print_page.pdf_path,
                job.print_page.page_index,
                job.cut_page.pdf_path,
                job.cut_page.page_index,
                float(self.gap_mm.value()),
                self.special_mode_prepared.temp_work_dir if self.special_mode_prepared is not None else None,
            )
        except Exception as exc:
            QMessageBox.warning(self, "summa-cut", f"Nie udało się przygotować trybu specjalnego.\n\n{exc}")
            return

        if self.special_mode_editor is not None:
            self.special_mode_editor.close()
        self.special_mode_editor = MontageEditorWindow(
            self,
            self.special_mode_prepared.preview,
            self.special_mode_prepared.page_size_pt,
            save_callback=None,
            finish_callback=self._finish_special_mode_editor,
            finish_label="Zakończ",
        )
        saved_state = self._matching_special_mode_state(job)
        if saved_state is not None:
            self.special_mode_editor.set_offsets_pt(
                _normalize_offset_list(saved_state.get("row_offsets_pt")),
                _normalize_offset_list(saved_state.get("col_offsets_pt")),
                _normalize_offset_list(saved_state.get("col_x_offsets_pt")),
                _normalize_offset_list(saved_state.get("row_y_offsets_pt")),
            )
        self.special_mode_editor.editor_widget.changed.connect(lambda: self._persist_special_mode_editor_state(job))
        self.special_mode_editor.destroyed.connect(lambda *_: setattr(self, "special_mode_editor", None))
        self.special_mode_editor.show()
        self.special_mode_editor.raise_()
        self.special_mode_editor.activateWindow()
        self.special_mode_editor.showMaximized()
        self.statusBar().showMessage("Otworzono edytor trybu specjalnego 2×2")

    def _finish_special_mode_editor(self) -> None:
        if self.special_mode_editor is None or self.special_mode_prepared is None:
            return
        row_offsets_pt, col_offsets_pt, col_x_offsets_pt, row_y_offsets_pt = self.special_mode_editor.get_offsets_pt()
        page_w_mm = self._pt_to_mm(self.special_mode_prepared.page_size_pt[0])
        page_h_mm = self._pt_to_mm(self.special_mode_prepared.page_size_pt[1])
        work_area = RectMM(
            x_mm=10.0,
            y_mm=40.0,
            width_mm=max(float(self.sheet_width.value()) - 20.0, 0.0),
            height_mm=max(float(self.sheet_height.value()) - 50.0, 0.0),
        )
        explicit_placements, rows, cols = build_special_mode_explicit_placements(
            page_w_mm,
            page_h_mm,
            [self._pt_to_mm(v) for v in row_offsets_pt],
            [self._pt_to_mm(v) for v in col_offsets_pt],
            [self._pt_to_mm(v) for v in col_x_offsets_pt],
            [self._pt_to_mm(v) for v in row_y_offsets_pt],
            work_area,
        )
        self.special_mode_pattern = SpecialModePattern(
            enabled=True,
            print_pdf_path=str(self.special_mode_prepared.print_pdf_path),
            cut_pdf_path=str(self.special_mode_prepared.cut_pdf_path),
            page_width_mm=page_w_mm,
            page_height_mm=page_h_mm,
            row_offsets_mm=[self._pt_to_mm(v) for v in row_offsets_pt],
            col_offsets_mm=[self._pt_to_mm(v) for v in col_offsets_pt],
            col_x_offsets_mm=[self._pt_to_mm(v) for v in col_x_offsets_pt],
            row_y_offsets_mm=[self._pt_to_mm(v) for v in row_y_offsets_pt],
            explicit_placements=explicit_placements,
        )
        self.settings["special_mode_state"] = self._make_special_mode_state(
            self._build_job_settings(),
            row_offsets_pt,
            col_offsets_pt,
            col_x_offsets_pt,
            row_y_offsets_pt,
        )
        self._save_ui_settings()
        self.special_mode_editor.close()
        self.statusBar().showMessage(f"Tryb specjalny: wypełniono pole robocze wzorcem {rows}×{cols} ({len(explicit_placements)} użytków)")
        self._schedule_preview_refresh()

    def _clear_special_mode_pattern(self) -> None:
        self.special_mode_pattern = None

    def _schedule_preview_refresh(self) -> None:
        self.current_layout = None
        self.state.estimated_items = 0
        self.preview_refresh_timer.start(250)
        self._update_summary(preview_pending=True)

    def _build_job_settings(self) -> JobSettings:
        print_file_index = self.print_file_combo.currentIndex()
        cut_file_index = self.cut_file_combo.currentIndex()
        print_page_index = self.print_page_combo.currentIndex()
        cut_page_index = self.cut_page_combo.currentIndex()
        with_gap = self.mode_with_gap.isChecked()
        if print_file_index < 0 or print_page_index < 0:
            raise ValueError("Najpierw wybierz plik i stronę druku.")
        if not with_gap:
            cut_file_index = print_file_index
            cut_page_index = print_page_index
        elif min(cut_file_index, cut_page_index) < 0:
            raise ValueError("W trybie z odstępami wybierz też plik i stronę wykrojnika.")

        if self.item_width.value() <= 0 or self.item_height.value() <= 0:
            raise ValueError("Rozmiar użytku musi być większy od zera.")
        if self.sheet_width.value() <= 0 or self.sheet_height.value() <= 0:
            raise ValueError("Rozmiar arkusza musi być większy od zera.")
        if self.manual_grid_enabled.isChecked():
            if self.manual_columns.value() <= 0 or self.manual_rows.value() <= 0:
                raise ValueError("W trybie manualnym liczba kolumn i rzędów musi być większa od zera.")
            if self.split_horizontal_groups.isChecked() and self.manual_rows.value() % 2 == 1:
                raise ValueError("Przy podziale na 2 grupy manualna liczba rzędów musi być parzysta.")
        if self.special_mode_pattern and self.montage_items:
            raise ValueError("Tryb specjalny nie obsługuje jeszcze listy montażowej wielu druków.")

        special_pattern = self.special_mode_pattern if self.special_mode_pattern and self.special_mode_pattern.enabled else None
        montage_items = [
            MontageItem(
                label=item.label,
                print_page=SelectedPage(item.print_page.pdf_path, item.print_page.page_index),
                cut_page=SelectedPage(item.cut_page.pdf_path, item.cut_page.page_index),
                print_page_size_mm=item.print_page_size_mm,
                cut_page_size_mm=item.cut_page_size_mm,
                print_content_size_mm=item.print_content_size_mm,
                cut_content_size_mm=item.cut_content_size_mm,
                print_content_bbox_pt=item.print_content_bbox_pt,
                cut_content_bbox_pt=item.cut_content_bbox_pt,
                quantity=item.quantity,
            )
            for item in self.montage_items
        ]

        base_print_item = montage_items[0] if montage_items else None
        print_page = base_print_item.print_page if base_print_item is not None else SelectedPage(self.input_files[print_file_index].path, print_page_index)
        cut_page = SelectedPage(self.input_files[cut_file_index].path, cut_page_index)
        print_page_size_mm = base_print_item.print_page_size_mm if base_print_item is not None else self.input_files[print_file_index].page_sizes_mm[print_page_index]
        cut_page_size_mm = self.input_files[cut_file_index].page_sizes_mm[cut_page_index]
        print_content_size_mm = base_print_item.print_content_size_mm if base_print_item is not None else self.input_files[print_file_index].page_content_sizes_mm[print_page_index]
        cut_content_size_mm = self.input_files[cut_file_index].page_content_sizes_mm[cut_page_index]
        print_content_bbox_pt = base_print_item.print_content_bbox_pt if base_print_item is not None else self.input_files[print_file_index].page_content_boxes_pt[print_page_index]
        cut_content_bbox_pt = self.input_files[cut_file_index].page_content_boxes_pt[cut_page_index]

        if special_pattern is not None:
            print_page = SelectedPage(special_pattern.print_pdf_path, 0)
            cut_page = SelectedPage(special_pattern.cut_pdf_path, 0)
            print_page_size_mm = (special_pattern.page_width_mm, special_pattern.page_height_mm)
            cut_page_size_mm = (special_pattern.page_width_mm, special_pattern.page_height_mm)
            print_content_size_mm = (special_pattern.page_width_mm, special_pattern.page_height_mm)
            cut_content_size_mm = (special_pattern.page_width_mm, special_pattern.page_height_mm)
            full_bbox = (0.0, 0.0, special_pattern.page_width_mm * 72.0 / 25.4, special_pattern.page_height_mm * 72.0 / 25.4)
            print_content_bbox_pt = full_bbox
            cut_content_bbox_pt = full_bbox

        return JobSettings(
            print_page=print_page,
            cut_page=cut_page,
            print_page_size_mm=print_page_size_mm,
            cut_page_size_mm=cut_page_size_mm,
            print_content_size_mm=print_content_size_mm,
            cut_content_size_mm=cut_content_size_mm,
            print_content_bbox_pt=print_content_bbox_pt,
            cut_content_bbox_pt=cut_content_bbox_pt,
            sheet_spec=SheetSpec(float(self.sheet_width.value()), float(self.sheet_height.value())),
            item_spec=ItemSpec(float(self.item_width.value() if special_pattern is None else special_pattern.page_width_mm), float(self.item_height.value() if special_pattern is None else special_pattern.page_height_mm), self.rotation_allowed.isChecked() if special_pattern is None else False),
            gap_enabled=with_gap if special_pattern is None else False,
            gap_mm=float(self.gap_mm.value()) if with_gap and special_pattern is None else 0.0,
            generate_cut_grid=not with_gap,
            split_horizontal_groups=self.split_horizontal_groups.isChecked(),
            split_max_spread=self.split_horizontal_groups.isChecked() and self.split_max_spread.isChecked(),
            manual_grid_enabled=self.manual_grid_enabled.isChecked(),
            manual_columns=self.manual_columns.value(),
            manual_rows=self.manual_rows.value(),
            montage_items=montage_items,
            special_mode_pattern=special_pattern,
        )

    def _close_current_output_docs(self) -> None:
        if not self.current_output_docs:
            return
        self.current_output_docs.print_doc.close()
        self.current_output_docs.cut_doc.close()
        self.current_output_docs = None

    def _refresh_live_preview(self) -> tuple[JobSettings, object] | None:
        self.save_btn.setEnabled(False)
        try:
            job = self._build_job_settings()
            layout = compute_layout(job)
            if layout.unplaced_count > 0:
                raise ValueError(
                    f"Na tej formatce mieści się {layout.capacity_count} szt., a lista montażu żąda {layout.requested_count} szt. "
                    f"Brakuje miejsca na {layout.unplaced_count} szt."
                )
            if layout.count <= 0:
                raise ValueError("Przy tych parametrach żaden użytek nie mieści się w polu roboczym OPOS.")
            self._close_current_output_docs()
            output_docs = generate_output_docs(job, layout)
            self.current_output_docs = output_docs
            self.current_layout = layout
            print_w, print_h = self._preview_target_size(self.print_preview_area)
            cut_w, cut_h = self._preview_target_size(self.cut_preview_area)
            sheet_w, sheet_h = self._preview_target_size(self.sheet_preview_area)
            self._set_preview_pixmap(self.print_preview_label, render_pdf_page_to_pixmap(output_docs.print_doc, max_width=print_w, max_height=print_h), "Brak podglądu druku")
            self._set_preview_pixmap(self.cut_preview_label, render_pdf_page_to_pixmap(output_docs.cut_doc, max_width=cut_w, max_height=cut_h), "Brak podglądu wykrojnika")
            self._set_preview_pixmap(self.sheet_preview_label, render_layout_preview(job, layout, width_px=sheet_w, height_px=sheet_h), "Brak podglądu arkusza")
            self.save_btn.setEnabled(True)
            self._update_summary()
            return job, layout
        except Exception as exc:
            self._close_current_output_docs()
            self.current_layout = None
            self._set_preview_pixmap(self.print_preview_label, None, f"Brak podglądu druku.\n\n{exc}")
            self._set_preview_pixmap(self.cut_preview_label, None, f"Brak podglądu wykrojnika.\n\n{exc}")
            self._set_preview_pixmap(self.sheet_preview_label, None, f"Brak podglądu arkusza.\n\n{exc}")
            self._update_summary(error_text=str(exc))
            return None

    def _generate_layout(self) -> None:
        result = self._refresh_live_preview()
        if result is None:
            QMessageBox.warning(self, "summa-cut", "Nie udało się wygenerować układu. Sprawdź parametry i podgląd błędu.")
            return
        _job, layout = result
        self.statusBar().showMessage(f"Układ wygenerowany: {layout.count} użytków ({layout.columns} × {layout.rows})")
        self._update_summary()

    def _save_both_pdfs(self) -> None:
        if not self.current_output_docs:
            if self._refresh_live_preview() is None:
                QMessageBox.warning(self, "summa-cut", "Najpierw ustaw poprawne parametry i wygeneruj układ.")
                return
        print_file_index = self.print_file_combo.currentIndex()
        if print_file_index < 0 or print_file_index >= len(self.input_files):
            QMessageBox.warning(self, "summa-cut", "Najpierw wybierz plik druku.")
            return
        default_base_name = self._suggest_output_base_name()
        last_output_dir = Path(self.settings.get("last_output_dir", str(Path.home())))

        dialog = QFileDialog(self, "Zapisz wynik PDF", str(last_output_dir), "PDF (*.pdf)")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setDefaultSuffix("pdf")
        dialog.selectFile(f"{default_base_name}_druk.pdf")
        dialog.setLabelText(QFileDialog.Accept, "Zapisz")

        if dialog.exec() != QDialog.Accepted or not self.current_output_docs:
            return

        selected_path = Path(dialog.selectedFiles()[0])
        target_dir = selected_path.parent
        selected_name = selected_path.stem
        base_name = selected_name[:-5] if selected_name.endswith("_druk") else selected_name

        self.settings["last_output_dir"] = str(target_dir)
        self._save_ui_settings()
        print_path, cut_path = save_output_docs(self.current_output_docs, target_dir, base_name)
        self.statusBar().showMessage(f"Zapisano {print_path.name} i {cut_path.name}")
        QMessageBox.information(self, "summa-cut", f"Zapisano:\n- {print_path}\n- {cut_path}")

    def _update_summary(self, preview_pending: bool = False, error_text: str | None = None) -> None:
        mode = "z odstępami" if self.mode_with_gap.isChecked() else "bez odstępów"
        cut_mode = "wykrojnik z PDF" if self.mode_with_gap.isChecked() else "wykrojnik generowany automatycznie"
        rotation = "tak" if self.rotation_allowed.isChecked() else "nie"
        montage_total = sum(item.quantity for item in self.montage_items)
        print_selection = self._selected_page_text(self.print_file_combo, self.print_page_combo)
        if self.montage_items:
            print_selection = f"Lista mieszana: {len(self.montage_items)} poz. / {montage_total} szt."
        cut_selection = self.cut_selection_info.text()
        layout_lines = ["Układ jeszcze niegotowy"]
        if preview_pending:
            layout_lines = ["Podgląd odświeża się…"]
        elif error_text:
            layout_lines = [f"Błąd: {error_text}"]
        elif self.current_layout is not None:
            layout = self.current_layout
            self.state.estimated_items = layout.count
            layout_lines = [
                f"Użytki: {layout.count}",
                f"Siatka: {layout.columns} × {layout.rows}",
                f"Pojemność siatki: {layout.capacity_count}",
                f"Obrót użyty: {'tak' if layout.used_rotation else 'nie'}",
                f"Pole robocze: {layout.work_area_rect.width_mm:.1f} × {layout.work_area_rect.height_mm:.1f} mm",
            ]
            if layout.requested_count:
                layout_lines.append(f"Zamówione z listy: {layout.requested_count}")
            if layout.manual_grid_enabled:
                layout_lines.append("Tryb manualny siatki: tak")
            if layout.split_horizontal_groups:
                layout_lines.append(f"Podział na 2 grupy: tak ({layout.group_rows} rz. na grupę)")
                layout_lines.append(f"Maksymalne rozsunięcie: {'tak' if layout.split_max_spread else 'nie'}")
                if layout.removed_row_for_split:
                    layout_lines.append("Usunięto 1 rząd, żeby grupy były równe")
        self.summary_label.setText(
            "\n".join([
                "summa-cut — v0.3",
                "",
                f"Pliki wejściowe: {len(self.input_files)}",
                f"Druk: {print_selection}",
                f"Wykrojnik: {cut_selection}",
                f"Arkusz: {self.sheet_width.value()} × {self.sheet_height.value()} mm",
                f"Użytek: {self.item_width.value()} × {self.item_height.value()} mm",
                f"Tryb: {mode}",
                f"Odstęp: {self.gap_mm.value()} mm" if self.mode_with_gap.isChecked() else "Odstęp: brak (układ na styk)",
                f"Obrót 90°: {rotation}",
                f"Lista montażu: {len(self.montage_items)} poz. / {montage_total} szt." if self.montage_items else "Lista montażu: wyłączona",
                f"Podziel na 2: {'tak' if self.split_horizontal_groups.isChecked() else 'nie'}",
                f"Maks. rozsunięcie: {'tak' if self.split_max_spread.isChecked() and self.split_horizontal_groups.isChecked() else 'nie'}",
                f"Siatka manualna: {'tak' if self.manual_grid_enabled.isChecked() else 'nie'}",
                f"Manualnie: {self.manual_columns.value()} × {self.manual_rows.value()}" if self.manual_grid_enabled.isChecked() else "Manualnie: auto",
                f"Tryb wykrojnika: {cut_mode}",
                f"Tryb specjalny: {'tak' if self.special_mode_pattern and self.special_mode_pattern.enabled else 'nie'}",
                "",
                *layout_lines,
            ])
        )
