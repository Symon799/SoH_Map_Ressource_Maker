from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from model import AreaDef, CheckDef, MapDef, MapLocation, PackModel

BANNED_MAP_FIELDS = {"location_size", "location_border_thickness"}
BANNED_CHECK_FIELDS = {"access_rules", "visibility_rules", "item_count"}


def safe_load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def area_to_filename(area_name: str) -> str:
    text = area_name.strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^A-Za-z0-9_\-]", "", text)
    if not text:
        text = "area"
    return f"{text}.json"


def _detect_pack_root(tmp_root: Path) -> Path:
    preferred = tmp_root / "soh-map-tracker"
    if preferred.exists() and (preferred / "maps.json").exists():
        return preferred

    candidates: List[Path] = []
    for maps_json in tmp_root.rglob("maps.json"):
        if maps_json.is_file():
            candidates.append(maps_json.parent)
    if not candidates:
        raise RuntimeError("Could not find root folder containing maps.json in zip")

    def score(pack_root: Path) -> Tuple[int, int, int]:
        depth = len(pack_root.relative_to(tmp_root).parts)
        has_areas = int((pack_root / "areas").exists())
        has_images = int((pack_root / "images" / "maps").exists())
        return (depth, -has_areas, -has_images)

    candidates.sort(key=score)
    return candidates[0]


def load_pack_from_zip(model: PackModel, zip_path: Path) -> None:
    model.clear(emit_signal=False)
    tmp = Path(tempfile.mkdtemp(prefix="soh_pack_edit_"))
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp)

    root = _detect_pack_root(tmp)
    model.root_name = root.name
    model.set_workspace(root, tmp)

    maps_raw = safe_load_json(root / "maps.json")
    model.maps = []
    for item in maps_raw:
        extra = {
            k: v
            for k, v in item.items()
            if k not in {"name", "img", "group"} | BANNED_MAP_FIELDS
        }
        model.maps.append(
            MapDef(
                name=str(item.get("name", "")),
                img=str(item.get("img", "")),
                group=str(item.get("group", "")),
                extra=extra,
            )
        )

    model.areas = []
    areas_dir = root / "areas"
    if areas_dir.exists():
        for area_file in sorted(areas_dir.glob("*.json")):
            raw = safe_load_json(area_file)
            area_name = str(raw.get("area", area_file.stem.replace("_", " ")))
            area_extra = {k: v for k, v in raw.items() if k not in {"area", "checks"}}
            checks: List[CheckDef] = []
            for check in raw.get("checks", []):
                check_extra = {
                    k: v
                    for k, v in check.items()
                    if k not in {"name", "hint", "soh_id", "map_locations"} | BANNED_CHECK_FIELDS
                }
                locations = [MapLocation.from_dict(d) for d in check.get("map_locations", [])]
                checks.append(
                    CheckDef(
                        name=str(check.get("name", "")),
                        hint=str(check.get("hint", "")),
                        soh_id=str(check.get("soh_id", "")),
                        map_locations=locations,
                        extra=check_extra,
                    )
                )
            model.areas.append(AreaDef(area=area_name, checks=checks, extra=area_extra))

    model.changed.emit()


def export_pack_to_zip(model: PackModel, out_zip: Path, preserve_unknown: bool) -> None:
    if not model.base_dir:
        raise RuntimeError("No pack loaded")

    tmp_out = Path(tempfile.mkdtemp(prefix="soh_pack_export_"))
    root = tmp_out / "soh-map-tracker"
    (root / "areas").mkdir(parents=True, exist_ok=True)
    (root / "images" / "maps").mkdir(parents=True, exist_ok=True)

    copied_image_names: set[str] = set()
    for m in model.maps:
        src = model.base_dir / m.img
        if not src.exists():
            src = model.base_dir / "images" / "maps" / Path(m.img).name
        if src.exists() and src.is_file():
            if src.name in copied_image_names:
                continue
            shutil.copy2(src, root / "images" / "maps" / src.name)
            copied_image_names.add(src.name)

    maps_out: List[Dict[str, Any]] = []
    for m in model.maps:
        out = {"name": m.name, "img": m.img, "group": m.group}
        if preserve_unknown:
            for k, v in m.extra.items():
                if k not in BANNED_MAP_FIELDS:
                    out[k] = v
        maps_out.append(out)
    safe_write_json(root / "maps.json", maps_out)

    for area in model.areas:
        area_out: Dict[str, Any] = {"area": area.area}
        if preserve_unknown:
            area_out.update(area.extra)

        checks_out: List[Dict[str, Any]] = []
        for check in area.checks:
            check_out: Dict[str, Any] = {
                "name": check.name,
                "hint": check.hint,
                "soh_id": check.soh_id,
                "map_locations": [ml.to_dict(preserve_unknown) for ml in check.map_locations],
            }
            if preserve_unknown:
                for k, v in check.extra.items():
                    if k not in BANNED_CHECK_FIELDS:
                        check_out[k] = v
            checks_out.append(check_out)
        area_out["checks"] = checks_out
        safe_write_json(root / "areas" / area_to_filename(area.area), area_out)

    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(tmp_out):
            for fn in files:
                fp = Path(folder) / fn
                rel = fp.relative_to(tmp_out)
                z.write(fp, rel.as_posix())

    shutil.rmtree(tmp_out, ignore_errors=True)
