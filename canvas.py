from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from model import AreaDef, CheckDef, MapLocation, PackModel


def clamp_int(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(value))))


class HoverMenuListWidget(QtWidgets.QListWidget):
    drag_started = QtCore.Signal()

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        drag_token_for_payload: Optional[Callable[[object], Optional[str]]] = None,
    ) -> None:
        super().__init__(parent)
        self._drag_token_for_payload = drag_token_for_payload
        self._press_pos: Optional[QtCore.QPoint] = None
        self._press_item: Optional[QtWidgets.QListWidgetItem] = None

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        # Keep wheel interaction scoped to the dropdown so wheel-at-end
        # does not bubble up and zoom the map view.
        super().wheelEvent(event)
        event.accept()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._press_pos = event.pos()
            self._press_item = self.itemAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.buttons() & QtCore.Qt.LeftButton
            and self._press_pos is not None
            and self._press_item is not None
            and self._drag_token_for_payload is not None
        ):
            if (event.pos() - self._press_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                payload = self._press_item.data(QtCore.Qt.UserRole)
                token = self._drag_token_for_payload(payload)
                if token:
                    mime = QtCore.QMimeData()
                    mime.setData("application/x-soh-map-location", token.encode("utf-8"))
                    drag = QtGui.QDrag(self)
                    drag.setMimeData(mime)
                    self.drag_started.emit()
                    drag.exec(QtCore.Qt.MoveAction)
                self._press_pos = None
                self._press_item = None
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._press_pos = None
        self._press_item = None
        super().mouseReleaseEvent(event)


class MarkerItem(QtWidgets.QGraphicsRectItem):
    def __init__(
        self,
        key: Tuple[int, int, int],
        checks: List[Tuple[AreaDef, CheckDef, MapLocation]],
        size: int,
        on_moved: Callable[["MarkerItem", QtCore.QPointF], None],
        on_move_finished: Callable[["MarkerItem"], None],
        on_clicked: Callable[["MarkerItem"], bool],
        on_hovered: Callable[["MarkerItem"], None],
    ) -> None:
        super().__init__()
        self.key = key
        self.checks = checks
        self.size = size
        self.on_moved = on_moved
        self.on_move_finished = on_move_finished
        self.on_clicked = on_clicked
        self.on_hovered = on_hovered
        self._was_moved = False
        self._selected = False
        self._selected_location = False

        self.setRect(-size / 2, -size / 2, size, size)
        self.setPos(key[0], key[1])
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._set_style(selected=False)

        self.badge: Optional[QtWidgets.QGraphicsPathItem] = None
        self.badge_shadow: Optional[QtWidgets.QGraphicsPathItem] = None
        if len(checks) > 1:
            badge_text = f"×{len(checks)}"
            font = QtGui.QFont()
            font.setBold(True)
            font_size = 11
            text_path = QtGui.QPainterPath()
            max_text_width = max(8.0, size - 6.0)
            while font_size > 7:
                font.setPointSize(font_size)
                text_path = QtGui.QPainterPath()
                text_path.addText(0, 0, font, badge_text)
                if text_path.boundingRect().width() <= max_text_width:
                    break
                font_size -= 1

            text_rect = text_path.boundingRect()
            text_path.translate(-text_rect.center().x(), -text_rect.center().y())

            self.badge_shadow = QtWidgets.QGraphicsPathItem(text_path, self)
            self.badge_shadow.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            self.badge_shadow.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 170)))

            self.badge = QtWidgets.QGraphicsPathItem(text_path, self)
            self.badge.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            self.badge.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))

            self.badge_shadow.setPos(1.0, 1.0)
            self.badge.setPos(0, 0)
            self.badge_shadow.setZValue(1)
            self.badge.setZValue(2)

    def _set_style(self, selected: bool, selected_location: bool = False) -> None:
        self._selected = selected
        self._selected_location = selected_location
        self.update()

    def set_selected_state(self, selected: bool) -> None:
        self._set_style(selected, self._selected_location)

    def set_selected_location_state(self, selected_location: bool) -> None:
        self._set_style(self._selected, selected_location)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        rect = self.rect()
        if self._selected_location:
            fill = QtGui.QColor(80, 200, 255, 95)
            inner_color = QtGui.QColor(80, 200, 255)
        elif self._selected:
            fill = QtGui.QColor(255, 223, 0, 70)
            inner_color = QtGui.QColor(255, 223, 0)
        else:
            fill = QtGui.QColor(0, 0, 0, 45)
            inner_color = QtGui.QColor(255, 255, 255)

        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setBrush(QtGui.QBrush(fill))

        outer_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 235))
        outer_pen.setWidth(4)
        outer_pen.setCosmetic(True)
        painter.setPen(outer_pen)
        painter.drawRect(rect)

        inner_pen = QtGui.QPen(inner_color)
        inner_pen.setWidth(4 if self._selected_location else (3 if self._selected else 2))
        inner_pen.setCosmetic(True)
        painter.setPen(inner_pen)
        painter.drawRect(rect)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        QtWidgets.QToolTip.hideText()
        self.on_hovered(self)
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._was_moved = False
            consumed = self.on_clicked(self)
            if consumed:
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._was_moved:
            self.on_move_finished(self)
            self._was_moved = False

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            pos: QtCore.QPointF = value
            self._was_moved = True
            self.on_moved(self, pos)
        return super().itemChange(change, value)


