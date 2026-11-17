"""Editor del indicador de aguja (meter): escalas, marcas, números, agujas, arcos y rangos de color.

Todo lo que admite el `meter` de ESPHome, con vista previa al momento. Se
aplica de una vez (un solo paso de deshacer) con «Aceptar» o «Aplicar».
"""
from __future__ import annotations

import copy
from typing import Any, Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSpinBox, QSplitter, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from olvgl.domain import catalog
from olvgl.domain import meter as mt
from olvgl.domain.model import Widget
from olvgl.i18n import tr, trf

BIG = 1_000_000
# (clave, etiqueta, tipo, valor por defecto mostrado); tipos: value, int, sint, angle, len, color, opa, bool, id, image
SCALE_FIELDS = (
    ("range_from", "Valor mínimo", "value", 0),
    ("range_to", "Valor máximo", "value", 100),
    ("angle_range", "Ángulo total (°)", "angle", 270),
    ("rotation", "Ángulo de inicio (°, 0 = las 3)", "angle", None),
    ("draw_ticks_on_top", "Marcas por encima de los indicadores", "bool", False),
)
TICK_FIELDS = (
    ("count", "Número de marcas", "int", 12),
    ("width", "Grosor", "int", 2),
    ("length", "Largo (px o %)", "len", 10),
    ("color", "Color", "color", "#808080"),
    ("radial_offset", "Separación del borde", "sint", 0),
)
MAJOR_FIELDS = (
    ("stride", "Cada cuántas marcas", "int", 3),
    ("width", "Grosor", "int", 5),
    ("length", "Largo (px o %)", "len", "15%"),
    ("color", "Color", "color", "#808080"),
    ("label_gap", "Separación de los números", "sint", 4),
    ("radial_offset", "Separación del borde", "sint", 0),
)
INDICATOR_FIELDS: dict[str, tuple] = {
    "line": (("id", "Id (para cambiarla con lvgl.indicator.update)", "id", ""),
             ("value", "Valor", "value", None),
             ("width", "Grosor", "int", 4),
             ("color", "Color", "color", "#000000"),
             ("r_mod", "Largo respecto al radio (px, negativo = más corta)", "sint", 0),
             ("opa", "Opacidad", "opa", "COVER")),
    "arc": (("id", "Id (para cambiarlo con lvgl.indicator.update)", "id", ""),
            ("start_value", "Desde el valor", "value", None),
            ("end_value", "Hasta el valor", "value", None),
            ("width", "Grosor", "int", 4),
            ("color", "Color", "color", "#000000"),
            ("r_mod", "Radio respecto a la escala (px)", "sint", 0),
            ("opa", "Opacidad", "opa", "COVER")),
    "image": (("id", "Id (para cambiarla con lvgl.indicator.update)", "id", ""),
              ("src", "Imagen", "image", ""),
              ("value", "Valor", "value", None),
              ("pivot_x", "Eje X en la imagen", "sint", 0),
              ("pivot_y", "Eje Y en la imagen", "sint", 0),
              ("opa", "Opacidad", "opa", "COVER")),
    "tick_style": (("id", "Id (para cambiarlo con lvgl.indicator.update)", "id", ""),
                   ("start_value", "Desde el valor", "value", None),
                   ("end_value", "Hasta el valor", "value", None),
                   ("color_start", "Color inicial", "color", "#000000"),
                   ("color_end", "Color final", "color", "#000000"),
                   ("width", "Grosor de las marcas", "int", 4),
                   ("local", "Degradado sólo en este rango", "bool", False)),
}


def indicator_title(kind: str, d: dict) -> str:
    name = tr(mt.INDICATOR_LABELS[kind])
    if d.get("id"):
        name += f" «{d['id']}»"
    if kind in ("line", "image") and "value" in d:
        return f"{name} = {d['value']}"
    if kind in ("arc", "tick_style"):
        return f"{name} {d.get('start_value', '…')}–{d.get('end_value', '…')}"
    return name


def render_meter(vm, widget: Widget, props: dict, size: int = 280) -> QImage:
    """Vista previa del meter con estas propiedades."""
    from olvgl.domain.layout import effective_props
    from olvgl.presentation import render as rnd
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#2B2B30"))
    w = Widget(id=widget.id, type="meter", x=0, y=0, width=size, height=size, props=props)
    ctx = rnd.RenderContext(vm.project, getattr(vm, "resolve_path", None))
    eff = effective_props(vm.project, w)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rnd.paint_widget(p, w, QRectF(4, 4, size - 8, size - 8), eff, ctx)
    p.end()
    return img


