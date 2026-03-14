from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6 import QtCore


@dataclass
class MapDef:
    name: str
    img: str
    group: str
    id: str
    links: List["MapLink"] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    runtime_key: str = field(default_factory=lambda: uuid.uuid4().hex, repr=False, compare=False)

    def editor_key(self) -> str:
        if self.id:
            return self.id
        return f"__missing_id__:{self.runtime_key}"


@dataclass
class MapLocation:
    map_id: str
    x: int
    y: int
    size: int = 24
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "MapLocation":
        extra = {k: v for k, v in data.items() if k not in {"map", "map_id", "x", "y", "size"}}
        return MapLocation(
            map_id=str(data.get("map_id", data.get("map", ""))),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            size=int(data.get("size", 24)),
            extra=extra,
        )

    def to_dict(self, preserve_unknown: bool) -> Dict[str, Any]:
        out = {
            "map_id": self.map_id,
            "x": int(self.x),
            "y": int(self.y),
            "size": int(self.size),
        }
        if preserve_unknown:
            out.update(self.extra)
        return out


@dataclass
class MapLink:
    target_map_id: str
    x: int
    y: int
    size: int = 24
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "MapLink":
        extra = {
            k: v for k, v in data.items() if k not in {"target_map", "target_map_id", "x", "y", "size"}
        }
        return MapLink(
            target_map_id=str(data.get("target_map_id", data.get("target_map", ""))),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            size=int(data.get("size", 24)),
            extra=extra,
        )

    def to_dict(self, preserve_unknown: bool) -> Dict[str, Any]:
        out = {
            "target_map_id": self.target_map_id,
            "x": int(self.x),
            "y": int(self.y),
            "size": int(self.size),
        }
        if preserve_unknown:
            out.update(self.extra)
        return out


@dataclass
class CheckDef:
    name: str
    hint: str
    soh_id: str
    map_locations: List[MapLocation] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


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
        self.base_dir: Optional[Path] = None
        self.maps: List[MapDef] = []
        self.areas: List[AreaDef] = []
        self.load_warnings: List[str] = []
        self._workspace_tmp: Optional[Path] = None

    def _cleanup_workspace(self) -> None:
        if self._workspace_tmp and self._workspace_tmp.exists():
            shutil.rmtree(self._workspace_tmp, ignore_errors=True)
        self._workspace_tmp = None

    def set_workspace(self, root: Path, workspace_tmp: Path) -> None:
        self._cleanup_workspace()
        self.base_dir = root
        self._workspace_tmp = workspace_tmp

    def clear(self, emit_signal: bool = True) -> None:
        self._cleanup_workspace()
        self.base_dir = None
        self.maps.clear()
        self.areas.clear()
        self.load_warnings = []
        if emit_signal:
            self.changed.emit()

    def new_pack(self) -> None:
        self.clear(emit_signal=False)
        self.root_name = "soh-map-tracker"
        tmp = Path(tempfile.mkdtemp(prefix="soh_pack_edit_"))
        root = tmp / self.root_name
        (root / "areas").mkdir(parents=True, exist_ok=True)
        (root / "images" / "maps").mkdir(parents=True, exist_ok=True)
        self.set_workspace(root, tmp)
        self.changed.emit()

    def all_checks(self) -> List[Tuple[AreaDef, CheckDef]]:
        out: List[Tuple[AreaDef, CheckDef]] = []
        for area in self.areas:
            for check in area.checks:
                out.append((area, check))
        return out

    def count_checks_on_map(self, map_id: str) -> int:
        count = 0
        for _area, check in self.all_checks():
            if any(location.map_id == map_id for location in check.map_locations):
                count += 1
        return count

    def find_map(self, identifier: str) -> Optional[MapDef]:
        if not identifier:
            return None
        for m in self.maps:
            if m.id == identifier:
                return m
        for m in self.maps:
            if m.editor_key() == identifier:
                return m
        return None

    def find_map_by_id(self, map_id: str) -> Optional[MapDef]:
        if not map_id:
            return None
        for m in self.maps:
            if m.id == map_id:
                return m
        return None

    def display_name_for_map_id(self, map_id: str) -> str:
        map_def = self.find_map_by_id(map_id)
        if map_def is not None:
            return map_def.name
        return map_id

    def format_map_label(self, map_id: str) -> str:
        map_def = self.find_map_by_id(map_id)
        if map_def is not None:
            return f"{map_def.name} [{map_def.id}]"
        if map_id:
            return map_id
        return "(missing map id)"

    def find_area(self, area_name: str) -> Optional[AreaDef]:
        for area in self.areas:
            if area.area == area_name:
                return area
        return None
