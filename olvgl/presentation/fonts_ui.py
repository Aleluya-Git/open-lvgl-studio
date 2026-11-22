"""Diseño › Fuentes: añadir fuentes (biblioteca, GitHub/URL, fichero, Google Fonts), editarlas,
quitarlas y elegir iconos de Material Design Icons."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout)

from olvgl.domain import fonts as F
from olvgl.i18n import tr, trf

SOURCES = ("library", "url", "file", "gfonts")
SOURCE_TITLES = {"library": "Añadir fuente de la biblioteca", "url": "Añadir fuente desde GitHub o una URL",
                 "file": "Añadir fuente desde un fichero", "gfonts": "Añadir fuente de Google Fonts",
                 "edit": "Editar fuente"}
SAMPLE = "Aa Bb Ññ 0123 ¿?¡! °C 24,5 %"


def preview_font(file, project_path_resolver=None, size: int = 22, weight: int = 400) -> QFont:
    """QFont para la vista previa: fichero de la biblioteca, en caché o local."""
    from olvgl.infrastructure import font_cache
    from olvgl.presentation import render
    from olvgl.presentation.fonts import pick_family
    path = font_cache.bundled_path(file) or font_cache.cached_path(file)
    if path is None and isinstance(file, str) and "://" not in file:
        path = project_path_resolver(file) if project_path_resolver else file
    fams = render._font_families_for_file(path) if path else []
    f = QFont()
    f.setFamily(pick_family(fams + render.FONT_FAMILIES))
    f.setPixelSize(max(8, min(int(size), 64)))
    if weight >= 650:
        f.setBold(True)
    return f


def mdi_family() -> str:
    from olvgl.infrastructure import font_cache
    from olvgl.presentation import render
    fams = render._font_families_for_file(font_cache.bundled_path({"type": "web", "url": F.MDI_URL}) or "")
    return fams[0] if fams else ""


class FontEditDialog(QDialog):
    """Una fuente: de dónde sale, tamaño, bpp, id y caracteres."""

    def __init__(self, vm, source: str = "library", font_id: str | None = None, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.source = source
        self.editing = font_id
        self.result_id: str | None = None
        self.result_data: dict | None = None
        self._id_touched = False
        self.setWindowTitle(tr(SOURCE_TITLES[source]))
        form = QFormLayout()
        # ---- origen
        self.family = QComboBox()
        for fam in F.LIBRARY:
            self.family.addItem(f"{fam.label} ({fam.license})", fam.key)
        self.weight = QComboBox()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://github.com/usuario/repo/blob/main/fonts/MiFuente.ttf")
        self.check_btn = QPushButton(tr("Comprobar"))
        self.check_btn.clicked.connect(lambda: self.check_url())
        self.path = QLineEdit()
        self.browse = QPushButton(tr("Elegir…"))
        self.browse.clicked.connect(lambda: self.pick_file())
        self.gfamily = QLineEdit()
        self.gfamily.setPlaceholderText(tr("p. ej. Open Sans, Inter, Lato"))
        self.italic = QCheckBox(tr("Cursiva"))
        if source == "library":
            form.addRow(tr("Familia"), self.family)
            form.addRow(tr("Grosor"), self.weight)
            self.family.currentIndexChanged.connect(lambda _i: self._on_family())
        elif source == "url":
            row = QHBoxLayout()
            row.addWidget(self.url, 1)
            row.addWidget(self.check_btn)
            form.addRow(tr("Enlace"), row)
            hint = QLabel(tr("Enlace de GitHub al fichero .ttf/.otf (el de la página del fichero o el «Raw») o "
                             "cualquier URL directa. ESPHome lo descarga al compilar."))
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#9E9E9E")
            form.addRow("", hint)
        elif source == "file":
            row = QHBoxLayout()
            row.addWidget(self.path, 1)
            row.addWidget(self.browse)
            form.addRow(tr("Fichero"), row)
        elif source == "gfonts":
            form.addRow(tr("Familia"), self.gfamily)
            form.addRow(tr("Grosor"), self.weight)
            form.addRow("", self.italic)
        if source in ("gfonts", "edit"):
            for w in (100, 200, 300, 400, 500, 600, 700, 800, 900):
                self.weight.addItem(f"{w} {F.WEIGHT_NAMES[w]}", w)
            self.weight.setCurrentIndex(self.weight.findData(400))
        if source == "edit":
            self.origin = QLabel()
            self.origin.setWordWrap(True)
            form.addRow(tr("Origen"), self.origin)
        # ---- comunes
        self.size = QSpinBox()
        self.size.setRange(6, 200)
        self.size.setValue(20)
        self.size.setSuffix(" px")
        self.bpp = QComboBox()
        self.bpp.addItem(tr("(por defecto)"), None)
        for b in F.BPP_OPTIONS:
            self.bpp.addItem(trf("{n} bits por píxel", n=b), b)
        self.bpp.setToolTip(tr("Más bits = bordes más suaves y más memoria. Los iconos suelen ir con 4."))
        self.ident = QLineEdit()
        self.ident.textEdited.connect(lambda _t: setattr(self, "_id_touched", True))
        self.glyphs = QPlainTextEdit()
        self.glyphs.setMaximumHeight(70)
        self.glyphs.setPlaceholderText(tr("Vacío: los caracteres por defecto de ESPHome. Escribe aquí los que "
                                          "quieras incluir (p. ej. áéíóúñÑ°€)."))
        self.glyph_note = QLabel()
        self.glyph_note.setWordWrap(True)
        self.glyph_note.setStyleSheet("color:#9E9E9E")
        form.addRow(tr("Tamaño"), self.size)
        form.addRow(tr("Calidad"), self.bpp)
        form.addRow(tr("Id"), self.ident)
        form.addRow(tr("Caracteres"), self.glyphs)
        form.addRow("", self.glyph_note)
        self.preview = QLabel()
        self.preview.setMinimumHeight(70)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#1E1E22;color:#ECEFF1;border-radius:6px;padding:6px")
        self.status = QLabel()
        self.status.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_result)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.preview)
        lay.addWidget(self.status)
        lay.addWidget(buttons)
        self.resize(560, 420)
        for sig in (self.size.valueChanged, self.weight.currentIndexChanged):
            sig.connect(lambda *_: self.update_auto())
        for sig in (self.url.textChanged, self.path.textChanged, self.gfamily.textChanged):
            sig.connect(lambda *_: self.update_auto())
        if source == "library":
            self._on_family()
        if source == "edit":
            self._load(font_id)
        self.update_auto()

    # ------------------------------------------------ datos
    def _on_family(self) -> None:
        fam = F.LIBRARY_BY_KEY.get(self.family.currentData(), F.LIBRARY[0])
        self.weight.blockSignals(True)
        self.weight.clear()
        for w in fam.weights:
            self.weight.addItem(f"{w} {F.WEIGHT_NAMES[w]}", w)
        self.weight.setCurrentIndex(max(0, self.weight.findData(400)))
        self.weight.setEnabled(len(fam.weights) > 1)
        self.weight.blockSignals(False)
        self.size.setValue(32 if fam.icons else 20)
        self.bpp.setCurrentIndex(self.bpp.findData(4) if fam.icons else 0)
        self.update_auto()

    def _load(self, font_id: str) -> None:
        f = self.vm.project.font(font_id)
        data = dict(f.data) if f else {}
        self.base_data = data
        self.origin.setText(F.describe(font_id, data))
        self.size.setValue(int(data.get("size", 20)) if str(data.get("size", 20)).isdigit() else 20)
        self.bpp.setCurrentIndex(max(0, self.bpp.findData(data.get("bpp"))))
        self.ident.setText(font_id)
        self.ident.setReadOnly(True)
        self._id_touched = True
        g = data.get("glyphs")
        self.glyphs.setPlainText("".join(F.glyph_list(g)) if g else "")

    def data(self) -> dict:
        """Los datos de `font:` según lo elegido (puede lanzar FontSourceError)."""
        size = self.size.value()
        if self.source == "library":
            fam = F.LIBRARY_BY_KEY.get(self.family.currentData(), F.LIBRARY[0])
            data = F.library_font(F.library_id(fam.key, size, self.weight.currentData() or 400)) or {}
        elif self.source == "url":
            data = F.font_from_url(self.url.text(), size)
        elif self.source == "file":
            if not self.path.text().strip():
                raise F.FontSourceError(tr("Elige el fichero de la fuente"))
            data = F.font_from_file(self.path.text().strip(), size)
        elif self.source == "gfonts":
            data = F.font_from_gfonts(self.gfamily.text(), self.weight.currentData() or 400, size,
                                      self.italic.isChecked())
        else:
            data = dict(self.base_data, size=size)
        data = dict(data)
        if self.bpp.currentData():
            data["bpp"] = self.bpp.currentData()
        elif self.source != "library":
            data.pop("bpp", None)
        chars = self.glyphs.toPlainText()
        g = F.glyph_list(chars)
        if g:
            data["glyphs"] = g if F.is_icon_font(data) else "".join(g)
        elif "glyphs" in data and not F.is_icon_font(data):
            data.pop("glyphs")
        return data

    def auto_id(self) -> str:
        size = self.size.value()
        taken = set(self.vm.project.all_ids()) | {f.id for f in self.vm.project.fonts}
        if self.source == "library":
            fam = F.LIBRARY_BY_KEY.get(self.family.currentData(), F.LIBRARY[0])
            return F.library_id(fam.key, size, self.weight.currentData() or 400)
        if self.source == "url":
            return F.suggest_id(self.url.text() or "fuente", size, taken)
        if self.source == "file":
            return F.suggest_id(self.path.text() or "fuente", size, taken)
        if self.source == "gfonts":
            w = self.weight.currentData() or 400
            name = (self.gfamily.text() or "fuente") + ("" if w == 400 else f"_{F.WEIGHT_NAMES[w]}")
            return F.suggest_id(name, size, taken)
        return self.editing or ""

    def update_auto(self) -> None:
        if not self._id_touched and self.source != "edit":
            self.ident.setText(self.auto_id())
        try:
            data = self.data()
        except F.FontSourceError:
            data = None
        icon = bool(data) and F.is_icon_font(data)
        self.glyph_note.setText(tr("Fuente de iconos: los iconos que pongas en los textos se añaden solos a "
                                   "«glyphs»; aquí puedes añadir otros (p. ej. los que usas en lambdas).")
                                if icon else "")
        self.update_preview(data)

    def update_preview(self, data: dict | None) -> None:
        if not data:
            self.preview.setText("")
            return
        file = data.get("file")
        from olvgl.infrastructure.font_cache import font_weight
        font = preview_font(file, self.vm.resolve_path, data.get("size", 20), font_weight(file))
        self.preview.setFont(font)
        if F.is_icon_font(data):
            names = ("home", "lightbulb", "thermometer", "water-percent", "fan", "power", "wifi", "cog")
            icons = dict(F.mdi_icons())
            self.preview.setText(" ".join(icons[n] for n in names if n in icons))
        else:
            self.preview.setText(SAMPLE)

    # ------------------------------------------------ acciones
    def pick_file(self, path: str | None = None) -> None:
        if path is None:
            path, _f = QFileDialog.getOpenFileName(self, tr("Elegir fuente"), os.path.expanduser("~"),
                                                   tr("Fuentes (*.ttf *.otf *.woff *.woff2 *.bdf *.pcf)"))
        if path:
            self.path.setText(path)

    def check_url(self) -> bool:
        """Descarga la fuente para comprobarla y verla (con un enlace de GitHub de página, el «Raw»)."""
        from olvgl.infrastructure import font_cache
        try:
            url = F.normalize_url(self.url.text())
        except F.FontSourceError as exc:
            self.status.setText(f"<span style='color:#EF5350'>{tr(str(exc))}</span>")
            return False
        if url != self.url.text().strip():
            self.url.setText(url)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            path, err = font_cache.check_download(url)
        finally:
            QApplication.restoreOverrideCursor()
        if path is None:
            self.status.setText(f"<span style='color:#EF5350'>{tr(err) if err else ''}</span>")
            return "descargar" in err.lower()          # sin red: se puede añadir igualmente
        self.status.setText(f"<span style='color:#66BB6A'>✓ {tr('Fuente descargada y comprobada')}</span>")
        self.update_auto()
        return True

    def accept_result(self) -> None:
        try:
            data = self.data()
        except F.FontSourceError as exc:
            self.status.setText(f"<span style='color:#EF5350'>{tr(str(exc))}</span>")
            return
        fid = self.ident.text().strip()
        if self.source == "url" and not self.check_url():
            return
        from olvgl.domain.model import is_valid_id
        if self.source != "edit":
            if not is_valid_id(fid):
                self.status.setText(f"<span style='color:#EF5350'>{tr('El id no es válido (letras, números y _)')}</span>")
                return
            if self.vm.project.font(fid) is not None or fid in self.vm.project.all_ids() or F.is_builtin(fid):
                self.status.setText(f"<span style='color:#EF5350'>{tr('Ya hay una fuente u objeto con ese id')}</span>")
                return
        self.result_id, self.result_data = fid, data
        self.accept()


class FontsDialog(QDialog):
    """Las fuentes del proyecto."""

    def __init__(self, vm, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.last_added: str | None = None
        self.setWindowTitle(tr("Fuentes del proyecto"))
        self.resize(760, 480)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(lambda _r: self.show_current())
        self.list.itemDoubleClicked.connect(lambda _i: self.edit())
        buttons = QVBoxLayout()
        for source, text in (("library", "＋ Montserrat, Roboto o iconos…"), ("url", "＋ Desde GitHub o una URL…"),
                             ("file", "＋ Desde un fichero…"), ("gfonts", "＋ Google Fonts…")):
            b = QPushButton(tr(text))
            b.clicked.connect(lambda _c=False, s=source: self.add(s))
            buttons.addWidget(b)
        buttons.addSpacing(12)
        self.b_edit = QPushButton(tr("Editar…"))
        self.b_edit.clicked.connect(lambda: self.edit())
        self.b_remove = QPushButton(tr("Eliminar"))
        self.b_remove.clicked.connect(lambda: self.remove())
        buttons.addWidget(self.b_edit)
        buttons.addWidget(self.b_remove)
        buttons.addStretch(1)
        self.preview = QLabel()
        self.preview.setMinimumHeight(64)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#1E1E22;color:#ECEFF1;border-radius:6px;padding:6px")
        info = QLabel(tr("Las fuentes de LVGL (montserrat_8 … montserrat_48) se pueden usar siempre. Roboto y los "
                         "iconos Material Design van con la aplicación: aparecen en todas las listas de fuentes y se "
                         "añaden aquí solas al elegirlas."))
        info.setWordWrap(True)
        info.setStyleSheet("color:#9E9E9E")
        top = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        left.addWidget(self.preview)
        top.addLayout(left, 1)
        top.addLayout(buttons)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top, 1)
        lay.addWidget(info)
        lay.addWidget(close)
        self.fill()

    def fill(self, select: str | None = None) -> None:
        self.list.clear()
        for f in self.vm.project.fonts:
            n = self.vm.font_uses(f.id)
            it = QListWidgetItem(f"{f.id}  —  {F.describe(f.id, f.data)}  ·  " + trf("{n} usos", n=n))
            it.setData(Qt.ItemDataRole.UserRole, f.id)
            self.list.addItem(it)
            if f.id == select:
                self.list.setCurrentItem(it)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self.show_current()

    def current(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def show_current(self) -> None:
        fid = self.current()
        self.b_edit.setEnabled(fid is not None)
        self.b_remove.setEnabled(fid is not None)
        f = self.vm.project.font(fid) if fid else None
        if f is None:
            self.preview.setText("")
            return
        from olvgl.infrastructure.font_cache import font_weight
        self.preview.setFont(preview_font(f.file, self.vm.resolve_path, f.size, font_weight(f.file)))
        if F.is_icon_font(f.data):
            g = F.glyph_list(f.data.get("glyphs"))[:16]
            self.preview.setText(" ".join(g) if g else tr("(sin iconos todavía)"))
        else:
            self.preview.setText(SAMPLE)

    def add(self, source: str, show: bool = True) -> FontEditDialog | str | None:
        dlg = FontEditDialog(self.vm, source, parent=self)
        if not show:
            return dlg
        if dlg.exec():
            return self.apply(dlg)
        return None

    def apply(self, dlg: FontEditDialog) -> str | None:
        if dlg.result_id is None:
            return None
        if dlg.source == "edit":
            self.vm.update_font(dlg.result_id, dlg.result_data)
            fid = dlg.result_id
        else:
            fid = self.vm.add_font(dlg.result_id, dlg.result_data)
            if fid:
                self.last_added = fid
        self.fill(select=fid)
        return fid

    def edit(self, show: bool = True):
        fid = self.current()
        if fid is None:
            return None
        dlg = FontEditDialog(self.vm, "edit", fid, parent=self)
        if not show:
            return dlg
        if dlg.exec():
            return self.apply(dlg)
        return None

    def remove(self, confirm: bool = True) -> bool:
        fid = self.current()
        if fid is None:
            return False
        n = self.vm.font_uses(fid)
        if confirm and QMessageBox.question(
                self, tr("Eliminar fuente"),
                trf("¿Eliminar la fuente «{id}»?", id=fid)
                + ("\n" + trf("La usan {n} widgets o estilos: volverán a la fuente por defecto.", n=n) if n else "")
        ) != QMessageBox.StandardButton.Yes:
            return False
        ok = self.vm.remove_font(fid)
        self.fill()
        return ok


class IconPickerDialog(QDialog):
    """Elegir un icono de Material Design Icons (7447) por su nombre."""

    def __init__(self, parent=None, initial: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("Insertar icono (Material Design Icons)"))
        self.resize(720, 560)
        self.selected_char: str | None = None
        self.search = QLineEdit(initial)
        self.search.setPlaceholderText(tr("Buscar en inglés: light, fan, thermometer, door, blind…"))
        self.search.setClearButtonEnabled(True)
        self.view = QListWidget()
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setUniformItemSizes(True)
        self.view.setGridSize(QSize(92, 78))
        self.view.setMovement(QListView.Movement.Static)
        self.view.setWordWrap(True)
        f = QFont()
        fam = mdi_family()
        if fam:
            f.setFamily(fam)
        f.setPixelSize(30)
        self.glyph_font = f
        self.view.itemDoubleClicked.connect(lambda _i: self.accept_icon())
        self.view.currentItemChanged.connect(lambda *_: self.show_selected())
        self.info = QLabel()
        self.count = QLabel()
        self.count.setStyleSheet("color:#9E9E9E")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_icon)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.search)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addWidget(self.info, 1)
        row.addWidget(self.count)
        lay.addLayout(row)
        lay.addWidget(buttons)
        self.search.textChanged.connect(lambda _t: self.fill())
        self.fill()

    LIMIT = 600

    def fill(self) -> None:
        words = [w for w in self.search.text().lower().replace("_", "-").split() if w]
        found = [(n, c) for n, c in F.mdi_icons() if all(w in n for w in words)]
        self.view.clear()
        for name, ch in found[:self.LIMIT]:
            it = QListWidgetItem(ch + "\n" + name)
            it.setData(Qt.ItemDataRole.UserRole, ch)
            it.setToolTip(f"{name}  ·  {F.escape_glyph(ch)}")
            it.setFont(self.glyph_font)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.view.addItem(it)
        shown = min(len(found), self.LIMIT)
        self.count.setText(trf("{shown} de {total} iconos", shown=shown, total=len(found)) +
                           ("" if shown == len(found) else " · " + tr("afina la búsqueda para ver más")))
        if self.view.count():
            self.view.setCurrentRow(0)

    def show_selected(self) -> None:
        it = self.view.currentItem()
        if it is None:
            self.info.setText("")
            return
        ch = it.data(Qt.ItemDataRole.UserRole)
        self.info.setText(f"<b>{F.icon_name(ch)}</b> · <code>{F.escape_glyph(ch)}</code>")

    def accept_icon(self) -> None:
        it = self.view.currentItem()
        if it is None:
            return
        self.selected_char = it.data(Qt.ItemDataRole.UserRole)
        self.accept()


def nearest_icon_font(size: int) -> str:
    """mdi_<tamaño> para un tamaño de texto."""
    return F.library_id("mdi", max(8, min(200, int(size))))
