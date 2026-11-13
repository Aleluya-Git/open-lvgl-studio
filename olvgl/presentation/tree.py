"""Árbol del proyecto: pantallas, capa superior y widgets anidados."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QInputDialog, QMessageBox,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from olvgl.i18n import tr, trf
from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain import catalog
from olvgl.domain.model import TOP_LAYER_ID, Widget
from olvgl.presentation.fonts import ui_font
from olvgl.presentation.icons import action_icon, widget_icon

ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_ID = Qt.ItemDataRole.UserRole + 1


def widget_text(w: Widget) -> str:
    label = tr(catalog.type_label(w.type))
    if w.type in catalog.PSEUDO_TYPES and isinstance(w.props.get("name"), str):
        label = f"{label} «{w.props['name']}»"
    text = f"{label} · {w.id}" if not w.auto_id else f"{label} " + tr("(sin id)")
    if w.type in ("label", "button") and isinstance(w.props.get("text"), str):
        t = w.props["text"].replace("\n", " ")
        text += f"  “{t[:18]}{'…' if len(t) > 18 else ''}”"
    if w.props.get("hidden") is True:
        text += tr("  (oculto)")
    return text


class ProjectTree(QWidget):
    def __init__(self, vm: ProjectViewModel, parent=None):
        super().__init__(parent)
        self.vm = vm
        self._updating = False
        self._items: dict[str, QTreeWidgetItem] = {}

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        self.btn_add = self._tool("+", tr("Nueva pantalla"), self._add_screen, "add_page")
        self.btn_del = self._tool("-", tr("Eliminar pantalla"), self._remove_screen, "remove_page")
        self.btn_up = self._tool("↑", tr("Subir pantalla"), lambda: self._move(-1), "move_up")
        self.btn_down = self._tool("↓", tr("Bajar pantalla"), lambda: self._move(1), "move_down")
        self.btn_top = self._tool(tr("Capa sup."), tr("Mostrar o crear la capa superior (top_layer): "
                                  "widgets visibles en todas las páginas"), self.vm.ensure_top_layer, "layers")
        self.btn_top.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for b in (self.btn_add, self.btn_del, self.btn_up, self.btn_down, self.btn_top):
            bar.addWidget(b)
        bar.addStretch(1)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(bar)
        lay.addWidget(self.tree)

        self._rebuild_pending = False
        vm.project_changed.connect(self._on_project_changed)
        vm.screen_changed.connect(lambda _id: self.schedule_rebuild())
        vm.selection_changed.connect(lambda _ids: self._apply_selection())
        self.rebuild()

    def _tool(self, text: str, tip: str, slot, icon: str = "") -> QToolButton:
        b = QToolButton()
        b.setText(text)
        if icon:
            b.setIcon(action_icon(icon))
        b.setToolTip(tip)
        b.clicked.connect(lambda _c=False: slot())
        return b

    # ------------------------------------------------------------------ construcción
    def _on_project_changed(self) -> None:
        # mover o redimensionar no cambia el árbol: no se reconstruye (miles de items)
        if getattr(self.vm, "last_change", None) is not None and self.vm.last_change.kind == "geometry":
            return
        self.schedule_rebuild()

    def schedule_rebuild(self) -> None:
        # Diferido: nunca se reconstruye el árbol dentro de una señal del propio árbol
        if not self._rebuild_pending:
            self._rebuild_pending = True
            QTimer.singleShot(0, self.rebuild)

    def _add_widgets(self, parent: QTreeWidgetItem, widgets: list[Widget], natural_order: bool = False) -> None:
        # En la pila el último se dibuja encima: se lista primero (como Figma),
        # salvo las pestañas, que se muestran en su orden.
        for w in (widgets if natural_order else reversed(widgets)):
            child = QTreeWidgetItem([widget_text(w)])
            icon = widget_icon(w.type)
            if icon is not None:
                child.setIcon(0, icon)
            child.setData(0, ROLE_KIND, "widget")
            child.setData(0, ROLE_ID, w.id)
            if w.auto_id:
                child.setForeground(0, QColor("#9E9E9E"))
            parent.addChild(child)
            self._items[w.id] = child
            if w.children:
                self._add_widgets(child, w.children, natural_order=w.type in catalog.CHILD_LISTS)

    def rebuild(self) -> None:
        self._rebuild_pending = False
        self._updating = True
        self._items = {}
        try:
            self.tree.clear()
            for s in self.vm.project.all_screens():
                title = s.name if s.id == TOP_LAYER_ID else f"{s.name}  ({s.id})"
                top = QTreeWidgetItem([title])
                top.setIcon(0, action_icon("layers" if s.id == TOP_LAYER_ID else "page"))
                top.setData(0, ROLE_KIND, "screen")
                top.setData(0, ROLE_ID, s.id)
                if s.id == self.vm.current_screen_id:
                    top.setFont(0, ui_font(bold=True))
                self.tree.addTopLevelItem(top)
                self._add_widgets(top, s.widgets)
                top.setExpanded(s.id == self.vm.current_screen_id)
        finally:
            self._updating = False
        self._apply_selection()
        self.btn_del.setEnabled(len(self.vm.project.screens) > 1
                                or self.vm.current_screen_id == TOP_LAYER_ID)

    def _apply_selection(self) -> None:
        self._updating = True
        try:
            self.tree.clearSelection()
            for wid in self.vm.selection:
                item = self._items.get(wid)
                if item is None:
                    continue
                item.setSelected(True)
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.tree.scrollToItem(item)
        finally:
            self._updating = False

    # ------------------------------------------------------------------ eventos
    def _on_tree_selection(self) -> None:
        if self._updating:
            return
        items = self.tree.selectedItems()
        widgets = [i.data(0, ROLE_ID) for i in items if i.data(0, ROLE_KIND) == "widget"]
        screens = [i.data(0, ROLE_ID) for i in items if i.data(0, ROLE_KIND) == "screen"]
        if widgets:
            self.vm.set_selection(widgets)
        elif screens:
            self.vm.set_current_screen(screens[0])
            self.vm.set_selection([])

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.data(0, ROLE_KIND) == "screen" and item.data(0, ROLE_ID) != TOP_LAYER_ID:
            self._rename_screen(item.data(0, ROLE_ID))

    def _rename_screen(self, screen_id: str) -> None:
        s = self.vm.project.screen(screen_id)
        if s is None:
            return
        name, ok = QInputDialog.getText(self, tr("Renombrar pantalla"), tr("Nombre:"), text=s.name)
        if ok and name.strip():
            self.vm.update_screen(screen_id, name=name.strip())

    def _add_screen(self) -> None:
        name, ok = QInputDialog.getText(self, tr("Nueva pantalla"), tr("Nombre de la pantalla:"),
                                        text=trf("Pantalla {n}", n=len(self.vm.project.screens) + 1))
        if ok and name.strip():
            self.vm.add_screen(name.strip())

    def _remove_screen(self) -> None:
        s = self.vm.current_screen
        if s is None:
            return
        n = sum(1 for _ in s.walk())
        what = tr("la capa superior") if s.id == TOP_LAYER_ID else f"la pantalla «{s.name}»"
        if QMessageBox.question(self, tr("Eliminar"), trf("¿Eliminar {what} y sus {n} widgets?", what=what, n=n)
                                ) == QMessageBox.StandardButton.Yes:
            self.vm.remove_screen(s.id)

    def _move(self, delta: int) -> None:
        self.vm.move_screen(self.vm.current_screen_id, delta)
