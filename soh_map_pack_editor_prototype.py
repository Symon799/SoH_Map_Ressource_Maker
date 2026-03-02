# SOH Map Pack Editor (Prototype)
# - Python 3.10+
# - PySide6
#
# Install:
#   pip install PySide6
# Run:
#   python main.py
#
# Notes:
# - Opens/exports packs as .zip with root folder name: soh-map-tracker/
# - Writes:
#     maps.json
#     areas/<area_name_with_underscores>.json
#     images/maps/*
# - Simplifies output by dropping:
#     maps: location_size, location_border_thickness
#     checks: access_rules, visibility_rules, item_count
# - Preserves unknown fields by default (toggle: "Clean output")
#   while still stripping the fields above.

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets


# -----------------------------
# Helpers
# -----------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

def area_to_filename(area_name: str) -> str:
    # Replace spaces with underscores, keep simple characters
    s = area_name.strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
    if not s:
        s = "area"
    return f"{s}.json"


def clamp_int(v: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(v))))


def safe_load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


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


# -----------------------------
# Data model
# -----------------------------

BANNED_MAP_FIELDS = {"location_size", "location_border_thickness"}
BANNED_CHECK_FIELDS = {"access_rules", "visibility_rules", "item_count"}


@dataclass
class MapDef:
    name: str
    img: str
    group: str
    extra: Dict[str, Any] = field(default_factory=dict)  # unknown fields


@dataclass
class MapLocation:
    map: str
    x: int
    y: int
    size: int = 24
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MapLocation":
        extra = {k: v for k, v in d.items() if k not in {"map", "x", "y", "size"}}
        return MapLocation(
            map=str(d.get("map", "")),
            x=int(d.get("x", 0)),
            y=int(d.get("y", 0)),
            size=int(d.get("size", 24)),
            extra=extra,
        )

    def to_dict(self, preserve_unknown: bool) -> Dict[str, Any]:
        out = {"map": self.map, "x": int(self.x), "y": int(self.y), "size": int(self.size)}
        if preserve_unknown:
            out.update(self.extra)
        return out


@dataclass
class CheckDef:
    name: str
    type: str
    soh_id: str
    map_locations: List[MapLocation] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)  # unknown fields


@dataclass
class AreaDef:
    area: str
    checks: List[CheckDef] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


