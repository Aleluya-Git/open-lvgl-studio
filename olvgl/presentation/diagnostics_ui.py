"""Diálogos de la beta: informe de diagnóstico y aviso de error inesperado."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from olvgl.application import diagnostics
from olvgl.i18n import tr, trf
from olvgl.presentation.fonts import mono_font


def open_folder(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class DiagnosticDialog(QDialog):
    """Ayuda › Informe de diagnóstico: texto para copiar o guardar y adjuntar a un aviso de error."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Informe de diagnóstico"))
        self.resize(760, 560)
        note = QLabel(tr("Adjunta este informe cuando avises de un problema. No incluye claves, "
                         "contraseñas ni el contenido de tus ficheros."))
        note.setWordWrap(True)
        self.text = QPlainTextEdit(text)
        self.text.setReadOnly(True)
        self.text.setFont(mono_font(9))
        b_copy = QPushButton(tr("Copiar"))
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        b_save = QPushButton(tr("Guardar…"))
        b_save.clicked.connect(self.save)
        b_logs = QPushButton(tr("Abrir carpeta de registros"))
        b_logs.clicked.connect(lambda: open_folder(diagnostics.logs_dir()))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        for b in (b_copy, b_save, b_logs):
            buttons.addButton(b, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addWidget(self.text, 1)
        lay.addWidget(buttons)

    def save(self, path: str | None = None) -> str | None:
        if path is None:
            path, _f = QFileDialog.getSaveFileName(self, tr("Guardar informe"),
                                                   os.path.join(os.path.expanduser("~"), "olvgl_diagnostico.txt"),
                                                   "*.txt")
            if not path:
                return None
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.text.toPlainText())
        return path


class ErrorDialog(QDialog):
    """Error inesperado: el programa sigue; se ofrece el informe guardado."""

    def __init__(self, report_path: str, summary: str, parent=None):
        super().__init__(parent)
        self.report_path = report_path
        self.setWindowTitle(tr("Error inesperado"))
        self.resize(620, 260)
        msg = QLabel("<p><b>" + tr("Algo ha fallado, pero puedes seguir trabajando.") + "</b></p><p>"
                     + tr("Tu proyecto se ha autoguardado. Guárdalo con otro nombre si algo no se ve bien.")
                     + "</p><p>" + trf("Informe guardado en: {path}", path=report_path) + "</p>")
        msg.setWordWrap(True)
        detail = QPlainTextEdit(summary)
        detail.setReadOnly(True)
        detail.setFont(mono_font(9))
        detail.setMaximumHeight(80)
        b_copy = QPushButton(tr("Copiar informe"))
        b_copy.clicked.connect(self.copy)
        b_logs = QPushButton(tr("Abrir carpeta de registros"))
        b_logs.clicked.connect(lambda: open_folder(os.path.dirname(report_path)))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.addButton(b_copy, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(b_logs, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(msg)
        lay.addWidget(detail)
        lay.addWidget(buttons)

    def copy(self) -> None:
        try:
            with open(self.report_path, encoding="utf-8") as f:
                QApplication.clipboard().setText(f.read())
        except OSError:
            pass


class ErrorBridge(QObject):
    """Pasa los errores (de cualquier hilo) al hilo de la interfaz."""
    error = Signal(str, str)
