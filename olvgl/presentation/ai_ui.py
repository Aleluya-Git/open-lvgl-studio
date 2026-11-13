"""Interfaz de la IA generativa: configuración, generar página y refactorizar."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSizePolicy, QTabWidget,
                               QVBoxLayout, QWidget)

from olvgl.application import ai
from olvgl.i18n import tr, trf
from olvgl.presentation.fonts import mono_font

EXAMPLES = [
    "Página de luces con 6 luces y el termostato, tema oscuro",
    "Control de 3 persianas con deslizadores y color verde",
    "Música del salón y escenas, con barra de navegación",
    "Energía: consumo y producción solar, con la hora",
    "Ajustes de la pantalla: modo noche, sonidos y brillo",
]
REFACTOR_EXAMPLES = [
    "Tema oscuro y textos más grandes",
    "Tema claro y botones azules",
    "Redondear las esquinas",
    "Extraer estilos compartidos",
    "Poner ids descriptivos",
]


def render_page(project, screen_id: str, max_w: int = 520) -> QImage:
    """Dibuja una página como en el canvas, escalada para la vista previa."""
    from olvgl.domain.extensions import expand_project
    from olvgl.domain.layout import LayoutContext, compute_layout
    from olvgl.presentation import render as rnd
    project = expand_project(project)
    screen = project.screen(screen_id)
    d = project.display
    scale = min(1.0, max_w / max(1, d.width))
    img = QImage(max(1, int(d.width * scale)), max(1, int(d.height * scale)), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    if screen is None:
        return img
    ctx = rnd.RenderContext(project)
    lctx = LayoutContext(project, ctx.measure_text, ctx.image_size_of, {})
    boxes = compute_layout(project, screen, lctx)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(scale, scale)
    p.setClipRect(QRectF(0, 0, d.width, d.height))
    p.fillRect(QRectF(0, 0, d.width, d.height), rnd.page_background(project, screen, ctx))
    rnd.paint_tree(p, screen.widgets, boxes, ctx)
    p.end()
    return img


class _Bridge(QObject):
    done = Signal(object, object)       # (resultado, error)
    progress = Signal(str)


class _AIDialogBase(QDialog):
    """Lo común: proveedor, ejecución en segundo plano, vista previa, YAML y avisos."""

    def __init__(self, vm, settings, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.settings = settings
        self.result: ai.DesignResult | None = None
        self.busy = False
        self._bridge = _Bridge()
        self._bridge.done.connect(self._finished)
        self._bridge.progress.connect(lambda m: self.status.setText(m))
        self.provider_label = QLabel()
        btn_cfg = QPushButton(tr("Configurar IA…"))
        btn_cfg.clicked.connect(self._configure)
        top = QHBoxLayout()
        top.addWidget(self.provider_label, 1)
        top.addWidget(btn_cfg)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(520, 320)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.yaml_view = QPlainTextEdit()
        self.yaml_view.setReadOnly(True)
        self.yaml_view.setFont(mono_font(9))
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.preview, tr("Vista previa"))
        self.tabs.addTab(self.yaml_view, tr("YAML"))
        self.tabs.addTab(self.notes, tr("Avisos y notas"))
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.btn_run = QPushButton()
        self.btn_run.clicked.connect(self.run)
        self.btn_apply = QPushButton(tr("Aplicar"))
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply)
        self.buttons = QDialogButtonBox()
        self.buttons.addButton(self.btn_run, QDialogButtonBox.ButtonRole.ActionRole)
        self.buttons.addButton(self.btn_apply, QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        privacy = QLabel(tr("Con un proveedor externo se envía el diseño de LVGL (no el resto del YAML ni las claves). "
                            "El generador local funciona sin conexión."))
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color: #9E9E9E;")
        self._privacy = privacy
        self._top = top
        self._refresh_provider()

    def _layout(self, form: QWidget) -> None:
        lay = QVBoxLayout(self)
        lay.addLayout(self._top)
        lay.addWidget(form)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.status)
        lay.addWidget(self._privacy)
        lay.addWidget(self.buttons)

    def config(self) -> ai.AIConfig:
        return ai.AIConfig.from_settings(self.settings)

    def _refresh_provider(self) -> None:
        c = self.config()
        label = tr(ai.provider_label(c.provider))
        if c.provider != "local":
            label += f" · {c.model or ai.DEFAULT_MODEL.get(c.provider) or '?'}"
        self.provider_label.setText(trf("Proveedor: {p}", p=label))

    def _configure(self) -> None:
        if AISettingsDialog(self.settings, self).exec():
            self._refresh_provider()

    # ------------------------------------------------ ejecución
    def task(self, designer: ai.AIDesigner) -> ai.DesignResult:
        raise NotImplementedError

    def _designer(self, log) -> ai.AIDesigner:
        return ai.AIDesigner(ai.make_provider(self.config()), log)

    def run(self, wait: bool = False) -> None:
        """Lanza la petición en segundo plano (o en el hilo actual con wait=True)."""
        if self.busy:
            return
        self.busy = True
        self.btn_run.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.status.setText(tr("Generando…"))
        if wait:
            try:
                self._finished(self.task(self._designer(lambda m: None)), None)
            except Exception as exc:
                self._finished(None, exc)
            return

        def work():
            try:
                res = self.task(self._designer(self._bridge.progress.emit))
                self._bridge.done.emit(res, None)
            except Exception as exc:          # se muestra en el diálogo
                self._bridge.done.emit(None, exc)
        threading.Thread(target=work, daemon=True).start()

    def _finished(self, result, error) -> None:
        self.busy = False
        self.btn_run.setEnabled(True)
        if error is not None:
            self.result = None
            self.status.setText(f"<span style='color:#EF5350'>{tr('Error')}: {error}</span>")
            return
        self.result = result
        self.btn_apply.setEnabled(True)
        self.show_result(result)
        msg = trf("{n} página(s), {w} widgets, {a} intento(s)", n=len(result.page_ids),
                  w=sum(len(list(result.project.screen(p).walk())) for p in result.page_ids
                        if result.project.screen(p)), a=result.attempts)
        if result.warnings:
            msg += " · " + trf("{n} aviso(s)", n=len(result.warnings))
        self.status.setText(msg)

    def show_result(self, result: ai.DesignResult) -> None:
        if result.page_ids:
            img = render_page(result.project, result.page_ids[0], max(320, self.preview.width() - 8))
            self.preview.setPixmap(QPixmap.fromImage(img))
        self.yaml_view.setPlainText(result.yaml)
        notes = []
        if result.warnings:
            notes.append(tr("Avisos:"))
            notes += [f"  • {w}" for w in result.warnings]
        if result.notes:
            notes.append(result.notes)
        self.notes.setPlainText("\n".join(notes))

    def apply(self) -> bool:
        raise NotImplementedError


class GenerateDialog(_AIDialogBase):
    """IA › Generar página: descripción → página nueva (o sustituye la actual)."""

    def __init__(self, vm, settings, parent=None):
        super().__init__(vm, settings, parent)
        self.setWindowTitle(tr("Generar página con IA"))
        self.resize(820, 760)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(tr("Describe la página: qué controles, cuántos, entidades de Home Assistant, "
                                          "colores, tema claro u oscuro…"))
        self.prompt.setMaximumHeight(110)
        self.examples = QComboBox()
        self.examples.addItem(tr("Ejemplos…"))
        for e in EXAMPLES:
            self.examples.addItem(tr(e), tr(e))
        self.examples.activated.connect(self._example)
        self.mode = QComboBox()
        self.mode.addItem(tr("Página nueva"), "new")
        self.mode.addItem(tr("Sustituir la página actual"), "replace")
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("automático"))
        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self.mode, 1)
        row.addWidget(QLabel(tr("Nombre:")))
        row.addWidget(self.name, 1)
        form.addRow(tr("Petición:"), self.prompt)
        form.addRow("", self.examples)
        form.addRow(tr("Destino:"), row)
        self.btn_run.setText(tr("Generar"))
        self._layout(form_w)

    def _example(self, index: int) -> None:
        if index > 0:
            self.prompt.setPlainText(self.examples.itemData(index))

    def task(self, designer):
        mode = self.mode.currentData()
        return designer.generate(self.prompt.toPlainText(), self.vm.project, mode,
                                 self.vm.current_screen_id if mode == "replace" else None,
                                 self.name.text().strip() or None)

    def _finished(self, result, error) -> None:
        super()._finished(result, error)
        if result is not None:
            self.btn_run.setText(tr("Regenerar"))

    def apply(self) -> bool:
        if self.result is None:
            return False
        ok = self.vm.apply_project(tr("Generar página con IA"), self.result.project, self.result.page_ids[0])
        self.accept()
        return ok


class RefactorDialog(_AIDialogBase):
    """IA › Refactorizar: instrucción → página modificada con sus diferencias."""

    def __init__(self, vm, settings, parent=None):
        super().__init__(vm, settings, parent)
        self.page_id = vm.current_screen_id
        s = vm.project.screen(self.page_id)
        self.setWindowTitle(trf("Refactorizar «{page}» con IA", page=s.name if s else self.page_id))
        self.resize(820, 760)
        self.instruction = QLineEdit()
        self.instruction.setPlaceholderText(tr("Qué quieres cambiar"))
        self.examples = QComboBox()
        self.examples.addItem(tr("Ejemplos…"))
        for e in REFACTOR_EXAMPLES:
            self.examples.addItem(tr(e), tr(e))
        self.examples.activated.connect(
            lambda i: i > 0 and self.instruction.setText(self.examples.itemData(i)))
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setFont(mono_font(9))
        self.tabs.insertTab(1, self.diff, tr("Cambios"))
        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(tr("Instrucción:"), self.instruction)
        form.addRow("", self.examples)
        self.btn_run.setText(tr("Proponer cambios"))
        self._layout(form_w)
        if s is not None:
            self.preview.setPixmap(QPixmap.fromImage(render_page(vm.project, self.page_id)))

    def task(self, designer):
        return designer.refactor(self.instruction.text(), self.vm.project, self.page_id)

    def show_result(self, result) -> None:
        super().show_result(result)
        before = ai.page_yaml(self.vm.project, self.page_id)
        after = ai.page_yaml(result.project, self.page_id)
        self.diff.setPlainText(ai.page_diff(before, after) or tr("Sin cambios"))
        self.tabs.setCurrentWidget(self.diff if self.tabs.currentWidget() is self.yaml_view else self.tabs.currentWidget())

    def apply(self) -> bool:
        if self.result is None:
            return False
        ok = self.vm.apply_project(tr("Refactorizar página con IA"), self.result.project, self.page_id)
        self.accept()
        return ok


class AISettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(tr("Configurar IA"))
        self.resize(560, 300)
        cfg = ai.AIConfig.from_settings(settings, env={})
        self.provider = QComboBox()
        for code, label in ai.PROVIDERS.items():
            self.provider.addItem(tr(label), code)
        self.provider.setCurrentIndex(max(0, self.provider.findData(cfg.provider)))
        self.model = QLineEdit(cfg.model)
        self.key = QLineEdit(cfg.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.url = QLineEdit(cfg.base_url)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setStyleSheet("color: #9E9E9E;")
        form = QFormLayout()
        form.addRow(tr("Proveedor:"), self.provider)
        form.addRow(tr("Modelo:"), self.model)
        form.addRow(tr("Clave de la API:"), self.key)
        form.addRow(tr("URL del servicio:"), self.url)
        btn_test = QPushButton(tr("Probar la conexión"))
        btn_test.clicked.connect(self.test)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.help)
        row = QHBoxLayout()
        row.addWidget(btn_test)
        row.addWidget(self.result_label, 1)
        lay.addLayout(row)
        lay.addStretch(1)
        lay.addWidget(buttons)
        self.provider.currentIndexChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        code = self.provider.currentData()
        external = code != "local"
        for w in (self.model, self.key, self.url):
            w.setEnabled(external)
        self.model.setPlaceholderText(ai.DEFAULT_MODEL.get(code) or tr("nombre del modelo"))
        self.url.setPlaceholderText(ai.DEFAULT_URL.get(code, ""))
        self.help.setText({
            "local": tr("Plantillas para peticiones habituales de domótica. No necesita conexión ni clave."),
            "anthropic": tr("Clave en console.anthropic.com (o variable ANTHROPIC_API_KEY). "
                            "La clave se guarda sólo en este equipo."),
            "openai": tr("OpenAI, LM Studio (http://localhost:1234/v1), Ollama (http://localhost:11434/v1)… "
                         "La clave es opcional en servicios locales."),
        }.get(code, ""))

    def config(self) -> ai.AIConfig:
        return ai.AIConfig(self.provider.currentData(), self.model.text().strip(), self.key.text().strip(),
                           self.url.text().strip(), timeout=30)

    def test(self) -> bool:
        cfg = self.config()
        try:
            prov = ai.make_provider(cfg)
            answer = prov.complete("Responde sólo OK.", [{"role": "user", "content": "OK?"}]) \
                if cfg.provider != "local" else "OK"
            self.result_label.setText(f"<span style='color:#66BB6A'>{tr('Conexión correcta')}</span> "
                                      f"<small>{answer.strip()[:40]}</small>")
            return True
        except Exception as exc:
            self.result_label.setText(f"<span style='color:#EF5350'>{exc}</span>")
            return False

    def save(self) -> None:
        self.config().save(self.settings)
        self.accept()

