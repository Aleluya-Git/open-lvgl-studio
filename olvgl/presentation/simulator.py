"""Simulador profesional (Fase 6).

- Pantalla táctil como LVGL: pulsar, pulsación larga (y repetida), doble clic,
  arrastrar para desplazar contenedores y páginas, deslizar entre mosaicos y
  pestañas, `on_swipe_*`, rueda del ratón para desplazar.
- Varios dispositivos a la vez (otras resoluciones y orientaciones del mismo
  proyecto), con navegación sincronizada opcional.
- Rotación 0/90/180/270, toques visibles, grabar y reproducir una sesión,
  capturas, reposo (`on_idle`).
- Rendimiento: tiempo de dibujo y de disposición por fotograma, objetos y
  eventos, y estimación de RAM/flash del proyecto en el dispositivo.
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from olvgl.application.simulation import LONG_PRESS_MS, LONG_PRESS_REPEAT_MS, ROTATIONS, SimulatorEngine
from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain.model import DISPLAY_PRESETS, DisplayProfile
from olvgl.domain.resources import estimate_resources, human
from olvgl.i18n import tr, trf
from olvgl.presentation import render
from olvgl.presentation.icons import action_icon


class SimCanvas(QWidget):
    page_changed = Signal(str)
    frame_painted = Signal(float)              # ms de dibujo
    touch_event = Signal(str, float, float)    # press / move / release, coordenadas lógicas

    def __init__(self, engine: SimulatorEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.scale = 1.0
        self.show_touches = True
        self.idle_label = ""
        self.paint_times: list[float] = []
        self._long = QTimer(self)
        self._long.setSingleShot(True)
        self._long.setInterval(LONG_PRESS_MS)
        self._long.timeout.connect(self._on_long)
        self._repeat = QTimer(self)
        self._repeat.setInterval(LONG_PRESS_REPEAT_MS)
        self._repeat.timeout.connect(self._on_repeat)
        self.setMouseTracking(False)
        self.update_size()

    def update_size(self) -> None:
        d = self.engine.display()
        self.setFixedSize(max(1, int(d.width * self.scale)), max(1, int(d.height * self.scale)))

    def set_scale(self, s: float) -> None:
        self.scale = s
        self.update_size()
        self.update()

    # ---------------------------------------------------------------- dibujo
    def paintEvent(self, _event) -> None:
        t0 = time.perf_counter()
        p = QPainter(self)
        self.paint_to(p, self.scale, overlays=True)
        p.end()
        ms = (time.perf_counter() - t0) * 1000
        self.paint_times.append(ms)
        if len(self.paint_times) > 120:
            self.paint_times = self.paint_times[-120:]
        self.frame_painted.emit(ms)

    def image(self) -> QImage:
        """La pantalla simulada a su resolución real (sin toques ni zoom)."""
        d = self.engine.display()
        img = QImage(d.width, d.height, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        self.paint_to(p, 1.0, overlays=False)
        p.end()
        return img

    def paint_to(self, p: QPainter, scale: float, overlays: bool) -> None:
        vm = self.engine.vm
        project = self.engine.project
        ctx = render.RenderContext(project, vm.resolve_path)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(scale, scale)
        page = self.engine.page
        d = project.display
        p.setClipRect(QRectF(0, 0, d.width, d.height))
        p.fillRect(QRectF(0, 0, d.width, d.height), render.page_background(project, page, ctx))
        for sid, widgets in self.engine.layers():
            render.paint_tree(p, widgets, self.engine.boxes(sid), ctx,
                              pressed=self.engine.pressed, checked=self.engine.checked)
        if not overlays:
            return
        if self.idle_label:
            p.fillRect(QRectF(0, 0, d.width, d.height), QColor(0, 0, 0, 150))
            p.setPen(QColor("#FFFFFF"))
            render.draw_text(p, QRectF(0, 0, d.width, d.height), self.idle_label, Qt.AlignmentFlag.AlignCenter)
        if self.show_touches and self.engine.touch is not None:
            pen = QPen(QColor(124, 77, 255, 200), 3 / max(0.25, self.scale))
            p.setPen(pen)
            trail = self.engine.trail
            for a, b in zip(trail, trail[1:]):
                p.drawLine(QPointF(*a), QPointF(*b))
            x, y = self.engine.touch
            p.setBrush(QColor(124, 77, 255, 70))
            p.drawEllipse(QPointF(x, y), 18, 18)

    # ---------------------------------------------------------------- ratón
    def _pos(self, event) -> QPointF:
        pos = event.position()
        return QPointF(pos.x() / self.scale, pos.y() / self.scale)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        p = self._pos(event)
        self.touch("press", p.x(), p.y())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            p = self._pos(event)
            self.touch("move", p.x(), p.y())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        p = self._pos(event)
        self.touch("release", p.x(), p.y())

    def wheelEvent(self, event) -> None:
        p = self._pos(event)
        dy = -event.angleDelta().y() / 2
        dx = -event.angleDelta().x() / 2
        horizontal = abs(dx) > abs(dy)
        target = self.engine.scroll_container_at(p.x(), p.y(), horizontal)
        if target is None:
            event.ignore()
            return
        cid, sid = target
        ox, oy = self.engine.scroll.get(cid, (0.0, 0.0))
        self.engine.set_scroll(cid, sid, ox + dx, oy + dy)
        self.update()

    def touch(self, kind: str, x: float, y: float) -> None:
        """Un evento táctil (también lo usan la reproducción y la autoprueba)."""
        self.touch_event.emit(kind, x, y)
        old = self.engine.page_id
        if kind == "press":
            if self.engine.press(x, y):
                self._long.start()
        elif kind == "move":
            if self.engine.pressed or self.engine.touch is not None:
                self.engine.move(x, y)
                if self.engine.pressed is None:
                    self._long.stop()
        else:
            self._long.stop()
            self._repeat.stop()
            self.engine.release(x, y)
        self._after(old)

    def _on_long(self) -> None:
        old = self.engine.page_id
        self.engine.long_press()
        if self.engine.long_fired:
            self._repeat.start()
        self._after(old)

    def _on_repeat(self) -> None:
        if not self.engine.pressed:
            self._repeat.stop()
            return
        self.engine.long_press_repeat()
        self.update()

    def _after(self, old_page: str) -> None:
        if self.engine.page_id != old_page:
            self.page_changed.emit(self.engine.page_id)
        self.update()


class DeviceView(QFrame):
    """Un dispositivo simulado: cabecera (resolución, giro, captura) y pantalla."""
    closed = Signal(object)

    def __init__(self, engine: SimulatorEngine, title: str, removable: bool, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.canvas = SimCanvas(engine)
        self.title = QLabel(title)
        self.res_combo = QComboBox()
        self.res_combo.addItem(tr("Pantalla del proyecto"), None)
        from olvgl.application import displays
        for d in displays.presets():
            self.res_combo.addItem(displays.label(d), d)
        if engine.display_override is not None:
            i = next((k for k in range(self.res_combo.count())
                      if isinstance(self.res_combo.itemData(k), DisplayProfile)
                      and (self.res_combo.itemData(k).width, self.res_combo.itemData(k).height)
                      == (engine.display_override.width, engine.display_override.height)), -1)
            if i < 0:
                d = engine.display_override
                self.res_combo.addItem(f"{d.name} ({d.width}×{d.height})", d)
                i = self.res_combo.count() - 1
            self.res_combo.setCurrentIndex(i)
        self.res_combo.activated.connect(self._on_resolution)
        self.rot_combo = QComboBox()
        for r in ROTATIONS:
            self.rot_combo.addItem(f"{r}°", r)
        self.rot_combo.setCurrentIndex(ROTATIONS.index(engine.rotation))
        self.rot_combo.setToolTip(tr("Girar el dispositivo"))
        self.rot_combo.activated.connect(lambda i: self.set_rotation(self.rot_combo.itemData(i)))
        shot = QToolButton()
        shot.setIcon(action_icon("export"))
        shot.setToolTip(tr("Guardar captura de esta pantalla…"))
        shot.clicked.connect(self.save_screenshot)
        head = QHBoxLayout()
        head.setContentsMargins(4, 2, 4, 2)
        head.addWidget(self.title)
        head.addWidget(self.res_combo, 1)
        head.addWidget(self.rot_combo)
        head.addWidget(shot)
        if removable:
            close = QToolButton()
            close.setText("×")
            close.setToolTip(tr("Quitar este dispositivo"))
            close.clicked.connect(lambda: self.closed.emit(self))
            head.addWidget(close)
        self.info = QLabel()
        self.info.setStyleSheet("color: #9E9E9E;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(head)
        lay.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.info)
        lay.addStretch(1)
        self.refresh_info()

    def refresh_info(self) -> None:
        d = self.engine.display()
        self.info.setText(f"{d.width}×{d.height} · {self.engine.rotation}° · "
                          + (tr("horizontal") if self.engine.is_landscape() else tr("vertical")))

    def _on_resolution(self, i: int) -> None:
        self.engine.set_display(self.res_combo.itemData(i))
        self.canvas.update_size()
        self.refresh_info()
        self.canvas.update()

    def set_rotation(self, degrees: int) -> None:
        self.engine.set_rotation(degrees)
        self.rot_combo.setCurrentIndex(ROTATIONS.index(self.engine.rotation))
        self.canvas.update_size()
        self.refresh_info()
        self.canvas.update()

    def screenshot(self):
        """Imagen a resolución real de la pantalla simulada."""
        return self.canvas.image()

    def save_screenshot(self) -> None:
        d = self.engine.display()
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar captura"),
                                              f"{self.engine.page_id}_{d.width}x{d.height}.png", "PNG (*.png)")
        if path:
            self.screenshot().save(path)


class SimulatorWindow(QWidget):
    def __init__(self, vm: ProjectViewModel, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.vm = vm
        self.setWindowTitle(tr("Simulador — Open LVGL Studio"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.devices: list[DeviceView] = []
        self.recording: list[tuple[float, int, str, float, float]] | None = None
        self._record_t0 = 0.0
        self._last_record: list[tuple[float, int, str, float, float]] = []
        self.scale = 1.0

        # ---------------------------------------------------------- barra
        self.page_combo = QComboBox()
        self.page_combo.activated.connect(self._on_page_selected)
        self.scale_combo = QComboBox()
        for s in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
            self.scale_combo.addItem(f"{int(s * 100)} %", s)
        self.scale_combo.setCurrentIndex(3)
        self.scale_combo.activated.connect(lambda i: self.set_scale(self.scale_combo.itemData(i)))
        reset = QPushButton(tr("Reiniciar"))
        reset.clicked.connect(self.reset)
        add = QPushButton(action_icon("add_page"), tr("Añadir dispositivo"))
        add.setToolTip(tr("Probar el mismo proyecto en otra pantalla u orientación"))
        add.clicked.connect(lambda: self.add_device())
        self.chk_touch = QCheckBox(tr("Mostrar toques"))
        self.chk_touch.setChecked(True)
        self.chk_touch.toggled.connect(self._toggle_touches)
        self.chk_sync = QCheckBox(tr("Navegación sincronizada"))
        self.chk_sync.setChecked(True)
        self.btn_rec = QPushButton(tr("● Grabar"))
        self.btn_rec.setCheckable(True)
        self.btn_rec.toggled.connect(self._toggle_record)
        self.btn_play = QPushButton(tr("▶ Reproducir"))
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.replay)
        self.info = QLabel()

        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr("Página:")))
        bar.addWidget(self.page_combo)
        bar.addWidget(QLabel(tr("Zoom:")))
        bar.addWidget(self.scale_combo)
        bar.addWidget(reset)
        bar.addWidget(add)
        bar.addWidget(self.chk_touch)
        bar.addWidget(self.chk_sync)
        bar.addWidget(self.btn_rec)
        bar.addWidget(self.btn_play)
        bar.addStretch(1)
        bar.addWidget(self.info)

        # ---------------------------------------------------------- dispositivos
        self.row = QHBoxLayout()
        self.row.setSpacing(12)
        holder = QWidget()
        holder_lay = QHBoxLayout(holder)
        holder_lay.addLayout(self.row)
        holder_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: #202024; }")

        # ---------------------------------------------------------- rendimiento
        self.perf_live = QTreeWidget()
        self.perf_live.setRootIsDecorated(False)
        self.perf_live.setHeaderLabels([tr("Dispositivo"), tr("Dibujo medio"), tr("Dibujo máx."),
                                        tr("FPS posibles"), tr("Disposición"), tr("Objetos visibles"),
                                        tr("Eventos")])
        self.perf_live.setMaximumHeight(110)
        live_note = QLabel(tr("Tiempos del simulador en este PC; en el ESP32 el dibujo es más lento, "
                              "compáralos entre diseños."))
        live_note.setWordWrap(True)
        live_note.setStyleSheet("color: #9E9E9E;")
        self.perf_tree = QTreeWidget()
        self.perf_tree.setHeaderLabels([tr("Página"), tr("Objetos"), tr("Niveles"), tr("Eventos"),
                                        tr("RAM objetos")])
        self.perf_res = QLabel()
        self.perf_res.setTextFormat(Qt.TextFormat.RichText)
        self.perf_res.setWordWrap(True)
        perf = QWidget()
        pl = QVBoxLayout(perf)
        pl.addWidget(self.perf_live)
        pl.addWidget(live_note)
        pl.addWidget(self.perf_res)
        pl.addWidget(self.perf_tree, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.log_view, tr("Registro"))
        self.tabs.addTab(perf, tr("Rendimiento"))

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(scroll)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        split.setChildrenCollapsible(False)
        self.split = split

        lay = QVBoxLayout(self)
        lay.addLayout(bar)
        lay.addWidget(split)

        # dispositivo principal
        self.add_device(primary=True)

        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(500)
        self.idle_timer.timeout.connect(self._tick)
        self.idle_timer.start()

        vm.project_changed.connect(self._on_project_changed)
        vm.project_replaced.connect(self.reset)
        self._on_project_changed()
        d = vm.project.display
        self.resize(min(1500, d.width + 80), min(1000, d.height + 360))
        top = d.height + 110
        self.split.setSizes([top, max(180, self.height() - top - 60)])

    # ---------------------------------------------------------- compatibilidad
    @property
    def engine(self) -> SimulatorEngine:
        return self.devices[0].engine

    @property
    def canvas(self) -> SimCanvas:
        return self.devices[0].canvas

    # ---------------------------------------------------------- dispositivos
    def add_device(self, display: DisplayProfile | None = None, rotation: int = 0,
                   primary: bool = False) -> DeviceView:
        idx = len(self.devices)
        if not primary and display is None:
            # por defecto, otra pantalla distinta de la del proyecto
            cur = (self.vm.project.display.width, self.vm.project.display.height)
            display = next((d for d in DISPLAY_PRESETS if (d.width, d.height) != cur), DISPLAY_PRESETS[0])
        engine = SimulatorEngine(self.vm, lambda msg, i=idx: self.log(msg, i), display, rotation)
        if not primary:
            engine.page_id = self.engine.page_id
        view = DeviceView(engine, tr("Principal") if primary else trf("Dispositivo {n}", n=idx + 1),
                          removable=not primary)
        view.canvas.set_scale(self.scale)
        view.canvas.show_touches = self.chk_touch.isChecked()
        view.canvas.page_changed.connect(lambda pid, v=view: self._on_device_page(v, pid))
        view.canvas.frame_painted.connect(lambda _ms: None)
        view.canvas.touch_event.connect(lambda k, x, y, v=view: self._record(v, k, x, y))
        view.closed.connect(self.remove_device)
        self.devices.append(view)
        self.row.addWidget(view, 0, Qt.AlignmentFlag.AlignTop)
        return view

    def remove_device(self, view: DeviceView) -> None:
        if view in self.devices[1:]:
            self.devices.remove(view)
            self.row.removeWidget(view)
            view.deleteLater()

    def set_scale(self, s: float) -> None:
        self.scale = s
        for v in self.devices:
            v.canvas.set_scale(s)

    def _toggle_touches(self, on: bool) -> None:
        for v in self.devices:
            v.canvas.show_touches = on
            v.canvas.update()

    def _on_device_page(self, view: DeviceView, page_id: str) -> None:
        if self.chk_sync.isChecked():
            for v in self.devices:
                if v is not view and v.engine.page_id != page_id:
                    v.engine.go_to_page(page_id, "sincronizado")
                    v.canvas.update()
        if view is self.devices[0] or self.chk_sync.isChecked():
            self._sync_page_combo(page_id)

    # ---------------------------------------------------------- registro
    def log(self, msg: str, device: int = 0) -> None:
        prefix = "" if device == 0 else f"[#{device + 1}] "
        self.log_view.appendPlainText(f"{time.strftime('%H:%M:%S')}  {prefix}{msg}")

    def reset(self) -> None:
        for v in self.devices:
            e = v.engine
            e.reload()
            e.page_id = self.vm.current_screen_id
            e.checked.clear()
            e.pressed = None
            e.active_tabs.clear()
            e.idle_fired.clear()
            e.last_activity = time.monotonic()
            v.canvas.idle_label = ""
        self.log_view.clear()
        self.log(tr("Simulación reiniciada"))
        self._on_project_changed()

    def _on_project_changed(self) -> None:
        for v in self.devices:
            v.engine.reload()
            v.canvas.update_size()
            v.refresh_info()
            v.canvas.update()
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for s in self.vm.project.screens:
            self.page_combo.addItem(f"{s.name} ({s.id})", s.id)
        self.page_combo.blockSignals(False)
        _ = self.engine.page  # corrige la página si se ha borrado
        self._sync_page_combo(self.engine.page_id)
        self.refresh_resources()

    def _sync_page_combo(self, page_id: str) -> None:
        idx = self.page_combo.findData(page_id)
        if idx >= 0:
            self.page_combo.blockSignals(True)
            self.page_combo.setCurrentIndex(idx)
            self.page_combo.blockSignals(False)

    def _on_page_selected(self, i: int) -> None:
        pid = self.page_combo.itemData(i)
        targets = self.devices if self.chk_sync.isChecked() else self.devices[:1]
        for v in targets:
            v.engine.go_to_page(pid, tr("selector de página"))
            v.canvas.update()

    # ---------------------------------------------------------- reposo y rendimiento
    def _tick(self) -> None:
        for v in self.devices:
            new = v.engine.check_idle()
            label = ""
            if v.engine.idle_fired:
                label = trf("Reposo (on_idle {t}s) — toca para despertar",
                            t=f"{max(v.engine.idle_fired):g}")
            if new or label != v.canvas.idle_label:
                v.canvas.idle_label = label
                v.canvas.update()
        if self.tabs.currentIndex() == 1:
            self.refresh_live()

    def refresh_live(self) -> None:
        self.perf_live.clear()
        for i, v in enumerate(self.devices):
            t = v.canvas.paint_times[-30:]
            avg = sum(t) / len(t) if t else 0.0
            mx = max(t) if t else 0.0
            shown = sum(1 for sid, _ in v.engine.layers() for b in v.engine.boxes(sid).values()
                        if b.shown and not b.hidden)
            d = v.engine.display()
            fps = 1000.0 / avg if avg > 0 else 0.0
            self.perf_live.addTopLevelItem(QTreeWidgetItem([
                f"#{i + 1}  {d.width}×{d.height}  {v.engine.rotation}°", f"{avg:.1f} ms", f"{mx:.1f} ms",
                f"{fps:.0f}", f"{v.engine.last_layout_ms:.1f} ms", str(shown), str(v.engine.events_fired)]))
        for c in range(7):
            self.perf_live.resizeColumnToContents(c)

    def live_text(self) -> str:
        it = [self.perf_live.topLevelItem(i) for i in range(self.perf_live.topLevelItemCount())]
        return "\n".join(" | ".join(x.text(c) for c in range(7)) for x in it)

    def refresh_resources(self) -> None:
        rep = estimate_resources(self.engine.project, self.vm.image_size)
        self.last_resources = rep
        warn = "".join(f"<li>{w}</li>" for w in rep.warnings)
        self.perf_res.setText(
            "<b>" + tr("Estimación en el dispositivo") + "</b> — "
            + trf("{n} objetos · RAM objetos {heap} · búfer de dibujo {buf} ({pct} %) · flash imágenes y fuentes {flash}",
                  n=rep.objects, heap=human(rep.heap_bytes), buf=human(rep.draw_buffer_bytes),
                  pct=f"{rep.buffer_fraction * 100:.0f}", flash=human(rep.flash_bytes))
            + (f"<ul style='color:#FFB74D'>{warn}</ul>" if warn else ""))
        self.perf_tree.clear()
        for p in rep.pages + ([rep.top_layer] if rep.top_layer else []):
            it = QTreeWidgetItem([f"{p.name} ({p.id})", str(p.objects), str(p.depth), str(p.events), human(p.heap)])
            if p.objects > 250:
                it.setForeground(1, QColor("#FFB74D"))
            self.perf_tree.addTopLevelItem(it)
        res = QTreeWidgetItem([tr("Fuentes e imágenes"), "", "", "", human(rep.flash_bytes)])
        for fid, size, glyphs, bpp, b in rep.fonts:
            res.addChild(QTreeWidgetItem([f"{fid} · {size}px · {glyphs} glifos · {bpp} bpp", "", "", "", human(b)]))
        for iid, w, h, b in rep.images:
            res.addChild(QTreeWidgetItem([f"{iid} · {w}×{h}", "", "", "", human(b)]))
        self.perf_tree.addTopLevelItem(res)
        for c in range(5):
            self.perf_tree.resizeColumnToContents(c)

    # ---------------------------------------------------------- grabar y reproducir
    def _toggle_record(self, on: bool) -> None:
        if on:
            self.recording = []
            self._record_t0 = time.monotonic()
            self.btn_rec.setText(tr("■ Detener"))
            self.log(tr("Grabando toques…"))
        else:
            self._last_record = self.recording or []
            self.recording = None
            self.btn_rec.setText(tr("● Grabar"))
            self.btn_play.setEnabled(bool(self._last_record))
            self.log(trf("Grabados {n} eventos", n=len(self._last_record)))

    def _record(self, view: DeviceView, kind: str, x: float, y: float) -> None:
        if self.recording is not None and not getattr(self, "_replaying", False):
            self.recording.append((time.monotonic() - self._record_t0, self.devices.index(view), kind, x, y))

    def replay(self, events=None, speed: float = 1.0) -> None:
        events = list(events if events is not None else self._last_record)
        if not events:
            return
        self.log(trf("Reproduciendo {n} eventos", n=len(events)))
        self._replaying = True
        for t, dev, kind, x, y in events:
            QTimer.singleShot(int(t * 1000 / speed), lambda d=dev, k=kind, px=x, py=y: self._play_one(d, k, px, py))
        end = int(events[-1][0] * 1000 / speed) + 50
        QTimer.singleShot(end, lambda: setattr(self, "_replaying", False))

    def _play_one(self, dev: int, kind: str, x: float, y: float) -> None:
        if 0 <= dev < len(self.devices):
            self.devices[dev].canvas.touch(kind, x, y)

    # ---------------------------------------------------------- pruebas
    def click(self, widget_id: str, device: int = 0) -> None:
        """Simula un clic completo en el centro de un widget (usado por la autoprueba)."""
        v = self.devices[device]
        loc = v.engine.project.locate(widget_id)
        if loc is None:
            return
        b = v.engine.boxes(loc.screen.id).get(widget_id)
        if b is None:
            return
        cx, cy = b.rect.x + b.rect.w / 2, b.rect.y + b.rect.h / 2
        v.canvas.touch("press", cx, cy)
        v.canvas.touch("release", cx, cy)

    def swipe(self, x0: float, y0: float, x1: float, y1: float, device: int = 0, steps: int = 8) -> None:
        c = self.devices[device].canvas
        c.touch("press", x0, y0)
        for i in range(1, steps + 1):
            c.touch("move", x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        c.touch("release", x1, y1)

    def save_screenshots(self, folder: str, prefix: str = "sim") -> list[str]:
        out = []
        for i, v in enumerate(self.devices):
            d = v.engine.display()
            path = os.path.join(folder, f"{prefix}_{i + 1}_{d.width}x{d.height}.png")
            v.screenshot().save(path)
            out.append(path)
        return out