class FieldForm(QWidget):
    """Formulario de un diccionario: un editor por campo, «×» para volver al valor por defecto."""

    def __init__(self, data: dict, fields: tuple, changed: Callable[[], None], image_ids: list[str],
                 parent=None):
        super().__init__(parent)
        self.data = data
        self.changed = changed
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.editors: dict[str, QWidget] = {}
        self.refreshers: list[Callable[[], None]] = []
        for key, label, kind, default in fields:
            ed, refresh = self._editor(key, label, kind, default, image_ids)
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(ed, 1)
            clear = QToolButton()
            clear.setText("×")
            clear.setToolTip(tr("Quitar (usar el valor por defecto)"))
            clear.clicked.connect(lambda _c=False, key=key, refresh=refresh: self._unset(key, refresh))
            h.addWidget(clear)
            self.form.addRow(tr(label), row)
            self.editors[key] = ed
            self.refreshers.append(refresh)
            refresh()

    def _unset(self, key: str, refresh) -> None:
        if key in self.data:
            del self.data[key]
            refresh()
            self.changed()

    def set(self, key: str, value: Any) -> None:
        if value in (None, "") and key in ("id", "src"):
            self.data.pop(key, None)
        else:
            self.data[key] = value
        self.changed()

    def _editor(self, key, label, kind, default, image_ids):
        d = self.data
        if kind in ("value", "int", "sint", "angle"):
            lo, hi = {"value": (-BIG, BIG), "int": (0, 10000), "sint": (-10000, 10000), "angle": (0, 360)}[kind]
            ed = QSpinBox()
            ed.setRange(lo, hi)
            ed.setKeyboardTracking(False)
            if default is None:
                ed.setRange(lo - 1, hi)
                ed.setSpecialValueText(tr("(automático)") if key == "rotation" else tr("(sin fijar)"))
            ed.valueChanged.connect(lambda v: self.set(key, v) if not (default is None and v == ed.minimum())
                                    else self._unset(key, lambda: None))

            def refresh():
                v = d.get(key, default)
                val = int(mt.num(v, ed.minimum())) if v is not None else ed.minimum()
                ed.blockSignals(True)
                ed.setValue(val)
                ed.blockSignals(False)
            return ed, refresh
        if kind in ("len", "id"):
            ed = QLineEdit()
            ed.setPlaceholderText(str(default) if default not in (None, "") else "")

            def commit():
                t = ed.text().strip()
                if kind == "len":
                    if not t:
                        self._unset(key, lambda: None)
                        return
                    try:
                        v: Any = int(t) if not t.endswith("%") else f"{int(float(t[:-1]))}%"
                    except ValueError:
                        refresh()
                        return
                    self.set(key, v)
                else:
                    self.set(key, t or None)
            ed.editingFinished.connect(commit)

            def refresh():
                v = d.get(key)
                ed.setText("" if v is None else str(v))
            return ed, refresh
        if kind == "color":
            from olvgl.presentation.properties import ColorButton
            ed = ColorButton()

            def pick():
                c = QColorDialog.getColor(QColor(str(d.get(key, default) or "#FFFFFF")), self, tr(label))
                if c.isValid():
                    self.set(key, c.name(QColor.NameFormat.HexRgb).upper())
                    refresh()
            ed.clicked.connect(pick)

            def refresh():
                v = d.get(key)
                ed.set_color(str(v) if isinstance(v, str) and v.startswith("#") else str(default or "#808080"))
                if v is None:
                    ed.setText(tr("(por defecto)"))
                elif not (isinstance(v, str) and v.startswith("#")):
                    ed.setText(str(v))
            return ed, refresh
        if kind == "opa":
            ed = QComboBox()
            ed.addItem(tr("(por defecto)"), None)
            for o in catalog.OPA_OPTIONS:
                ed.addItem(o, o)
            ed.activated.connect(lambda i: self.set(key, ed.itemData(i)) if ed.itemData(i)
                                 else self._unset(key, lambda: None))

            def refresh():
                i = ed.findData(d.get(key))
                if i < 0:
                    ed.addItem(str(d.get(key)), d.get(key))
                    i = ed.count() - 1
                ed.setCurrentIndex(i)
            return ed, refresh
        if kind == "image":
            ed = QComboBox()
            ed.addItem(tr("(ninguna)"), "")
            for i in image_ids:
                ed.addItem(i, i)
            ed.activated.connect(lambda i: self.set(key, ed.itemData(i) or None))

            def refresh():
                v = d.get(key) or ""
                i = ed.findData(v)
                if i < 0:
                    ed.addItem(str(v), v)
                    i = ed.count() - 1
                ed.setCurrentIndex(i)
            return ed, refresh
        ed = QCheckBox()           # bool
        ed.toggled.connect(lambda on: self.set(key, bool(on)))

        def refresh():
            ed.blockSignals(True)
            ed.setChecked(bool(d.get(key, default)))
            ed.blockSignals(False)
        return ed, refresh


