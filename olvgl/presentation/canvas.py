"""Canvas tipo Figma: QGraphicsScene/QGraphicsView sincronizados con el ViewModel.

Cada widget es un QGraphicsItem hijo del item de su padre (como en LVGL), en
la posición que calcula el motor de disposición. Mover un widget desplaza sus
x/y relativos; los hijos de un contenedor flex/grid no se pueden arrastrar.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsScene, QGraphicsSceneHoverEvent,
                               QGraphicsSceneMouseEvent, QGraphicsView, QStyleOptionGraphicsItem,
                               QWidget)

from olvgl.i18n import tr
from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain.layout import Box
from olvgl.domain.model import TOP_LAYER_ID
from olvgl.presentation import render

MIME_WIDGET = "application/x-olvgl-widget"
HANDLE = 7.0
SELECT_COLOR = QColor("#7C4DFF")
OUTSIDE_COLOR = QColor("#2B2B2E")

# Tiradores: (nombre, fx, fy) con fx/fy en {0, 0.5, 1}
HANDLES = [("tl", 0, 0), ("t", 0.5, 0), ("tr", 1, 0), ("r", 1, 0.5),
           ("br", 1, 1), ("b", 0.5, 1), ("bl", 0, 1), ("l", 0, 0.5)]
HANDLE_CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
}


class WidgetItem(QGraphicsItem):
    def __init__(self, scene: "DesignScene", widget_id: str):
        super().__init__()
        self.design_scene = scene
        self.widget_id = widget_id
        self.w = 10.0
        self.h = 10.0
        self.abs_origin = QPointF()      # posición absoluta según el modelo
        self.parent_origin = QPointF()   # posición absoluta del item padre
        self.box: Box | None = None
        self._resize_handle: str | None = None
        self._resize_start: QRectF | None = None
        self._press_scene = QPointF()
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

    # ------------------------------------------------------------------ datos
    @property
    def vm(self) -> ProjectViewModel:
        return self.design_scene.vm

    def model(self):
        return self.vm.widget(self.widget_id)

    def expected_pos(self) -> QPointF:
        return self.abs_origin - self.parent_origin

    def apply_box(self, box: Box, parent_origin: QPointF, force: bool = True) -> None:
        old = self.box
        if not force and old is not None and old == box and self.parent_origin == parent_origin:
            return                      # nada que cambie su aspecto ni su posición
        self.box = box
        if (box.rect.w, box.rect.h) != (self.w, self.h):
            self.prepareGeometryChange()
            self.w, self.h = float(box.rect.w), float(box.rect.h)
        self.abs_origin = QPointF(box.rect.x, box.rect.y)
        self.parent_origin = parent_origin
        self.design_scene._syncing += 1
        try:
            self.setPos(self.expected_pos())
        finally:
            self.design_scene._syncing -= 1
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, box.movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape,
                     not bool(box.props.get("overflow_visible")))
        self.setVisible(box.shown)
        w = self.model()
        if w is not None:
            from olvgl.domain import catalog
            tip = f"{catalog.type_label(w.type)} · {w.id}"
            if box.managed:
                tip += tr("\nPosición fijada por la disposición (flex/grid) del contenedor")
            self.setToolTip(tip)
        self.update()

    def resizable(self) -> bool:
        return bool(self.box and self.box.resizable)

    def show_handles(self) -> bool:
        return (self.isSelected() and self.resizable()
                and len(self.design_scene.selectedItems()) == 1)

    # ------------------------------------------------------------------ geometría
    def boundingRect(self) -> QRectF:
        m = HANDLE / max(min(self.design_scene.view_scale(), 1.0), 0.05) + 2
        return QRectF(-m, -m, self.w + 2 * m, self.h + 2 * m)

    def refresh_geometry(self) -> None:
        self.prepareGeometryChange()
        self.update()

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.w, self.h))
        if self.show_handles():
            for _, r in self.handle_rects():
                path.addRect(r)
        return path

    def handle_rects(self) -> list[tuple[str, QRectF]]:
        scale = self.design_scene.view_scale()
        size = HANDLE / max(scale, 0.05)
        out = []
        for name, fx, fy in HANDLES:
            cx, cy = self.w * fx, self.h * fy
            out.append((name, QRectF(cx - size / 2, cy - size / 2, size, size)))
        return out

    def handle_at(self, pos: QPointF) -> str | None:
        if not self.show_handles():
            return None
        for name, r in self.handle_rects():
            if r.adjusted(-2, -2, 2, 2).contains(pos):
                return name
        return None

    # ------------------------------------------------------------------ pintado
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        w = self.model()
        if w is None or self.box is None:
            return
        rect = QRectF(0, 0, self.w, self.h)
        if self.box.hidden:
            painter.setOpacity(0.35)
        painter.save()
        painter.translate(-self.box.rect.x, -self.box.rect.y)
        render.paint_widget(painter, w, QRectF(self.box.rect.x, self.box.rect.y, self.w, self.h),
                            self.box.props, self.design_scene.render_ctx, self.box)
        painter.restore()
        painter.setOpacity(1.0)
        scale = self.design_scene.view_scale()
        if self.isSelected():
            pen = QPen(SELECT_COLOR, 1.5 / max(scale, 0.05))
            if self.box.managed:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            if self.show_handles():
                painter.setBrush(QBrush(QColor("#FFFFFF")))
                for _, r in self.handle_rects():
                    painter.drawRect(r)
        elif self.design_scene.show_outlines:
            pen = QPen(QColor(124, 77, 255, 70), 1 / max(scale, 0.05), Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    # ------------------------------------------------------------------ interacción
    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and not self.design_scene._syncing and isinstance(value, QPointF)):
            absolute = value + self.parent_origin
            snapped = QPointF(self.vm.snap_value(absolute.x()), self.vm.snap_value(absolute.y()))
            return snapped - self.parent_origin
        return super().itemChange(change, value)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        h = self.handle_at(event.pos())
        if h:
            self.setCursor(QCursor(HANDLE_CURSORS[h]))
        elif self.isSelected() and self.box and self.box.movable:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().hoverMoveEvent(event)

    def _tab_at(self, pos: QPointF) -> int | None:
        if self.box is None or "tab_buttons" not in self.box.extra:
            return None
        ax, ay = pos.x() + self.box.rect.x, pos.y() + self.box.rect.y
        for i, (r, _name, _tid) in enumerate(self.box.extra["tab_buttons"]):
            if r.x <= ax < r.right and r.y <= ay < r.bottom:
                return i
        return None

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            h = self.handle_at(event.pos())
            if h:
                self._resize_handle = h
                self._resize_start = QRectF(self.abs_origin.x(), self.abs_origin.y(), self.w, self.h)
                self._press_scene = event.scenePos()
                event.accept()
                return
            tab = self._tab_at(event.pos())
            if tab is not None:
                self.vm.set_active_tab(self.widget_id, tab)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._resize_handle and self._resize_start is not None:
            start = self._resize_start
            r = QRectF(start)
            d = event.scenePos() - self._press_scene
            snap = self.vm.snap_value
            h = self._resize_handle
            movable = bool(self.box and self.box.movable)
            if "l" in h and movable:
                r.setLeft(snap(start.left() + d.x()))
            if "r" in h:
                r.setRight(snap(start.right() + d.x()))
            if "t" in h and movable:
                r.setTop(snap(start.top() + d.y()))
            if "b" in h:
                r.setBottom(snap(start.bottom() + d.y()))
            r = r.normalized()
            if r.width() < 4:
                r.setWidth(4)
            if r.height() < 4:
                r.setHeight(4)
            self.prepareGeometryChange()
            self.w, self.h = r.width(), r.height()
            self.design_scene._syncing += 1
            try:
                self.setPos(r.topLeft() - self.parent_origin)
            finally:
                self.design_scene._syncing -= 1
            self.design_scene.geometry_preview.emit(self.widget_id, r)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._resize_handle:
            self._resize_handle = None
            self._resize_start = None
            absolute = self.pos() + self.parent_origin
            rect = (absolute.x(), absolute.y(), self.w, self.h)
            event.accept()
            self.vm.set_geometry(self.widget_id, rect)
            self.design_scene.sync()   # por si el cambio no se aceptó
            return
        super().mouseReleaseEvent(event)


class DesignScene(QGraphicsScene):
    geometry_preview = Signal(str, QRectF)

    def __init__(self, vm: ProjectViewModel, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.items_by_id: dict[str, WidgetItem] = {}
        self._syncing = 0
        self._selecting = False
        self.show_grid = True
        self.show_outlines = True
        self.show_top_layer = True
        self.comment_counts: dict[str, int] = {}    # comentarios abiertos por widget (colaboración)
        self.render_ctx = render.RenderContext(vm.project, vm.resolve_path)
        self.selectionChanged.connect(self._on_scene_selection)
        vm.project_changed.connect(lambda: self.sync(incremental=True))
        vm.layout_changed.connect(self.sync)
        vm.project_replaced.connect(self.sync)
        vm.screen_changed.connect(lambda _id: self.sync())
        vm.selection_changed.connect(self._on_vm_selection)
        self.sync()

    # ------------------------------------------------------------------ utilidades
    def view_scale(self) -> float:
        views = self.views()
        return views[0].transform().m11() if views else 1.0

    def screen_rect(self) -> QRectF:
        d = self.vm.project.display
        return QRectF(0, 0, d.width, d.height)

    # ------------------------------------------------------------------ sincronización
    def _resources_signature(self) -> tuple:
        p = self.vm.project
        return (id(p), repr([f.to_dict() for f in p.fonts]), repr([i.to_dict() for i in p.images]),
                repr(p.extra_sections.get("color")), repr([s.to_dict() for s in p.styles]), repr(p.lvgl_extra.get("theme")),
                repr(p.display.to_dict()))

    def sync(self, incremental: bool = False) -> None:
        """Recoloca los items. Con `incremental` (un cambio de widgets) sólo se
        vuelven a dibujar los que han cambiado: mover con las flechas no
        repinta toda la página ni recrea las fuentes."""
        change = self.vm.last_change if incremental else None
        touched = change.ids if change is not None and change.kind != "structure" else None
        sig = self._resources_signature()
        if sig != getattr(self, "_res_sig", None) or touched is None:
            if sig != getattr(self, "_res_sig", None):
                self.render_ctx = render.RenderContext(self.vm.project, self.vm.resolve_path)
                self._res_sig = sig
            touched = None
        screen = self.vm.current_screen
        boxes = self.vm.layout() if screen else {}
        order: list[tuple[str, str | None]] = []   # (id, padre) en orden de pila

        def visit(lst, parent):
            for w in lst:
                order.append((w.id, parent))
                visit(w.children, w.id)

        if screen:
            visit(screen.widgets, None)
        wanted = {wid for wid, _ in order}
        self._selecting = True  # los cambios de escena no deben tocar la selección del VM
        try:
            # 1) sacar de padres que desaparecen los hijos que siguen existiendo
            for wid, item in list(self.items_by_id.items()):
                if wid in wanted:
                    continue
                for child in list(item.childItems()):
                    if isinstance(child, WidgetItem) and child.widget_id in wanted:
                        child.setParentItem(None)
            # 2) eliminar los que ya no existen. Primero se desanidan todos: si se
            #    quitara un padre con hijos, Qt destruiría también los hijos.
            unwanted = [self.items_by_id.pop(w) for w in list(self.items_by_id) if w not in wanted]
            for item in unwanted:
                item.setParentItem(None)
            for item in unwanted:
                if item.scene() is self:
                    self.removeItem(item)
            unwanted.clear()
            # 3) crear, reubicar y colocar
            for z, (wid, parent) in enumerate(order):
                item = self.items_by_id.get(wid)
                if item is None:
                    item = WidgetItem(self, wid)
                    self.items_by_id[wid] = item
                    self.addItem(item)
                parent_item = self.items_by_id.get(parent) if parent else None
                if item.parentItem() is not parent_item:
                    item.setParentItem(parent_item)
                item.setZValue(z)
                box = boxes.get(wid)
                if box is not None:
                    origin = QPointF(boxes[parent].rect.x, boxes[parent].rect.y) if parent and parent in boxes \
                        else QPointF(0, 0)
                    item.apply_box(box, origin, force=touched is None or wid in touched)
            self.items_by_id = {wid: self.items_by_id[wid] for wid, _ in order}
        finally:
            self._selecting = False
        r = self.screen_rect()
        margin = max(r.width(), r.height()) * 0.5
        self.setSceneRect(r.adjusted(-margin, -margin, margin, margin))
        self._apply_selection(self.vm.selection, repaint_all=touched is None)
        if touched is None:
            self.update()

    def _apply_selection(self, ids: list[str], repaint_all: bool = True) -> None:
        self._selecting = True
        changed = []
        try:
            for wid, item in self.items_by_id.items():
                sel = wid in ids
                if item.isSelected() != sel:
                    item.setSelected(sel)
                    changed.append(item)
        finally:
            self._selecting = False
        for item in (self.items_by_id.values() if repaint_all else changed):
            item.update()

    def _on_vm_selection(self, ids: list[str]) -> None:
        self._apply_selection(ids)

    def on_zoom_changed(self) -> None:
        for item in self.items_by_id.values():
            item.refresh_geometry()

    def _on_scene_selection(self) -> None:
        if self._selecting:
            return
        ids = [i.widget_id for i in self.selectedItems() if isinstance(i, WidgetItem)]
        order = list(self.items_by_id)
        ids.sort(key=lambda i: order.index(i) if i in order else 0)
        self.vm.set_selection(ids)
        for item in self.items_by_id.values():
            item.update()

    # ------------------------------------------------------------------ fin de arrastre
    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        deltas = {}
        for wid, item in self.items_by_id.items():
            d = item.pos() - item.expected_pos()
            if abs(d.x()) >= 0.5 or abs(d.y()) >= 0.5:
                deltas[wid] = (round(d.x()), round(d.y()))
        if deltas:
            self.vm.move_by(deltas)

    # ------------------------------------------------------------------ fondo y capa superior
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, OUTSIDE_COLOR)
        sr = self.screen_rect()
        screen = self.vm.current_screen
        if screen is not None and screen.id == TOP_LAYER_ID:
            bg = QColor("#3A3A40")
            painter.fillRect(sr, bg)
        else:
            bg = render.page_background(self.vm.project, screen, self.render_ctx)
            painter.fillRect(sr, bg)
        scale = self.view_scale()
        g = self.vm.grid_size
        if self.show_grid and g > 1 and g * scale >= 6:
            line = QColor(0, 0, 0, 28) if bg.lightness() > 128 else QColor(255, 255, 255, 22)
            painter.setPen(QPen(line, 0))
            visible = rect.intersected(sr)
            x = int(visible.left() // g) * g
            while x <= visible.right():
                if x >= sr.left():
                    painter.drawLine(QPointF(x, visible.top()), QPointF(x, visible.bottom()))
                x += g
            y = int(visible.top() // g) * g
            while y <= visible.bottom():
                if y >= sr.top():
                    painter.drawLine(QPointF(visible.left(), y), QPointF(visible.right(), y))
                y += g

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        tl = self.vm.project.top_layer
        screen = self.vm.current_screen
        if self.show_top_layer and tl is not None and screen is not None and screen.id != TOP_LAYER_ID:
            painter.save()
            painter.setClipRect(self.screen_rect())
            painter.setOpacity(0.85)
            render.paint_tree(painter, tl.widgets, self.vm.layout(TOP_LAYER_ID), self.render_ctx)
            painter.restore()
        painter.setPen(QPen(QColor("#5C5C66"), 0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.screen_rect())
        if self.comment_counts and screen is not None:
            self._paint_comment_badges(painter, screen.id)

    def _paint_comment_badges(self, painter: QPainter, screen_id: str) -> None:
        """Un globo amarillo con el nº de comentarios abiertos en cada widget."""
        boxes = self.vm.layout(screen_id)
        scale = self.view_scale() or 1.0
        r = 9 / scale
        painter.save()
        f = painter.font()
        f.setPointSizeF(max(1.0, 7.5 / scale))
        f.setBold(True)
        painter.setFont(f)
        for wid, n in self.comment_counts.items():
            b = boxes.get(wid)
            if b is None or not b.shown:
                continue
            c = QPointF(b.rect.x + b.rect.w, b.rect.y)
            painter.setPen(QPen(QColor("#5D4037"), 1 / scale))
            painter.setBrush(QColor("#FFCA28"))
            painter.drawEllipse(c, r, r)
            painter.setPen(QColor("#212121"))
            painter.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, str(n))
        painter.restore()


class DesignView(QGraphicsView):
    zoom_changed = Signal(float)
    cursor_moved = Signal(int, int)

    MIN_ZOOM, MAX_ZOOM = 0.1, 8.0

    def __init__(self, scene: DesignScene, parent=None):
        super().__init__(scene, parent)
        self.design_scene = scene
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
                            | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setBackgroundBrush(QBrush(OUTSIDE_COLOR))
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._panning = False
        self._pan_last = QPointF()
        self._space = False

    @property
    def vm(self) -> ProjectViewModel:
        return self.design_scene.vm

    # ------------------------------------------------------------------ zoom
    def zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, z: float) -> None:
        z = max(self.MIN_ZOOM, min(self.MAX_ZOOM, z))
        factor = z / self.zoom()
        self.scale(factor, factor)
        self.design_scene.on_zoom_changed()
        self.zoom_changed.emit(self.zoom())
        self.viewport().update()

    def zoom_by(self, factor: float) -> None:
        self.set_zoom(self.zoom() * factor)

    def fit_screen(self) -> None:
        r = self.design_scene.screen_rect().adjusted(-30, -30, 30, 30)
        self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
        self.design_scene.on_zoom_changed()
        self.zoom_changed.emit(self.zoom())

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.zoom_by(factor)
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------ desplazamiento
    def _start_pan(self, pos: QPointF) -> None:
        self._panning = True
        self._pan_last = pos
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
                event.button() == Qt.MouseButton.LeftButton and self._space):
            self._start_pan(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return
        p = self.mapToScene(event.position().toPoint())
        self.cursor_moved.emit(int(p.x()), int(p.y()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning:
            self._panning = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if self._space
                                      else Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ teclado
    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if key in moves and self.vm.selection:
            self.vm.nudge(*moves[key])
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.vm.set_selection([])
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = False
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) \
                and not event.isAutoRepeat():
            self.vm.end_interaction()
        super().keyReleaseEvent(event)

    # ------------------------------------------------------------------ arrastrar desde la paleta
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME_WIDGET):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME_WIDGET):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(MIME_WIDGET):
            event.ignore()
            return
        wtype = bytes(event.mimeData().data(MIME_WIDGET).data()).decode("utf-8")
        p = self.mapToScene(event.position().toPoint())
        event.acceptProposedAction()
        parent = self.vm.container_at(p.x(), p.y())
        self.vm.add_widget(wtype, p.x(), p.y(), parent_id=parent)
        self.setFocus()
