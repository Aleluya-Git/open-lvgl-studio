"""Interfaz de los plugins: gestor y resultado de las comprobaciones."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from olvgl.application import plugins as pl
from olvgl.domain.extensions import Issue
from olvgl.i18n import tr, trf


class PluginsDialog(QDialog):
    """Lista de plugins: activar/desactivar, recargar, abrir carpeta y crear uno nuevo."""

    def __init__(self, manager: pl.PluginManager, settings, on_reload, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.settings = settings
        self.on_reload = on_reload
        self.setWindowTitle(tr("Plugins"))
        self.resize(820, 440)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Plugin"), tr("Versión"), tr("Origen"), tr("Estado"), tr("Aporta")])
        self.tree.setRootIsDecorated(False)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.currentItemChanged.connect(lambda *_: self._show_details())
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        btn_reload = QPushButton(tr("Recargar"))
        btn_reload.clicked.connect(self.reload)
        btn_folder = QPushButton(tr("Abrir carpeta de plugins"))
        btn_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(pl.user_plugins_dir())))
        btn_new = QPushButton(tr("Nuevo plugin…"))
        btn_new.clicked.connect(self.new_plugin)
        bar = QHBoxLayout()
        for b in (btn_reload, btn_folder, btn_new):
            bar.addWidget(b)
        bar.addStretch(1)
        note = QLabel(tr("Los plugins son código Python con los mismos permisos que la aplicación: "
                         "instala sólo los de quien te fíes. SDK: docs/10_plugins.md"))
        note.setWordWrap(True)
        note.setStyleSheet("color: #9E9E9E;")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.details)
        lay.addLayout(bar)
        lay.addWidget(note)
        lay.addWidget(buttons)
        self.fill()

    def disabled(self) -> set[str]:
        return set(self.settings.get("plugins_disabled", []) or [])

    def fill(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        for info in sorted(self.manager.plugins.values(), key=lambda i: i.name.lower()):
            if info.error:
                state = tr("Error")
            elif info.loaded:
                state = tr("Cargado")
            else:
                state = tr("Desactivado")
            it = QTreeWidgetItem([info.name, info.version, tr(info.source.capitalize()) if info.source else "",
                                  state, ", ".join(info.provides)])
            it.setData(0, Qt.ItemDataRole.UserRole, info.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked if info.enabled else Qt.CheckState.Unchecked)
            if info.error:
                it.setForeground(3, QColor("#EF5350"))
            self.tree.addTopLevelItem(it)
        for c in range(5):
            self.tree.resizeColumnToContents(c)
        self.tree.blockSignals(False)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self._show_details()

    def _show_details(self) -> None:
        it = self.tree.currentItem()
        info = self.manager.plugins.get(it.data(0, Qt.ItemDataRole.UserRole)) if it else None
        if info is None:
            self.details.setText("")
            return
        text = f"<b>{info.name}</b> ({info.id}) — {info.description}<br>"
        if info.author:
            text += trf("Autor: {a}", a=info.author) + "<br>"
        text += f"<span style='color:#9E9E9E'>{info.path}</span>"
        if info.error:
            text += f"<br><span style='color:#EF5350'>{info.error}</span>"
        self.details.setText(text)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        pid = item.data(0, Qt.ItemDataRole.UserRole)
        disabled = self.disabled()
        if item.checkState(0) == Qt.CheckState.Checked:
            disabled.discard(pid)
        else:
            disabled.add(pid)
        self.settings.set("plugins_disabled", sorted(disabled))
        self.reload()

    def reload(self) -> None:
        self.manager.load_all(self.disabled())
        self.on_reload()
        self.fill()

    def new_plugin(self) -> None:
        pid, ok = QInputDialog.getText(self, tr("Nuevo plugin"),
                                       tr("Id del plugin (minúsculas, números y _):"), text="mi_plugin")
        if not ok or not pid.strip():
            return
        try:
            path = pl.create_plugin(pl.user_plugins_dir(), pid.strip())
        except Exception as exc:
            QMessageBox.warning(self, tr("Nuevo plugin"), str(exc))
            return
        self.reload()
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class IssuesDialog(QDialog):
    """Resultado de los validadores: doble clic lleva al widget."""

    def __init__(self, issues: list[Issue], select, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Comprobación del proyecto"))
        self.resize(760, 420)
        self.select = select
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Tipo"), tr("Mensaje"), tr("Widget"), tr("Plugin")])
        self.tree.setRootIsDecorated(False)
        colors = {"error": "#EF5350", "warning": "#FFB74D", "info": "#64B5F6"}
        names = {"error": tr("Error"), "warning": tr("Aviso"), "info": tr("Información")}
        for it in issues:
            row = QTreeWidgetItem([names.get(it.severity, it.severity), it.message, it.widget_id or "", it.plugin])
            row.setForeground(0, QColor(colors.get(it.severity, "#BDBDBD")))
            row.setData(0, Qt.ItemDataRole.UserRole, (it.widget_id, it.page_id))
            self.tree.addTopLevelItem(row)
        self.tree.itemDoubleClicked.connect(self._go)
        for c in (0, 2, 3):
            self.tree.resizeColumnToContents(c)
        summary = QLabel(trf("{n} resultado(s). Doble clic para ir al widget.", n=len(issues)) if issues
                         else tr("✓ Ninguna regla de los plugins encuentra problemas."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(summary)
        lay.addWidget(self.tree, 1)
        lay.addWidget(buttons)

    def _go(self, item: QTreeWidgetItem, _col: int) -> None:
        wid, page = item.data(0, Qt.ItemDataRole.UserRole)
        if wid:
            self.select(wid, page)


def open_folder(path: str) -> None:
    if os.path.isdir(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