class MeterDialog(QDialog):
    def __init__(self, vm, widget_id: str, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.widget_id = widget_id
        w = vm.widget(widget_id)
        self.widget = w
        self.scales: list[dict] = copy.deepcopy(mt.scales_of(w.props)) if w else []
        self.setWindowTitle(trf("Indicador de aguja «{id}»: escalas e indicadores", id=widget_id))
        self.resize(1000, 640)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(lambda *_: self.show_item())
        add = QGridLayout()
        self.b_scale = QPushButton(tr("＋ Escala"))
        self.b_scale.clicked.connect(lambda: self.add_scale())
        add.addWidget(self.b_scale, 0, 0)
        self.add_buttons: dict[str, QPushButton] = {}
        for i, kind in enumerate(mt.INDICATOR_TYPES):
            b = QPushButton("＋ " + tr(mt.INDICATOR_LABELS[kind]))
            b.clicked.connect(lambda _c=False, k=kind: self.add_indicator(k))
            add.addWidget(b, (i + 1) // 2, (i + 1) % 2)
            self.add_buttons[kind] = b
        row = QHBoxLayout()
        self.b_del = QPushButton(tr("Eliminar"))
        self.b_del.clicked.connect(lambda: self.remove())
        self.b_up = QPushButton("↑")
        self.b_up.setToolTip(tr("Subir (se dibuja antes)"))
        self.b_up.clicked.connect(lambda: self.move(-1))
        self.b_down = QPushButton("↓")
        self.b_down.setToolTip(tr("Bajar (se dibuja después, encima)"))
        self.b_down.clicked.connect(lambda: self.move(1))
        for b in (self.b_del, self.b_up, self.b_down):
            row.addWidget(b)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.tree, 1)
        ll.addLayout(add)
        ll.addLayout(row)
        self.editor_area = QScrollArea()
        self.editor_area.setWidgetResizable(True)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(290, 290)
        hint = QLabel(tr("Los ángulos van en grados desde las 3 en punto, en el sentido de las agujas del reloj. "
                         "Los largos admiten píxeles (10) o porcentaje del radio (15%)."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9E9E9E")
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.preview)
        rl.addWidget(hint)
        rl.addStretch(1)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.editor_area)
        split.addWidget(right)
        split.setSizes([280, 400, 300])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Apply
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_apply)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(lambda: self.apply())
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addWidget(buttons)
        self.forms: list[FieldForm] = []
        self.fill()

    # ------------------------------------------------ árbol
    def fill(self, select: tuple | None = None) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        target = None
        for si, sc in enumerate(self.scales):
            g = mt.scale_geo(sc)
            top = QTreeWidgetItem([trf("Escala {n}: {a} a {b}", n=si + 1, a=_fmt(g.range_from), b=_fmt(g.range_to))])
            top.setData(0, Qt.ItemDataRole.UserRole, ("scale", si))
            self.tree.addTopLevelItem(top)
            if select == ("scale", si):
                target = top
            for ii, it in enumerate(sc.get("indicators") or []):
                k = mt.indicator_kind(it)
                if k is None:
                    child = QTreeWidgetItem([tr("(indicador desconocido: se conserva)")])
                else:
                    child = QTreeWidgetItem([indicator_title(*k)])
                child.setData(0, Qt.ItemDataRole.UserRole, ("ind", si, ii))
                top.addChild(child)
                if select == ("ind", si, ii):
                    target = child
            top.setExpanded(True)
        self.tree.blockSignals(False)
        if target is None and self.tree.topLevelItemCount():
            target = self.tree.topLevelItem(0)
        if target is not None:
            self.tree.setCurrentItem(target)
        self.show_item()

    def selected(self) -> tuple | None:
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def current_scale(self) -> int:
        sel = self.selected()
        return sel[1] if sel else -1

    # ------------------------------------------------ editor
    def changed(self) -> None:
        self.update_preview()
        it = self.tree.currentItem()
        sel = self.selected()
        if it is None or sel is None:
            return
        if sel[0] == "scale":
            g = mt.scale_geo(self.scales[sel[1]])
            it.setText(0, trf("Escala {n}: {a} a {b}", n=sel[1] + 1, a=_fmt(g.range_from), b=_fmt(g.range_to)))
        else:
            k = mt.indicator_kind(self.scales[sel[1]]["indicators"][sel[2]])
            if k:
                it.setText(0, indicator_title(*k))

    def show_item(self) -> None:
        sel = self.selected()
        box = QWidget()
        v = QVBoxLayout(box)
        self.forms = []
        images = [i.id for i in self.vm.project.images]
        has = bool(sel)
        self.b_del.setEnabled(has)
        self.b_up.setEnabled(has)
        self.b_down.setEnabled(has)
        for b in self.add_buttons.values():
            b.setEnabled(bool(self.scales))
        if sel is None:
            msg = QLabel(tr("Este indicador no tiene escalas. Pulsa «＋ Escala» para empezar."))
            msg.setWordWrap(True)
            v.addWidget(msg)
        elif sel[0] == "scale":
            sc = self.scales[sel[1]]
            g1 = QGroupBox(tr("Escala"))
            f = FieldForm(sc, SCALE_FIELDS, self.changed, images)
            QVBoxLayout(g1).addWidget(f)
            self.forms.append(f)
            v.addWidget(g1)
            ticks = sc.get("ticks")
            if not isinstance(ticks, dict):
                ticks = sc["ticks"] = {}
            g2 = QGroupBox(tr("Marcas"))
            f2 = FieldForm(ticks, TICK_FIELDS, self.changed, images)
            QVBoxLayout(g2).addWidget(f2)
            self.forms.append(f2)
            v.addWidget(g2)
            g3 = QGroupBox(tr("Marcas principales con números"))
            g3.setCheckable(True)
            g3.setChecked(isinstance(ticks.get("major"), dict))
            l3 = QVBoxLayout(g3)
            major = ticks.get("major") if isinstance(ticks.get("major"), dict) else {}
            f3 = FieldForm(major, MAJOR_FIELDS, self.changed, images)
            f3.setEnabled(g3.isChecked())
            l3.addWidget(f3)
            self.forms.append(f3)

            def toggle_major(on, ticks=ticks, major=major, f3=f3):
                if on:
                    ticks["major"] = major
                else:
                    ticks.pop("major", None)
                f3.setEnabled(on)
                self.changed()
            g3.toggled.connect(toggle_major)
            v.addWidget(g3)
            self.major_box = g3
        else:
            it = self.scales[sel[1]]["indicators"][sel[2]]
            k = mt.indicator_kind(it)
            if k is None:
                msg = QLabel(tr("Este indicador no se puede editar aquí; se conserva tal cual en el YAML."))
                msg.setWordWrap(True)
                v.addWidget(msg)
            else:
                kind, data = k
                it[kind] = data                     # el formulario edita el diccionario del indicador
                g = QGroupBox(tr(mt.INDICATOR_LABELS[kind]))
                f = FieldForm(data, INDICATOR_FIELDS[kind], self.changed, images)
                QVBoxLayout(g).addWidget(f)
                self.forms.append(f)
                v.addWidget(g)
        v.addStretch(1)
        self.editor_area.setWidget(box)
        self.update_preview()

    def update_preview(self) -> None:
        if self.widget is None:
            return
        props = dict(self.widget.props, scales=self.scales)
        self.preview.setPixmap(QPixmap.fromImage(render_meter(self.vm, self.widget, props)))

    # ------------------------------------------------ acciones
    def add_scale(self) -> None:
        self.scales.append(copy.deepcopy(mt.NEW_SCALE))
        self.fill(("scale", len(self.scales) - 1))

    def add_indicator(self, kind: str) -> None:
        si = self.current_scale()
        if si < 0:
            if not self.scales:
                return
            si = 0
        sc = self.scales[si]
        g = mt.scale_geo(sc)
        d = copy.deepcopy(mt.NEW_INDICATOR[kind])
        for key in ("value", "start_value", "end_value"):      # dentro del rango de la escala
            if key in d:
                d[key] = int(g.range_from + (g.range_to - g.range_from) * d[key] / 100)
        inds = sc.setdefault("indicators", [])
        inds.append({kind: d})
        self.fill(("ind", si, len(inds) - 1))

    def remove(self) -> None:
        sel = self.selected()
        if sel is None:
            return
        if sel[0] == "scale":
            del self.scales[sel[1]]
            self.fill(("scale", max(0, sel[1] - 1)))
        else:
            inds = self.scales[sel[1]]["indicators"]
            del inds[sel[2]]
            self.fill(("ind", sel[1], sel[2] - 1) if sel[2] > 0 else ("scale", sel[1]))

    def move(self, delta: int) -> None:
        sel = self.selected()
        if sel is None:
            return
        lst = self.scales if sel[0] == "scale" else self.scales[sel[1]]["indicators"]
        i = sel[-1]
        j = i + delta
        if not 0 <= j < len(lst):
            return
        lst[i], lst[j] = lst[j], lst[i]
        self.fill((sel[0], j) if sel[0] == "scale" else ("ind", sel[1], j))

    def cleaned(self) -> list[dict]:
        out = copy.deepcopy(self.scales)
        for sc in out:
            if isinstance(sc.get("ticks"), dict) and not sc["ticks"]:
                del sc["ticks"]
            if "indicators" in sc and not sc["indicators"]:
                del sc["indicators"]
        return out

    def apply(self) -> None:
        self.vm.set_raw_prop([self.widget_id], "scales", self.cleaned() or None)

    def accept_apply(self) -> None:
        self.apply()
        self.accept()


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"
