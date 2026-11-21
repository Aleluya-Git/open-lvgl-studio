"""Diálogos: nuevo proyecto, eventos y estilos/tema."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from olvgl.i18n import tr, trf
from olvgl.domain import catalog
from olvgl.presentation.fonts import mono_font
from olvgl.domain.model import (DISPLAY_PRESETS, Action, DisplayProfile, EventHandler, Project,
                                Widget)


def display_preview(w: int, h: int, size: tuple[int, int] = (220, 140)):
    """Rectángulo con la proporción de la pantalla y su tamaño."""
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
    W, H = size
    pm = QPixmap(W, H)
    pm.fill(QColor("#26262B"))
    s = min((W - 20) / max(1, w), (H - 20) / max(1, h))
    rw, rh = max(4, int(w * s)), max(4, int(h * s))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#7C4DFF"), 2))
    p.setBrush(QColor("#101018"))
    p.drawRoundedRect((W - rw) // 2, (H - rh) // 2, rw, rh, 6, 6)
    p.setPen(QColor("#E6E6E6"))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, f"{w}×{h}")
    p.end()
    return pm


class CustomDisplayDialog(QDialog):
    """Pantalla personalizada para el proyecto actual (panel lateral › Proyecto)."""

    def __init__(self, parent=None, settings=None, initial: DisplayProfile | None = None):
        super().__init__(parent)
        from olvgl.application import displays
        self.settings = settings if settings is not None else displays.SETTINGS
        self.setWindowTitle(tr("Pantalla personalizada"))
        d = initial or DisplayProfile(tr("Mi pantalla"), 800, 480)
        generic = d.name in (tr("Personalizada"), "Personalizada") or (displays.is_known(d) and
                                                                       not displays.is_custom(d.name))
        self.name = QLineEdit("" if generic else d.name)
        self.name.setPlaceholderText(tr("p. ej. Mi placa 5\" 800×480"))
        self.width_sb = QSpinBox()
        self.width_sb.setRange(displays.MIN_SIZE, displays.MAX_SIZE)
        self.width_sb.setValue(d.width)
        self.height_sb = QSpinBox()
        self.height_sb.setRange(displays.MIN_SIZE, displays.MAX_SIZE)
        self.height_sb.setValue(d.height)
        rotate = QPushButton(tr("⇄ Girar"))
        rotate.setToolTip(tr("Intercambia ancho y alto (horizontal ↔ vertical)"))
        rotate.clicked.connect(self.rotate)
        row = QHBoxLayout()
        row.addWidget(self.width_sb)
        row.addWidget(QLabel("×"))
        row.addWidget(self.height_sb)
        row.addWidget(rotate)
        self.save_custom = QCheckBox(tr("Guardar en «Mis pantallas» para otros proyectos"))
        self.save_custom.setChecked(True)
        self.save_custom.setEnabled(self.settings is not None)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error = QLabel()
        self.error.setStyleSheet("color:#EF5350")
        self.error.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Nombre de la pantalla"), self.name)
        form.addRow(tr("Tamaño (px)"), row)
        form.addRow("", self.save_custom)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(lambda: self.apply() is not None and self.accept())
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.preview)
        lay.addWidget(self.error)
        lay.addWidget(buttons)
        self.name.textChanged.connect(lambda _t: self.error.clear())
        self.width_sb.valueChanged.connect(lambda _v: self._update_preview())
        self.height_sb.valueChanged.connect(lambda _v: self._update_preview())
        self._update_preview()

    def rotate(self) -> None:
        w, h = self.width_sb.value(), self.height_sb.value()
        self.width_sb.setValue(h)
        self.height_sb.setValue(w)

    def _update_preview(self) -> None:
        self.preview.setPixmap(display_preview(self.width_sb.value(), self.height_sb.value()))

    def apply(self) -> DisplayProfile | None:
        """La pantalla elegida (y guardada en «Mis pantallas» si se pide) o None si hay un error."""
        from olvgl.application import displays
        name = self.name.text().strip()
        try:
            if not name:
                raise displays.DisplayError("Ponle un nombre a la pantalla")
            displays.validate(name, self.width_sb.value(), self.height_sb.value())
            if self.save_custom.isChecked() and self.save_custom.isEnabled():
                displays.save(self.settings, name, self.width_sb.value(), self.height_sb.value())
        except displays.DisplayError as exc:
            self.error.setText(tr(str(exc)))
            return None
        self.error.clear()
        self.result_display = DisplayProfile(name, self.width_sb.value(), self.height_sb.value())
        return self.result_display


class NewProjectDialog(QDialog):
    """Nuevo proyecto: nombre y pantalla (de serie, propia o personalizada, que se puede guardar)."""

    CUSTOM_ROLE = "__custom__"

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        from olvgl.application import displays
        self.settings = settings if settings is not None else getattr(parent, "settings", None)
        if self.settings is not None:
            displays.load(self.settings)
        self.setWindowTitle(tr("Nuevo proyecto"))
        self.name = QLineEdit(tr("Nuevo proyecto"))
        self.preset = QComboBox()
        self.width_sb = QSpinBox()
        self.width_sb.setRange(displays.MIN_SIZE, displays.MAX_SIZE)
        self.height_sb = QSpinBox()
        self.height_sb.setRange(displays.MIN_SIZE, displays.MAX_SIZE)
        self.rotate_btn = QPushButton(tr("⇄ Girar"))
        self.rotate_btn.setToolTip(tr("Intercambia ancho y alto (horizontal ↔ vertical)"))
        self.rotate_btn.clicked.connect(self.rotate)
        from olvgl.domain.model import ORIENTATION_LABELS, ROTATIONS
        self.orient = QComboBox()
        for r in ROTATIONS:
            self.orient.addItem(f"{tr(ORIENTATION_LABELS[r])} ({r}°)", r)
        self.orient.setToolTip(tr("Gira la pantalla: en vertical se intercambian ancho y alto. Se escribe como "
                                  "«lvgl: rotation:» (ESPHome 2026.4 o posterior; también gira el táctil)."))
        self._rotation = 0
        size_row = QHBoxLayout()
        size_row.addWidget(self.width_sb)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.height_sb)
        size_row.addWidget(self.rotate_btn)
        self.screen_name = QLineEdit()
        self.screen_name.setPlaceholderText(tr("p. ej. Mi placa 5\" 800×480"))
        self.save_custom = QCheckBox(tr("Guardar en «Mis pantallas» para otros proyectos"))
        self.save_custom.setChecked(True)
        self.delete_btn = QPushButton(tr("Eliminar esta pantalla de «Mis pantallas»"))
        self.delete_btn.clicked.connect(self.delete_custom)
        self.preview = QLabel()
        self.preview.setMinimumSize(220, 140)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error = QLabel()
        self.error.setStyleSheet("color:#EF5350")
        self.error.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Nombre"), self.name)
        form.addRow(tr("Pantalla"), self.preset)
        form.addRow(tr("Orientación"), self.orient)
        form.addRow(tr("Tamaño (px)"), size_row)
        self.screen_name_label = QLabel(tr("Nombre de la pantalla"))
        form.addRow(self.screen_name_label, self.screen_name)
        form.addRow("", self.save_custom)
        form.addRow("", self.delete_btn)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.preview)
        lay.addWidget(self.error)
        lay.addWidget(buttons)
        self.fill()
        self.preset.currentIndexChanged.connect(self._on_preset)
        self.screen_name.textChanged.connect(lambda _t: self.error.clear())
        self.orient.currentIndexChanged.connect(lambda _i: self._on_orientation())
        self.width_sb.valueChanged.connect(lambda _v: self._on_size_edited())
        self.height_sb.valueChanged.connect(lambda _v: self._on_size_edited())
        self._on_preset(self.preset.currentIndex())

    # ------------------------------------------------ lista
    def fill(self, select: str | None = None) -> None:
        from olvgl.application import displays
        self.preset.blockSignals(True)
        self.preset.clear()
        for d in DISPLAY_PRESETS:
            self.preset.addItem(f"{d.name} ({d.width}×{d.height})", d)
        if displays.CUSTOM:
            self.preset.insertSeparator(self.preset.count())
            for d in displays.CUSTOM:
                self.preset.addItem(displays.label(d), d)
        self.preset.insertSeparator(self.preset.count())
        self.preset.addItem(tr("Personalizada…"), self.CUSTOM_ROLE)
        idx = 0
        if select:
            idx = next((i for i in range(self.preset.count()) if isinstance(self.preset.itemData(i), DisplayProfile)
                        and self.preset.itemData(i).name == select), 0)
        self.preset.setCurrentIndex(idx)
        self.preset.blockSignals(False)

    def custom_index(self) -> int:
        return self.preset.findData(self.CUSTOM_ROLE)

    def is_custom(self) -> bool:
        return self.preset.currentData() == self.CUSTOM_ROLE

    def _on_preset(self, i: int) -> None:
        from olvgl.application import displays
        d = self.preset.itemData(i)
        if isinstance(d, DisplayProfile):
            d = self._oriented(d)
            for sb, v in ((self.width_sb, d.width), (self.height_sb, d.height)):
                sb.blockSignals(True)
                sb.setValue(v)
                sb.blockSignals(False)
        custom = d == self.CUSTOM_ROLE
        for w in (self.screen_name_label, self.screen_name, self.save_custom):
            w.setVisible(custom)
        self.delete_btn.setVisible(isinstance(d, DisplayProfile) and displays.is_custom(d.name))
        self.error.clear()
        self._update_preview()

    def _on_size_edited(self) -> None:
        """Cambiar el tamaño de una pantalla de la lista la convierte en personalizada."""
        d = self.preset.currentData()
        d = self._oriented(d) if isinstance(d, DisplayProfile) else d
        if isinstance(d, DisplayProfile) and (d.width, d.height) != (self.width_sb.value(), self.height_sb.value()):
            if not self.screen_name.text().strip():
                self.screen_name.setText(f"{d.name} {self.width_sb.value()}×{self.height_sb.value()}")
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(self.custom_index())
            self.preset.blockSignals(False)
            self._on_preset(self.custom_index())
        self._update_preview()

    def rotation(self) -> int:
        return int(self.orient.currentData() or 0)

    def _oriented(self, d: DisplayProfile) -> DisplayProfile:
        from olvgl.domain.model import rotate_display
        return rotate_display(d, 0, self.rotation())

    def _on_orientation(self) -> None:
        """Al pasar de horizontal a vertical (o al revés) se intercambian ancho y alto."""
        new = self.rotation()
        if (new in (90, 270)) != (self._rotation in (90, 270)):
            w, h = self.width_sb.value(), self.height_sb.value()
            for sb, v in ((self.width_sb, h), (self.height_sb, w)):
                sb.blockSignals(True)
                sb.setValue(v)
                sb.blockSignals(False)
        self._rotation = new
        self._update_preview()

    def rotate(self) -> None:
        """⇄ Girar: horizontal ↔ vertical (la pantalla elegida sigue siendo la misma)."""
        nxt = {0: 90, 90: 0, 180: 270, 270: 180}[self.rotation()]
        self.orient.setCurrentIndex(self.orient.findData(nxt))

    def _update_preview(self) -> None:
        self.preview.setPixmap(display_preview(self.width_sb.value(), self.height_sb.value()))

    # ------------------------------------------------ pantallas propias
    def delete_custom(self) -> bool:
        from olvgl.application import displays
        d = self.preset.currentData()
        if not isinstance(d, DisplayProfile) or self.settings is None:
            return False
        ok = displays.remove(self.settings, d.name)
        self.fill()
        self._on_preset(self.preset.currentIndex())
        return ok

    def _accept(self) -> None:
        if self.store_custom():
            self.accept()

    def store_custom(self) -> bool:
        """Con «Personalizada» y «Guardar…» marcado, la añade a Mis pantallas. False si hay un error."""
        from olvgl.application import displays
        if not self.is_custom():
            return True
        name = self.screen_name.text().strip()
        try:
            displays.validate(name or tr("Personalizada"), self.width_sb.value(), self.height_sb.value())
            if self.save_custom.isChecked() and self.settings is not None:
                if not name:
                    raise displays.DisplayError(tr("Ponle un nombre a la pantalla"))
                from olvgl.domain.model import rotate_display
                nat = rotate_display(DisplayProfile(name, self.width_sb.value(), self.height_sb.value()),
                                     self.rotation(), 0)          # «Mis pantallas» guarda el tamaño natural
                displays.save(self.settings, name, nat.width, nat.height)
        except displays.DisplayError as exc:
            self.error.setText(tr(str(exc)))
            return False
        self.error.clear()
        return True

    def result_project(self) -> tuple[str, DisplayProfile]:
        d = self.preset.currentData()
        if isinstance(d, DisplayProfile):
            name = d.name
        else:
            name = self.screen_name.text().strip() or tr("Personalizada")
        return (self.name.text().strip() or tr("Nuevo proyecto"),
                DisplayProfile(name, self.width_sb.value(), self.height_sb.value()))


class DisplayDialog(QDialog):
    """Elegir la resolución cuando no se puede deducir del YAML importado."""

    def __init__(self, current: DisplayProfile, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Resolución de la pantalla"))
        info = QLabel(tr("No se pudo deducir la resolución de la pantalla del YAML.\n"
                      "Elige tu placa o indica el tamaño en píxeles:"))
        self.preset = QComboBox()
        from olvgl.application import displays
        for d in displays.presets():
            self.preset.addItem(displays.label(d), d)
        self.preset.addItem(tr("Personalizada"), None)
        self.width_sb = QSpinBox()
        self.width_sb.setRange(32, 4096)
        self.width_sb.setValue(current.width)
        self.height_sb = QSpinBox()
        self.height_sb.setRange(32, 4096)
        self.height_sb.setValue(current.height)
        self.preset.currentIndexChanged.connect(self._on_preset)
        form = QFormLayout()
        form.addRow(tr("Placa"), self.preset)
        form.addRow(tr("Ancho (px)"), self.width_sb)
        form.addRow(tr("Alto (px)"), self.height_sb)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(form)
        lay.addWidget(buttons)
        self._on_preset(0)

    def _on_preset(self, i: int) -> None:
        d = self.preset.itemData(i)
        self.width_sb.setEnabled(d is None)
        self.height_sb.setEnabled(d is None)
        if d:
            self.width_sb.setValue(d.width)
            self.height_sb.setValue(d.height)

    def result_display(self) -> DisplayProfile:
        d = self.preset.currentData()
        return DisplayProfile(d.name if d else tr("Personalizada"), self.width_sb.value(), self.height_sb.value())


class EventsDialog(QDialog):
    """Edita los manejadores de eventos de un widget sobre una copia."""

    def __init__(self, widget: Widget, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle(trf("Eventos de {id}", id=widget.id))
        self.resize(720, 420)
        self.project = project
        sp = catalog.spec(widget.type)
        self.triggers = list(dict.fromkeys(list(sp.events) + [ev.trigger for ev in widget.events]))
        self.data: dict[str, list[Action]] = {t: [] for t in self.triggers}
        for ev in widget.events:
            self.data.setdefault(ev.trigger, []).extend(copy.deepcopy(ev.actions))
        self._loading = False

        self.trigger_list = QListWidget()
        for t in self.triggers:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, t)
            self.trigger_list.addItem(it)
        self.trigger_list.currentRowChanged.connect(self._load_actions)
        self.btn_trigger = QPushButton(tr("Otro evento…"))
        tmenu = QMenu(self.btn_trigger)
        for t, label in catalog.EVENT_LABELS.items():
            act = tmenu.addAction(f"{tr(label)} ({t})")
            act.triggered.connect(lambda _c=False, t=t: self._add_trigger(t))
        self.btn_trigger.setMenu(tmenu)

        self.action_list = QListWidget()
        self.action_list.currentRowChanged.connect(self._load_editor)

        add = QPushButton(tr("Añadir acción"))
        menu = QMenu(add)
        for kind, label in catalog.ACTION_KINDS.items():
            act = menu.addAction(tr(label))
            act.triggered.connect(lambda _checked=False, k=kind: self._add_action(k))
        add.setMenu(menu)
        rm = QPushButton(tr("Quitar"))
        rm.clicked.connect(self._remove_action)
        up = QPushButton("↑")
        up.clicked.connect(lambda: self._move_action(-1))
        down = QPushButton("↓")
        down.clicked.connect(lambda: self._move_action(1))
        bar = QHBoxLayout()
        for b in (add, rm, up, down):
            bar.addWidget(b)
        bar.addStretch(1)

        self.editor = QStackedWidget()
        self._build_editors()

        right = QVBoxLayout()
        right.addWidget(QLabel(tr("Acciones (se ejecutan en orden):")))
        right.addWidget(self.action_list, 1)
        right.addLayout(bar)
        right.addWidget(self.editor)

        left = QVBoxLayout()
        left.addWidget(QLabel(tr("Evento:")))
        left.addWidget(self.trigger_list)
        left.addWidget(self.btn_trigger)

        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addLayout(right, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(body)
        lay.addWidget(buttons)

        self._refresh_triggers()
        self.trigger_list.setCurrentRow(0)

    # ------------------------------------------------------------------ editores por tipo
    def _build_editors(self) -> None:
        self.ed_empty = QLabel(tr("Selecciona o añade una acción."))
        self.ed_none = QLabel(tr("Esta acción no tiene parámetros."))

        self.ed_page = QWidget()
        f = QFormLayout(self.ed_page)
        self.page_combo = QComboBox()
        for s in self.project.screens:
            self.page_combo.addItem(f"{s.name} ({s.id})", s.id)
        self.page_combo.currentIndexChanged.connect(
            lambda _i: self._set_param("page", self.page_combo.currentData()))
        f.addRow(tr("Página"), self.page_combo)

        self.ed_ha = QWidget()
        f = QFormLayout(self.ed_ha)
        self.ha_action = QLineEdit()
        self.ha_action.setPlaceholderText("light.toggle")
        self.ha_action.textChanged.connect(lambda t: self._set_param("action", t.strip()))
        self.ha_entity = QLineEdit()
        self.ha_entity.setPlaceholderText("light.salon")
        self.ha_entity.textChanged.connect(lambda t: self._set_param("entity_id", t.strip()))
        f.addRow(tr("Acción"), self.ha_action)
        f.addRow("entity_id", self.ha_entity)

        self.ed_log = QWidget()
        f = QFormLayout(self.ed_log)
        self.log_msg = QLineEdit()
        self.log_msg.textChanged.connect(lambda t: self._set_param("message", t))
        f.addRow(tr("Mensaje"), self.log_msg)

        self.ed_raw = QWidget()
        v = QVBoxLayout(self.ed_raw)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel(tr("YAML de una acción ESPHome (sin el guion inicial):")))
        self.raw_text = QPlainTextEdit()
        self.raw_text.setFixedHeight(90)
        self.raw_text.textChanged.connect(lambda: self._set_param("yaml", self.raw_text.toPlainText()))
        v.addWidget(self.raw_text)

        ids = [w.id for _, w in self.project.iter_widgets() if w.type not in catalog.PSEUDO_TYPES]
        self.types = {w.id: w.type for _, w in self.project.iter_widgets()}

        def id_combo(key: str) -> QComboBox:
            c = QComboBox()
            c.setEditable(True)
            c.addItems(ids)
            c.currentTextChanged.connect(lambda t: self._set_param(key, t.strip()))
            return c

        self.ed_wstate = QWidget()
        f = QFormLayout(self.ed_wstate)
        self.ws_op = QComboBox()
        for op, label in catalog.WIDGET_STATE_OPS.items():
            self.ws_op.addItem(tr(label), op)
        self.ws_op.currentIndexChanged.connect(lambda _i: self._set_param("op", self.ws_op.currentData()))
        self.ws_id = id_combo("id")
        f.addRow(tr("Operación"), self.ws_op)
        f.addRow(tr("Widget"), self.ws_id)

        self.ed_wupdate = QWidget()
        f = QFormLayout(self.ed_wupdate)
        self.wu_id = QComboBox()
        self.wu_id.setEditable(True)
        self.wu_id.addItems(ids)
        self.wu_id.currentTextChanged.connect(self._on_update_id)
        self.wu_props = QPlainTextEdit()
        self.wu_props.setFont(mono_font())
        self.wu_props.setFixedHeight(80)
        self.wu_props.setPlaceholderText(tr("text: Encendido\nbg_color: 0x00FF00"))
        self.wu_props.textChanged.connect(self._on_update_props)
        self.wu_status = QLabel()
        f.addRow(tr("Widget"), self.wu_id)
        f.addRow(tr("Propiedades (YAML)"), self.wu_props)
        f.addRow("", self.wu_status)

        self.ed_call = QWidget()
        f = QFormLayout(self.ed_call)
        self.call_action = QLineEdit()
        self.call_action.setPlaceholderText(tr("light.toggle · script.execute · switch.turn_on"))
        self.call_action.textChanged.connect(lambda t: self._set_param("action", t.strip()))
        self.call_target = QLineEdit()
        self.call_target.setPlaceholderText(tr("id del componente (opcional)"))
        self.call_target.textChanged.connect(lambda t: self._set_param("target", t.strip()))
        f.addRow(tr("Acción"), self.call_action)
        f.addRow(tr("Destino"), self.call_target)

        self.ed_delay = QWidget()
        f = QFormLayout(self.ed_delay)
        self.delay_text = QLineEdit()
        self.delay_text.setPlaceholderText(tr("500ms · 2s · 1min"))
        self.delay_text.textChanged.connect(lambda t: self._set_param("duration", t.strip()))
        f.addRow(tr("Duración"), self.delay_text)

        self.ed_lambda = QWidget()
        v = QVBoxLayout(self.ed_lambda)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel(tr("Código C++ (se ejecuta en el dispositivo; el simulador sólo lo registra):")))
        self.lambda_text = QPlainTextEdit()
        self.lambda_text.setFont(mono_font())
        self.lambda_text.setFixedHeight(90)
        self.lambda_text.textChanged.connect(lambda: self._set_param("code", self.lambda_text.toPlainText()))
        v.addWidget(self.lambda_text)

        for w in (self.ed_empty, self.ed_none, self.ed_page, self.ed_ha, self.ed_log, self.ed_raw,
                  self.ed_wstate, self.ed_wupdate, self.ed_call, self.ed_delay, self.ed_lambda):
            self.editor.addWidget(w)

    def _on_update_id(self, text: str) -> None:
        wid = text.strip()
        self._set_param("id", wid)
        if wid in self.types:
            self._set_param("type", self.types[wid])

    def _on_update_props(self) -> None:
        if self._loading:
            return
        from olvgl.presentation.properties import yaml_to_props
        try:
            props = yaml_to_props(self.wu_props.toPlainText())
        except Exception as exc:
            self.wu_status.setText(trf("YAML no válido: {exc}", exc=exc))
            self.wu_status.setStyleSheet("color: #EF5350;")
            return
        self.wu_status.setText("")
        self._set_param("props", props)

    def _add_trigger(self, t: str) -> None:
        if t not in self.data:
            self.data[t] = []
            self.triggers.append(t)
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, t)
            self.trigger_list.addItem(it)
            self._refresh_triggers()
        for i in range(self.trigger_list.count()):
            if self.trigger_list.item(i).data(Qt.ItemDataRole.UserRole) == t:
                self.trigger_list.setCurrentRow(i)

    # ------------------------------------------------------------------ estado
    def _trigger(self) -> str | None:
        it = self.trigger_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _actions(self) -> list[Action]:
        t = self._trigger()
        return self.data.setdefault(t, []) if t else []

    def _action(self) -> Action | None:
        row = self.action_list.currentRow()
        acts = self._actions()
        return acts[row] if 0 <= row < len(acts) else None

    def _refresh_triggers(self) -> None:
        for i in range(self.trigger_list.count()):
            it = self.trigger_list.item(i)
            t = it.data(Qt.ItemDataRole.UserRole)
            n = len(self.data.get(t, []))
            it.setText(f"{tr(catalog.EVENT_LABELS.get(t, t))} ({t})" + (f"  · {n}" if n else ""))

    def _load_actions(self, _row: int = 0, select: int = 0) -> None:
        self.action_list.blockSignals(True)
        self.action_list.clear()
        for a in self._actions():
            self.action_list.addItem(catalog.describe_action(a.kind, a.params))
        self.action_list.blockSignals(False)
        if self.action_list.count():
            self.action_list.setCurrentRow(max(0, min(select, self.action_list.count() - 1)))
        self._load_editor()

    def _load_editor(self, _row: int = 0) -> None:
        a = self._action()
        self._loading = True
        try:
            if a is None:
                self.editor.setCurrentWidget(self.ed_empty)
            elif a.kind == "page_show":
                idx = self.page_combo.findData(a.params.get("page"))
                if idx < 0 and self.page_combo.count():
                    idx = 0
                self.page_combo.setCurrentIndex(idx)
                if idx >= 0:
                    a.params["page"] = self.page_combo.itemData(idx)
                self.editor.setCurrentWidget(self.ed_page)
            elif a.kind == "ha_action":
                self.ha_action.setText(a.params.get("action", ""))
                self.ha_entity.setText(a.params.get("entity_id", ""))
                self.editor.setCurrentWidget(self.ed_ha)
            elif a.kind == "logger":
                self.log_msg.setText(a.params.get("message", ""))
                self.editor.setCurrentWidget(self.ed_log)
            elif a.kind == "raw":
                self.raw_text.setPlainText(a.params.get("yaml", ""))
                self.editor.setCurrentWidget(self.ed_raw)
            elif a.kind == "widget_state":
                self.ws_op.setCurrentIndex(max(0, self.ws_op.findData(a.params.get("op", "hide"))))
                self.ws_id.setCurrentText(a.params.get("id", ""))
                self.editor.setCurrentWidget(self.ed_wstate)
            elif a.kind == "widget_update":
                from olvgl.presentation.properties import props_to_yaml
                self.wu_id.setCurrentText(a.params.get("id", ""))
                self.wu_props.setPlainText(props_to_yaml(a.params.get("props") or {}))
                self.wu_status.setText("")
                self.editor.setCurrentWidget(self.ed_wupdate)
            elif a.kind == "call":
                self.call_action.setText(a.params.get("action", ""))
                self.call_target.setText(a.params.get("target") or "")
                self.editor.setCurrentWidget(self.ed_call)
            elif a.kind == "delay":
                self.delay_text.setText(str(a.params.get("duration", "")))
                self.editor.setCurrentWidget(self.ed_delay)
            elif a.kind == "lambda":
                self.lambda_text.setPlainText(a.params.get("code", ""))
                self.editor.setCurrentWidget(self.ed_lambda)
            else:
                self.editor.setCurrentWidget(self.ed_none)
        finally:
            self._loading = False

    def _set_param(self, key: str, value) -> None:
        if self._loading:
            return
        a = self._action()
        if a is None:
            return
        if key == "target" and not value:
            a.params.pop(key, None)
        else:
            a.params[key] = value
        it = self.action_list.currentItem()
        if it:
            it.setText(catalog.describe_action(a.kind, a.params))

    # ------------------------------------------------------------------ acciones
    def _add_action(self, kind: str) -> None:
        if self._trigger() is None:
            return
        acts = self._actions()
        acts.append(Action(kind, catalog.default_action(kind)))
        self._refresh_triggers()
        self._load_actions(select=len(acts) - 1)

    def _remove_action(self) -> None:
        row = self.action_list.currentRow()
        acts = self._actions()
        if 0 <= row < len(acts):
            acts.pop(row)
            self._refresh_triggers()
            self._load_actions(select=row)

    def _move_action(self, delta: int) -> None:
        row = self.action_list.currentRow()
        acts = self._actions()
        j = row + delta
        if 0 <= row < len(acts) and 0 <= j < len(acts):
            acts[row], acts[j] = acts[j], acts[row]
            self._load_actions(select=j)

    def result_events(self) -> list[EventHandler]:
        return [EventHandler(t, list(acts)) for t, acts in self.data.items() if acts]


class StylesDialog(QDialog):
    """Estilos reutilizables (`style_definitions`) y tema por tipo de widget (`theme`).

    Cada cambio se aplica al momento y se puede deshacer desde el editor."""

    def __init__(self, vm, parent=None):
        super().__init__(parent)
        from olvgl.presentation.properties import YamlPropsEditor
        self.vm = vm
        self.setWindowTitle(tr("Estilos y tema"))
        self.resize(760, 480)
        tabs = QTabWidget()

        # ---- definiciones de estilo
        page = QWidget()
        self.style_list = QListWidget()
        self.style_list.currentRowChanged.connect(lambda _r: self.style_editor.refresh_force())
        add = QPushButton(tr("Nuevo"))
        add.clicked.connect(self._add_style)
        ren = QPushButton(tr("Renombrar"))
        ren.clicked.connect(self._rename_style)
        rm = QPushButton(tr("Eliminar"))
        rm.clicked.connect(self._remove_style)
        bar = QHBoxLayout()
        for b in (add, ren, rm):
            bar.addWidget(b)
        left = QVBoxLayout()
        left.addWidget(QLabel(tr("Estilos (style_definitions):")))
        left.addWidget(self.style_list, 1)
        left.addLayout(bar)
        self.style_editor = YamlPropsEditor(self._style_props, self._apply_style)
        self.style_editor.edit.setPlaceholderText(tr("bg_color: 0x1F1F29\nradius: 12\npressed:\n  bg_color: 0x333333"))
        right = QVBoxLayout()
        right.addWidget(QLabel(tr("Propiedades del estilo (con estados: pressed:, checked:…):")))
        right.addWidget(self.style_editor, 1)
        right.addWidget(QLabel(tr("Aplica un estilo a un widget desde «Estilos aplicados» en sus propiedades.")))
        lay = QHBoxLayout(page)
        lay.addLayout(left, 1)
        lay.addLayout(right, 2)
        tabs.addTab(page, tr("Estilos"))

        # ---- tema
        page = QWidget()
        self.theme_type = QComboBox()
        for sp in catalog.ALL_SPECS:
            self.theme_type.addItem(f"{tr(sp.label)} ({sp.type})", sp.type)
        self.theme_type.currentIndexChanged.connect(lambda _i: self.theme_editor.refresh_force())
        self.theme_editor = YamlPropsEditor(self._theme_props, self._apply_theme)
        v = QVBoxLayout(page)
        v.addWidget(QLabel(tr("El tema se aplica a todos los widgets de un tipo (lvgl: theme:).")))
        f = QFormLayout()
        f.addRow(tr("Tipo de widget"), self.theme_type)
        v.addLayout(f)
        v.addWidget(self.theme_editor, 1)
        self.theme_info = QLabel()
        v.addWidget(self.theme_info)
        tabs.addTab(page, tr("Tema"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        main = QVBoxLayout(self)
        main.addWidget(tabs)
        main.addWidget(buttons)
        self.tabs = tabs
        self._fill_styles()
        self._update_theme_info()

    # ---- estilos
    def current_style(self) -> str | None:
        it = self.style_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _fill_styles(self, select: str | None = None) -> None:
        cur = select or self.current_style()
        self.style_list.blockSignals(True)
        self.style_list.clear()
        for st in self.vm.project.styles:
            uses = sum(1 for _, w in self.vm.project.iter_widgets()
                       if st.id in (w.props.get("styles") if isinstance(w.props.get("styles"), list)
                                    else [w.props.get("styles")]))
            it = QListWidgetItem(f"{st.id}" + (f"  · {uses} widget(s)" if uses else ""))
            it.setData(Qt.ItemDataRole.UserRole, st.id)
            self.style_list.addItem(it)
            if st.id == cur:
                self.style_list.setCurrentItem(it)
        if self.style_list.currentRow() < 0 and self.style_list.count():
            self.style_list.setCurrentRow(0)
        self.style_list.blockSignals(False)
        self.style_editor.refresh_force()
        self.style_editor.setEnabled(self.current_style() is not None)

    def _style_props(self) -> dict:
        sid = self.current_style()
        for st in self.vm.project.styles:
            if st.id == sid:
                return dict(st.props)
        return {}

    def _apply_style(self, props: dict) -> None:
        sid = self.current_style()
        if sid:
            self.vm.set_style_props(sid, props)

    def _add_style(self) -> None:
        sid = self.vm.add_style("estilo")
        self._fill_styles(sid)

    def _rename_style(self) -> None:
        sid = self.current_style()
        if not sid:
            return
        new, ok = QInputDialog.getText(self, tr("Renombrar estilo"), tr("Nuevo id:"), text=sid)
        if ok:
            err = self.vm.rename_style(sid, new)
            if err:
                QMessageBox.warning(self, tr("Renombrar estilo"), err)
            else:
                self._fill_styles(new.strip())

    def _remove_style(self) -> None:
        sid = self.current_style()
        if sid:
            self.vm.remove_style(sid)
            self._fill_styles()

    # ---- tema
    def _theme_props(self) -> dict:
        theme = self.vm.project.lvgl_extra.get("theme") or {}
        v = theme.get(self.theme_type.currentData()) if isinstance(theme, dict) else None
        return dict(v) if isinstance(v, dict) else {}

    def _apply_theme(self, props: dict) -> None:
        self.vm.set_theme_props(self.theme_type.currentData(), props)
        self._update_theme_info()

    def _update_theme_info(self) -> None:
        theme = self.vm.project.lvgl_extra.get("theme") or {}
        types = sorted(theme) if isinstance(theme, dict) else []
        self.theme_info.setText(tr("Tipos con tema: ") + (", ".join(types) if types else "ninguno"))