class PackModel(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.root_name = "soh-map-tracker"
        self.base_dir: Optional[Path] = None  # extracted working directory (contains root_name)
        self.maps: List[MapDef] = []
        self.areas: List[AreaDef] = []

    def clear(self) -> None:
        self.base_dir = None
        self.maps.clear()
        self.areas.clear()
        self.changed.emit()

    def all_checks(self) -> List[Tuple[AreaDef, CheckDef]]:
        out: List[Tuple[AreaDef, CheckDef]] = []
        for a in self.areas:
            for c in a.checks:
                out.append((a, c))
        return out

    def find_map(self, name: str) -> Optional[MapDef]:
        for m in self.maps:
            if m.name == name:
                return m
        return None

    def load_zip(self, zip_path: Path) -> None:
        self.clear()
        tmp = Path(tempfile.mkdtemp(prefix="soh_pack_edit_"))
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)

        # Find root folder
        # Robust detection: find any maps.json anywhere in the extracted tree.
        # Choose the shallowest candidate (closest to zip root) to avoid picking nested duplicates.
        preferred = tmp / "soh-map-tracker"
        if preferred.exists() and (preferred / "maps.json").exists():
            root = preferred
        else:
            candidates: List[Path] = []
            for p in tmp.rglob("maps.json"):
                if p.is_file():
                    candidates.append(p.parent)

            if not candidates:
                raise RuntimeError("Could not find root folder containing maps.json in zip")

            # Prefer folders that look like a pack root
            def score(pack_root: Path) -> Tuple[int, int, int]:
                # smaller depth is better
                depth = len(pack_root.relative_to(tmp).parts)
                has_areas = int((pack_root / "areas").exists())
                has_images = int((pack_root / "images" / "maps").exists())
                # We want: minimal depth, then those with areas/images
                return (depth, -has_areas, -has_images)

            candidates.sort(key=score)
            root = candidates[0]

        # Normalize internal root name (export will always use soh-map-tracker)
        self.root_name = root.name
        self.base_dir = root

        # maps.json
        maps_path = root / "maps.json"
        maps_raw = safe_load_json(maps_path)
        self.maps = []
        for m in maps_raw:
            extra = {k: v for k, v in m.items() if k not in {"name", "img", "group"} | BANNED_MAP_FIELDS}
            self.maps.append(MapDef(
                name=str(m.get("name", "")),
                img=str(m.get("img", "")),
                group=str(m.get("group", "")),
                extra=extra,
            ))

        # areas
        areas_dir = root / "areas"
        self.areas = []
        if areas_dir.exists():
            for p in sorted(areas_dir.glob("*.json")):
                a_raw = safe_load_json(p)
                area_name = str(a_raw.get("area", p.stem.replace("_", " ")))
                a_extra = {k: v for k, v in a_raw.items() if k not in {"area", "checks"}}
                checks: List[CheckDef] = []
                for c in a_raw.get("checks", []):
                    c_extra = {k: v for k, v in c.items() if k not in {"name", "type", "soh_id", "map_locations"} | BANNED_CHECK_FIELDS}
                    mlocs = [MapLocation.from_dict(d) for d in c.get("map_locations", [])]
                    checks.append(CheckDef(
                        name=str(c.get("name", "")),
                        type=str(c.get("type", "")),
                        soh_id=str(c.get("soh_id", "")),
                        map_locations=mlocs,
                        extra=c_extra,
                    ))
                self.areas.append(AreaDef(area=area_name, checks=checks, extra=a_extra))

        self.changed.emit()

    def new_pack(self) -> None:
        self.clear()
        self.root_name = "soh-map-tracker"
        tmp = Path(tempfile.mkdtemp(prefix="soh_pack_edit_"))
        root = tmp / self.root_name
        (root / "areas").mkdir(parents=True, exist_ok=True)
        (root / "images" / "maps").mkdir(parents=True, exist_ok=True)
        safe_write_json(root / "maps.json", [])
        self.base_dir = root
        self.changed.emit()

    def export_zip(self, out_zip: Path, preserve_unknown: bool) -> None:
        if not self.base_dir:
            raise RuntimeError("No pack loaded")

        tmp_out = Path(tempfile.mkdtemp(prefix="soh_pack_export_"))
        root = tmp_out / "soh-map-tracker"
        (root / "areas").mkdir(parents=True, exist_ok=True)
        (root / "images" / "maps").mkdir(parents=True, exist_ok=True)

        # Copy images
        src_maps = self.base_dir / "images" / "maps"
        if src_maps.exists():
            for img in src_maps.glob("*.*"):
                shutil.copy2(img, root / "images" / "maps" / img.name)

        # maps.json
        maps_out: List[Dict[str, Any]] = []
        for m in self.maps:
            base = {"name": m.name, "img": m.img, "group": m.group}
            if preserve_unknown:
                # keep other unknown fields, but never banned ones
                for k, v in m.extra.items():
                    if k not in BANNED_MAP_FIELDS:
                        base[k] = v
            maps_out.append(base)
        safe_write_json(root / "maps.json", maps_out)

        # areas
        for a in self.areas:
            a_out: Dict[str, Any] = {"area": a.area}
            if preserve_unknown:
                a_out.update(a.extra)
            checks_out: List[Dict[str, Any]] = []
            for c in a.checks:
                c_out: Dict[str, Any] = {
                    "name": c.name,
                    "type": c.type,
                    "soh_id": c.soh_id,
                    "map_locations": [ml.to_dict(preserve_unknown) for ml in c.map_locations],
                }
                if preserve_unknown:
                    for k, v in c.extra.items():
                        if k not in BANNED_CHECK_FIELDS:
                            c_out[k] = v
                checks_out.append(c_out)
            a_out["checks"] = checks_out

            safe_write_json(root / "areas" / area_to_filename(a.area), a_out)

        # Zip it
        if out_zip.exists():
            out_zip.unlink()
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for folder, _, files in os.walk(tmp_out):
                for fn in files:
                    fp = Path(folder) / fn
                    rel = fp.relative_to(tmp_out)
                    z.write(fp, rel.as_posix())


# -----------------------------
# Graphics: Map canvas
# -----------------------------

