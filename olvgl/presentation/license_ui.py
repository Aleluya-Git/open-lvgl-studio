"""Ayuda › Licencia: edición, licencia instalada, funciones y licencias de terceros."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QLabel, QPlainTextEdit, QPushButton,
                               QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from olvgl.application import licensing as lc
from olvgl.i18n import tr, trf
from olvgl.presentation.fonts import mono_font

THIRD_PARTY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "THIRD_PARTY.md")


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Licencia"))
        self.resize(720, 520)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.features = QTreeWidget()
        self.features.setHeaderLabels([tr("Función"), tr("Edición"), tr("Disponible")])
        self.features.setRootIsDecorated(False)
        b_load = QPushButton(tr("Cargar licencia…"))
        b_load.clicked.connect(lambda: self.load())
        b_remove = QPushButton(tr("Quitar licencia"))
        b_remove.clicked.connect(lambda: self.remove())
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.addWidget(self.summary)
        pl.addWidget(self.features, 1)
        pl.addWidget(b_load)
        pl.addWidget(b_remove)
        third = QPlainTextEdit()
        third.setReadOnly(True)
        third.setFont(mono_font(9))
        try:
            with open(THIRD_PARTY, encoding="utf-8") as f:
                third.setPlainText(f.read())
        except OSError:
            third.setPlainText("")
        self.tabs = QTabWidget()
        self.tabs.addTab(page, tr("Tu licencia"))
        self.tabs.addTab(third, tr("Licencias de terceros"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        st = lc.current()
        lines = [f"<b>{trf('Edición {name}', name=st.name)}</b>"]
        if st.license:
            lic = st.license
            lines.append(f"{tr('Licenciatario')}: {lic.licensee}" + (f" &lt;{lic.email}&gt;" if lic.email else ""))
            lines.append(f"{tr('Puestos')}: {lic.seats} · {tr('Emitida')}: {lic.issued} · "
                         f"{tr('Caduca')}: {lic.expires or tr('nunca')}")
        color = {"valid": "#66BB6A", "expired": "#FFB74D", "invalid": "#EF5350"}.get(st.state, "#9E9E9E")
        lines.append(f"<span style='color:{color}'>{tr(st.message)}</span>")
        if not lc.ENFORCE:
            lines.append("<span style='color:#9E9E9E'>" + tr("El sistema de licencias está desactivado: todas las "
                                                            "funciones están disponibles.") + "</span>")
        self.summary.setText("<br>".join(lines))
        self.features.clear()
        for f, need in lc.FEATURES.items():
            ok = lc.has(f, st)
            self.features.addTopLevelItem(QTreeWidgetItem([tr(lc.FEATURE_NAMES.get(f, f)), lc.EDITION_NAMES[need],
                                                           "✓" if ok else "—"]))
        self.features.resizeColumnToContents(0)
        self.status = st

    def load(self, path: str | None = None) -> bool:
        if path is None:
            path, _f = QFileDialog.getOpenFileName(self, tr("Cargar licencia"), os.path.expanduser("~"),
                                                   tr("Licencias (*.olvgl-lic)"))
            if not path:
                return False
        try:
            lc.install(path)
        except (lc.LicenseError, OSError) as exc:
            self.refresh()
            self.summary.setText(self.summary.text() + f"<br><span style='color:#EF5350'>{exc}</span>")
            return False
        self.refresh()
        return True

    def remove(self) -> None:
        lc.remove()
        self.refresh()
