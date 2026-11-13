"""Paleta de widgets: arrastrar al canvas o doble clic para añadir."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QDrag, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from olvgl.application.viewmodel import ProjectViewModel
from olvgl.i18n import tr
from olvgl.domain import catalog
from olvgl.domain.model import Widget
from olvgl.presentation import render
from olvgl.presentation.canvas import MIME_WIDGET
from olvgl.presentation.fonts import ui_font
from olvgl.presentation.icons import widget_icon


def widget_preview_icon(widget_type: str, size: int = 40) -> QIcon:
    from olvgl.domain.layout import effective_props
    from olvgl.domain.model import Project
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ECEFF1"))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 6, 6)
    project = Project()
    ctx = render.RenderContext(project)
    if widget_type == "button":
        w = Widget("x", "button", props={"text": "OK", "radius": 6, "text_font": "montserrat_10",
                                         "pad_all": 0})
        rect = QRectF(5, 12, size - 10, size - 24)
    elif widget_type == "label":
        w = Widget("x", "label", props={"text": "Aa", "text_font": "montserrat_20", "text_align": "CENTER"})
        rect = QRectF(2, 8, size - 4, size - 10)
    else:
        w = Widget("x", widget_type)
        rect = QRectF(6, 6, size - 12, size - 12)
    render.paint_widget(p, w, rect, effective_props(project, w), ctx)
    p.end()
    return QIcon(pm)


class WidgetPalette(QListWidget):
    def __init__(self, vm: ProjectViewModel, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setIconSize(QSize(40, 40))
        self.setSpacing(2)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rebuild()
        self.itemDoubleClicked.connect(self._add_centered)

    def rebuild(self) -> None:
        """Vuelve a llenar la paleta (al cargar o quitar plugins)."""
        self.clear()
        specs = catalog.palette_specs()
        for cat in catalog.CATEGORIES:
            group = [sp for sp in specs if sp.category == cat]
            if not group:
                continue
            head = QListWidgetItem(tr(cat).upper())
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            head.setFont(ui_font(bold=True, point_size=8.5))
            head.setForeground(QColor("#607D8B"))
            self.addItem(head)
            for sp in group:
                icon = widget_icon(sp.type) or widget_preview_icon(sp.type)
                item = QListWidgetItem(icon, f"{tr(sp.label)}\n{tr(sp.description)}")
                item.setData(Qt.ItemDataRole.UserRole, sp.type)
                item.setToolTip(f"{tr(sp.label)} ({sp.type}) — " + tr("arrastra al canvas o haz doble clic"))
                self.addItem(item)

    def types(self) -> list[str]:
        return [t for i in range(self.count()) if (t := self.item(i).data(Qt.ItemDataRole.UserRole))]

    def _add_centered(self, item: QListWidgetItem) -> None:
        t = item.data(Qt.ItemDataRole.UserRole)
        if t:
            self.vm.add_widget(t)

    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if item is None or not item.data(Qt.ItemDataRole.UserRole):
            return
        mime = QMimeData()
        mime.setData(MIME_WIDGET, item.data(Qt.ItemDataRole.UserRole).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(item.icon().pixmap(40, 40))
        drag.exec(Qt.DropAction.CopyAction)