class MarkerItem(QtWidgets.QGraphicsRectItem):
    def __init__(
        self,
        key: Tuple[int, int, int],
        checks: List[Tuple[AreaDef, CheckDef, MapLocation]],
        size: int,
        on_moved,
        on_clicked,
    ):
        super().__init__()
        self.setRect(-size/2, -size/2, size, size)
        self.setPos(key[0], key[1])
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self.key = key
        self.checks = checks  # clustered
        self.size = size
        self.on_moved = on_moved
        self.on_clicked = on_clicked

        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidth(2)
        self.setPen(pen)
        self.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0)))

        self.badge: Optional[QtWidgets.QGraphicsSimpleTextItem] = None
        if len(checks) > 1:
            self.badge = QtWidgets.QGraphicsSimpleTextItem(f"×{len(checks)}", self)
            self.badge.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
            self.badge.setPos(-size/2, -size/2 - 16)

    def hoverEnterEvent(self, event):
        if len(self.checks) == 1:
            _, c, _ = self.checks[0]
            tip = f"{c.name}\n{c.soh_id}"
        else:
            tip = "Multiple checks:\n" + "\n".join([f"- {c.name}" for _, c, _ in self.checks[:10]])
            if len(self.checks) > 10:
                tip += f"\n… (+{len(self.checks)-10})"
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), tip)
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.on_clicked(self)
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            pos: QtCore.QPointF = value
            self.on_moved(self, pos)
        return super().itemChange(change, value)


class MapCanvas(QtWidgets.QGraphicsView):
    # Emits (area, check) when a check is selected from the map.
    check_selected = QtCore.Signal(object, object)  # AreaDef, CheckDef

    def __init__(self, model: PackModel):
        super().__init__()
        self.model = model
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setMouseTracking(True)

        self._map_name: Optional[str] = None
        self._pix_item: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self._markers: List[MarkerItem] = []

        self.place_mode = False
        self.selected_check_ref: Optional[Tuple[AreaDef, CheckDef]] = None

        # Panning via drag; zoom via wheel.
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)

    def set_map(self, map_name: str) -> None:
        self._map_name = map_name
        self.resetTransform()
        self.reload()

    def set_selected_check(self, area: AreaDef, check: CheckDef) -> None:
        self.selected_check_ref = (area, check)

    def set_place_mode(self, enabled: bool) -> None:
        self.place_mode = enabled
        self.viewport().setCursor(QtCore.Qt.CrossCursor if enabled else QtCore.Qt.ArrowCursor)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        # Zoom on mouse wheel (no modifier)
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        # In place mode, clicking on empty space places/moves the selected check.
        if self.place_mode and event.button() == QtCore.Qt.LeftButton and self._map_name:
            # If user clicked on an existing marker, let the marker handle selection/drag.
            item = self.itemAt(event.pos())
            if isinstance(item, MarkerItem) or (item and isinstance(item.parentItem(), MarkerItem)):
                return super().mousePressEvent(event)

            if self.selected_check_ref:
                pos = self.mapToScene(event.pos())
                x = clamp_int(pos.x(), 0, 99999)
                y = clamp_int(pos.y(), 0, 99999)
                area, check = self.selected_check_ref
                # Update existing location on this map if exists; else add
                existing = None
                for ml in check.map_locations:
                    if ml.map == self._map_name:
                        existing = ml
                        break
                if existing:
                    existing.x, existing.y = x, y
                else:
                    check.map_locations.append(MapLocation(map=self._map_name, x=x, y=y, size=24))
                self.model.changed.emit()
                self.reload()
                return

        super().mousePressEvent(event)

    def reload(self) -> None:

        self.scene.clear()
        self._markers.clear()
        if not self._map_name or not self.model.base_dir:
            return

        mdef = self.model.find_map(self._map_name)
        if not mdef:
            return

        img_path = (self.model.base_dir / mdef.img)
        if not img_path.exists():
            # try relative to images/maps
            img_path = self.model.base_dir / "images" / "maps" / Path(mdef.img).name
        if img_path.exists():
            pix = QtGui.QPixmap(str(img_path))
            self._pix_item = self.scene.addPixmap(pix)
            self.scene.setSceneRect(pix.rect())
        else:
            self._pix_item = None

        # cluster by (x,y,size)
        clusters: Dict[Tuple[int, int, int], List[Tuple[AreaDef, CheckDef, MapLocation]]] = {}
        for area, chk in self.model.all_checks():
            for ml in chk.map_locations:
                if ml.map != self._map_name:
                    continue
                key = (int(ml.x), int(ml.y), int(ml.size))
                clusters.setdefault(key, []).append((area, chk, ml))

        def on_moved(marker: MarkerItem, pos: QtCore.QPointF) -> None:
            x = clamp_int(pos.x(), 0, 99999)
            y = clamp_int(pos.y(), 0, 99999)
            # Move ALL checks in the cluster together (Option A editing for stacked checks)
            for _, _, ml in marker.checks:
                ml.x, ml.y = x, y
            self.model.changed.emit()

        def on_clicked(marker: MarkerItem) -> None:
            # Always select a single check into the right panel.
            if len(marker.checks) == 1:
                area, chk, _ = marker.checks[0]
                self.selected_check_ref = (area, chk)
                self.check_selected.emit(area, chk)
                return

            # If multiple checks stacked: show a menu to pick one
            menu = QtWidgets.QMenu()
            for area, chk, _ in marker.checks:
                act = QtGui.QAction(chk.name, menu)
                act.setData((area, chk))
                menu.addAction(act)
            chosen = menu.exec(QtGui.QCursor.pos())
            if chosen:
                area, chk = chosen.data()
                self.selected_check_ref = (area, chk)
                self.check_selected.emit(area, chk)

        # Add markers
        for key, lst in clusters.items():
            size = key[2] if key[2] else 24
            marker = MarkerItem(key, lst, size=size, on_moved=on_moved, on_clicked=on_clicked)
            self.scene.addItem(marker)
            self._markers.append(marker)


