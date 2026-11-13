"""Vista del YAML ESPHome generado en vivo."""
from __future__ import annotations

import re

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from olvgl.i18n import tr, trf
from olvgl.application.viewmodel import ProjectViewModel


def changed_span(old: str, new: str) -> tuple[int, int, int]:
    """(inicio, fin en old, fin en new) del trozo que cambia, en caracteres."""
    n = min(len(old), len(new))
    start = 0
    step = 4096
    while start < n:                                   # prefijo común por bloques
        k = min(step, n - start)
        if old[start:start + k] == new[start:start + k]:
            start += k
        elif k > 1:
            step = max(1, k // 2)
        else:
            break
    end = 0
    limit = n - start
    step = 4096
    while end < limit:                                 # sufijo común por bloques
        k = min(step, limit - end)
        if old[len(old) - end - k:len(old) - end] == new[len(new) - end - k:len(new) - end]:
            end += k
        elif k > 1:
            step = max(1, k // 2)
        else:
            break
    return start, len(old) - end, len(new) - end


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    f.setFontItalic(italic)
    return f


class YamlHighlighter(QSyntaxHighlighter):
    RULES = [
        (re.compile(r"^\s*(- )?([A-Za-z_][\w.]*)(?=:)"), _fmt("#82AAFF", bold=True), 2),
        (re.compile(r"0x[0-9A-Fa-f]{6}"), _fmt("#F78C6C"), 0),
        (re.compile(r"(?<=: )-?\d+\b"), _fmt("#F78C6C"), 0),
        (re.compile(r"\b(true|false)\b"), _fmt("#C792EA"), 0),
        (re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), _fmt("#C3E88D"), 0),
        (re.compile(r"!\w+"), _fmt("#FFCB6B"), 0),
        (re.compile(r"#.*$"), _fmt("#697098", italic=True), 0),
    ]

    def highlightBlock(self, text: str) -> None:
        for rx, fmt, group in self.RULES:
            for m in rx.finditer(text):
                start, end = m.span(group)
                if start >= 0:
                    self.setFormat(start, end - start, fmt)


class CodeView(QWidget):
    export_requested = Signal()

    def __init__(self, vm: ProjectViewModel, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setUndoRedoEnabled(False)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        from olvgl.presentation.fonts import mono_font
        font = mono_font()
        font.setPointSize(10)
        self.editor.setFont(font)
        self.editor.setStyleSheet("QPlainTextEdit { background: #1E1E24; color: #E0E0E0; }")
        self.highlighter = YamlHighlighter(self.editor.document())

        self.status = QLabel()
        copy_btn = QPushButton(tr("Copiar"))
        copy_btn.clicked.connect(self.copy_all)
        export_btn = QPushButton(tr("Exportar ESPHome…"))
        export_btn.clicked.connect(self.export_requested.emit)
        bar = QHBoxLayout()
        bar.addWidget(self.status, 1)
        bar.addWidget(copy_btn)
        bar.addWidget(export_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(bar)
        lay.addWidget(self.editor)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)
        vm.project_changed.connect(self._timer.start)
        self.refresh()

    def text(self) -> str:
        return self.editor.toPlainText()

    def refresh(self) -> None:
        try:
            text = self.vm.generate_yaml()
        except Exception as exc:  # el generador nunca debe tumbar la UI
            text = f"# Error al generar: {exc}\n"
        old = self.editor.toPlainText()
        if text != old:
            vbar = self.editor.verticalScrollBar()
            hbar = self.editor.horizontalScrollBar()
            v, h = vbar.value(), hbar.value()
            start, end_old, end_new = changed_span(old, text)
            if not old or end_old - start > len(old) * 0.6:
                self.editor.setPlainText(text)
            else:
                # sólo se sustituye el trozo que cambia: el resaltado y el
                # desplazamiento del resto del fichero (miles de líneas) no se rehacen
                cur = QTextCursor(self.editor.document())
                cur.setPosition(start)
                cur.setPosition(end_old, QTextCursor.MoveMode.KeepAnchor)
                cur.insertText(text[start:end_new])
            vbar.setValue(v)
            hbar.setValue(h)
        problems = self.vm.validate()
        lines = text.count("\n")
        if problems:
            self.status.setText(trf("⚠ {n} aviso(s) · {lines} líneas", n=len(problems), lines=lines))
            self.status.setToolTip("\n".join(problems))
            self.status.setStyleSheet("color: #FFB74D;")
        else:
            self.status.setText(trf("✓ YAML válido · {lines} líneas", lines=lines))
            self.status.setToolTip("")
            self.status.setStyleSheet("color: #81C784;")

    def copy_all(self) -> None:
        QApplication.clipboard().setText(self.text())
