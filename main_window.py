
from __future__ import annotations

import copy
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from canvas import MapCanvas
from model import AreaDef, CheckDef, MapDef, MapLink, MapLocation, PackModel
from pack_io import export_pack_to_zip, load_pack_from_zip


SCRIPT_DIR = Path(__file__).resolve().parent


def dialog_start_path(previous_path: Optional[str] = None, default_name: Optional[str] = None) -> str:
    if previous_path:
        candidate = Path(previous_path).expanduser()
        if not candidate.is_absolute():
            candidate = SCRIPT_DIR / candidate
        if candidate.exists():
            return str(candidate)
        if candidate.parent.exists():
            return str(candidate.parent)
    if default_name:
        return str(SCRIPT_DIR / default_name)
    return str(SCRIPT_DIR)


class AddEditMapDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        title: str,
        existing_names: List[str],
        allowed_map_ids: List[str],
        existing_ids: List[str],
        original_name: Optional[str] = None,
        original_id: Optional[str] = None,
        initial_id: str = "",
        initial_name: str = "",
        initial_group: str = "",
        initial_image: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._existing_names = set(existing_names)
        self._allowed_map_ids = allowed_map_ids
        self._allowed_map_id_set = set(allowed_map_ids)
        self._existing_ids = set(existing_ids)
        self._original_name = original_name
        self._original_id = original_id

        layout = QtWidgets.QFormLayout(self)
        self.cb_id = QtWidgets.QComboBox()
        self.cb_id.setEditable(True)
        self.cb_id.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_id.addItems(self._allowed_map_ids)
        self.cb_id.setCurrentText(initial_id)
        self.cb_id.setMaxVisibleItems(20)
        id_completer = QtWidgets.QCompleter(self._allowed_map_ids, self.cb_id)
        id_completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        id_completer.setFilterMode(QtCore.Qt.MatchContains)
        id_completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.cb_id.setCompleter(id_completer)
        self.ed_name = QtWidgets.QLineEdit(initial_name)
        self.ed_group = QtWidgets.QLineEdit(initial_group)
        self.ed_image = QtWidgets.QLineEdit(initial_image)
        self.btn_browse = QtWidgets.QPushButton("Browse…")
        image_row = QtWidgets.QHBoxLayout()
        image_row.addWidget(self.ed_image, 1)
        image_row.addWidget(self.btn_browse)

        layout.addRow("Id", self.cb_id)
        layout.addRow("Name", self.ed_name)
        layout.addRow("Group", self.ed_group)
        layout.addRow("Image", image_row)

        self.btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addRow(self.btns)

        self.btn_browse.clicked.connect(self.on_browse)
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        self.resize(620, 155)

    def on_browse(self) -> None:
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose map image",
            dialog_start_path(self.ed_image.text().strip()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*.*)",
        )
        if fn:
            self.ed_image.setText(fn)

    def values(self) -> Tuple[str, str, str, str]:
        return (
            self.cb_id.currentText().strip(),
            self.ed_name.text().strip(),
            self.ed_group.text().strip(),
            self.ed_image.text().strip(),
        )

    def accept(self) -> None:
        map_id, name, _, image = self.values()
        if not map_id:
            QtWidgets.QMessageBox.warning(self, "Validation", "Map id is required.")
            return
        if self._allowed_map_ids and map_id not in self._allowed_map_id_set:
            QtWidgets.QMessageBox.warning(
                self,
                "Validation",
                "Map id must be selected from the allowed map ids list.",
            )
            return
        if map_id in self._existing_ids and map_id != self._original_id:
            QtWidgets.QMessageBox.warning(self, "Validation", f"Map id '{map_id}' already exists.")
            return
        if not name:
            QtWidgets.QMessageBox.warning(self, "Validation", "Map name is required.")
            return
        if name in self._existing_names and name != self._original_name:
            QtWidgets.QMessageBox.warning(self, "Validation", f"Map name '{name}' already exists.")
            return
        if not image:
            QtWidgets.QMessageBox.warning(self, "Validation", "Map image is required.")
            return
        super().accept()


class AddCheckDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        map_name: Optional[str],
        allowed_soh_ids: List[str],
        preset_xy: Optional[Tuple[int, int]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Check")
        self._map_name = map_name or ""
        self._allowed_soh_ids = allowed_soh_ids
        self._allowed_soh_set = set(allowed_soh_ids)

        layout = QtWidgets.QFormLayout(self)
        self.ed_name = QtWidgets.QLineEdit()
        self.ed_hint = QtWidgets.QLineEdit()
        self.cb_soh = QtWidgets.QComboBox()
        self.cb_soh.setEditable(True)
        self.cb_soh.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_soh.addItems(self._allowed_soh_ids)
        self.cb_soh.setMaxVisibleItems(20)
        completer = QtWidgets.QCompleter(self._allowed_soh_ids, self.cb_soh)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.cb_soh.setCompleter(completer)

        self.ed_map = QtWidgets.QLineEdit(self._map_name)
        self.ed_map.setReadOnly(True)

        if map_name and preset_xy:
            self.lbl_hint = QtWidgets.QLabel(f"Location preset: {preset_xy[0]}, {preset_xy[1]}")
        else:
            self.lbl_hint = QtWidgets.QLabel("")

        layout.addRow("Map", self.ed_map)
        layout.addRow("Name", self.ed_name)
        layout.addRow("Hint", self.ed_hint)
        layout.addRow("soh_id", self.cb_soh)
        layout.addRow(self.lbl_hint)

        self.btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        layout.addRow(self.btns)
        self.resize(560, 170)

    def values(self) -> Tuple[str, str, str]:
        return (
            self.ed_name.text().strip(),
            self.ed_hint.text().strip(),
            self.cb_soh.currentText().strip(),
        )

    def accept(self) -> None:
        check_name, _, soh_id = self.values()
        if not self._map_name:
            QtWidgets.QMessageBox.warning(self, "Validation", "A current map is required.")
            return
        if not check_name:
            QtWidgets.QMessageBox.warning(self, "Validation", "Check name is required.")
            return
        if not soh_id:
            QtWidgets.QMessageBox.warning(self, "Validation", "soh_id is required.")
            return
        if self._allowed_soh_ids and soh_id not in self._allowed_soh_set:
            QtWidgets.QMessageBox.warning(
                self,
                "Validation",
                "soh_id must be selected from the allowed in-game checks list.",
            )
            return
        super().accept()


class EditLocationDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        title: str,
        available_maps: List[MapDef],
        initial_map_id: str = "",
        initial_x: int = 0,
        initial_y: int = 0,
        initial_size: int = 24,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._valid_map_ids = [map_def.id for map_def in available_maps if map_def.id]
        self._valid_map_id_set = set(self._valid_map_ids)
        self._label_to_map_id: Dict[str, str] = {}

        layout = QtWidgets.QFormLayout(self)

        self.cb_map = QtWidgets.QComboBox()
        self.cb_map.setEditable(True)
        self.cb_map.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_map.setMaxVisibleItems(20)
        labels: List[str] = []
        for map_def in available_maps:
            if not map_def.id:
                continue
            label = f"{map_def.name} [{map_def.id}]"
            self.cb_map.addItem(label, map_def.id)
            self._label_to_map_id[label] = map_def.id
            labels.append(label)

        if initial_map_id and initial_map_id not in self._valid_map_id_set:
            missing_label = f"{initial_map_id} (missing from pack)"
            self.cb_map.addItem(missing_label, initial_map_id)
            self._label_to_map_id[missing_label] = initial_map_id
            labels.append(missing_label)

        completer = QtWidgets.QCompleter(labels, self.cb_map)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.cb_map.setCompleter(completer)
        if self.cb_map.lineEdit():
            self.cb_map.lineEdit().setPlaceholderText("Select a map from this pack")

        current_index = self.cb_map.findData(initial_map_id)
        if current_index >= 0:
            self.cb_map.setCurrentIndex(current_index)
        else:
            self.cb_map.setEditText(initial_map_id)

        self.sp_x = QtWidgets.QSpinBox()
        self.sp_x.setRange(-99999, 99999)
        self.sp_x.setValue(initial_x)
        self.sp_y = QtWidgets.QSpinBox()
        self.sp_y.setRange(-99999, 99999)
        self.sp_y.setValue(initial_y)
        self.sp_size = QtWidgets.QSpinBox()
        self.sp_size.setRange(1, 99999)
        self.sp_size.setValue(max(1, initial_size))

        layout.addRow("Map id", self.cb_map)
        layout.addRow("X", self.sp_x)
        layout.addRow("Y", self.sp_y)
        layout.addRow("Size", self.sp_size)

        self.btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        layout.addRow(self.btns)
        self.resize(560, 180)

    def _selected_map_id(self) -> str:
        text = self.cb_map.currentText().strip()
        index = self.cb_map.currentIndex()
        if index >= 0 and self.cb_map.itemText(index).strip() == text:
            data = self.cb_map.itemData(index)
            if isinstance(data, str):
                return data.strip()
        return self._label_to_map_id.get(text, text)

    def values(self) -> Tuple[str, int, int, int]:
        return (
            self._selected_map_id(),
            self.sp_x.value(),
            self.sp_y.value(),
            self.sp_size.value(),
        )

    def accept(self) -> None:
        map_id, _, _, _ = self.values()
        if not map_id:
            QtWidgets.QMessageBox.warning(self, "Validation", "Map id is required.")
            return
        if self._valid_map_id_set and map_id not in self._valid_map_id_set:
            QtWidgets.QMessageBox.warning(
                self,
                "Validation",
                "Map id must match a map in this pack.",
            )
            return
        super().accept()


class MapTreeWidget(QtWidgets.QTreeWidget):
    MAP_LINK_MIME_TYPE = "application/x-soh-map-link"

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._press_item: Optional[QtWidgets.QTreeWidgetItem] = None
        self._press_pos: Optional[QtCore.QPoint] = None
        self._press_column = 0
        self._dragging_map = False

    def mimeTypes(self) -> List[str]:
        return [self.MAP_LINK_MIME_TYPE]

    def mimeData(self, items: List[QtWidgets.QTreeWidgetItem]) -> Optional[QtCore.QMimeData]:
        if not items:
            return None
        data = items[0].data(0, QtCore.Qt.UserRole)
        if not data:
            return None
        kind, _value = data
        if kind != "map":
            return None
        map_id = str(items[0].data(0, QtCore.Qt.UserRole + 1) or "").strip()
        if not map_id:
            return None
        mime = QtCore.QMimeData()
        mime.setData(self.MAP_LINK_MIME_TYPE, map_id.encode("utf-8"))
        return mime

    def _is_map_item(self, item: Optional[QtWidgets.QTreeWidgetItem]) -> bool:
        if item is None:
            return False
        data = item.data(0, QtCore.Qt.UserRole)
        return bool(data and data[0] == "map")

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            item = self.itemAt(event.pos())
            if self._is_map_item(item):
                self._press_item = item
                self._press_pos = event.pos()
                self._press_column = max(0, self.columnAt(event.pos().x()))
                self._dragging_map = False
                event.accept()
                return
        self._press_item = None
        self._press_pos = None
        self._dragging_map = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.buttons() & QtCore.Qt.LeftButton
            and self._press_item is not None
            and self._press_pos is not None
            and self._is_map_item(self._press_item)
        ):
            if (event.pos() - self._press_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                mime = self.mimeData([self._press_item])
                if mime is not None:
                    self._dragging_map = True
                    drag = QtGui.QDrag(self)
                    drag.setMimeData(mime)
                    drag.exec(QtCore.Qt.CopyAction)
                self._press_item = None
                self._press_pos = None
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton and self._press_item is not None:
            released_item = self.itemAt(event.pos())
            if not self._dragging_map and released_item is self._press_item:
                self.setCurrentItem(self._press_item, self._press_column)
                self.itemClicked.emit(self._press_item, self._press_column)
            self._press_item = None
            self._press_pos = None
            self._dragging_map = False
            event.accept()
            return
        self._press_item = None
        self._press_pos = None
        self._dragging_map = False
        super().mouseReleaseEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._title_base = "SOH Map Pack Editor"
        self.resize(1400, 860)
        self.settings = QtCore.QSettings("soh-map-tracker", "pack-editor")

        self.model = PackModel()
        self.model.changed.connect(self.on_model_changed)

        self._current_map: Optional[str] = None
        self._selected_ref: Optional[Tuple[AreaDef, CheckDef]] = None
        self._suspend_dirty_tracking = False
        self._restoring_history = False
        self._dirty = False
        self._current_zip_path: Optional[Path] = None

        self._history: List[Dict[str, Any]] = []
        self._history_index = -1
        self._saved_history_index = -1
        self._history_limit = 200
        self._allowed_soh_ids = self._load_allowed_soh_ids()
        self._allowed_soh_set = set(self._allowed_soh_ids)
        self._allowed_map_ids = self._load_allowed_map_ids()
        self._allowed_map_id_set = set(self._allowed_map_ids)

        self._build_ui()
        self._apply_view_selection_palettes()
        self._wire_signals()

        self._suspend_dirty_tracking = True
        self.model.new_pack()
        self._suspend_dirty_tracking = False
        self._selected_ref = None
        self._current_map = None
        self.refresh_ui()
        self._reset_history()
        self.show_status("Created new pack")

    def _apply_view_selection_style(
        self,
        widget: QtWidgets.QWidget,
        selector: str,
        item_padding_left: int = 0,
    ) -> None:
        pal = widget.palette()
        highlight = pal.color(QtGui.QPalette.Highlight)
        highlighted_text = pal.color(QtGui.QPalette.HighlightedText)
        widget.setStyleSheet(
            f"""
            {selector} {{
                outline: 0;
            }}
            {selector}::item {{
                padding-left: {item_padding_left}px;
            }}
            {selector}::item:selected,
            {selector}::item:selected:active,
            {selector}::item:selected:!active {{
                background: {highlight.name()};
                color: {highlighted_text.name()};
                border: none;
                outline: none;
            }}
            """
        )

    def _apply_view_selection_palettes(self) -> None:
        self._apply_view_selection_style(self.tree, "QTreeWidget")
        self._apply_view_selection_style(self.list_checks, "QListWidget", item_padding_left=4)

    def changeEvent(self, event: QtCore.QEvent) -> None:
        if event.type() in (
            QtCore.QEvent.PaletteChange,
            QtCore.QEvent.ApplicationPaletteChange,
            QtCore.QEvent.StyleChange,
        ):
            self._apply_view_selection_palettes()
        super().changeEvent(event)

    def _load_text_choices(self, filename: str) -> List[str]:
        script_dir = Path(__file__).resolve().parent
        candidates = [script_dir / filename]
        for path in candidates:
            if not path.exists():
                continue
            ids: List[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if text:
                    ids.append(text)
            # Preserve source order, drop duplicates.
            return list(dict.fromkeys(ids))
        return []

    def _load_allowed_soh_ids(self) -> List[str]:
        return self._load_text_choices("in_game_checks.txt")

    def _load_allowed_map_ids(self) -> List[str]:
        return self._load_text_choices("map_tracker_map_ids.txt")

    def _map_label(self, map_def: MapDef) -> str:
        if map_def.id:
            return f"{map_def.name} [{map_def.id}]"
        return f"{map_def.name} [missing id]"

    def _tree_map_label(self, map_def: MapDef) -> str:
        return map_def.name or map_def.id or "(unnamed map)"

    def _map_label_for_id(self, map_id: str) -> str:
        return self.model.format_map_label(map_id)

    def _set_current_map(self, map_def: Optional[MapDef]) -> None:
        self._current_map = map_def.editor_key() if map_def is not None else None

    def _current_map_id(self) -> str:
        map_def = self._current_map_def()
        if map_def is None:
            return ""
        return map_def.id

    def _find_area_for_new_check(self, map_def: MapDef) -> AreaDef:
        if map_def.id:
            for area, check in self.model.all_checks():
                if any(location.map_id == map_def.id for location in check.map_locations):
                    return area
        preferred_names = [text for text in (map_def.id, map_def.name) if text]
        for preferred_name in preferred_names:
            area = self.model.find_area(preferred_name)
            if area is not None:
                return area
        area_name = map_def.id or map_def.name or "checks"
        area = AreaDef(area=area_name, checks=[], extra={})
        self.model.areas.append(area)
        return area

    def _prune_empty_areas(self) -> None:
        self.model.areas = [area for area in self.model.areas if area.checks]

    def _show_load_warnings(self) -> None:
        if not self.model.load_warnings:
            return
        QtWidgets.QMessageBox.warning(self, "Outdated Pack", "\n\n".join(self.model.load_warnings))

    def _build_ui(self) -> None:
        self._build_toolbar()

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.setCentralWidget(splitter)

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_btn_row = QtWidgets.QHBoxLayout()
        self.btn_add_map = QtWidgets.QPushButton("Add Map")
        self.btn_edit_map = QtWidgets.QPushButton("Edit Map")
        left_btn_row.addWidget(self.btn_add_map)
        left_btn_row.addWidget(self.btn_edit_map)
        left_layout.addLayout(left_btn_row)

        self.tree = MapTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        left_layout.addWidget(self.tree, 1)
        splitter.addWidget(left)

        self.canvas = MapCanvas(self.model)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(1, 1)

        right = QtWidgets.QWidget()
        splitter.addWidget(right)
        right_layout = QtWidgets.QVBoxLayout(right)

        self.chk_filter_current_map = QtWidgets.QCheckBox("Only show checks in Current map")
        self.chk_filter_current_map.setChecked(True)
        right_layout.addWidget(self.chk_filter_current_map)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search checks (name or soh_id)…")
        right_layout.addWidget(self.search)

        self.list_checks = QtWidgets.QListWidget()
        self.list_checks.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        right_layout.addWidget(self.list_checks, 1)

        form = QtWidgets.QGroupBox("Selected check")
        form_layout = QtWidgets.QFormLayout(form)
        right_layout.addWidget(form)

        self.ed_name = QtWidgets.QLineEdit()
        self.ed_hint = QtWidgets.QLineEdit()
        self.cb_soh = QtWidgets.QComboBox()
        self.cb_soh.setEditable(True)
        self.cb_soh.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_soh.addItems(self._allowed_soh_ids)
        self.cb_soh.setMaxVisibleItems(20)
        soh_completer = QtWidgets.QCompleter(self._allowed_soh_ids, self.cb_soh)
        soh_completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        soh_completer.setFilterMode(QtCore.Qt.MatchContains)
        soh_completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.cb_soh.setCompleter(soh_completer)
        form_layout.addRow("Name", self.ed_name)
        form_layout.addRow("Hint", self.ed_hint)
        form_layout.addRow("soh_id", self.cb_soh)

        self.tbl_locations = QtWidgets.QTableWidget(0, 4)
        self.tbl_locations.setHorizontalHeaderLabels(["Map", "X", "Y", "Size"])
        self.tbl_locations.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tbl_locations.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_locations.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_locations.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tbl_locations.verticalHeader().setVisible(False)
        header = self.tbl_locations.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.tbl_locations.setFixedHeight(170)
        form_layout.addRow(self.tbl_locations)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        self.act_new = QtGui.QAction("New", self)
        self.act_open = QtGui.QAction("Open…", self)
        self.act_open_recent = QtGui.QAction("Open Recent", self)
        self.act_export = QtGui.QAction("Export…", self)
        self.act_undo = QtGui.QAction("Undo", self)
        self.act_undo.setShortcut(QtGui.QKeySequence.Undo)
        self.act_redo = QtGui.QAction("Redo", self)
        self.act_redo.setShortcut(QtGui.QKeySequence.Redo)
        undo_shortcut = self.act_undo.shortcut().toString(QtGui.QKeySequence.NativeText)
        redo_shortcut = self.act_redo.shortcut().toString(QtGui.QKeySequence.NativeText)
        self.act_undo.setToolTip(f"Undo ({undo_shortcut})" if undo_shortcut else "Undo")
        self.act_redo.setToolTip(f"Redo ({redo_shortcut})" if redo_shortcut else "Redo")

        self.chk_clean = QtWidgets.QCheckBox("Clean output (strip unused fields)")
        self.chk_clean.setChecked(False)
        self.lbl_pack_name = QtWidgets.QLabel("Pack: (new pack)")
        self.lbl_pack_name.setMinimumWidth(260)
        self.lbl_pack_name.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        tb.addAction(self.act_new)
        tb.addAction(self.act_open)
        tb.addAction(self.act_open_recent)
        tb.addAction(self.act_export)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addWidget(self.chk_clean)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(self.lbl_pack_name)

    def _wire_signals(self) -> None:
        self.act_new.triggered.connect(self.on_new)
        self.act_open.triggered.connect(self.on_open)
        self.act_open_recent.triggered.connect(self.on_open_recent)
        self.act_export.triggered.connect(self.on_export)
        self.act_undo.triggered.connect(self.on_undo)
        self.act_redo.triggered.connect(self.on_redo)

        self.btn_add_map.clicked.connect(self.on_add_map)
        self.btn_edit_map.clicked.connect(self.on_edit_map)

        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        self.tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        self.canvas.check_selected.connect(self.on_canvas_check_selected)
        self.canvas.map_link_activated.connect(self.on_canvas_map_link_activated)
        self.canvas.selection_cleared.connect(self.on_canvas_selection_cleared)
        self.canvas.locations_changed.connect(self.on_canvas_locations_changed)
        self.canvas.links_changed.connect(self.on_canvas_links_changed)
        self.canvas.remove_checks_requested.connect(self.on_canvas_remove_checks_requested)
        self.canvas.add_check_requested.connect(self.on_canvas_add_check_requested)

        self.search.textChanged.connect(self.refresh_check_list)
        self.chk_filter_current_map.toggled.connect(self.refresh_check_list)
        self.list_checks.currentItemChanged.connect(self.on_check_selected)
        self.list_checks.customContextMenuRequested.connect(self.on_check_list_context_menu)

        self.ed_name.editingFinished.connect(self.on_check_fields_changed)
        self.ed_hint.editingFinished.connect(self.on_check_fields_changed)
        if self.cb_soh.lineEdit():
            self.cb_soh.lineEdit().editingFinished.connect(self.on_check_fields_changed)
        self.cb_soh.activated.connect(lambda _idx: self.on_check_fields_changed())
        self.tbl_locations.customContextMenuRequested.connect(self.on_locations_context_menu)
        self.tbl_locations.currentCellChanged.connect(self.on_location_row_selected)
        self.tbl_locations.itemSelectionChanged.connect(self.on_location_selection_changed)
        self.tbl_locations.cellClicked.connect(self.on_location_cell_clicked)
        self.tbl_locations.cellDoubleClicked.connect(self.on_location_cell_double_clicked)

    def _snapshot_state(self) -> Dict[str, Any]:
        return {
            "maps": copy.deepcopy(self.model.maps),
            "areas": copy.deepcopy(self.model.areas),
            "current_map": self._current_map,
        }

    def _reset_history(self) -> None:
        self._history = [self._snapshot_state()]
        self._history_index = 0
        self._saved_history_index = 0
        self.set_dirty(False)
        self._update_history_actions()

    def _update_history_actions(self) -> None:
        self.act_undo.setEnabled(self._history_index > 0)
        self.act_redo.setEnabled(self._history_index < len(self._history) - 1)

    def _update_current_zip_label(self) -> None:
        if self._current_zip_path:
            self.lbl_pack_name.setText(f"Pack: {self._current_zip_path}")
        else:
            self.lbl_pack_name.setText("Pack: (new pack)")

    def _record_history_state(self) -> None:
        if self._suspend_dirty_tracking or self._restoring_history:
            return
        snap = self._snapshot_state()
        if self._history and snap == self._history[self._history_index]:
            self.set_dirty(self._history_index != self._saved_history_index)
            self._update_history_actions()
            return

        if self._history_index < len(self._history) - 1:
            self._history = self._history[: self._history_index + 1]

        self._history.append(snap)
        self._history_index = len(self._history) - 1

        if len(self._history) > self._history_limit:
            drop = len(self._history) - self._history_limit
            self._history = self._history[drop:]
            self._history_index -= drop
            self._saved_history_index = max(0, self._saved_history_index - drop)

        self.set_dirty(self._history_index != self._saved_history_index)
        self._update_history_actions()

    def _restore_history_index(self, index: int) -> None:
        if index < 0 or index >= len(self._history):
            return
        self._restoring_history = True
        snap = self._history[index]
        current_map = self._current_map
        self.model.maps = copy.deepcopy(snap["maps"])
        self.model.areas = copy.deepcopy(snap["areas"])
        if current_map and self.model.find_map(current_map):
            self._current_map = current_map
        else:
            self._current_map = snap["current_map"]
        self._selected_ref = None
        self.refresh_ui()
        self._history_index = index
        self.set_dirty(self._history_index != self._saved_history_index)
        self._update_history_actions()
        self._restoring_history = False

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        suffix = " *" if dirty else ""
        self.setWindowTitle(f"{self._title_base}{suffix}")

    def _has_unsaved_changes(self) -> bool:
        return self._dirty or self._history_index != self._saved_history_index

    def show_status(self, message: str, timeout_ms: int = 4000) -> None:
        _ = (message, timeout_ms)

    def maybe_prompt_export(self) -> bool:
        if not self._has_unsaved_changes():
            return True
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Unsaved changes")
        msg.setText("You have changes that have not been exported.")
        msg.setInformativeText("Export before continuing?")
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel
        )
        msg.button(QtWidgets.QMessageBox.Save).setText("Export")
        msg.button(QtWidgets.QMessageBox.Discard).setText("Continue without exporting")
        msg.setDefaultButton(QtWidgets.QMessageBox.Save)
        choice = msg.exec()
        if choice == QtWidgets.QMessageBox.Cancel:
            return False
        if choice == QtWidgets.QMessageBox.Save:
            return self.on_export()
        return True

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.maybe_prompt_export():
            event.accept()
        else:
            event.ignore()

    def on_undo(self) -> None:
        if self._history_index <= 0:
            return
        self._restore_history_index(self._history_index - 1)
        self.show_status("Undo")

    def on_redo(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._restore_history_index(self._history_index + 1)
        self.show_status("Redo")

    def on_new(self) -> None:
        if not self.maybe_prompt_export():
            return
        self._suspend_dirty_tracking = True
        self.model.new_pack()
        self._suspend_dirty_tracking = False
        self._selected_ref = None
        self._current_map = None
        self._current_zip_path = None
        self.refresh_ui()
        self._reset_history()
        self._update_current_zip_label()
        self.show_status("Created new pack")

    def on_open(self) -> None:
        if not self.maybe_prompt_export():
            return
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open pack zip",
            dialog_start_path(str(self.settings.value("recent_zip", ""))),
            "Zip files (*.zip)",
        )
        if not fn:
            return
        path = Path(fn)
        try:
            self._suspend_dirty_tracking = True
            load_pack_from_zip(self.model, path)
            self._suspend_dirty_tracking = False
            self.settings.setValue("recent_zip", str(path))
            self._current_zip_path = path
            self._selected_ref = None
            self._current_map = None
            self.refresh_ui()
            self._reset_history()
            self._update_current_zip_label()
            self._show_load_warnings()
            self.show_status(f"Loaded zip: {path}")
        except Exception as exc:
            self._suspend_dirty_tracking = False
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))
    def on_open_recent(self) -> None:
        if not self.maybe_prompt_export():
            return
        fn = self.settings.value("recent_zip", "")
        if not fn or not Path(str(fn)).exists():
            QtWidgets.QMessageBox.information(self, "Open Recent", "No recent project found.")
            return
        path = Path(str(fn))
        try:
            self._suspend_dirty_tracking = True
            load_pack_from_zip(self.model, path)
            self._suspend_dirty_tracking = False
            self._current_zip_path = path
            self._selected_ref = None
            self._current_map = None
            self.refresh_ui()
            self._reset_history()
            self._update_current_zip_label()
            self._show_load_warnings()
            self.show_status(f"Loaded zip: {path}")
        except Exception as exc:
            self._suspend_dirty_tracking = False
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))

    def on_export(self) -> bool:
        default_export = self._current_zip_path
        if default_export is None:
            recent = self.settings.value("recent_zip", "")
            if recent:
                default_export = Path(str(recent))
        if default_export is None:
            default_export = SCRIPT_DIR / "soh-map-tracker.zip"

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontConfirmOverwrite
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export pack zip",
            str(default_export),
            "Zip files (*.zip)",
            options=options,
        )
        if not fn:
            return False
        out = Path(fn)
        if out.suffix.lower() != ".zip":
            out = out.with_suffix(".zip")

        if out.exists():
            confirm = QtWidgets.QMessageBox.question(
                self,
                "Confirm overwrite",
                f"Overriding the previous pack:\n{out}\n\nAre you sure?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if confirm != QtWidgets.QMessageBox.Yes:
                return False

        preserve_unknown = not self.chk_clean.isChecked()
        try:
            export_pack_to_zip(self.model, out, preserve_unknown=preserve_unknown)
            self.settings.setValue("recent_zip", str(out))
            self._current_zip_path = out
            self._saved_history_index = self._history_index
            self.set_dirty(False)
            self._update_history_actions()
            self._update_current_zip_label()
            self.show_status(f"Exported zip: {out}")
            return True
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))
            return False

    def on_model_changed(self) -> None:
        self.refresh_ui()
        self._record_history_state()

    def refresh_ui(self) -> None:
        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_check_list()
        self.refresh_selected_editor()

    def refresh_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        groups: Dict[str, List[MapDef]] = {}
        for m in self.model.maps:
            groups.setdefault(m.group or "(no group)", []).append(m)

        selected_item: Optional[QtWidgets.QTreeWidgetItem] = None
        for group_name in sorted(groups.keys()):
            group_item = QtWidgets.QTreeWidgetItem([group_name])
            group_item.setData(0, QtCore.Qt.UserRole, ("group", group_name))
            group_item.setFlags(group_item.flags() & ~QtCore.Qt.ItemIsDragEnabled)
            self.tree.addTopLevelItem(group_item)
            for map_def in groups[group_name]:
                map_item = QtWidgets.QTreeWidgetItem([self._tree_map_label(map_def)])
                map_item.setToolTip(0, self._map_label(map_def))
                map_item.setData(0, QtCore.Qt.UserRole, ("map", map_def.editor_key()))
                map_item.setData(0, QtCore.Qt.UserRole + 1, map_def.id)
                map_item.setFlags(map_item.flags() | QtCore.Qt.ItemIsDragEnabled)
                group_item.addChild(map_item)
                if map_def.editor_key() == self._current_map:
                    selected_item = map_item
            group_item.setExpanded(True)

        if selected_item:
            self.tree.setCurrentItem(selected_item)
        self.tree.blockSignals(False)

    def refresh_canvas(self) -> None:
        if not self.model.maps:
            self._current_map = None
            self.canvas.clear_map()
            return

        if self._current_map is None or not self.model.find_map(self._current_map):
            self._set_current_map(self.model.maps[0])

        if not self._current_map:
            self.canvas.clear_map()
            return

        if self.canvas.current_map_name() != self._current_map:
            self.canvas.set_map(self._current_map)
        else:
            self.canvas.reload()

        if self._selected_ref:
            area, check = self._selected_ref
            self.canvas.set_selected_check(area, check)
        else:
            self.canvas.clear_selected_check()

    def refresh_check_list(self) -> None:
        query = self.search.text().strip().lower()
        keep = self._selected_ref
        filter_current_map = self.chk_filter_current_map.isChecked()
        current_map_id = self._current_map_id()

        self.list_checks.blockSignals(True)
        self.list_checks.clear()
        for area, check in self.model.all_checks():
            if filter_current_map:
                if not current_map_id:
                    continue
                if not any(loc.map_id == current_map_id for loc in check.map_locations):
                    continue
            if query and (query not in check.name.lower() and query not in check.soh_id.lower()):
                continue
            text = f"{check.name}  [{check.soh_id}]"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, (area, check))
            self.list_checks.addItem(item)
        self.list_checks.blockSignals(False)

        if keep:
            found = self._select_check_in_list(
                keep[0],
                keep[1],
                ensure_visible=False,
                emit_signals=False,
            )
            if not found and filter_current_map:
                self._selected_ref = None
                self.refresh_selected_editor()

    def refresh_selected_editor(self) -> None:
        if not self._selected_ref:
            self.ed_name.setText("")
            self.ed_hint.setText("")
            self.cb_soh.setEditText("")
            self.tbl_locations.setRowCount(0)
            self.canvas.clear_selected_check()
            return

        area, check = self._selected_ref
        if check not in area.checks:
            self._selected_ref = None
            self.refresh_selected_editor()
            return

        self.ed_name.setText(check.name)
        self.ed_hint.setText(check.hint)
        self.cb_soh.setEditText(check.soh_id)

        self.tbl_locations.blockSignals(True)
        self.tbl_locations.clearSelection()
        self.tbl_locations.setRowCount(0)
        for location in check.map_locations:
            row = self.tbl_locations.rowCount()
            self.tbl_locations.insertRow(row)
            map_label = self._map_label_for_id(location.map_id)
            map_item = QtWidgets.QTableWidgetItem(map_label)
            map_item.setToolTip(map_label)
            map_item.setData(QtCore.Qt.UserRole, location.map_id)
            self.tbl_locations.setItem(row, 0, map_item)
            self.tbl_locations.setItem(row, 1, QtWidgets.QTableWidgetItem(str(location.x)))
            self.tbl_locations.setItem(row, 2, QtWidgets.QTableWidgetItem(str(location.y)))
            self.tbl_locations.setItem(row, 3, QtWidgets.QTableWidgetItem(str(location.size)))
        self.tbl_locations.setCurrentItem(None)
        self.tbl_locations.blockSignals(False)
        self.canvas.set_selected_check(area, check)
        self.canvas.set_selected_location(area, check, None)

    def on_fit_to_view(self) -> None:
        self.canvas.fit_to_view()

    def on_tree_item_clicked(self, item: QtWidgets.QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return
        kind, value = data
        if kind == "map":
            self._current_map = value
            self.refresh_canvas()
            self.refresh_tree()
            self.refresh_check_list()

    def on_tree_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return
        kind, value = data
        if kind != "map":
            return

        map_key = str(value)
        menu = QtWidgets.QMenu(self.tree)
        act_edit = menu.addAction("Edit map")
        act_delete = menu.addAction("Delete map")
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._current_map = map_key
            self.on_edit_map()
            return
        if chosen is act_delete:
            self.on_delete_map(map_key)

    def on_delete_map(self, map_key: Optional[str] = None) -> None:
        target = map_key or self._current_map
        if not target:
            return
        map_def = self.model.find_map(target)
        if map_def is None:
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Delete Map",
            f"Delete map '{self._map_label(map_def)}' and its linked checks?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        # Drop the map definition.
        self.model.maps = [m for m in self.model.maps if m is not map_def]

        # Remove map locations that target this map from remaining checks.
        for area2 in self.model.areas:
            new_checks: List[CheckDef] = []
            for check in area2.checks:
                check.map_locations = [ml for ml in check.map_locations if ml.map_id != map_def.id]
                if check.map_locations:
                    new_checks.append(check)
            area2.checks = new_checks

        for other_map in self.model.maps:
            other_map.links = [link for link in other_map.links if link.target_map_id != map_def.id]

        self._prune_empty_areas()
        if self._current_map == target:
            self._set_current_map(self.model.maps[0] if self.model.maps else None)
        self._selected_ref = None
        self.model.changed.emit()
        self.show_status(f"Deleted map: {self._map_label(map_def)}")

    def _select_check_in_list(
        self,
        area: AreaDef,
        check: CheckDef,
        ensure_visible: bool,
        emit_signals: bool = True,
    ) -> bool:
        for idx in range(self.list_checks.count()):
            item = self.list_checks.item(idx)
            area2, check2 = item.data(QtCore.Qt.UserRole)
            if area2 is area and check2 is check:
                if emit_signals:
                    self.list_checks.setCurrentItem(item)
                else:
                    self.list_checks.blockSignals(True)
                    self.list_checks.setCurrentItem(item)
                    self.list_checks.blockSignals(False)
                return True
        if ensure_visible:
            self.search.clear()
            self.refresh_check_list()
            return self._select_check_in_list(
                area,
                check,
                ensure_visible=False,
                emit_signals=emit_signals,
            )
        return False

    def select_check(self, area: AreaDef, check: CheckDef, ensure_visible: bool = True) -> None:
        self._selected_ref = (area, check)
        self._select_check_in_list(area, check, ensure_visible=ensure_visible)
        self.refresh_selected_editor()

    def on_canvas_check_selected(self, area: AreaDef, check: CheckDef) -> None:
        self._selected_ref = (area, check)
        self._select_check_in_list(area, check, ensure_visible=True, emit_signals=False)
        self.refresh_selected_editor()

    def on_canvas_map_link_activated(self, map_id: str) -> None:
        map_def = self.model.find_map_by_id(map_id)
        if map_def is None:
            return
        self._set_current_map(map_def)
        self._selected_ref = None
        self.refresh_canvas()
        self.refresh_tree()
        self.refresh_check_list()
        self.refresh_selected_editor()

    def on_canvas_selection_cleared(self) -> None:
        self._selected_ref = None
        self.list_checks.blockSignals(True)
        self.list_checks.clearSelection()
        self.list_checks.setCurrentRow(-1)
        self.list_checks.blockSignals(False)
        self.refresh_selected_editor()

    def on_check_list_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.list_checks.itemAt(pos)
        if item is None:
            return
        area, check = item.data(QtCore.Qt.UserRole)

        menu = QtWidgets.QMenu(self.list_checks)
        act_delete = menu.addAction("Delete check")
        chosen = menu.exec(self.list_checks.viewport().mapToGlobal(pos))
        if chosen is not act_delete:
            return

        self.select_check(area, check, ensure_visible=False)
        self.on_delete_check()

    def on_check_selected(
        self,
        current: Optional[QtWidgets.QListWidgetItem],
        _previous: Optional[QtWidgets.QListWidgetItem],
    ) -> None:
        if not current:
            self._selected_ref = None
            self.refresh_selected_editor()
            return
        area, check = current.data(QtCore.Qt.UserRole)
        self._selected_ref = (area, check)
        self.refresh_selected_editor()

    def on_canvas_locations_changed(self) -> None:
        self.model.changed.emit()

    def on_canvas_links_changed(self) -> None:
        self.model.changed.emit()

    def on_canvas_remove_checks_requested(
        self,
        checks_to_remove: List[Tuple[AreaDef, CheckDef, MapLocation]],
    ) -> None:
        current_map_id = self._current_map_id()
        if not checks_to_remove or not current_map_id:
            return

        removed_locations = 0
        deleted_checks = 0
        removed_selected_check = False

        for area, check, location in checks_to_remove:
            if location.map_id != current_map_id:
                continue
            try:
                check.map_locations.remove(location)
                removed_locations += 1
            except ValueError:
                continue

            if not check.map_locations:
                try:
                    area.checks.remove(check)
                    deleted_checks += 1
                    if self._selected_ref and self._selected_ref[0] is area and self._selected_ref[1] is check:
                        removed_selected_check = True
                except ValueError:
                    pass

        if removed_locations == 0:
            return

        if removed_selected_check:
            self._selected_ref = None

        self._prune_empty_areas()
        self.model.changed.emit()
        if deleted_checks > 0:
            self.show_status(
                f"Removed {removed_locations} marker location(s) from map and deleted {deleted_checks} check(s)"
            )
        else:
            self.show_status(f"Removed {removed_locations} marker location(s) from map")

    def on_check_fields_changed(self) -> None:
        if not self._selected_ref:
            return
        _, check = self._selected_ref
        new_name = self.ed_name.text().strip()
        new_hint = self.ed_hint.text().strip()
        new_soh = self.cb_soh.currentText().strip()
        if self._allowed_soh_ids and new_soh and new_soh not in self._allowed_soh_set:
            QtWidgets.QMessageBox.warning(
                self,
                "Validation",
                "soh_id must be selected from the allowed in-game checks list.",
            )
            self.cb_soh.setEditText(check.soh_id)
            return
        if check.name == new_name and check.hint == new_hint and check.soh_id == new_soh:
            return
        check.name = new_name
        check.hint = new_hint
        check.soh_id = new_soh
        self.model.changed.emit()

    def on_locations_context_menu(self, pos: QtCore.QPoint) -> None:
        if not self._selected_ref:
            return
        item = self.tbl_locations.itemAt(pos)
        row = item.row() if item is not None else -1
        if row >= 0:
            self.tbl_locations.selectRow(row)
        else:
            self.tbl_locations.clearSelection()
            self.tbl_locations.setCurrentItem(None)

        menu = QtWidgets.QMenu(self.tbl_locations)
        act_add = menu.addAction("Add location")
        act_edit = menu.addAction("Edit location")
        act_delete = menu.addAction("Delete location")
        act_edit.setEnabled(row >= 0)
        act_delete.setEnabled(row >= 0)

        chosen = menu.exec(self.tbl_locations.viewport().mapToGlobal(pos))
        if chosen is act_add:
            self.on_add_location()
            return
        if chosen is act_edit:
            self.on_edit_location(row)
            return
        if chosen is act_delete:
            self.on_del_location(row)

    def on_location_row_selected(
        self,
        current_row: int,
        current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if not self._selected_ref:
            return
        area, check = self._selected_ref
        if current_row < 0:
            self.canvas.set_selected_location(area, check, None)
            return
        if current_row >= len(check.map_locations):
            return
        location = check.map_locations[current_row]
        self.canvas.set_selected_location(area, check, location)

    def on_location_selection_changed(self) -> None:
        if not self._selected_ref:
            return
        area, check = self._selected_ref
        if self.tbl_locations.selectionModel() and self.tbl_locations.selectionModel().hasSelection():
            return
        self.canvas.set_selected_location(area, check, None)

    def on_location_cell_clicked(self, row: int, _column: int) -> None:
        if not self._selected_ref:
            return
        area, check = self._selected_ref
        if row < 0 or row >= len(check.map_locations):
            return

        location = check.map_locations[row]
        map_def = self.model.find_map_by_id(location.map_id)
        if map_def is None:
            return

        if map_def.editor_key() != self._current_map:
            self._set_current_map(map_def)
            self.refresh_tree()
            self.refresh_canvas()
            self.refresh_check_list()

        self.canvas.set_selected_location(area, check, location)

    def on_location_cell_double_clicked(self, row: int, _column: int) -> None:
        self.on_edit_location(row)

    def _available_location_maps(self) -> List[MapDef]:
        return [map_def for map_def in self.model.maps if map_def.id]

    def _select_location_row(self, row: int) -> None:
        if row < 0 or row >= self.tbl_locations.rowCount():
            return
        self.tbl_locations.setCurrentCell(row, 0)
        self.tbl_locations.selectRow(row)
        item = self.tbl_locations.item(row, 0)
        if item is not None:
            self.tbl_locations.scrollToItem(item)

    def on_edit_location(self, row: Optional[int] = None) -> None:
        if not self._selected_ref:
            return
        _, check = self._selected_ref
        if row is None:
            row = self.tbl_locations.currentRow()
        if row < 0 or row >= len(check.map_locations):
            return

        available_maps = self._available_location_maps()
        if not available_maps:
            QtWidgets.QMessageBox.information(
                self,
                "Edit location",
                "Assign ids to the maps in this pack before editing locations.",
            )
            return

        location = check.map_locations[row]
        dlg = EditLocationDialog(
            self,
            "Edit location",
            available_maps=available_maps,
            initial_map_id=location.map_id,
            initial_x=location.x,
            initial_y=location.y,
            initial_size=location.size,
        )
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        map_id, x, y, size = dlg.values()
        if location.map_id == map_id and location.x == x and location.y == y and location.size == size:
            return

        location.map_id = map_id
        location.x = x
        location.y = y
        location.size = size
        self.model.changed.emit()
        self._select_location_row(row)

    def on_add_location(self) -> None:
        if not self._selected_ref:
            return
        available_maps = self._available_location_maps()
        if not available_maps:
            QtWidgets.QMessageBox.information(
                self,
                "Add location",
                "Assign ids to the maps in this pack before adding locations.",
            )
            return
        _, check = self._selected_ref
        default_map_id = self._current_map_id()
        if not default_map_id or default_map_id not in {map_def.id for map_def in available_maps}:
            default_map_id = available_maps[0].id

        dlg = EditLocationDialog(
            self,
            "Add location",
            available_maps=available_maps,
            initial_map_id=default_map_id,
            initial_x=0,
            initial_y=0,
            initial_size=24,
        )
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        map_id, x, y, size = dlg.values()
        check.map_locations.append(MapLocation(map_id=map_id, x=x, y=y, size=size))
        self.model.changed.emit()
        new_row = len(check.map_locations) - 1
        self._select_location_row(new_row)

    def on_del_location(self, row: Optional[int] = None) -> None:
        if not self._selected_ref:
            return
        area, check = self._selected_ref
        if row is None:
            row = self.tbl_locations.currentRow()
        if row < 0 or row >= len(check.map_locations):
            return
        check.map_locations.pop(row)
        first_location = check.map_locations[0] if check.map_locations else None
        if first_location is not None:
            map_def = self.model.find_map_by_id(first_location.map_id)
            if map_def is not None:
                self._set_current_map(map_def)
        self.model.changed.emit()
        remaining = len(check.map_locations)
        if remaining > 0:
            self._select_location_row(0)
        else:
            self.canvas.set_selected_location(area, check, None)

    def _current_map_def(self) -> Optional[MapDef]:
        if not self._current_map:
            return None
        return self.model.find_map(self._current_map)

    def _resolve_map_image_path(self, map_def: MapDef) -> str:
        if not self.model.base_dir:
            return map_def.img
        candidate = self.model.base_dir / map_def.img
        if candidate.exists():
            return str(candidate)
        fallback = self.model.base_dir / "images" / "maps" / Path(map_def.img).name
        if fallback.exists():
            return str(fallback)
        return map_def.img

    def _image_pixel_size(self, image_path: str) -> Optional[Tuple[int, int]]:
        image = QtGui.QImage(image_path)
        if image.isNull():
            return None
        return (image.width(), image.height())

    def _rescale_map_locations(
        self,
        map_id: str,
        old_size: Optional[Tuple[int, int]],
        new_size: Optional[Tuple[int, int]],
    ) -> None:
        if not old_size or not new_size:
            return
        old_w, old_h = old_size
        new_w, new_h = new_size
        if old_w <= 0 or old_h <= 0 or new_w <= 0 or new_h <= 0:
            return
        if old_w == new_w and old_h == new_h:
            return

        scale_x = new_w / old_w
        scale_y = new_h / old_h
        for _, check in self.model.all_checks():
            for location in check.map_locations:
                if location.map_id != map_id:
                    continue
                location.x = int(round(location.x * scale_x))
                location.y = int(round(location.y * scale_y))

    def _rescale_map_links(
        self,
        map_def: MapDef,
        old_size: Optional[Tuple[int, int]],
        new_size: Optional[Tuple[int, int]],
    ) -> None:
        if not old_size or not new_size:
            return
        old_w, old_h = old_size
        new_w, new_h = new_size
        if old_w <= 0 or old_h <= 0 or new_w <= 0 or new_h <= 0:
            return
        if old_w == new_w and old_h == new_h:
            return

        scale_x = new_w / old_w
        scale_y = new_h / old_h
        for link in map_def.links:
            link.x = int(round(link.x * scale_x))
            link.y = int(round(link.y * scale_y))

    def _copy_image_into_pack(self, source_path: str) -> str:
        if not self.model.base_dir:
            raise RuntimeError("No pack loaded.")
        src = Path(source_path)
        if not src.exists() or not src.is_file():
            raise RuntimeError(f"Image not found: {src}")

        maps_dir = self.model.base_dir / "images" / "maps"
        maps_dir.mkdir(parents=True, exist_ok=True)

        clean_name = re.sub(r"[^A-Za-z0-9_.\-]", "_", src.name)
        if not clean_name:
            clean_name = "map.png"
        stem = Path(clean_name).stem
        suffix = Path(clean_name).suffix or ".png"

        dest = maps_dir / f"{stem}{suffix}"
        index = 1
        while dest.exists():
            try:
                if src.resolve() == dest.resolve():
                    return f"images/maps/{dest.name}"
            except OSError:
                pass
            dest = maps_dir / f"{stem}_{index}{suffix}"
            index += 1

        shutil.copy2(src, dest)
        return f"images/maps/{dest.name}"

    def on_add_map(self) -> None:
        if not self.model.base_dir:
            return
        existing_names = [m.name for m in self.model.maps]
        existing_ids = [m.id for m in self.model.maps if m.id]
        dlg = AddEditMapDialog(
            parent=self,
            title="Add Map",
            existing_names=existing_names,
            allowed_map_ids=self._allowed_map_ids,
            existing_ids=existing_ids,
            initial_group="",
        )
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        map_id, name, group, image_path = dlg.values()
        try:
            rel_img = self._copy_image_into_pack(image_path)
            map_def = MapDef(name=name, img=rel_img, group=group, id=map_id, links=[], extra={})
            self.model.maps.append(map_def)
            self._set_current_map(map_def)
            self.model.changed.emit()
            self.show_status(f"Added map: {self._map_label(map_def)}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Add Map failed", str(exc))

    def on_edit_map(self) -> None:
        map_def = self._current_map_def()
        if not map_def:
            QtWidgets.QMessageBox.information(self, "Edit Map", "Select a map first.")
            return

        existing_names = [m.name for m in self.model.maps if m is not map_def]
        existing_ids = [m.id for m in self.model.maps if m is not map_def and m.id]
        old_editor_key = map_def.editor_key()
        dlg = AddEditMapDialog(
            parent=self,
            title="Edit Map",
            existing_names=existing_names,
            allowed_map_ids=self._allowed_map_ids,
            existing_ids=existing_ids,
            original_name=map_def.name,
            original_id=map_def.id,
            initial_id=map_def.id,
            initial_name=map_def.name,
            initial_group=map_def.group,
            initial_image=self._resolve_map_image_path(map_def),
        )
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        new_id, new_name, new_group, image_path = dlg.values()
        old_id = map_def.id
        old_image_path = self._resolve_map_image_path(map_def)
        old_image_size = self._image_pixel_size(old_image_path)
        try:
            rel_img = self._copy_image_into_pack(image_path)
            new_image_path = str(self.model.base_dir / rel_img) if self.model.base_dir else image_path
            new_image_size = self._image_pixel_size(new_image_path)
            self._rescale_map_locations(old_id, old_image_size, new_image_size)
            self._rescale_map_links(map_def, old_image_size, new_image_size)

            map_def.id = new_id
            map_def.name = new_name
            map_def.group = new_group
            map_def.img = rel_img

            if old_id != new_id:
                for _, check in self.model.all_checks():
                    for location in check.map_locations:
                        if location.map_id == old_id:
                            location.map_id = new_id

                for other_map in self.model.maps:
                    for link in other_map.links:
                        if link.target_map_id == old_id:
                            link.target_map_id = new_id

                if self._current_map == old_editor_key:
                    self._set_current_map(map_def)
            self.model.changed.emit()
            self.show_status(f"Edited map: {self._map_label(map_def)}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Edit Map failed", str(exc))

    def on_canvas_add_check_requested(self, map_id: str, x: int, y: int) -> None:
        self._open_add_check_dialog(map_id, (x, y))

    def _open_add_check_dialog(
        self,
        map_id: Optional[str],
        preset_xy: Optional[Tuple[int, int]],
    ) -> None:
        if not map_id:
            QtWidgets.QMessageBox.information(self, "Add Check", "Select a map first.")
            return
        map_def = self.model.find_map_by_id(map_id)
        if map_def is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Add Check",
                "The current map has no valid id. Set a map id before adding checks.",
            )
            return

        dlg = AddCheckDialog(
            self,
            self._map_label(map_def),
            allowed_soh_ids=self._allowed_soh_ids,
            preset_xy=preset_xy,
        )
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        check_name, check_hint, soh_id = dlg.values()
        area = self._find_area_for_new_check(map_def)

        new_check = CheckDef(
            name=check_name,
            hint=check_hint,
            soh_id=soh_id,
            map_locations=[],
            extra={},
        )
        x = preset_xy[0] if preset_xy else 0
        y = preset_xy[1] if preset_xy else 0
        new_check.map_locations.append(MapLocation(map_id=map_def.id, x=x, y=y, size=24))
        self._set_current_map(map_def)
        area.checks.append(new_check)
        self.model.changed.emit()
        self.select_check(area, new_check, ensure_visible=True)
        self.show_status(f"Added check: {check_name}")

    def on_delete_check(self) -> None:
        if not self._selected_ref:
            return
        area, check = self._selected_ref
        self._delete_check(area, check)

    def _delete_check(self, area: AreaDef, check: CheckDef) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Delete Check",
            f"Delete check '{check.name}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            area.checks.remove(check)
            self._prune_empty_areas()
            self._selected_ref = None
            self.model.changed.emit()
            self.show_status("Deleted check")
        except ValueError:
            pass
