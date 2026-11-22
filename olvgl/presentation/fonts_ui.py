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


def font_file(file, project_path_resolver=None) -> str | None:
    """El fichero de la fuente en este equipo (biblioteca, caché de descargas o fichero local), o None."""
    from olvgl.infrastructure import font_cache
    path = font_cache.bundled_path(file) or font_cache.cached_path(file)
    if path is None and isinstance(file, str) and file and "://" not in file and not file.startswith("mdi:"):
        path = project_path_resolver(file) if project_path_resolver else file
    return path if path and os.path.exists(path) else None


def preview_font(file, project_path_resolver=None, size: int = 22, weight: int = 400) -> QFont:
    """QFont para la vista previa: fichero de la biblioteca, en caché o local."""
    from olvgl.presentation import render
    from olvgl.presentation.fonts import pick_family
    path = font_file(file, project_path_resolver)
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
        glyph_row = QHBoxLayout()
        glyph_row.addWidget(self.glyphs, 1)
        self.glyph_btn = QPushButton(tr("Elegir…"))
        self.glyph_btn.setToolTip(tr("Elegir los caracteres en una tabla (los iconos, por categorías)"))
        self.glyph_btn.clicked.connect(lambda: self.pick_glyphs())
        glyph_row.addWidget(self.glyph_btn, 0, Qt.AlignmentFlag.AlignTop)
        form.addRow(tr("Caracteres"), glyph_row)
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
        gf = QFont(font)                       # los caracteres elegidos se ven con la propia fuente
        gf.setPixelSize(18)
        self.glyphs.setFont(gf)
        if F.is_icon_font(data):
            names = ("home", "lightbulb", "thermometer", "water-percent", "fan", "power", "wifi", "cog")
            icons = dict(F.mdi_icons())
            self.preview.setText(" ".join(icons[n] for n in names if n in icons))
        else:
            self.preview.setText(SAMPLE)

    # ------------------------------------------------ acciones
    def pick_glyphs(self, show: bool = True):
        """Tabla de caracteres de la fuente (o de iconos por categoría) para elegir los `glyphs`."""
        try:
            data = self.data()
        except F.FontSourceError:
            data = {}
        icon = bool(data) and F.is_icon_font(data)
        dlg = GlyphPickerDialog(self, icons=icon, multi=True, selected=F.glyph_list(self.glyphs.toPlainText()),
                                file=data.get("file") if data else None)
        if not show:
            return dlg
        if dlg.exec():
            self.apply_glyphs(dlg.result_chars())
        return dlg

    def apply_glyphs(self, chars: list[str]) -> None:
        self.glyphs.setPlainText("".join(chars))
        self.update_auto()

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
        self.b_glyphs = QPushButton(tr("Caracteres…"))
        self.b_glyphs.setToolTip(tr("Elegir los caracteres de la fuente en una tabla (los iconos, por categorías)"))
        self.b_glyphs.clicked.connect(lambda: self.pick_glyphs())
        self.b_remove = QPushButton(tr("Eliminar"))
        self.b_remove.clicked.connect(lambda: self.remove())
        buttons.addWidget(self.b_edit)
        buttons.addWidget(self.b_glyphs)
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
        self.b_glyphs.setEnabled(fid is not None)
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

    def pick_glyphs(self, show: bool = True):
        """Caracteres… de la fuente elegida: tabla de caracteres o de iconos por categoría."""
        fid = self.current()
        f = self.vm.project.font(fid) if fid else None
        if f is None:
            return None
        icon = F.is_icon_font(f.data)
        dlg = GlyphPickerDialog(self, icons=icon, multi=True, selected=F.glyph_list(f.data.get("glyphs")),
                                file=f.file, title=trf("Caracteres de «{id}»", id=fid))
        if not show:
            return dlg
        if dlg.exec():
            self.apply_glyphs(fid, dlg.result_chars())
        return dlg

    def apply_glyphs(self, fid: str, chars: list[str]) -> bool:
        f = self.vm.project.font(fid)
        if f is None:
            return False
        data = dict(f.data)
        value = F.glyphs_value(chars, F.is_icon_font(data))
        if value is None:
            data.pop("glyphs", None)
        else:
            data["glyphs"] = value
        ok = self.vm.update_font(fid, data)
        self.fill(select=fid)
        return ok

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


ALL_KEY = "__todos__"
SELECTED_KEY = "__elegidos__"


