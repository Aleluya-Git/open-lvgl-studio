"""Panel de propiedades.

- Widgets del catálogo (Label, Button, Image): editores específicos.
- Cualquier widget: id, geometría tal como se escribe en ESPHome (px, %,
  SIZE_CONTENT o vacío), alineación, eventos y un bloque «Más propiedades
  (YAML)» donde se edita todo lo demás (estilos, estados, partes, lambdas…).
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from olvgl.i18n import tr, trf
from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain import catalog
from olvgl.domain.model import TOP_LAYER_ID, DisplayProfile
from olvgl.domain.values import ALIGNS, REGISTRY, is_tagged, node_to_value, value_to_node
from olvgl.domain.yaml_ast import YMap
from olvgl.presentation import render
from olvgl.presentation.fonts import mono_font, ui_font

IMAGE_FILTER = "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.svg)"


def is_primitive(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) and not is_tagged(v)


def fits_editor(prop: catalog.PropSpec, v: Any) -> bool:
    """¿Puede el editor visual de la propiedad mostrar este valor?"""
    if not is_primitive(v):
        return False
    k = prop.kind
    if k == catalog.KIND_INT:
        return isinstance(v, int) and not isinstance(v, bool)
    if k == catalog.KIND_BOOL:
        return isinstance(v, bool)
    if k in (catalog.KIND_STR, catalog.KIND_TEXT, catalog.KIND_COLOR, catalog.KIND_ENUM, catalog.KIND_IMAGE,
             catalog.KIND_WIDGET):
        return isinstance(v, str)
    return True


def fits_value(prop: catalog.PropSpec, v: Any) -> bool:
    if prop.kind == catalog.KIND_LINES:
        return isinstance(v, list) and all(is_primitive(x) for x in v)
    return fits_editor(prop, v)


# Propiedades del editor de estilo por parte y estado, por grupos (todas las de estilo de ESPHome LVGL)
# tipos: color, opa, int (0…1000), sint (−1000…1000), byte (0…255), bool, font, enum:A,B,C
BORDER_SIDES = "FULL,NONE,TOP,BOTTOM,LEFT,RIGHT,INTERNAL"
STYLE_GROUPS = (
    ("Fondo", (("bg_color", "Fondo", "color"), ("bg_opa", "Opacidad del fondo", "opa"),
               ("radius", "Radio", "int"), ("opa", "Opacidad", "opa"))),
    ("Degradado", (("bg_grad_dir", "Dirección del degradado", "enum:NONE,HOR,VER"),
                   ("bg_grad_color", "Color final del degradado", "color"),
                   ("bg_main_stop", "Empieza en (0-255)", "byte"),
                   ("bg_grad_stop", "Termina en (0-255)", "byte"))),
    ("Borde", (("border_color", "Color del borde", "color"), ("border_width", "Grosor del borde", "int"),
               ("border_opa", "Opacidad del borde", "opa"), ("border_side", "Lados del borde", "enum:" + BORDER_SIDES),
               ("border_post", "Borde por encima de los hijos", "bool"))),
    ("Contorno", (("outline_color", "Color del contorno", "color"), ("outline_width", "Grosor del contorno", "int"),
                  ("outline_pad", "Separación del contorno", "int"), ("outline_opa", "Opacidad del contorno", "opa"))),
    ("Sombra", (("shadow_color", "Color de la sombra", "color"), ("shadow_width", "Sombra", "int"),
                ("shadow_ofs_x", "Desplazamiento X", "sint"), ("shadow_ofs_y", "Desplazamiento Y", "sint"),
                ("shadow_spread", "Extensión", "sint"), ("shadow_opa", "Opacidad de la sombra", "opa"))),
    ("Texto", (("text_color", "Color del texto", "color"), ("text_opa", "Opacidad del texto", "opa"),
               ("text_font", "Fuente", "font"), ("text_align", "Alineación del texto", "enum:AUTO,LEFT,CENTER,RIGHT"),
               ("text_letter_space", "Espacio entre letras", "sint"), ("text_line_space", "Espacio entre líneas", "sint"),
               ("text_decor", "Decoración", "enum:NONE,UNDERLINE,STRIKETHROUGH"))),
    ("Relleno", (("pad_all", "Relleno", "int"), ("pad_top", "Arriba", "int"), ("pad_bottom", "Abajo", "int"),
                 ("pad_left", "Izquierda", "int"), ("pad_right", "Derecha", "int"),
                 ("pad_row", "Entre filas", "int"), ("pad_column", "Entre columnas", "int"))),
    ("Arco", (("arc_color", "Color del arco", "color"), ("arc_width", "Grosor del arco", "int"),
              ("arc_opa", "Opacidad del arco", "opa"), ("arc_rounded", "Extremos redondeados", "bool"))),
    ("Línea", (("line_color", "Color de la línea", "color"), ("line_width", "Grosor de la línea", "int"),
               ("line_opa", "Opacidad de la línea", "opa"), ("line_rounded", "Extremos redondeados", "bool"),
               ("line_dash_width", "Trazo (discontinua)", "int"), ("line_dash_gap", "Hueco (discontinua)", "int"))),
    ("Imagen", (("image_recolor", "Teñir con color", "color"), ("image_recolor_opa", "Intensidad del tinte", "opa"),
                ("bg_image_recolor", "Teñir la imagen de fondo", "color"),
                ("bg_image_recolor_opa", "Intensidad del tinte de fondo", "opa"))),
    ("Tamaño y posición", (("min_width", "Ancho mínimo", "int"), ("max_width", "Ancho máximo", "int"),
                           ("min_height", "Alto mínimo", "int"), ("max_height", "Alto máximo", "int"),
                           ("translate_x", "Desplazar X", "sint"), ("translate_y", "Desplazar Y", "sint"),
                           ("transform_angle", "Giro (décimas de grado)", "sint"),
                           ("clip_corner", "Recortar esquinas", "bool"))),
)
STYLE_FIELDS = tuple(f for _g, fields in STYLE_GROUPS for f in fields)
# grupos abiertos al principio, según el tipo de widget (el resto se abre con un clic)
STYLE_OPEN_BY_TYPE = {"arc": {"Arco"}, "spinner": {"Arco"}, "meter": {"Línea", "Texto"}, "line": {"Línea"},
                      "label": {"Texto"}, "image": {"Imagen"}, "button": {"Texto"}}
STYLE_OPEN_ALWAYS = {"Fondo", "Degradado", "Borde"}


def style_path(part: str, state: str, key: str) -> str:
    return ".".join(x for x in ((part if part != "main" else ""), state, key) if x)


def props_to_yaml(values: dict) -> str:
    if not values:
        return ""
    from olvgl.infrastructure.yaml_emitter import _emit_map
    m = YMap()
    for k, v in values.items():
        m.set(k, value_to_node(v, k))
    return "\n".join(_emit_map(m, 0)) + "\n"


def yaml_to_props(text: str) -> dict:
    from olvgl.infrastructure.yaml_parser import parse
    if not text.strip():
        return {}
    root = parse(text)
    if not isinstance(root, YMap):
        raise ValueError(tr("Escribe pares «clave: valor», una propiedad por línea"))
    return {p.key: node_to_value(p.value, p.key) for p in root.items}


class ColorButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = "#000000"
        self.setFixedHeight(24)

    def set_color(self, value: str) -> None:
        self._color = value
        c = render.qcolor(value)
        fg = "#000000" if c.lightness() > 140 else "#FFFFFF"
        self.setText(value.upper())
        self.setStyleSheet(f"QPushButton {{ background: {value}; color: {fg}; "
                           f"border: 1px solid #555; border-radius: 3px; }}")

    def color(self) -> str:
        return self._color


class YamlPropsEditor(QWidget):
    """Bloque YAML editable para las propiedades sin editor específico."""

    def __init__(self, getter: Callable[[], dict], apply: Callable[[dict], None], parent=None):
        super().__init__(parent)
        self._getter = getter
        self._apply = apply
        self.edit = QPlainTextEdit()
        font = mono_font()
        self.edit.setFont(font)
        self.edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.edit.setPlaceholderText(tr("bg_opa: 50%\npressed:\n  bg_color: 0x333333"))
        self.edit.setMinimumHeight(110)
        self.edit.textChanged.connect(self._on_changed)
        self.add_combo = QComboBox()
        self.add_combo.addItem(tr("Añadir propiedad…"), None)
        for k in sorted(REGISTRY):
            self.add_combo.addItem(k, k)
        self.add_combo.activated.connect(self._add_key)
        self.btn_apply = QPushButton(tr("Aplicar"))
        self.btn_apply.clicked.connect(self.apply)
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            sc = QShortcut(QKeySequence(seq), self.edit)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(self.apply)
        self.btn_revert = QPushButton(tr("Descartar"))
        self.btn_revert.clicked.connect(self.refresh_force)
        self.status = QLabel()
        self.status.setWordWrap(True)
        bar = QHBoxLayout()
        bar.addWidget(self.add_combo, 1)
        bar.addWidget(self.btn_revert)
        bar.addWidget(self.btn_apply)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit)
        lay.addLayout(bar)
        lay.addWidget(self.status)
        self._loading = False
        self._modified = False
        self.refresh_force()

    def _on_changed(self) -> None:
        if not self._loading:
            self._modified = True
            self.status.setText(tr("Cambios sin aplicar (Ctrl+Intro)"))
            self.status.setStyleSheet("color: #FFB74D;")

    def _add_key(self, i: int) -> None:
        key = self.add_combo.itemData(i)
        self.add_combo.setCurrentIndex(0)
        if not key:
            return
        text = self.edit.toPlainText()
        if text and not text.endswith("\n"):
            text += "\n"
        self.edit.setPlainText(text + f"{key}: ")
        cur = self.edit.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.edit.setTextCursor(cur)
        self.edit.setFocus()

    def refresh(self) -> None:
        if self._modified or self.edit.hasFocus():
            return
        self.refresh_force()

    def refresh_force(self) -> None:
        self._loading = True
        try:
            self.edit.setPlainText(props_to_yaml(self._getter()))
        finally:
            self._loading = False
        self._modified = False
        self.status.setText("")

    def apply(self) -> None:
        try:
            values = yaml_to_props(self.edit.toPlainText())
        except Exception as exc:
            self.status.setText(trf("YAML no válido: {exc}", exc=exc))
            self.status.setStyleSheet("color: #EF5350;")
            return
        self._modified = False
        self._apply(values)
        self.status.setText(tr("✓ Aplicado"))
        self.status.setStyleSheet("color: #81C784;")
        self.refresh_force()
        self.status.setText(tr("✓ Aplicado"))


class PropertiesPanel(QScrollArea):
    style_groups_open: dict[str, bool] = {}     # grupos del editor de estilo abiertos o cerrados por el usuario

    def __init__(self, vm: ProjectViewModel, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.setWidgetResizable(True)
        self._key: tuple | None = None
        self._refreshers: list[Callable[[], None]] = []
        self._refreshing = False
        self._rebuild_pending = False
        self.container: QWidget | None = None

        vm.project_changed.connect(self._on_model_changed)
        vm.selection_changed.connect(lambda _ids: self._on_model_changed())
        vm.screen_changed.connect(lambda _id: self._on_model_changed())
        vm.project_replaced.connect(self._force_rebuild)
        self._force_rebuild()

    # ================================================================ ciclo de vida
    def _current_key(self) -> tuple:
        sel = tuple(self.vm.selection)
        ws = self.vm.selected_widgets()
        types = tuple(w.type for w in ws)
        # reconstruir si cambia qué propiedades son «simples» (cambian los editores)
        shapes = tuple(tuple(sorted((k, type(v).__name__) for k, v in w.props.items())) for w in ws)
        managed = tuple(bool(self.vm.box(w.id) and self.vm.box(w.id).managed) for w in ws)
        return (sel, types, shapes, managed, self.vm.current_screen_id, len(self.vm.project.images),
                len(self.vm.project.fonts), tuple(s.id for s in self.vm.project.all_screens()))

    def _on_model_changed(self) -> None:
        if self._current_key() != self._key:
            self._schedule_rebuild()
        else:
            self.refresh()

    def _force_rebuild(self) -> None:
        self._key = None
        self._schedule_rebuild()

    def _schedule_rebuild(self) -> None:
        if not self._rebuild_pending:
            self._rebuild_pending = True
            QTimer.singleShot(0, self.rebuild)

    def refresh(self) -> None:
        self._refreshing = True
        try:
            for fn in self._refreshers:
                fn()
        finally:
            self._refreshing = False

    def rebuild(self) -> None:
        self._rebuild_pending = False
        self._key = self._current_key()
        self._refreshers = []
        self.container = QWidget()
        self.layout_ = QVBoxLayout(self.container)
        self.layout_.setContentsMargins(6, 6, 6, 6)
        widgets = self.vm.selected_widgets()
        if not widgets:
            self._build_screen_section()
            self._build_project_section()
        elif len(widgets) == 1:
            self._build_widget_section(widgets[0].id)
        else:
            self._build_multi_section([w.id for w in widgets])
        self.layout_.addStretch(1)
        self.setWidget(self.container)
        self.refresh()

    # ================================================================ fábricas de editores
    def _guard(self, fn: Callable[..., Any]) -> Callable[..., None]:
        def wrapper(*args):
            if not self._refreshing:
                fn(*args)
        return wrapper

    def _int(self, getter, setter, minimum=-10000, maximum=10000, enabled=True) -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(minimum, maximum)
        sb.setKeyboardTracking(False)
        sb.setEnabled(enabled)
        sb.valueChanged.connect(self._guard(lambda v: v != getter() and setter(v)))

        def refresh():
            v = getter()
            if sb.value() != v:
                sb.blockSignals(True)
                sb.setValue(int(v))
                sb.blockSignals(False)
        self._refreshers.append(refresh)
        return sb

    def _str(self, getter, setter, placeholder: str = "") -> QLineEdit:
        le = QLineEdit()
        le.setPlaceholderText(placeholder)

        def commit():
            if le.text() != getter():
                err = setter(le.text())
                if isinstance(err, str) and err:
                    QMessageBox.warning(self, tr("Valor no válido"), err)
                    le.setText(getter())
        le.editingFinished.connect(self._guard(commit))

        def refresh():
            if not le.hasFocus() and le.text() != getter():
                le.setText(getter())
        self._refreshers.append(refresh)
        return le

    def _text(self, getter, setter) -> QPlainTextEdit:
        te = QPlainTextEdit()
        te.setFixedHeight(56)
        timer = QTimer(te)
        timer.setSingleShot(True)
        timer.setInterval(350)

        def commit():
            if te.toPlainText() != getter():
                setter(te.toPlainText())
        timer.timeout.connect(commit)
        te.textChanged.connect(self._guard(timer.start))

        def refresh():
            if not te.hasFocus() and te.toPlainText() != getter():
                te.blockSignals(True)
                te.setPlainText(getter())
                te.blockSignals(False)
        self._refreshers.append(refresh)
        return te

    def _color(self, getter, setter, title: str) -> ColorButton:
        btn = ColorButton()

        def pick():
            initial = render.qcolor(getter())
            c = QColorDialog.getColor(initial, self, title)
            if c.isValid():
                setter(c.name(QColor.NameFormat.HexRgb).upper())
        btn.clicked.connect(pick)

        def refresh():
            v = getter()
            if isinstance(v, str) and not v.startswith("#"):
                ctx = render.RenderContext(self.vm.project)
                btn.set_color(ctx.color(v).name(QColor.NameFormat.HexRgb).upper())
                btn.setText(v)
            else:
                btn.set_color(str(v))
        self._refreshers.append(refresh)
        return btn

    def _bool(self, getter, setter, text: str = "") -> QCheckBox:
        cb = QCheckBox(text)
        cb.toggled.connect(self._guard(lambda v: setter(bool(v))))

        def refresh():
            v = bool(getter())
            if cb.isChecked() != v:
                cb.blockSignals(True)
                cb.setChecked(v)
                cb.blockSignals(False)
        self._refreshers.append(refresh)
        return cb

    def _enum(self, getter, setter, options: list, labels: list[str] | None = None) -> QComboBox:
        combo = QComboBox()
        for i, opt in enumerate(options):
            combo.addItem(labels[i] if labels else str(opt), opt)
        combo.activated.connect(self._guard(lambda i: setter(combo.itemData(i))))

        def refresh():
            v = getter()
            idx = combo.findData(v)
            if idx < 0 and v not in (None, ""):
                combo.addItem(str(v), v)
                idx = combo.count() - 1
            if idx != combo.currentIndex():
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)
        self._refreshers.append(refresh)
        return combo

    def _group(self, title: str) -> QFormLayout:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.layout_.addWidget(box)
        return form

    def _yaml_group(self, title: str, getter, apply, hint: str = "") -> None:
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        if hint:
            h = QLabel(hint)
            h.setWordWrap(True)
            h.setStyleSheet("color: #888;")
            lay.addWidget(h)
        ed = YamlPropsEditor(getter, apply)
        lay.addWidget(ed)
        self._refreshers.append(ed.refresh)
        self.layout_.addWidget(box)

    # ================================================================ pantalla y proyecto
    def _build_screen_section(self) -> None:
        sid = self.vm.current_screen_id
        if self.vm.project.screen(sid) is None:
            return
        top = sid == TOP_LAYER_ID
        form = self._group(tr("Capa superior (top_layer)") if top else tr("Pantalla"))

        def scr():
            return self.vm.project.screen(self.vm.current_screen_id)
        if top:
            info = QLabel(tr("Sus widgets se ven encima de todas las páginas."))
            info.setWordWrap(True)
            form.addRow(info)
        else:
            form.addRow(tr("Id"), self._str(lambda: scr().id if scr() else "",
                                        lambda v: self.vm.update_screen(self.vm.current_screen_id,
                                                                        new_id=v.strip())))
            form.addRow(tr("Nombre"), self._str(lambda: scr().name if scr() else "",
                                            lambda v: self.vm.update_screen(self.vm.current_screen_id, name=v)))
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(self._color(lambda: (scr().bg_color if scr() and scr().bg_color
                                             else render.page_background(self.vm.project, scr(),
                                                                         render.RenderContext(self.vm.project))
                                             .name(QColor.NameFormat.HexRgb).upper()),
                                    lambda v: self.vm.update_screen(self.vm.current_screen_id, bg_color=v),
                                    tr("Color de fondo")), 1)
            clear = QToolButton()
            clear.setText("×")
            clear.setToolTip(tr("Quitar el color propio (usa el del tema o de lvgl:)"))
            clear.clicked.connect(lambda: self.vm.update_screen(self.vm.current_screen_id, clear_bg=True))
            h.addWidget(clear)
            form.addRow(tr("Fondo"), row)
        self._yaml_group(tr("Más propiedades de la página (YAML)"),
                         lambda: dict(scr().props) if scr() else {},
                         lambda values: self.vm.replace_screen_props(self.vm.current_screen_id, values),
                         tr("Disparadores (on_load…), estilos, layout, padding… en formato ESPHome."))
        hint = QLabel(tr("Selecciona un widget para editar sus propiedades."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        self.layout_.addWidget(hint)

    def _build_project_section(self) -> None:
        form = self._group(tr("Proyecto"))
        p = lambda: self.vm.project  # noqa: E731
        form.addRow(tr("Nombre"), self._str(lambda: p().name, lambda v: self.vm.set_project_meta(name=v)))
        form.addRow(tr("Dispositivo"), self._str(lambda: p().esphome.device_name,
                                             lambda v: self.vm.set_project_meta(device_name=v.strip())))
        combo = QComboBox()
        self.display_combo = combo
        combo.addItem(tr("Elegir pantalla…"), None)
        from olvgl.application import displays
        for d in displays.presets():
            combo.addItem(displays.label(d), d)
        combo.insertSeparator(combo.count())
        combo.addItem(tr("＋ Nueva pantalla personalizada…"), "__new__")

        def apply_preset(i: int):
            d = combo.itemData(i)
            combo.setCurrentIndex(0)
            if isinstance(d, DisplayProfile):
                self.vm.set_display_keep_orientation(DisplayProfile(d.name, d.width, d.height))
            elif d == "__new__":
                self.open_custom_display()
        combo.activated.connect(apply_preset)
        form.addRow(tr("Placa"), combo)
        from olvgl.domain.model import ORIENTATION_LABELS, ROTATIONS
        orient = QComboBox()
        self.orientation_combo = orient
        for r in ROTATIONS:
            orient.addItem(f"{tr(ORIENTATION_LABELS[r])} ({r}°)", r)
        orient.setToolTip(tr("Gira la pantalla: en vertical se intercambian ancho y alto. Se escribe como "
                             "«lvgl: rotation:» (ESPHome 2026.4 o posterior; también gira el táctil)."))
        orient.activated.connect(self._guard(lambda i: self.vm.set_orientation(orient.itemData(i))))

        def refresh_orient():
            orient.blockSignals(True)
            orient.setCurrentIndex(max(0, orient.findData(p().rotation)))
            orient.blockSignals(False)
        self._refreshers.append(refresh_orient)
        form.addRow(tr("Orientación"), orient)
        save_btn = QPushButton(tr("★ Guardar esta pantalla en «Mis pantallas»…"))
        save_btn.setToolTip(tr("Para elegirla en otros proyectos y en el simulador"))
        save_btn.clicked.connect(lambda: self.open_custom_display(save_current=True))
        self.save_display_btn = save_btn
        from olvgl.domain.model import rotate_display as _rot
        self._refreshers.append(lambda: save_btn.setVisible(not displays.is_known(_rot(p().display, p().rotation, 0))))
        form.addRow("", save_btn)
        name_lbl = QLabel()
        self._refreshers.append(lambda: name_lbl.setText(p().display.name))
        form.addRow("", name_lbl)

        def set_size(w=None, h=None):
            d = p().display
            self.vm.set_project_meta(display=DisplayProfile(tr("Personalizada"), w or d.width, h or d.height))
        form.addRow(tr("Ancho"), self._int(lambda: p().display.width, lambda v: set_size(w=v), 32, 4096))
        form.addRow(tr("Alto"), self._int(lambda: p().display.height, lambda v: set_size(h=v), 32, 4096))
        info = QLabel()
        info.setWordWrap(True)
        info.setStyleSheet("color: #888;")

        def refresh_info():
            pr = p()
            parts = [f"{len(pr.fonts)} fuente(s)", f"{len(pr.images)} imagen(es)", f"{len(pr.styles)} estilo(s)"]
            src = pr.source.get("path") if pr.source else ""
            text = " · ".join(parts)
            if src:
                text += f"\nImportado de: {src}"
            info.setText(text)
        self._refreshers.append(refresh_info)
        form.addRow(info)

    def open_custom_display(self, save_current: bool = False, show: bool = True):
        """＋ Nueva pantalla personalizada: la aplica al proyecto y, si se pide, la guarda en «Mis pantallas»."""
        from olvgl.presentation.dialogs import CustomDisplayDialog
        from olvgl.domain.model import rotate_display
        cur = rotate_display(self.vm.project.display, self.vm.project.rotation, 0)   # tamaño natural de la placa
        dlg = CustomDisplayDialog(self, initial=DisplayProfile(cur.name, cur.width, cur.height))
        if not show:
            return dlg
        if dlg.exec():
            self.apply_custom_display(dlg)
        return dlg

    def apply_custom_display(self, dlg) -> None:
        d = getattr(dlg, "result_display", None) or dlg.apply()
        if d is None:
            return
        self.vm.set_display_keep_orientation(d)
        self._force_rebuild()                       # la lista de pantallas incluye la nueva

    # ================================================================ un widget
    def _build_widget_section(self, wid: str) -> None:
        state = {"id": wid}

        def w():
            return self.vm.widget(state["id"])
        model = w()
        sp = catalog.spec(model.type)
        box = self.vm.box(wid)

        title = QLabel(f"{tr(sp.label)} <span style='color:#888'>({sp.type})</span>")
        title.setFont(ui_font(bold=True, point_size=10))
        self.layout_.addWidget(title)
        form = self._group(tr("General"))

        def rename(v: str):
            if not v.strip():
                return None
            err = self.vm.rename_widget(state["id"], v)
            if err is None:
                state["id"] = v.strip()
            return err
        form.addRow(tr("Id"), self._str(lambda: (w().id if w() and not w().auto_id else ""), rename,
                                    placeholder=tr("(sin id: escribe uno para referenciarlo)")))

        geo = QWidget()
        g = QGridLayout(geo)
        g.setContentsMargins(0, 0, 0, 0)
        names = (("x", "X"), ("y", "Y"), ("width", tr("Ancho")), ("height", tr("Alto")))
        managed = bool(box and box.managed)
        for i, (key, label) in enumerate(names):
            def getter(key=key):
                m = w()
                v = getattr(m, key) if m else None
                return "" if v is None else str(v)

            def setter(text, key=key):
                return self.vm.set_geom_value(state["id"], key, text)
            le = self._str(getter, setter, placeholder="auto" if key in ("width", "height") else "0")
            le.setToolTip(tr("Píxeles, porcentaje del padre (50%)")
                          + (", SIZE_CONTENT" if key in ("width", "height") else "")
                          + tr(" o vacío para el valor por defecto de LVGL"))
            if key in ("x", "y") and managed:
                le.setEnabled(False)
            if key in ("width", "height") and not sp.resizable:
                le.setEnabled(False)
            g.addWidget(QLabel(label), (i // 2) * 2, i % 2)
            g.addWidget(le, (i // 2) * 2 + 1, i % 2)
        form.addRow(geo)
        if box is not None:
            real = QLabel()
            real.setStyleSheet("color: #888;")

            def refresh_real():
                b = self.vm.box(state["id"])
                if b:
                    real.setText(tr("En pantalla") + f": {b.rect.x:.0f}, {b.rect.y:.0f} · {b.rect.w:.0f}×{b.rect.h:.0f} px")
            self._refreshers.append(refresh_real)
            form.addRow(real)
        if managed:
            note = QLabel(tr("La posición la decide la disposición (flex/grid) del contenedor."))
            note.setWordWrap(True)
            note.setStyleSheet("color: #888;")
            form.addRow(note)
        elif model.type not in catalog.PSEUDO_TYPES:
            opts = [""] + list(ALIGNS)
            labels = [tr("(por defecto: TOP_LEFT)")] + list(ALIGNS)
            form.addRow(tr("Alineación"), self._enum(
                lambda: (str(w().props.get("align") or "") if w() else ""),
                lambda v: self.vm.set_raw_prop([state["id"]], "align", v or None), opts, labels))

        shown_keys: set[str] = set()
        if model.type in catalog.PSEUDO_TYPES:
            form.addRow(tr("Nombre"), self._str(lambda: str(w().props.get("name", "")) if w() else "",
                                            lambda v: self.vm.set_raw_prop([state["id"]], "name", v)))
            shown_keys.add("name")
        if sp.known:
            groups: dict[str, QFormLayout] = {}
            for prop in sp.props:
                cur = catalog.get_path(model.props, prop.name, catalog._MISSING)
                if cur is not catalog._MISSING and not fits_value(prop, cur):
                    continue  # valor avanzado (lambda, format, %…): se edita en YAML
                if prop.group not in groups:
                    groups[prop.group] = self._group(tr(prop.group))
                groups[prop.group].addRow(tr(prop.label), self._prop_editor([state["id"]], prop, state))
                if "." not in prop.name:
                    shown_keys.add(prop.name)
        else:
            row = QLabel(tr("Tipo de widget desconocido para el editor: "
                         "edita sus propiedades en el bloque YAML."))
            row.setWordWrap(True)
            row.setStyleSheet("color: #888;")
            self.layout_.addWidget(row)
            shown_keys.add("hidden")
            hid = self._group(tr("Comportamiento"))
            hid.addRow(tr("Oculto"), self._bool(lambda: bool(w().props.get("hidden") is True) if w() else False,
                                            lambda v: self.vm.set_raw_prop([state["id"]], "hidden",
                                                                           True if v else None)))
        shown_keys.add("align")

        if sp.child_type:
            self._build_children_section(state, sp)
        if model.type == "meter":
            self._build_meter_section(state)
            shown_keys.add("scales")
        self._build_style_section(state, sp)
        self._build_applied_styles(state)
        shown_keys.add("styles")

        if sp.events or model.events:
            self._build_events_section(state)

        def extra():
            m = w()
            return {k: v for k, v in m.props.items() if k not in shown_keys} if m else {}

        def apply(values: dict):
            scope = [k for k in (w().props if w() else {}) if k not in shown_keys]
            self.vm.replace_props(state["id"], scope, values)
        self._yaml_group(tr("Más propiedades (YAML)"), extra, apply,
                         tr("Estilos, estados (pressed:, checked:…), partes (indicator:, knob:…), "
                         "styles:, layout:, lambdas… en formato ESPHome. Ctrl+Intro aplica."))

    def _prop_editor(self, ids: list[str], prop: catalog.PropSpec, state: dict | None = None) -> QWidget:
        def current_ids():
            return [state["id"]] if state else ids

        def getter():
            m = self.vm.widget(current_ids()[0])
            return catalog.prop_value(m, prop.name) if m else prop.default

        def setter(v, merge=False):
            self.vm.set_prop(current_ids(), prop.name, v, merge=merge)

        k = prop.kind
        if k == catalog.KIND_INT:
            return self._int(lambda: int(getter() or 0), setter, prop.minimum, prop.maximum)
        if k == catalog.KIND_STR:
            return self._str(lambda: str(getter()), setter)
        if k == catalog.KIND_TEXT:
            return self._text(lambda: str(getter()), lambda v: setter(v, merge=True))
        if k == catalog.KIND_COLOR:
            return self._color(getter, setter, tr(prop.label))
        if k == catalog.KIND_BOOL:
            return self._bool(getter, setter)
        if k == catalog.KIND_ENUM:
            opts = self.vm.font_ids() if prop.name == "text_font" else list(prop.options)
            return self._enum(getter, setter, opts)
        if k == catalog.KIND_IMAGE:
            return self._image_editor(current_ids, getter)
        if k == catalog.KIND_LINES:
            def lines_get():
                v = getter()
                return "\n".join(str(x) for x in v) if isinstance(v, list) else ""

            def lines_set(text):
                items = [ln.strip() for ln in text.splitlines() if ln.strip()]
                setter(items or None, merge=True)
            return self._text(lines_get, lines_set)
        if k == catalog.KIND_WIDGET:
            ids = [""] + [w.id for _, w in self.vm.project.iter_widgets()
                          if not w.auto_id and w.id not in current_ids()]
            return self._enum(lambda: getter() or "", lambda v: setter(v or None), ids,
                              ["(ninguno)"] + ids[1:])
        return QLabel(str(getter()))

    # ================================================================ estilo por parte y estado
    def _build_style_section(self, state: dict, sp: catalog.WidgetSpec) -> None:
        box = QGroupBox(tr("Estilo por parte y estado"))
        lay = QVBoxLayout(box)
        sel = QHBoxLayout()
        part = QComboBox()
        for pt in sp.parts:
            part.addItem(tr(catalog.PART_LABELS.get(pt, pt)), pt)
        st = QComboBox()
        st.addItem(tr(catalog.STATE_LABELS[""]), "")
        for s_ in catalog.STATES:
            st.addItem(tr(catalog.STATE_LABELS.get(s_, s_)), s_)
        sel.addWidget(QLabel(tr("Parte")))
        sel.addWidget(part, 1)
        sel.addWidget(QLabel(tr("Estado")))
        sel.addWidget(st, 1)
        lay.addLayout(sel)
        local: list[Callable[[], None]] = []
        self.style_part_combo, self.style_state_combo = part, st
        self.style_editors: dict[str, QWidget] = {}
        self.style_group_heads: dict[str, QToolButton] = {}

        def path(key: str) -> str:
            return style_path(part.currentData() or "main", st.currentData() or "", key)

        def get(key: str):
            m = self.vm.widget(state["id"])
            return catalog.get_path(m.props, path(key)) if m else None

        def put(key: str, v):
            self.vm.set_prop([state["id"]], path(key), v)

        open_groups = STYLE_OPEN_ALWAYS | STYLE_OPEN_BY_TYPE.get(sp.type, set())
        remembered: dict = PropertiesPanel.style_groups_open
        for gname, fields in STYLE_GROUPS:
            head = QToolButton()
            head.setText(tr(gname))
            head.setCheckable(True)
            head.setChecked(remembered.get(gname, gname in open_groups))
            head.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            head.setArrowType(Qt.ArrowType.DownArrow if head.isChecked() else Qt.ArrowType.RightArrow)
            head.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
            body = QWidget()
            form = QFormLayout(body)
            form.setContentsMargins(12, 0, 0, 4)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            body.setVisible(head.isChecked())

            def toggled(on, head=head, body=body, gname=gname):
                body.setVisible(on)
                head.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
                PropertiesPanel.style_groups_open[gname] = on
            head.toggled.connect(toggled)
            lay.addWidget(head)
            lay.addWidget(body)
            self.style_group_heads[gname] = head
            for key, label, kind in fields:
                ed, refresh = self._style_field(key, label, kind, get, put)
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                clear = QToolButton()
                clear.setText("×")
                clear.setToolTip(tr("Quitar (usar el valor heredado)"))
                clear.clicked.connect(lambda _c=False, key=key: get(key) is not None and put(key, None))
                h.addWidget(ed, 1)
                h.addWidget(clear)
                form.addRow(tr(label), row)
                local.append(refresh)
                self.style_editors[key] = ed

        def refresh_all():
            for fn in local:
                fn()
        part.currentIndexChanged.connect(lambda _i: refresh_all())
        st.currentIndexChanged.connect(lambda _i: refresh_all())
        self._refreshers.extend(local)
        hint = QLabel(tr("Se escribe en ESPHome como «pressed: bg_color: …» o «indicator: …»."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        lay.addWidget(hint)
        self.layout_.addWidget(box)

    # ================================================================ indicador de aguja
    def _build_meter_section(self, state: dict) -> None:
        from olvgl.domain import meter as mt
        from olvgl.presentation.meter_ui import indicator_title
        box = QGroupBox(tr("Escalas e indicadores"))
        lay = QVBoxLayout(box)
        info = QLabel()
        info.setWordWrap(True)
        lay.addWidget(info)
        quick = QFormLayout()
        lay.addLayout(quick)
        btn = QPushButton(tr("Editar escalas, marcas y agujas…"))
        btn.clicked.connect(lambda: self.open_meter_editor(state["id"]))
        lay.addWidget(btn)
        self.layout_.addWidget(box)
        m = self.vm.widget(state["id"])
        scales = mt.scales_of(m.props) if m else []
        n_ind = sum(len(s.get("indicators") or []) for s in scales)
        info.setText(trf("{s} escalas · {i} indicadores", s=len(scales), i=n_ind) if scales
                     else tr("Sin escalas: pulsa el botón para añadir escala, marcas y agujas."))
        # valores de cada aguja/arco para ajustarlos rápido
        for si, sc in enumerate(scales):
            for ii, it in enumerate(sc.get("indicators") or []):
                k = mt.indicator_kind(it)
                if k is None:
                    continue
                kind, d = k
                keys = ("value",) if kind in ("line", "image") else ("start_value", "end_value")
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                for key in keys:
                    spin = QSpinBox()
                    spin.setRange(-1_000_000, 1_000_000)
                    spin.setKeyboardTracking(False)
                    g = mt.scale_geo(sc)
                    spin.setValue(int(mt.num(d.get(key), g.range_from if key != "end_value" else g.range_to)))
                    spin.valueChanged.connect(self._guard(
                        lambda v, si=si, ii=ii, kind=kind, key=key: self.set_meter_value(state["id"], si, ii, kind,
                                                                                         key, v)))
                    h.addWidget(spin)
                quick.addRow(indicator_title(kind, {kk: vv for kk, vv in d.items() if kk == "id"}), row)

    def set_meter_value(self, wid: str, si: int, ii: int, kind: str, key: str, value: int) -> None:
        import copy
        from olvgl.domain import meter as mt
        m = self.vm.widget(wid)
        if m is None:
            return
        scales = copy.deepcopy(mt.scales_of(m.props))
        try:
            scales[si]["indicators"][ii][kind][key] = value
        except (IndexError, KeyError, TypeError):
            return
        self.vm.set_raw_prop([wid], "scales", scales)

    def open_meter_editor(self, wid: str, show: bool = True):
        from olvgl.presentation.meter_ui import MeterDialog
        dlg = MeterDialog(self.vm, wid, self)
        if show:
            dlg.exec()
        return dlg

    def _style_field(self, key: str, label: str, kind: str, get, put):
        """Editor de una propiedad de estilo (con «(heredado)» = sin fijar) y su función de refresco."""
        if kind == "color":
            ed = ColorButton()

            def pick(_c=False):
                c = QColorDialog.getColor(render.qcolor(get(key) or "#FFFFFF"), self, tr(label))
                if c.isValid():
                    put(key, c.name(QColor.NameFormat.HexRgb).upper())
            ed.clicked.connect(pick)

            def refresh():
                v = get(key)
                if v is None:
                    ed.set_color("#455A64")
                    ed.setText(tr("(heredado)"))
                elif isinstance(v, str) and not v.startswith("#"):
                    ed.set_color(render.RenderContext(self.vm.project).color(v).name(
                        QColor.NameFormat.HexRgb).upper())
                    ed.setText(v)
                else:
                    ed.set_color(str(v))
            return ed, refresh
        if kind in ("opa", "bool", "font") or kind.startswith("enum:"):
            ed = QComboBox()
            ed.addItem(tr("(heredado)"), None)
            if kind == "opa":
                opts = [(o, o) for o in catalog.OPA_OPTIONS]
            elif kind == "bool":
                opts = [(tr("Sí"), True), (tr("No"), False)]
            elif kind == "font":
                opts = [(f, f) for f in self.vm.font_ids()]
            else:
                opts = [(o, o) for o in kind[5:].split(",")]
            for text, data in opts:
                ed.addItem(text, data)
            ed.activated.connect(self._guard(lambda i: put(key, ed.itemData(i))))

            def refresh():
                v = get(key)
                i = 0 if v is None else next((j for j in range(1, ed.count())
                                              if ed.itemData(j) == v and type(ed.itemData(j)) is type(v)), -1)
                if i < 0:
                    ed.addItem(str(v), v)
                    i = ed.count() - 1
                ed.blockSignals(True)
                ed.setCurrentIndex(i)
                ed.blockSignals(False)
            return ed, refresh
        lo, hi = {"sint": (-1000, 1000), "byte": (0, 255)}.get(kind, (0, 1000))
        none = lo - 1                                  # el valor especial «(heredado)»
        ed = QSpinBox()
        ed.setRange(none, hi)
        ed.setSpecialValueText(tr("(heredado)"))
        ed.setKeyboardTracking(False)

        def changed(v):
            new = None if v == none else v
            if new != get(key):
                put(key, new)
        ed.valueChanged.connect(self._guard(changed))

        def refresh():
            v = get(key)
            val = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else none
            ed.setEnabled(v is None or val != none)
            if ed.value() != val:
                ed.blockSignals(True)
                ed.setValue(val)
                ed.blockSignals(False)
        return ed, refresh

    def _build_applied_styles(self, state: dict) -> None:
        styles = [st.id for st in self.vm.project.styles]
        box = QGroupBox(tr("Estilos aplicados"))
        lay = QVBoxLayout(box)
        checks: list[tuple[str, QCheckBox]] = []

        def current() -> list[str]:
            m = self.vm.widget(state["id"])
            v = m.props.get("styles") if m else None
            return [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])

        def toggled(_v=False):
            chosen = [sid for sid, cb in checks if cb.isChecked()]
            chosen += [sid for sid in current() if sid not in styles]   # referencias desconocidas
            if chosen != current():
                self.vm.set_widget_styles(state["id"], chosen)

        for sid in styles:
            cb = QCheckBox(sid)
            cb.toggled.connect(self._guard(toggled))
            checks.append((sid, cb))
            lay.addWidget(cb)

        def refresh():
            cur = current()
            for sid, cb in checks:
                if cb.isChecked() != (sid in cur):
                    cb.blockSignals(True)
                    cb.setChecked(sid in cur)
                    cb.blockSignals(False)
        self._refreshers.append(refresh)
        if not styles:
            lay.addWidget(QLabel(tr("No hay estilos definidos.")))
        btn = QPushButton(tr("Estilos y tema…"))

        def open_dialog():
            from olvgl.presentation.dialogs import StylesDialog
            StylesDialog(self.vm, self).exec()
            self._force_rebuild()
        btn.clicked.connect(open_dialog)
        lay.addWidget(btn)
        self.layout_.addWidget(box)

    def _build_children_section(self, state: dict, sp: catalog.WidgetSpec) -> None:
        child = catalog.spec(sp.child_type)
        box = QGroupBox(tr(sp.child_type == "tab" and "Pestañas" or "Mosaicos"))
        lay = QVBoxLayout(box)
        info = QLabel()

        def refresh():
            m = self.vm.widget(state["id"])
            info.setText(f"{len(m.children) if m else 0} × {tr(child.label)}")
        self._refreshers.append(refresh)
        btn = QPushButton(tr(sp.child_type == "tab" and "Añadir pestaña" or "Añadir mosaico"))
        btn.clicked.connect(lambda: self.vm.add_child(state["id"]))
        lay.addWidget(info)
        lay.addWidget(btn)
        self.layout_.addWidget(box)

    def _image_editor(self, current_ids, getter) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        ids = [""] + [i.id for i in self.vm.project.images]
        labels = ["(ninguna)"] + ids[1:]
        combo = self._enum(lambda: getter() or "", lambda v: self.vm.set_prop(current_ids(), "src", v or None),
                           ids, labels)
        btn = QToolButton()
        btn.setText("…")
        btn.setToolTip(tr("Añadir una imagen al proyecto"))

        def add():
            path, _ = QFileDialog.getOpenFileName(self, tr("Añadir imagen"), "", tr(IMAGE_FILTER))
            if path:
                iid = self.vm.add_image(path)
                self.vm.set_prop(current_ids(), "src", iid)
        btn.clicked.connect(add)
        h.addWidget(combo, 1)
        h.addWidget(btn)
        return box

    def _build_events_section(self, state: dict) -> None:
        box = QGroupBox(tr("Eventos"))
        lay = QVBoxLayout(box)
        summary = QLabel()
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.PlainText)

        def refresh():
            m = self.vm.widget(state["id"])
            lines = []
            if m:
                for ev in m.events:
                    for a in ev.actions:
                        lines.append(f"• {tr(catalog.EVENT_LABELS.get(ev.trigger, ev.trigger))}: "
                                     f"{catalog.describe_action(a.kind, a.params)}")
            summary.setText("\n".join(lines) or tr("Sin eventos"))
        self._refreshers.append(refresh)
        btn = QPushButton(tr("Editar eventos…"))

        def edit():
            from olvgl.presentation.dialogs import EventsDialog
            m = self.vm.widget(state["id"])
            if m is None:
                return
            dlg = EventsDialog(m, self.vm.project, self)
            if dlg.exec():
                self.vm.set_events(m.id, dlg.result_events())
        btn.clicked.connect(edit)
        lay.addWidget(summary)
        lay.addWidget(btn)
        self.layout_.addWidget(box)

    # ================================================================ varios widgets
    def _build_multi_section(self, ids: list[str]) -> None:
        multi = QLabel(trf("{n} widgets seleccionados", n=len(ids)))
        multi.setFont(ui_font(bold=True, point_size=10))
        self.layout_.addWidget(multi)
        box = QGroupBox(tr("Alinear y distribuir"))
        grid = QGridLayout(box)
        buttons = [
            (tr("⇤ Izquierda"), lambda: self.vm.align("left")),
            (tr("↔ Centro H"), lambda: self.vm.align("hcenter")),
            (tr("⇥ Derecha"), lambda: self.vm.align("right")),
            (tr("⤒ Arriba"), lambda: self.vm.align("top")),
            (tr("↕ Centro V"), lambda: self.vm.align("vcenter")),
            (tr("⤓ Abajo"), lambda: self.vm.align("bottom")),
            (tr("Distribuir H"), lambda: self.vm.distribute("h")),
            (tr("Distribuir V"), lambda: self.vm.distribute("v")),
        ]
        for i, (text, fn) in enumerate(buttons):
            b = QPushButton(text)
            b.clicked.connect(lambda _c=False, fn=fn: fn())
            grid.addWidget(b, i // 3, i % 3)
        self.layout_.addWidget(box)

        specs = [catalog.spec(w.type) for w in self.vm.selected_widgets()]
        if all(s.known for s in specs):
            common = [p for p in specs[0].props
                      if p.kind != catalog.KIND_IMAGE
                      and all(s.prop(p.name) is not None and s.prop(p.name).kind == p.kind for s in specs[1:])]
            if common:
                form = self._group(tr("Propiedades comunes"))
                for prop in common:
                    form.addRow(tr(prop.label), self._prop_editor(ids, prop))