class MapCanvas(QtWidgets.QGraphicsView):
    check_selected = QtCore.Signal(object, object)
    selection_cleared = QtCore.Signal()
    locations_changed = QtCore.Signal()
    add_check_requested = QtCore.Signal(str, int, int)

    def __init__(self, model: PackModel) -> None:
        super().__init__()
        self.model = model
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setMouseTracking(True)

        self._map_name: Optional[str] = None
        self._pix_item: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self._markers: List[MarkerItem] = []
        self._hover_menu: Optional[QtWidgets.QListWidget] = None
        self._hover_menu_key: Optional[Tuple[int, int, int]] = None
        self._reload_in_progress = False
        self._pending_reload = False
        self._left_press_pos: Optional[QtCore.QPoint] = None
        self._left_press_on_marker = False
        self._left_press_moved = False
        self._hover_menu_slop_px = 24
        self._hover_menu_watchdog = QtCore.QTimer(self)
        self._hover_menu_watchdog.setInterval(60)
        self._hover_menu_watchdog.timeout.connect(self._check_hover_menu_cursor)
        self._drag_payload_nonce = 0
        self._drag_payloads: Dict[str, Tuple[AreaDef, CheckDef, MapLocation]] = {}

        self.selected_check_ref: Optional[Tuple[AreaDef, CheckDef]] = None
        self.selected_location_ref: Optional[MapLocation] = None

        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def set_map(self, map_name: str) -> None:
        self._map_name = map_name
        self.resetTransform()
        self.reload()
        self.fit_to_view()

    def current_map_name(self) -> Optional[str]:
        return self._map_name

    def clear_map(self) -> None:
        self._map_name = None
        self._reset_scene()

    def fit_to_view(self) -> None:
        if self._pix_item:
            self.fitInView(self._pix_item, QtCore.Qt.KeepAspectRatio)

    def _current_scale(self) -> float:
        return self.transform().m11()

    def _minimum_scale(self) -> float:
        if not self._pix_item:
            return 1.0
        pix_rect = self._pix_item.boundingRect()
        viewport_rect = self.viewport().rect()
        if pix_rect.width() <= 0 or pix_rect.height() <= 0:
            return 1.0
        if viewport_rect.width() <= 0 or viewport_rect.height() <= 0:
            return 1.0
        return min(
            viewport_rect.width() / pix_rect.width(),
            viewport_rect.height() / pix_rect.height(),
        )

    def _maximum_scale(self) -> float:
        min_scale = self._minimum_scale()
        return max(min_scale, min_scale * 8.0)

    def _enforce_zoom_limits(self) -> None:
        if not self._pix_item:
            return
        current = self._current_scale()
        min_scale = self._minimum_scale()
        max_scale = self._maximum_scale()
        if current < min_scale - 1e-6:
            self.fit_to_view()
            return
        if current > max_scale + 1e-6:
            center = self.mapToScene(self.viewport().rect().center())
            factor = max_scale / current
            self.scale(factor, factor)
            self.centerOn(center)

    def clear_selected_check(self) -> None:
        self.selected_check_ref = None
        self.selected_location_ref = None
        self._refresh_marker_selection()

    def set_selected_check(self, area: AreaDef, check: CheckDef) -> None:
        self.selected_check_ref = (area, check)
        self.selected_location_ref = None
        self._refresh_marker_selection()

    def set_selected_location(
        self,
        area: AreaDef,
        check: CheckDef,
        location: Optional[MapLocation],
    ) -> None:
        self.selected_check_ref = (area, check)
        self.selected_location_ref = location
        self._refresh_marker_selection()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._pix_item:
            super().wheelEvent(event)
            return
        angle = event.angleDelta().y()
        if angle == 0:
            event.accept()
            return
        current = self._current_scale()
        min_scale = self._minimum_scale()
        max_scale = self._maximum_scale()
        factor = 1.15 if angle > 0 else 1 / 1.15
        target = max(min_scale, min(max_scale, current * factor))
        self.scale(target / current, target / current)
        event.accept()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._enforce_zoom_limits()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            item = self.itemAt(event.pos())
            marker = (
                isinstance(item, MarkerItem)
                or (item is not None and isinstance(item.parentItem(), MarkerItem))
            )
            if self._hover_menu and self._hover_menu.isVisible():
                if not self._hover_menu.geometry().contains(event.pos()) and not marker:
                    self._close_hover_menu()
            self._left_press_pos = event.pos()
            self._left_press_on_marker = marker
            self._left_press_moved = False

        if event.button() == QtCore.Qt.RightButton and self._map_name:
            scene_pos = self.mapToScene(event.pos())
            x = clamp_int(scene_pos.x(), 0, 99999)
            y = clamp_int(scene_pos.y(), 0, 99999)
            menu = QtWidgets.QMenu(self)
            add_here = menu.addAction("Add check here…")
            chosen = menu.exec(self.mapToGlobal(event.pos()))
            if chosen is add_here:
                self.add_check_requested.emit(self._map_name, x, y)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._left_press_pos is not None and not self._left_press_moved:
            dist = (event.pos() - self._left_press_pos).manhattanLength()
            if dist >= QtWidgets.QApplication.startDragDistance():
                self._left_press_moved = True
                if self._left_press_on_marker and self._hover_menu and self._hover_menu.isVisible():
                    # Keep menu while clicking/selecting; only hide once an actual drag starts.
                    self._close_hover_menu()
        self._maybe_close_hover_menu(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton and self._left_press_pos is not None:
            if (
                not self._left_press_on_marker
                and not self._left_press_moved
                and self.selected_check_ref is not None
            ):
                self.clear_selected_check()
                self.selection_cleared.emit()
            self._left_press_pos = None
            self._left_press_on_marker = False
            self._left_press_moved = False
        super().mouseReleaseEvent(event)

    def _close_hover_menu(self) -> None:
        if self._hover_menu:
            self._hover_menu.hide()
            self._hover_menu_key = None
        self._hover_menu_watchdog.stop()

    def _item_to_marker(self, item: Optional[QtWidgets.QGraphicsItem]) -> Optional[MarkerItem]:
        if isinstance(item, MarkerItem):
            return item
        if item is not None and isinstance(item.parentItem(), MarkerItem):
            return item.parentItem()  # type: ignore[return-value]
        return None

    def _maybe_close_hover_menu(self, view_pos: QtCore.QPoint) -> None:
        if not self._hover_menu or not self._hover_menu.isVisible():
            return
        menu_rect = self._hover_menu.geometry().adjusted(
            -self._hover_menu_slop_px,
            -self._hover_menu_slop_px,
            self._hover_menu_slop_px,
            self._hover_menu_slop_px,
        )
        if menu_rect.contains(view_pos):
            return
        marker = self._item_to_marker(self.itemAt(view_pos))
        if marker and marker.key == self._hover_menu_key:
            return
        if self._hover_menu_key is not None:
            for m in self._markers:
                if m.key != self._hover_menu_key:
                    continue
                marker_rect = self.mapFromScene(m.sceneBoundingRect()).boundingRect().adjusted(
                    -self._hover_menu_slop_px,
                    -self._hover_menu_slop_px,
                    self._hover_menu_slop_px,
                    self._hover_menu_slop_px,
                )
                if marker_rect.contains(view_pos):
                    return
                break
        self._close_hover_menu()

    def _check_hover_menu_cursor(self) -> None:
        if not self._hover_menu or not self._hover_menu.isVisible():
            self._hover_menu_watchdog.stop()
            return
        view_pos = self.viewport().mapFromGlobal(QtGui.QCursor.pos())
        self._maybe_close_hover_menu(view_pos)

    def _ensure_hover_menu(self) -> QtWidgets.QListWidget:
        if self._hover_menu is None:
            menu = HoverMenuListWidget(
                self.viewport(),
                drag_token_for_payload=self._register_drag_payload,
            )
            menu.setFrameShape(QtWidgets.QFrame.Box)
            menu.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            menu.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            menu.setFocusPolicy(QtCore.Qt.NoFocus)
            menu.setMouseTracking(True)

            def on_item_clicked(item: QtWidgets.QListWidgetItem) -> None:
                data = item.data(QtCore.Qt.UserRole)
                if not data:
                    return
                area, check, _location = data
                self.selected_check_ref = (area, check)
                self._refresh_marker_selection()
                self.check_selected.emit(area, check)
                self._close_hover_menu()

            menu.itemClicked.connect(on_item_clicked)
            menu.drag_started.connect(self._close_hover_menu)
            self._hover_menu = menu
        return self._hover_menu

    def _register_drag_payload(self, payload: object) -> Optional[str]:
        if not isinstance(payload, tuple) or len(payload) != 3:
            return None
        area, check, location = payload
        if not isinstance(location, MapLocation):
            return None
        self._drag_payload_nonce += 1
        token = f"{self._drag_payload_nonce}"
        self._drag_payloads[token] = (area, check, location)
        return token

    def _find_merge_target(
        self,
        scene_pos: QtCore.QPointF,
        excluded_locations: Optional[set[int]] = None,
    ) -> Optional[MarkerItem]:
        excluded_locations = excluded_locations or set()
        for marker in reversed(self._markers):
            if any(id(ml) in excluded_locations for _, _, ml in marker.checks):
                continue
            if marker.sceneBoundingRect().contains(scene_pos):
                return marker
        return None

    def _open_stack_menu(
        self, key: Tuple[int, int, int], checks: List[Tuple[AreaDef, CheckDef, MapLocation]]
    ) -> None:
        menu = self._ensure_hover_menu()
        if self._hover_menu_key == key and menu.isVisible():
            return

        menu.clear()
        for area, check, location in checks:
            item = QtWidgets.QListWidgetItem(f"{check.name} [{check.soh_id}]")
            item.setData(QtCore.Qt.UserRole, (area, check, location))
            menu.addItem(item)

        rows = max(1, min(menu.count(), 10))
        row_h = menu.sizeHintForRow(0) if menu.count() > 0 else 20
        width = 320
        height = rows * max(row_h, 20) + 8
        menu.resize(width, height)

        vp_w = self.viewport().width()
        vp_h = self.viewport().height()
        margin = 12

        marker_rect: Optional[QtCore.QRect] = None
        for marker in self._markers:
            if marker.key == key:
                marker_rect = self.mapFromScene(marker.sceneBoundingRect()).boundingRect()
                break

        if marker_rect is not None:
            candidates = [
                QtCore.QPoint(marker_rect.right() + margin, marker_rect.top()),
                QtCore.QPoint(marker_rect.left() - margin - width, marker_rect.top()),
                QtCore.QPoint(marker_rect.left(), marker_rect.bottom() + margin),
                QtCore.QPoint(marker_rect.left(), marker_rect.top() - margin - height),
            ]

            chosen: Optional[QtCore.QPoint] = None
            for pt in candidates:
                if (
                    0 <= pt.x() <= max(0, vp_w - width)
                    and 0 <= pt.y() <= max(0, vp_h - height)
                ):
                    chosen = pt
                    break
            if chosen is None:
                chosen = candidates[0]
            x = max(0, min(chosen.x(), max(0, vp_w - width)))
            y = max(0, min(chosen.y(), max(0, vp_h - height)))
        else:
            view_pos = self.viewport().mapFromGlobal(QtGui.QCursor.pos())
            x = max(0, min(view_pos.x() + 14, max(0, vp_w - width)))
            y = max(0, min(view_pos.y() + 14, max(0, vp_h - height)))

        menu.move(x, y)
        menu.show()
        menu.raise_()
        self._hover_menu_key = key
        self._hover_menu_watchdog.start()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if self._map_name and event.mimeData().hasFormat("application/x-soh-map-location"):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if self._map_name and event.mimeData().hasFormat("application/x-soh-map-location"):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        if not self._map_name or not event.mimeData().hasFormat("application/x-soh-map-location"):
            super().dropEvent(event)
            return
        token = bytes(event.mimeData().data("application/x-soh-map-location")).decode("utf-8")
        payload = self._drag_payloads.pop(token, None)
        if not payload:
            event.ignore()
            return
        area, check, location = payload
        pos = event.position().toPoint()
        scene_pos = self.mapToScene(pos)
        location.map = self._map_name
        merge_target = self._find_merge_target(scene_pos, excluded_locations={id(location)})
        if merge_target is not None:
            location.x = merge_target.key[0]
            location.y = merge_target.key[1]
            location.size = merge_target.key[2]
        else:
            location.x = clamp_int(scene_pos.x(), 0, 99999)
            location.y = clamp_int(scene_pos.y(), 0, 99999)
        self.selected_check_ref = (area, check)
        self.selected_location_ref = location
        self.reload()
        self.check_selected.emit(area, check)
        self.locations_changed.emit()
        event.acceptProposedAction()

    def _reset_scene(self) -> None:
        self._close_hover_menu()
        old_scene = self._scene
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._markers.clear()
        self._pix_item = None
        old_scene.deleteLater()

    def reload(self) -> None:
        if self._reload_in_progress:
            self._pending_reload = True
            return

        self._reload_in_progress = True
        try:
            # Preserve view position/zoom during incremental redraws.
            saved_transform = QtGui.QTransform(self.transform())
            saved_h = self.horizontalScrollBar().value()
            saved_v = self.verticalScrollBar().value()

            self._pending_reload = False
            self._reset_scene()
            if not self._map_name or not self.model.base_dir:
                return

            map_def = self.model.find_map(self._map_name)
            if not map_def:
                return

            img_path = self.model.base_dir / map_def.img
            if not img_path.exists():
                img_path = self.model.base_dir / "images" / "maps" / Path(map_def.img).name
            if img_path.exists():
                pix = QtGui.QPixmap(str(img_path))
                self._pix_item = self._scene.addPixmap(pix)
                self._scene.setSceneRect(pix.rect())

            clusters: Dict[Tuple[int, int, int], List[Tuple[AreaDef, CheckDef, MapLocation]]] = {}
            for area, check in self.model.all_checks():
                for ml in check.map_locations:
                    if ml.map != self._map_name:
                        continue
                    key = (int(ml.x), int(ml.y), int(ml.size))
                    clusters.setdefault(key, []).append((area, check, ml))

            def on_moved(marker: MarkerItem, pos: QtCore.QPointF) -> None:
                x = clamp_int(pos.x(), 0, 99999)
                y = clamp_int(pos.y(), 0, 99999)
                for _, _, ml in marker.checks:
                    ml.x = x
                    ml.y = y

            def on_move_finished(marker: MarkerItem) -> None:
                merge_target = self._find_merge_target(
                    marker.scenePos(),
                    excluded_locations={id(ml) for _, _, ml in marker.checks},
                )
                if merge_target is not None:
                    for _, _, ml in marker.checks:
                        ml.x = merge_target.key[0]
                        ml.y = merge_target.key[1]
                        ml.size = merge_target.key[2]
                self.locations_changed.emit()

            def on_clicked(marker: MarkerItem) -> bool:
                if len(marker.checks) == 1:
                    area, check, _ = marker.checks[0]
                    self.selected_check_ref = (area, check)
                    self._refresh_marker_selection()
                    self.check_selected.emit(area, check)
                    return False

                # Multi-check selection is hover-driven via dropdown menu.
                return False

            def on_hovered(marker: MarkerItem) -> None:
                self._open_stack_menu(marker.key, marker.checks)

            for key, checks in clusters.items():
                size = key[2] if key[2] else 24
                marker = MarkerItem(
                    key=key,
                    checks=checks,
                    size=size,
                    on_moved=on_moved,
                    on_move_finished=on_move_finished,
                    on_clicked=on_clicked,
                    on_hovered=on_hovered,
                )
                self._scene.addItem(marker)
                self._markers.append(marker)

            self.setTransform(saved_transform)
            self.horizontalScrollBar().setValue(saved_h)
            self.verticalScrollBar().setValue(saved_v)
            self._enforce_zoom_limits()
            self._refresh_marker_selection()
        finally:
            self._reload_in_progress = False
            if self._pending_reload:
                self._pending_reload = False
                QtCore.QTimer.singleShot(0, self.reload)

    def _refresh_marker_selection(self) -> None:
        if not self.selected_check_ref:
            for marker in self._markers:
                marker.set_selected_state(False)
                marker.set_selected_location_state(False)
            return

        selected_area, selected_check = self.selected_check_ref
        for marker in self._markers:
            match = any(
                (area is selected_area and check is selected_check)
                for area, check, _ in marker.checks
            )
            marker.set_selected_state(match)
            location_match = (
                self.selected_location_ref is not None
                and any(ml is self.selected_location_ref for _, _, ml in marker.checks)
            )
            marker.set_selected_location_state(location_match)