class GlyphPickerDialog(QDialog):
    """Elegir caracteres de una fuente.

    - Material Design Icons: los 7447 iconos por categoría (Domótica, Tiempo, Flechas…) y con buscador.
    - Fuentes de texto: los caracteres que tiene la fuente, por bloques de Unicode, con atajos
      («Español», «Números»).
    Con `multi` se marcan varios (los `glyphs:` de la fuente); sin él se elige uno (insertar un icono).
    """

    LIMIT = 1500

    def __init__(self, parent=None, *, icons: bool = True, multi: bool = False, selected=(), file=None,
                 initial: str = "", title: str | None = None):
        super().__init__(parent)
        self.icons, self.multi = icons, multi
        self.selected: list[str] = list(dict.fromkeys(selected))
        self.selected_char: str | None = None
        self.setWindowTitle(title or (tr("Insertar icono (Material Design Icons)") if not multi
                                      else tr("Elegir caracteres de la fuente")))
        self.resize(900, 620)
        # fuente para dibujar las celdas
        f = QFont()
        fam = mdi_family() if icons else ""
        if not icons and file is not None:
            f = preview_font(file, None, 26)
        elif fam:
            f.setFamily(fam)
        f.setPixelSize(26 if not icons else 30)
        self.glyph_font = f
        from PySide6.QtGui import QFontMetrics
        self._metrics = QFontMetrics(f)
        # sólo se filtran los caracteres que tiene la fuente si su fichero está en el equipo
        self._check_support = not icons and file is not None and font_file(file) is not None
        # categorías / bloques
        self.groups = QListWidget()
        self.groups.setMaximumWidth(260)
        self.search = QLineEdit(initial)
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(tr("Buscar en inglés: light, fan, thermometer, door, blind…") if icons
                                       else tr("Escribe caracteres y pulsa Intro para marcarlos (p. ej. ºª€)"))
        self.view = QListWidget()
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setUniformItemSizes(True)
        self.view.setGridSize(QSize(96, 80) if icons else QSize(54, 54))
        self.view.setMovement(QListView.Movement.Static)
        self.view.setWordWrap(True)
        self.view.itemDoubleClicked.connect(lambda _i: self.accept_icon() if not self.multi else None)
        self.view.currentItemChanged.connect(lambda *_: self.show_selected())
        self.view.itemChanged.connect(self._on_check)
        self.info = QLabel()
        self.count = QLabel()
        self.count.setStyleSheet("color:#9E9E9E")
        right = QVBoxLayout()
        right.addWidget(self.search)
        if multi:
            presets = QHBoxLayout()
            self.b_all = QPushButton(tr("Marcar todos los visibles"))
            self.b_all.clicked.connect(lambda: self.set_visible_checked(True))
            self.b_none = QPushButton(tr("Desmarcar los visibles"))
            self.b_none.clicked.connect(lambda: self.set_visible_checked(False))
            presets.addWidget(self.b_all)
            presets.addWidget(self.b_none)
            if not icons:
                for label, chars in ((tr("Español"), F.PRESET_SPANISH), (tr("Números"), F.PRESET_DIGITS)):
                    b = QPushButton("＋ " + label)
                    b.clicked.connect(lambda _c=False, ch=chars: self.add_chars(ch))
                    presets.addWidget(b)
            b = QPushButton(tr("Quitar todos"))
            b.clicked.connect(lambda: self.clear_selection())
            presets.addWidget(b)
            presets.addStretch(1)
            right.addLayout(presets)
        right.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addWidget(self.info, 1)
        row.addWidget(self.count)
        right.addLayout(row)
        body = QHBoxLayout()
        body.addWidget(self.groups)
        body.addLayout(right, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_icon)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(buttons)
        self._fill_groups()
        self.groups.currentRowChanged.connect(lambda _r: self.fill())
        self.search.textChanged.connect(lambda _t: self._on_search())
        if not icons:
            self.search.returnPressed.connect(lambda: (self.add_chars(self.search.text()), self.search.clear()))
        self.fill()

    # ------------------------------------------------ grupos
    def _fill_groups(self) -> None:
        self.groups.clear()
        if self.icons:
            items = [(ALL_KEY, trf("Todos ({n})", n=len(F.mdi_info())))]
            items += [(c, f"{tr(F.category_label(c))} ({n})") for c, n in F.mdi_categories()]
        else:
            items = [(ALL_KEY, tr("Todos los bloques"))]
            for name, a, b in F.UNICODE_BLOCKS:
                n = len(self._supported(F.block_chars(a, b)))
                if n:
                    items.append(((a, b), f"{tr(name)} ({n})"))
        if self.multi:
            items.insert(1, (SELECTED_KEY, trf("Elegidos ({n})", n=len(self.selected))))
        for key, text in items:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.groups.addItem(it)
        start = 1 if self.icons and not self.search.text() else 0
        if self.icons and not self.search.text():
            start = next((i for i in range(self.groups.count())
                          if self.groups.item(i).data(Qt.ItemDataRole.UserRole) == "Home Automation"), 0)
        self.groups.setCurrentRow(start)

    def select_group(self, key) -> bool:
        for i in range(self.groups.count()):
            if self.groups.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.groups.setCurrentRow(i)
                self.fill()
                return True
        return False

    def _update_selected_label(self) -> None:
        for i in range(self.groups.count()):
            it = self.groups.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == SELECTED_KEY:
                it.setText(trf("Elegidos ({n})", n=len(self.selected)))

    def _supported(self, chars: list[str]) -> list[str]:
        if not self._check_support:
            return chars
        return [c for c in chars if self._metrics.inFontUcs4(ord(c))]

    # ------------------------------------------------ celdas
    def _on_search(self) -> None:
        if not self.icons:
            return                              # en las fuentes de texto se escriben caracteres para marcarlos
        if self.search.text().strip():
            self.select_group(ALL_KEY)          # buscar en todos los iconos
        self.fill()

    def entries(self) -> list[tuple[str, str, str]]:
        """[(carácter, texto de la celda, ayuda)] del grupo y búsqueda actuales."""
        it = self.groups.currentItem()
        key = it.data(Qt.ItemDataRole.UserRole) if it else ALL_KEY
        text = self.search.text()
        if self.icons:
            if key == SELECTED_KEY:
                info = [i for i in F.mdi_info() if i.char in self.selected]
            else:
                info = F.search_icons(text, None if key == ALL_KEY else key)
            return [(i.char, i.char + "\n" + i.name,
                     f"{i.name} · {F.escape_glyph(i.char)} · " + ", ".join(tr(F.category_label(c)) for c in i.categories))
                    for i in info]
        if key == SELECTED_KEY:
            chars = sorted(self.selected, key=ord)
        elif key == ALL_KEY:
            chars = [c for _n, a, b in F.UNICODE_BLOCKS for c in F.block_chars(a, b)]
        else:
            chars = F.block_chars(*key)
        chars = self._supported(chars)
        return [(c, c, f"U+{ord(c):04X}") for c in chars]

    def fill(self) -> None:
        entries = self.entries()
        self.view.blockSignals(True)
        self.view.clear()
        for ch, label, tip in entries[:self.LIMIT]:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, ch)
            it.setToolTip(tip)
            it.setFont(self.glyph_font)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            if self.multi:
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if ch in self.selected else Qt.CheckState.Unchecked)
            self.view.addItem(it)
        self.view.blockSignals(False)
        shown = min(len(entries), self.LIMIT)
        msg = trf("{shown} de {total}", shown=shown, total=len(entries))
        if shown < len(entries):
            msg += " · " + tr("afina la búsqueda para ver más")
        if self.multi:
            msg += " · " + trf("{n} elegidos", n=len(self.selected))
        self.count.setText(msg)
        if self.view.count() and not self.multi:
            self.view.setCurrentRow(0)

    def visible_chars(self) -> list[str]:
        return [self.view.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.view.count())]

    def _on_check(self, item) -> None:
        ch = item.data(Qt.ItemDataRole.UserRole)
        on = item.checkState() == Qt.CheckState.Checked
        if on and ch not in self.selected:
            self.selected.append(ch)
        elif not on and ch in self.selected:
            self.selected.remove(ch)
        self._update_selected_label()
        self.count.setText(self.count.text().rsplit(" · ", 1)[0] + " · " + trf("{n} elegidos", n=len(self.selected)))

    def set_checked(self, chars, on: bool) -> None:
        for ch in chars:
            if on and ch not in self.selected:
                self.selected.append(ch)
            elif not on and ch in self.selected:
                self.selected.remove(ch)
        self._update_selected_label()
        self.fill()

    def set_visible_checked(self, on: bool) -> None:
        self.set_checked(self.visible_chars(), on)

    def add_chars(self, text: str) -> None:
        self.set_checked(self._supported([c for c in dict.fromkeys(text) if not c.isspace()]), True)

    def clear_selection(self) -> None:
        self.selected = []
        self._update_selected_label()
        self.fill()

    def show_selected(self) -> None:
        it = self.view.currentItem()
        if it is None:
            self.info.setText("")
            return
        ch = it.data(Qt.ItemDataRole.UserRole)
        name = F.icon_name(ch) if self.icons else f"U+{ord(ch):04X}"
        self.info.setText(f"<b>{name}</b> · <code>{F.escape_glyph(ch)}</code>")

    def result_chars(self) -> list[str]:
        return sorted(dict.fromkeys(self.selected), key=ord)

    def accept_icon(self) -> None:
        if self.multi:
            self.accept()
            return
        it = self.view.currentItem()
        if it is None:
            return
        self.selected_char = it.data(Qt.ItemDataRole.UserRole)
        self.accept()


class IconPickerDialog(GlyphPickerDialog):
    """Insertar un icono de Material Design Icons (por categoría o buscando)."""

    def __init__(self, parent=None, initial: str = ""):
        super().__init__(parent, icons=True, multi=False, initial=initial)
        if initial:
            self._on_search()


def nearest_icon_font(size: int) -> str:
    """mdi_<tamaño> para un tamaño de texto."""
    return F.library_id("mdi", max(8, min(200, int(size))))