# -----------------------------
# Main window
# -----------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SOH Map Pack Editor (Prototype)")
        self.resize(1400, 850)

        self.settings = QtCore.QSettings("soh-map-tracker", "pack-editor")

        self.model = PackModel()
        self.model.changed.connect(self.on_model_changed)

        self._current_map: Optional[str] = None
        self._selected_ref: Optional[Tuple[AreaDef, CheckDef]] = None
        self._suspend_table_events = False
        self._dirty = False

        # Toolbar
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        act_new = QtGui.QAction("New", self)
        act_open = QtGui.QAction("Open…", self)
        act_recent = QtGui.QAction("Open Recent", self)
        act_export = QtGui.QAction("Export…", self)
        self.act_place = QtGui.QAction("Place mode", self)
        self.act_place.setCheckable(True)

        self.chk_clean = QtWidgets.QCheckBox("Clean output (strip unused fields)")
        self.chk_clean.setChecked(False)  # default: preserve unknown fields

        tb.addAction(act_new)
        tb.addAction(act_open)
        tb.addAction(act_recent)
        tb.addAction(act_export)
        tb.addSeparator()
        tb.addAction(self.act_place)
        tb.addSeparator()
        tb.addWidget(self.chk_clean)

        act_new.triggered.connect(self.on_new)
        act_open.triggered.connect(self.on_open)
        act_recent.triggered.connect(self.on_open_recent)
        act_export.triggered.connect(self.on_export)
        self.act_place.toggled.connect(self.on_place_toggled)

        # Central splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.setCentralWidget(splitter)

        # Left: group/map tree
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        splitter.addWidget(self.tree)
        self.tree.itemSelectionChanged.connect(self.on_tree_selection)

        # Center: single map canvas (tabs removed)
        self.canvas = MapCanvas(self.model)
        self.canvas.check_selected.connect(self.on_canvas_check_selected)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(1, 1)

        # Right: checklist + properties
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        splitter.addWidget(right)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search checks (name or soh_id)…")
        right_layout.addWidget(self.search)

        self.list_checks = QtWidgets.QListWidget()
        right_layout.addWidget(self.list_checks, 1)

        form = QtWidgets.QGroupBox("Selected check")
        form_layout = QtWidgets.QFormLayout(form)
        right_layout.addWidget(form)

        self.ed_name = QtWidgets.QLineEdit()
        self.ed_type = QtWidgets.QLineEdit()
        self.ed_soh = QtWidgets.QLineEdit()
        form_layout.addRow("Name", self.ed_name)
        form_layout.addRow("Type", self.ed_type)
        form_layout.addRow("soh_id", self.ed_soh)

        self.tbl_locations = QtWidgets.QTableWidget(0, 4)
        self.tbl_locations.setHorizontalHeaderLabels(["Map", "X", "Y", "Size"])
        self.tbl_locations.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(self.tbl_locations)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_add_loc = QtWidgets.QPushButton("Add location")
        self.btn_del_loc = QtWidgets.QPushButton("Remove location")
        btn_row.addWidget(self.btn_add_loc)
        btn_row.addWidget(self.btn_del_loc)
        right_layout.addLayout(btn_row)

        self.btn_add_loc.clicked.connect(self.on_add_location)
        self.btn_del_loc.clicked.connect(self.on_del_location)

        # Wiring for editing
        self.search.textChanged.connect(self.refresh_check_list)
        self.list_checks.currentItemChanged.connect(self.on_check_selected)

        self.ed_name.editingFinished.connect(self.on_check_fields_changed)
        self.ed_type.editingFinished.connect(self.on_check_fields_changed)
        self.ed_soh.editingFinished.connect(self.on_check_fields_changed)
        self.tbl_locations.itemChanged.connect(self.on_locations_table_changed)

        # Start with empty pack
        self.model.new_pack()
        self.refresh_ui()
        self._dirty = False


    # -------- File actions

    def maybe_prompt_export(self) -> bool:
        # Returns True if we should proceed (user didn't cancel)
        if not self._dirty:
            return True
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Unsaved changes")
        msg.setText("You have unsaved changes. Export before continuing?")
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        )
        ret = msg.exec()
        if ret == QtWidgets.QMessageBox.Cancel:
            return False
        if ret == QtWidgets.QMessageBox.Yes:
            self.on_export()
            # if export canceled, user likely still wants to continue; keep it simple
        return True

    def on_new(self) -> None:
        if not self.maybe_prompt_export():
            return
        self.model.new_pack()
        self._dirty = False
        self._selected_ref = None
        self._current_map = None
        self.refresh_ui()

    def on_open(self) -> None:
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open pack zip",
            dialog_start_path(str(self.settings.value("recent_zip", ""))),
            "Zip files (*.zip)",
        )
        if not fn:
            return
        try:
            self.model.load_zip(Path(fn))
            self.settings.setValue("recent_zip", fn)
            self._dirty = False
            self._selected_ref = None
            self._current_map = None
            self.refresh_ui()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(e))

    def on_open_recent(self) -> None:
        if not self.maybe_prompt_export():
            return
        fn = self.settings.value("recent_zip", "")
        if not fn or not Path(str(fn)).exists():
            QtWidgets.QMessageBox.information(self, "Open Recent", "No recent project found.")
            return
        try:
            self.model.load_zip(Path(str(fn)))
            self._dirty = False
            self._selected_ref = None
            self._current_map = None
            self.refresh_ui()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(e))

    def on_export(self) -> None:
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export pack zip",
            dialog_start_path(str(self.settings.value("recent_zip", "")), "soh-map-tracker.zip"),
            "Zip files (*.zip)",
        )
        if not fn:
            return
        out = Path(fn)
        if out.suffix.lower() != ".zip":
            out = out.with_suffix(".zip")

        preserve_unknown = not self.chk_clean.isChecked()
        try:
            self.model.export_zip(out, preserve_unknown=preserve_unknown)
            self.settings.setValue("recent_zip", str(out))
            self._dirty = False
            QtWidgets.QMessageBox.information(self, "Export", f"Exported: {out}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export failed", str(e))
    def on_model_changed(self) -> None:
        self._dirty = True
        self.refresh_ui()

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

        # Keep group names stable (alphabetical). Map order stays as in maps.json.
        for g in sorted(groups.keys()):
            g_item = QtWidgets.QTreeWidgetItem([g])
            g_item.setData(0, QtCore.Qt.UserRole, ("group", g))
            self.tree.addTopLevelItem(g_item)
            for m in groups[g]:
                m_item = QtWidgets.QTreeWidgetItem([m.name])
                m_item.setData(0, QtCore.Qt.UserRole, ("map", m.name))
                g_item.addChild(m_item)
            g_item.setExpanded(True)
        self.tree.blockSignals(False)

    def refresh_canvas(self) -> None:
        # Choose a map to show
        if not self.model.maps:
            self._current_map = None
            return
        if self._current_map is None or not self.model.find_map(self._current_map):
            self._current_map = self.model.maps[0].name
        if self._current_map:
            self.canvas.set_map(self._current_map)
            self.canvas.set_place_mode(self.act_place.isChecked())
            # Keep selected check reference synced
            if self._selected_ref:
                area, chk = self._selected_ref
                self.canvas.set_selected_check(area, chk)

    def refresh_check_list(self) -> None:

        query = self.search.text().strip().lower()
        self.list_checks.blockSignals(True)
        self.list_checks.clear()
        for area, chk in self.model.all_checks():
            text = f"{chk.name}  [{chk.soh_id}]"
            if query and (query not in chk.name.lower() and query not in chk.soh_id.lower()):
                continue
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, (area, chk))
            self.list_checks.addItem(item)
        self.list_checks.blockSignals(False)

    def refresh_selected_editor(self) -> None:
        if not self._selected_ref:
            self.ed_name.setText("")
            self.ed_type.setText("")
            self.ed_soh.setText("")
            self.tbl_locations.setRowCount(0)
            return

        area, chk = self._selected_ref
        self.ed_name.setText(chk.name)
        self.ed_type.setText(chk.type)
        self.ed_soh.setText(chk.soh_id)

        self._suspend_table_events = True
        self.tbl_locations.setRowCount(0)
        for ml in chk.map_locations:
            r = self.tbl_locations.rowCount()
            self.tbl_locations.insertRow(r)
            self.tbl_locations.setItem(r, 0, QtWidgets.QTableWidgetItem(ml.map))
            self.tbl_locations.setItem(r, 1, QtWidgets.QTableWidgetItem(str(ml.x)))
            self.tbl_locations.setItem(r, 2, QtWidgets.QTableWidgetItem(str(ml.y)))
            self.tbl_locations.setItem(r, 3, QtWidgets.QTableWidgetItem(str(ml.size)))
        self._suspend_table_events = False

        # Inform canvas
        self.canvas.set_selected_check(area, chk)

    # -------- Interaction

    def on_place_toggled(self, enabled: bool) -> None:
        self.canvas.set_place_mode(enabled)

    def on_tree_selection(self) -> None:

        items = self.tree.selectedItems()
        if not items:
            return
        kind, val = items[0].data(0, QtCore.Qt.UserRole)
        if kind == "map":
            self._current_map = val
            self.refresh_canvas()

    def on_canvas_check_selected(self, area: AreaDef, chk: CheckDef) -> None:
        # Select in right panel
        self._selected_ref = (area, chk)
        self.refresh_selected_editor()
        # Also try to highlight the item in the list
        for i in range(self.list_checks.count()):
            it = self.list_checks.item(i)
            a2, c2 = it.data(QtCore.Qt.UserRole)
            if c2 is chk and a2 is area:
                self.list_checks.setCurrentItem(it)
                break

        # If marker had menu selection, canvas already set selected_check_ref
        # sync right-side editor by selecting in list
        if not isinstance(self.sender(), MapCanvas):
            return
        canvas: MapCanvas = self.sender()  # type: ignore
        if not canvas.selected_check_ref:
            return
        self._selected_ref = canvas.selected_check_ref
        self.refresh_selected_editor()

    def on_check_selected(self, current: Optional[QtWidgets.QListWidgetItem], prev: Optional[QtWidgets.QListWidgetItem]) -> None:
        if not current:
            self._selected_ref = None
            self.refresh_selected_editor()
            return
        area, chk = current.data(QtCore.Qt.UserRole)
        self._selected_ref = (area, chk)
        self.refresh_selected_editor()

    def on_check_fields_changed(self) -> None:
        if not self._selected_ref:
            return
        area, chk = self._selected_ref
        chk.name = self.ed_name.text().strip()
        chk.type = self.ed_type.text().strip()
        chk.soh_id = self.ed_soh.text().strip()
        self.model.changed.emit()

    def on_locations_table_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._suspend_table_events or not self._selected_ref:
            return
        _, chk = self._selected_ref
        r = item.row()
        if r < 0 or r >= len(chk.map_locations):
            return
        ml = chk.map_locations[r]
        try:
            if item.column() == 0:
                ml.map = item.text().strip()
            elif item.column() == 1:
                ml.x = int(item.text())
            elif item.column() == 2:
                ml.y = int(item.text())
            elif item.column() == 3:
                ml.size = int(item.text())
            self.model.changed.emit()
            self.canvas.reload()
        except ValueError:
            pass

    def on_add_location(self) -> None:
        if not self._selected_ref:
            return
        area, chk = self._selected_ref
        maps = [m.name for m in self.model.maps]
        if not maps:
            return
        m, ok = QtWidgets.QInputDialog.getItem(self, "Add location", "Map:", maps, 0, False)
        if not ok or not m:
            return
        chk.map_locations.append(MapLocation(map=m, x=0, y=0, size=24))
        self.model.changed.emit()
        self.canvas.reload()

    def on_del_location(self) -> None:
        if not self._selected_ref:
            return
        area, chk = self._selected_ref
        r = self.tbl_locations.currentRow()
        if r < 0 or r >= len(chk.map_locations):
            return
        chk.map_locations.pop(r)
        self.model.changed.emit()
        self.canvas.reload()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
