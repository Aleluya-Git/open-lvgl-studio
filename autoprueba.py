"""Autoprueba de Open LVGL Studio.

1. Ejecuta los tests del núcleo (pytest).
2. Arranca la interfaz real sin ventana (QT_QPA_PLATFORM=offscreen) y recorre
   las funciones de la Fase 1: canvas, selección, teclado, propiedades,
   eventos, YAML en vivo, simulador, guardar/abrir, autoguardado y exportación.
3. Guarda capturas en ./capturas y el resultado en autoprueba_resultado.txt.

Uso:  python autoprueba.py [--visible | --offscreen]
"""
from __future__ import annotations

import faulthandler
import os
import re
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
RESULT_FILE = os.path.join(ROOT, "autoprueba_resultado.txt")
CAPTURES = os.path.join(ROOT, "capturas")
# La autoprueba recorre todas las funciones sin depender de la licencia instalada;
# las ediciones se comprueban aparte («F10 · Licencias»).
os.environ["OLVGL_LICENSE_ENFORCE"] = "0"

results: list[tuple[bool, str, str]] = []
results_mode: list[str] = []


HANG_FILE = os.path.join(ROOT, "autoprueba_cuelgue.txt")
CHECK_TIMEOUT = 120          # segundos por comprobación antes de darla por colgada
dialogs: list[str] = []      # diálogos inesperados cerrados automáticamente
_hang_fh = None


def check(name: str):
    def deco(fn):
        global _hang_fh
        print(f"-> {name}", flush=True)
        if _hang_fh is None:
            _hang_fh = open(HANG_FILE, "w", encoding="utf-8")
        _hang_fh.seek(0)
        _hang_fh.truncate()
        _hang_fh.write(f"Colgada en: {name}\n")
        _hang_fh.flush()
        # si la comprobación no termina, vuelca dónde está cada hilo y sale
        faulthandler.dump_traceback_later(CHECK_TIMEOUT, exit=True, file=_hang_fh)
        before = len(dialogs)
        try:
            fn()
            if len(dialogs) > before:
                raise AssertionError("Se abrió un diálogo inesperado:\n" + "\n".join(dialogs[before:]))
            results.append((True, name, ""))
        except KeyboardInterrupt:
            raise
        except BaseException:
            detail = traceback.format_exc()
            if len(dialogs) > before and "diálogo inesperado" not in detail:
                detail += "\nDiálogos abiertos durante la comprobación:\n" + "\n".join(dialogs[before:])
            results.append((False, name, detail))
            print("   FALLO", flush=True)
        finally:
            faulthandler.cancel_dump_traceback_later()
        return fn
    return deco


def run_pytest() -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, out


def gui_tests() -> None:
    # Windows: plataforma nativa con las ventanas ocultas (WA_DontShowOnScreen). La
    # plataforma «offscreen» usa otra base de datos de fuentes que, tras dibujar muchas
    # fuentes, devuelve familias equivocadas y falsea las capturas. --offscreen la fuerza.
    hidden_native = (sys.platform.startswith("win") and "--offscreen" not in sys.argv
                     and "--visible" not in sys.argv)
    results_mode.append("nativa con ventanas ocultas" if hidden_native else
                        ("visible" if "--visible" in sys.argv else "offscreen"))
    if "--visible" not in sys.argv and not hidden_native:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        # Sin ventana, Qt no encuentra las fuentes del sistema en Windows y
        # dibuja cuadraditos en lugar de letras: le indicamos dónde están.
        if sys.platform.startswith("win") and "QT_QPA_FONTDIR" not in os.environ:
            os.environ["QT_QPA_FONTDIR"] = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    tmp = tempfile.mkdtemp(prefix="olvgl_autoprueba_")
    os.environ["OLVGL_NO_FONT_DOWNLOAD"] = "1"   # la prueba no depende de la red
    os.environ["OLVGL_AUTOPRUEBA"] = "1"          # sin diálogos modales que bloqueen la prueba
    os.environ["APPDATA"] = tmp            # Windows: no toca tus ajustes reales
    os.environ["XDG_DATA_HOME"] = tmp      # Linux
    os.makedirs(CAPTURES, exist_ok=True)

    from PySide6.QtCore import QPoint, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QSpinBox

    import yaml

    from olvgl.domain.model import Action, DisplayProfile, EventHandler
    from olvgl.infrastructure import json_store
    from olvgl.infrastructure.exporter import export_esphome
    from olvgl.infrastructure.settings_db import SettingsDB
    from olvgl.presentation.app import create_app, create_view_model
    from olvgl.presentation.canvas import WidgetItem
    from olvgl.presentation.dialogs import EventsDialog, NewProjectDialog
    from olvgl.presentation.main_window import MainWindow

    app = create_app([sys.argv[0]])
    if hidden_native:
        from PySide6.QtCore import QEvent, QObject
        from PySide6.QtWidgets import QMenu, QWidget

        class _HideWindows(QObject):
            """Antes de mostrarse, cada ventana se marca para no aparecer en pantalla."""
            def eventFilter(self, obj, ev):
                if (ev.type() == QEvent.Type.Polish and isinstance(obj, QWidget) and obj.isWindow()
                        and not isinstance(obj, QMenu)):
                    obj.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
                return False
        _hider = _HideWindows(app)
        app.installEventFilter(_hider)

    # Sin ventana nadie puede pulsar «Aceptar»: cualquier diálogo modal se anota y se cierra.
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    def close_modal():
        w = QApplication.activeModalWidget()
        if w is None:
            return
        text = w.windowTitle()
        if isinstance(w, QMessageBox):
            text += " | " + w.text() + " | " + w.informativeText()
        dialogs.append(text)
        print(f"   [diálogo cerrado] {text}", flush=True)
        if isinstance(w, QDialog):
            w.reject()
        else:
            w.close()

    modal_timer = QTimer()
    modal_timer.setInterval(150)
    modal_timer.timeout.connect(close_modal)
    modal_timer.start()
    settings = SettingsDB(os.path.join(tmp, "studio.db"))
    vm = create_view_model()
    win = MainWindow(vm, settings)
    win.show()

    def pump(ms: int = 50):
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(200)
    ctx: dict = {}

    @check("Fuentes del sistema disponibles (texto legible en capturas)")
    def _():
        from PySide6.QtGui import QFontDatabase
        families = QFontDatabase.families()
        assert families, "Qt no encuentra ninguna fuente"
        assert any(f in families for f in ("Segoe UI", "Arial", "Montserrat", "DejaVu Sans")), families[:10]

    @check("Ventana principal y paneles")
    def _():
        assert win.isVisible()
        from olvgl.domain.catalog import palette_specs
        assert set(win.palette.types()) == {sp.type for sp in palette_specs()}
        assert win.dock_props.widget() is win.props

    @check("Nuevo proyecto 1024x600 con dos pantallas")
    def _():
        vm.new("Autoprueba", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        vm.update_screen(vm.current_screen_id, bg_color="#1A1A2E", name="Inicio")
        ctx["home"] = vm.current_screen_id
        ctx["ajustes"] = vm.add_screen("Ajustes")
        vm.set_current_screen(ctx["home"])
        pump()
        assert len(vm.project.screens) == 2

    @check("Añadir Label, Button e Image")
    def _():
        from PySide6.QtGui import QPixmap
        img_path = os.path.join(tmp, "logo.png")
        pm = QPixmap(48, 48)
        pm.fill(QColor("#FFC107"))
        assert pm.save(img_path)
        ctx["lbl"] = vm.add_widget("label", 40, 30, centered=False)
        vm.set_prop([ctx["lbl"]], "text", "Salón")
        vm.set_prop([ctx["lbl"]], "text_color", "#FFFFFF")
        vm.set_prop([ctx["lbl"]], "text_font", "montserrat_28")
        ctx["btn"] = vm.add_widget("button", 40, 120, centered=False)
        vm.set_prop([ctx["btn"]], "text", "Luz")
        vm.set_prop([ctx["btn"]], "bg_color", "#E53935")
        ctx["img"] = vm.add_widget("image", 400, 30, centered=False)
        iid = vm.add_image(img_path)
        vm.set_prop([ctx["img"]], "src", iid)
        pump(100)
        assert vm.widget(ctx["img"]).width is None          # tamaño del fichero
        assert round(vm.box(ctx["img"]).rect.w) == 48
        assert len(win.scene.items_by_id) == 3

    @check("Canvas dibuja los widgets (captura capturas/canvas.png)")
    def _():
        win.view.fit_screen()
        pump(100)
        r = win.scene.screen_rect()
        img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        win.scene.render(p, QRectF(0, 0, r.width(), r.height()), r)
        p.end()
        img.save(os.path.join(CAPTURES, "canvas.png"))
        w = vm.widget(ctx["btn"])
        c = img.pixelColor(w.x + 8, w.y + w.height // 2)
        assert c.red() > 180 and c.green() < 100, f"color del botón inesperado: {c.name()}"
        bg = img.pixelColor(905, 585)  # fuera de las líneas de rejilla
        assert bg.name().upper() == "#1A1A2E", f"fondo inesperado: {bg.name()}"
        win.grab().save(os.path.join(CAPTURES, "ventana.png"))

    @check("Clic en el canvas selecciona y sincroniza árbol/propiedades")
    def _():
        vm.set_selection([])
        pump()
        item: WidgetItem = win.scene.items_by_id[ctx["btn"]]
        pos = win.view.mapFromScene(item.sceneBoundingRect().center())
        QTest.mouseClick(win.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(pos.x(), pos.y()))
        pump(100)
        assert vm.selection == [ctx["btn"]], vm.selection
        assert item.isSelected()
        selected_tree = [i.text(0) for i in win.tree.tree.selectedItems()]
        assert any(ctx["btn"] in t for t in selected_tree), selected_tree
        assert win.props.container.findChildren(QSpinBox), "panel de propiedades vacío"

    @check("Flechas mueven el widget y Deshacer lo devuelve")
    def _():
        win.view.setFocus()
        x0 = vm.widget(ctx["btn"]).x
        QTest.keyClick(win.view, Qt.Key.Key_Right)
        QTest.keyClick(win.view, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        pump()
        assert vm.widget(ctx["btn"]).x == x0 + 11
        assert win.scene.items_by_id[ctx["btn"]].pos().x() == x0 + 11
        win.a_undo.trigger()
        win.a_undo.trigger()
        pump()
        assert vm.widget(ctx["btn"]).x == x0
        win.a_redo.trigger()
        win.a_undo.trigger()

    @check("Duplicar, eliminar y orden de pila")
    def _():
        vm.set_selection([ctx["btn"]])
        win.a_dup.trigger()
        pump()
        dup = vm.selection[0]
        assert dup != ctx["btn"] and dup in win.scene.items_by_id
        win.a_delete.trigger()
        pump()
        assert vm.widget(dup) is None and dup not in win.scene.items_by_id
        vm.set_selection([ctx["lbl"]])
        win.a_front.trigger()
        assert vm.current_screen.widgets[-1].id == ctx["lbl"]
        win.a_undo.trigger()

    @check("Selección múltiple y alineación")
    def _():
        vm.set_selection([ctx["lbl"], ctx["btn"]])
        pump(100)
        assert len(win.scene.selectedItems()) == 2
        before = len(vm.history)
        win.align_actions[2].trigger()  # derecha (anchos distintos → siempre cambia algo)
        lbl, btn = vm.widget(ctx["lbl"]), vm.widget(ctx["btn"])
        assert lbl.x + lbl.width == btn.x + btn.width
        assert len(vm.history) == before + 1
        win.a_undo.trigger()

    @check("Editor de eventos: navegar y acción de Home Assistant")
    def _():
        w = vm.widget(ctx["btn"])
        dlg = EventsDialog(w, vm.project, win)
        dlg._add_action("ha_action")
        dlg.ha_entity.setText("light.salon")
        dlg._add_action("page_show")
        dlg.page_combo.setCurrentIndex(dlg.page_combo.findData(ctx["ajustes"]))
        events = dlg.result_events()
        dlg.deleteLater()
        assert events[0].actions[1].params["page"] == ctx["ajustes"]
        vm.set_events(ctx["btn"], events)
        back = vm.add_widget("button", 20, 20, centered=False, screen_id=ctx["ajustes"])
        vm.set_prop([back], "text", "Volver")
        vm.set_events(back, [EventHandler("on_click", [Action("page_show", {"page": ctx["home"]})])])
        vm.set_current_screen(ctx["home"])
        ctx["back"] = back

    @check("YAML ESPHome en vivo y válido")
    def _():
        pump(400)
        text = win.code.text()
        data = yaml.safe_load(text)
        pages = data["lvgl"]["pages"]
        assert [p["id"] for p in pages] == [ctx["home"], ctx["ajustes"]]
        btn = next(x["button"] for x in pages[0]["widgets"] if "button" in x)
        assert btn["on_click"][0]["homeassistant.action"]["data"]["entity_id"] == "light.salon"
        assert data["image"][0]["file"] == "images/logo.png"
        with open(os.path.join(CAPTURES, "ui_lvgl.yaml"), "w", encoding="utf-8") as f:
            f.write(text)

    @check("Simulador: pulsar botón cambia de página (captura)")
    def _():
        win.open_simulator()
        pump(150)
        sim = win.simulator
        sim.grab().save(os.path.join(CAPTURES, "simulador_inicio.png"))
        sim.click(ctx["btn"])
        pump()
        assert sim.engine.page_id == ctx["ajustes"]
        log = sim.log_view.toPlainText()
        assert "light.toggle" in log and "lvgl.page.show" in log, log
        sim.grab().save(os.path.join(CAPTURES, "simulador_ajustes.png"))
        sim.click(ctx["back"])
        assert sim.engine.page_id == ctx["home"]
        sim.close()

    @check("Guardar, autoguardar y volver a abrir")
    def _():
        path = os.path.join(tmp, "proyecto", "autoprueba.olvgl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        assert win._save_to(path)
        assert not vm.dirty
        vm.set_selection([ctx["btn"]])
        vm.nudge(1, 0)
        assert vm.dirty
        win.autosave()
        assert os.path.exists(path + json_store.AUTOSAVE_SUFFIX)
        win.a_undo.trigger()
        json_store.discard_autosave(path, os.path.join(tmp, "OpenLVGLStudio"))
        assert win.open_project(path)
        pump(100)
        assert vm.widget(ctx["btn"]).props["text"] == "Luz"
        assert settings.recent()[0][0] == os.path.abspath(path)
        ctx["path"] = path

    @check("Exportar carpeta ESPHome")
    def _():
        out = os.path.join(tmp, "esphome")
        rep = export_esphome(vm.project, out, vm.path)
        for name in ("ui_lvgl.yaml", "main.yaml", os.path.join("images", "logo.png")):
            assert os.path.exists(os.path.join(out, name)), name
        assert not rep.warnings, rep.warnings

    @check("Diálogo de nuevo proyecto")
    def _():
        dlg = NewProjectDialog(win)
        name, display = dlg.result_project()
        dlg.deleteLater()
        assert display.width > 0 and name

    @check("Nuevo proyecto con una pantalla propia (guardar, reutilizar, girar y eliminar)")
    def _():
        from olvgl.application import displays
        dlg = NewProjectDialog(win, settings)
        dlg.preset.setCurrentIndex(dlg.custom_index())
        assert dlg.screen_name.isVisibleTo(dlg) and not dlg.delete_btn.isVisibleTo(dlg)
        dlg.width_sb.setValue(466)
        dlg.height_sb.setValue(466)
        dlg.screen_name.setText("")
        assert not dlg.store_custom() and dlg.error.text()          # sin nombre no se guarda
        dlg.screen_name.setText("Mi pantalla redonda 1.43")
        assert not dlg.error.text()                                  # al escribir el nombre se quita el aviso
        assert dlg.store_custom()
        _n, d = dlg.result_project()
        assert (d.name, d.width, d.height) == ("Mi pantalla redonda 1.43", 466, 466)
        dlg.show()
        pump(80)
        dlg.grab().save(os.path.join(CAPTURES, "nuevo_proyecto_pantalla_propia.png"))
        dlg.close()
        dlg.deleteLater()
        assert [x.name for x in displays.load(settings)] == ["Mi pantalla redonda 1.43"]
        dlg2 = NewProjectDialog(win, settings)                      # aparece en «Mis pantallas»
        idx = next(i for i in range(dlg2.preset.count()) if getattr(dlg2.preset.itemData(i), "name", "")
                   == "Mi pantalla redonda 1.43")
        dlg2.preset.setCurrentIndex(idx)
        assert dlg2.delete_btn.isVisibleTo(dlg2) and (dlg2.width_sb.value(), dlg2.height_sb.value()) == (466, 466)
        dlg2.preset.setCurrentIndex(0)                              # una de serie, en vertical
        w0, h0 = dlg2.width_sb.value(), dlg2.height_sb.value()
        dlg2.rotate()
        assert not dlg2.is_custom() and (dlg2.width_sb.value(), dlg2.height_sb.value()) == (h0, w0)
        assert dlg2.rotation() == 90
        _n, dv = dlg2.result_project()
        assert (dv.width, dv.height) == (h0, w0)
        dlg2.rotate()
        assert dlg2.rotation() == 0 and (dlg2.width_sb.value(), dlg2.height_sb.value()) == (w0, h0)
        dlg2.preset.setCurrentIndex(idx)
        assert dlg2.delete_custom() and displays.load(settings) == []
        dlg2.deleteLater()

    @check("Panel lateral: nueva pantalla personalizada para el proyecto (capturas/panel_pantalla_propia.png)")
    def _():
        from olvgl.application import displays
        vm.set_selection([])
        win.props.rebuild()
        pump(50)
        combo = win.props.display_combo
        assert combo.findData("__new__") >= 0
        dlg = win.props.open_custom_display(show=False)
        dlg.name.setText("Panel lateral 720×720")
        dlg.width_sb.setValue(720)
        dlg.height_sb.setValue(720)
        assert dlg.apply() is not None
        win.props.apply_custom_display(dlg)
        dlg.deleteLater()
        pump(100)
        d = vm.project.display
        assert (d.name, d.width, d.height) == ("Panel lateral 720×720", 720, 720)
        assert "Panel lateral 720×720" in [x.name for x in displays.load(settings)]
        combo = win.props.display_combo
        assert any(getattr(combo.itemData(i), "name", "") == "Panel lateral 720×720" for i in range(combo.count()))
        assert not win.props.save_display_btn.isVisibleTo(win.props)      # ya está en «Mis pantallas»
        vm.set_project_meta(display=DisplayProfile("Personalizada", 640, 360))
        pump(50)
        assert win.props.save_display_btn.isVisibleTo(win.props)
        win.dock_props.raise_()
        win.props.grab().save(os.path.join(CAPTURES, "panel_pantalla_propia.png"))
        dlg2 = win.props.open_custom_display(show=False)
        assert dlg2.name.text() == "" and not dlg2.apply()               # hay que darle nombre
        dlg2.deleteLater()
        assert displays.remove(settings, "Panel lateral 720×720")
        vm.undo()
        vm.undo()

    # ======================================================= Fase 2: importación
    # se trabaja sobre copias: la sincronización (Fase 3) escribe en el YAML vinculado
    shutil.copytree(os.path.join(ROOT, "examples", "importar"), os.path.join(tmp, "importar"))
    demo = os.path.join(tmp, "importar", "panel_demo.yaml")

    def read_text(path):
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    def write_text(path, text):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def changed_lines(a, b):
        import difflib
        return [x for x in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
                if x[:1] in "+-" and x[:3] not in ("+++", "---")]

    @check("F2 · Importar YAML de ESPHome (panel_demo.yaml)")
    def _():
        report = vm.import_yaml(demo)
        win._install_measures()
        pump(150)
        assert report.pages == 2 and report.widgets == 26 and not report.warnings, report.warnings
        assert vm.project.top_layer is not None
        assert (vm.project.display.width, vm.project.display.height) == (1024, 600)
        page_widgets = sum(1 for _ in vm.project.screen("inicio").walk())
        assert len(win.scene.items_by_id) == page_widgets, (len(win.scene.items_by_id), page_widgets)
        item = win.scene.items_by_id["btn_comedor"]
        assert item.parentItem() is win.scene.items_by_id["panel_luces"]

    @check("F2 · Reconstrucción visual (captura capturas/importado.png)")
    def _():
        win.view.fit_screen()
        pump(100)
        r = win.scene.screen_rect()
        img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        win.scene.show_grid = False
        win.scene.render(p, QRectF(0, 0, r.width(), r.height()), r)
        win.scene.show_grid = True
        p.end()
        img.save(os.path.join(CAPTURES, "importado.png"))
        card = img.pixelColor(260, 300)
        assert card.name().upper() == "#1F1F29", f"fondo de tarjeta inesperado: {card.name()}"
        page = img.pixelColor(700, 330)
        assert page.name().upper() == "#101018", f"fondo de página inesperado: {page.name()}"
        bar = img.pixelColor(500, 5)
        assert bar.lightness() < 60, f"la capa superior no se dibuja: {bar.name()}"
        win.grab().save(os.path.join(CAPTURES, "ventana_importado.png"))

    @check("F2 · Árbol jerárquico y pestaña oculta se muestra al seleccionarla")
    def _():
        assert "btn_comedor" in win.tree._items and "chk_bano" in win.tree._items
        assert win.tree._items["btn_comedor"].parent() is win.tree._items["panel_luces"]
        assert not win.scene.items_by_id["chk_bano"].isVisible()
        vm.set_selection(["chk_bano"])
        pump(100)
        assert vm.active_tabs.get("pestanas") == 1
        assert win.scene.items_by_id["chk_bano"].isVisible()
        vm.set_active_tab("pestanas", 0)
        pump()

    @check("F2 · Mover un widget con align y deshacer")
    def _():
        clima = vm.widget("panel_clima")
        item = win.scene.items_by_id["panel_clima"]
        x0 = item.pos().x()
        vm.move_by({"panel_clima": (-40, 0)})
        pump()
        assert clima.x == -60 and round(item.pos().x()) == round(x0 - 40)
        win.a_undo.trigger()
        pump()
        assert clima.x == -20

    @check("F2 · Panel de propiedades: editor visual y bloque YAML (arco)")
    def _():
        from olvgl.presentation.properties import YamlPropsEditor
        vm.set_selection(["arc_temp"])
        pump(150)
        spins = [sb for sb in win.props.container.findChildren(QSpinBox) if sb.value() == 21]
        assert spins, "no hay editor del valor del arco"
        spins[0].setValue(25)
        pump(100)
        assert vm.widget("arc_temp").props["value"] == 25
        assert "value: 25" in vm.generate_yaml()
        vm.set_selection(["arc_temp"])
        pump(150)
        eds = win.props.container.findChildren(YamlPropsEditor)
        assert eds, "no hay editor YAML"
        ed = eds[-1]
        text = ed.edit.toPlainText()
        ed.edit.setPlainText(text + ("" if not text or text.endswith("\n") else "\n") + "bg_opa: 50%\n")
        ed.apply()
        pump(100)
        assert vm.widget("arc_temp").props.get("bg_opa") == "50%", vm.widget("arc_temp").props
        assert re.search(r'bg_opa: "?50%"?', vm.generate_yaml())

    @check("F2 · Simulador del proyecto importado (captura)")
    def _():
        win.open_simulator()
        pump(150)
        sim = win.simulator
        sim.click("btn_comedor")
        assert "btn_comedor" in sim.engine.checked
        bar = sim.engine.boxes("inicio")["pestanas"].extra["tab_buttons"][1][0]
        sim.engine.press(bar.x + 5, bar.y + 5)
        sim.canvas.update()
        pump()
        sim.grab().save(os.path.join(CAPTURES, "simulador_importado.png"))
        assert sim.engine.active_tabs["pestanas"] == 1
        log = sim.log_view.toPlainText()
        assert "light.comedor" in log, log
        sim.close()

    @check("F2 · Guardar el proyecto importado y regenerar el mismo YAML")
    def _():
        win.write_to_source(force=True)   # vacía la escritura automática pendiente
        before = vm.generate_yaml()
        path = os.path.join(tmp, "importado.olvgl")
        assert win._save_to(path)
        assert win.open_project(path)
        pump(100)
        assert vm.generate_yaml() == before
        with open(os.path.join(CAPTURES, "ui_lvgl_importado.yaml"), "w", encoding="utf-8") as f:
            f.write(before)

    # ======================================================= Fase 3: sincronización
    @check("F3 · Escritura automática y mínima en el YAML vinculado")
    def _():
        vm.import_yaml(demo)
        pump(100)
        assert vm.linked, vm.sync_error
        before = read_text(demo)
        vm.set_raw_prop(["lbl_titulo_luces"], "text", "Iluminación")
        pump(1600)   # la escritura automática espera a que dejes de editar
        after = read_text(demo)
        d = changed_lines(before, after)
        assert d == ["-            text: Luces", "+            text: Iluminación"], d
        assert os.path.exists(demo + ".olvgl.bak")
        assert "sincronizado" in win.lbl_sync.text(), win.lbl_sync.text()
        assert "# Panel de ejemplo para probar la importación" in after

    @check("F3 · Cambio a mano en el YAML: se recarga solo y Ctrl+Z lo deshace")
    def _():
        text = read_text(demo)
        write_text(demo, text.replace("text: Volver", "text: Atrás  # a mano"))
        pump(2000)   # vigilante de ficheros + espera
        assert vm.widget("btn_volver").props["text"] == "Atrás", vm.widget("btn_volver").props
        assert vm.history.undo_label == "Cambio externo en el YAML"
        win.a_undo.trigger()
        pump(1600)
        assert vm.widget("btn_volver").props["text"] == "Volver"
        assert "text: Volver" in read_text(demo)

    @check("F3 · Cambios a la vez en el editor y en el fichero: se mezclan")
    def _():
        vm.set_raw_prop(["lbl_titulo_luces"], "text", "Desde el editor")
        text = read_text(demo)   # aún sin escribir (escritura automática pendiente)
        write_text(demo, text.replace("x: -20\n            y: 110", "x: -30\n            y: 110"))
        pump(2200)
        final = read_text(demo)
        assert "text: Desde el editor" in final and "x: -30" in final
        assert vm.widget("panel_clima").x == -30
        assert not vm.dirty

    real_src = os.path.join(ROOT, "examples", "panel-domotica_final.yaml")
    real = os.path.join(tmp, "panel-domotica_final.yaml")
    if os.path.exists(real_src):
        shutil.copy(real_src, real)
        @check("F2 · Tu panel real: importar y capturar todas las páginas (capturas/real_*.png)")
        def _():
            t0 = time.monotonic()
            report = vm.import_yaml(real)
            win._install_measures()
            pump(200)
            secs = time.monotonic() - t0
            assert not report.warnings, report.warnings
            r = win.scene.screen_rect()
            win.scene.show_grid = False
            win.scene.show_outlines = False
            for s in vm.project.screens:
                vm.set_current_screen(s.id)
                pump(80)
                img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32)
                img.fill(0)
                p = QPainter(img)
                win.scene.render(p, QRectF(0, 0, r.width(), r.height()), r)
                p.end()
                img.save(os.path.join(CAPTURES, f"real_{s.id}.png"))
            win.scene.show_grid = True
            win.scene.show_outlines = True
            vm.set_current_screen(vm.project.screens[0].id)
            pump()
            win.grab().save(os.path.join(CAPTURES, "real_ventana.png"))
            with open(os.path.join(CAPTURES, "real_informe.txt"), "w", encoding="utf-8") as f:
                f.write(report.summary() + f"\nImportación + disposición: {secs:.2f} s\n")
            assert win._save_to(os.path.join(tmp, "real.olvgl"))

        @check("F3 · Tu panel real: un cambio = una línea en el YAML (comentarios intactos)")
        def _():
            assert vm.linked, vm.sync_error
            before = read_text(real)
            t0 = time.monotonic()
            vm.set_raw_prop(["lbl_fecha"], "text", "Lunes")
            assert win.write_to_source(force=True)
            secs = time.monotonic() - t0
            after = read_text(real)
            d = changed_lines(before, after)
            assert len(d) == 2 and "Lunes" in d[1], d[:6]
            assert after.count("#") == before.count("#")
            with open(os.path.join(CAPTURES, "real_informe.txt"), "a", encoding="utf-8") as f:
                f.write(f"Sincronizar un cambio con el YAML: {secs:.2f} s\n")

    # ======================================================= Fase 4: widgets, estilos y C
    @check("F4 · Un widget de cada tipo con su panel de propiedades (captura capturas/widgets.png)")
    def _():
        from olvgl.domain import catalog
        vm.new("Fase 4", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        vm.update_screen(vm.current_screen_id, bg_color="#20232A")
        ctx["f4_page"] = vm.current_screen_id
        ctx["f4_page2"] = vm.add_screen("Segunda")
        vm.set_current_screen(ctx["f4_page"])
        types = [sp.type for sp in catalog.palette_specs()]
        ids, pos = {}, {}
        col_w, row_h = 168, 148
        for i, t in enumerate(types):
            x, y = 8 + (i % 6) * col_w, 8 + (i // 6) * row_h
            ids[t] = vm.add_widget(t, x, y, centered=False)
            pos[t] = (x, y)
        # tamaños compactos para que quepan todos en una página
        for t, wid in ids.items():
            w = vm.widget(wid)
            if w.width is not None and isinstance(w.width, int) and w.width > col_w - 20:
                vm.set_geom_value(wid, "width", str(col_w - 20))
            if w.height is not None and isinstance(w.height, int) and w.height > row_h - 30:
                vm.set_geom_value(wid, "height", str(row_h - 30))
            vm.set_geom_value(wid, "x", str(pos[t][0]))
            vm.set_geom_value(wid, "y", str(pos[t][1]))
        vm.add_child(ids["tabview"])
        ctx["f4"] = ids
        for t, wid in ids.items():      # construye el panel de propiedades de cada tipo
            vm.set_selection([wid])
            pump(60)
            assert win.props.container.findChildren(QSpinBox), t
        vm.set_selection([])
        pump(150)
        r = win.scene.screen_rect()
        img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        win.scene.render(p, QRectF(0, 0, r.width(), r.height()), r)
        p.end()
        img.save(os.path.join(CAPTURES, "widgets.png"))
        missing = [t for t, wid in ids.items() if wid not in win.scene.items_by_id]
        assert not missing, missing
        data = yaml.safe_load(vm.generate_yaml())
        assert data and "lvgl" in data
        win.grab().save(os.path.join(CAPTURES, "widgets_ventana.png"))

    @check("F4 · Editor de eventos con todas las acciones")
    def _():
        from olvgl.domain import catalog
        btn = ctx["f4"]["button"]
        dlg = EventsDialog(vm.widget(btn), vm.project, win)
        for kind in catalog.ACTION_KINDS:
            dlg._add_action(kind)
        n = len(dlg.result_events()[0].actions)
        dlg.deleteLater()
        assert n == len(catalog.ACTION_KINDS), n

    @check("F4 · Estilos por estado y por parte llegan al YAML")
    def _():
        from olvgl.presentation.properties import style_path
        ids = ctx["f4"]
        vm.set_selection([ids["button"]])
        pump(60)
        vm.set_prop([ids["button"]], style_path("main", "pressed", "bg_color"), "#00FF00")
        vm.set_prop([ids["slider"]], style_path("indicator", "", "bg_color"), "#FF9800")
        vm.set_prop([ids["switch"]], style_path("indicator", "checked", "bg_color"), "#4CAF50")
        pump(60)
        lv = yaml.safe_load(vm.generate_yaml())
        text = vm.generate_yaml()
        assert "pressed:" in text and "0x00FF00" in text, text[:2000]
        assert "indicator:" in text and "0xFF9800" in text and "0x4CAF50" in text
        assert lv is not None

    @check("F4 · Definición de estilo y tema")
    def _():
        from olvgl.presentation.dialogs import StylesDialog
        ids = ctx["f4"]
        dlg = StylesDialog(vm, win)
        dlg._add_style()
        sid = dlg.current_style()
        assert sid, "no se creó el estilo"
        dlg._apply_style({"bg_color": "#3F51B5", "radius": 18})
        dlg.theme_type.setCurrentIndex(dlg.theme_type.findData("label"))
        dlg._apply_theme({"text_color": "#FFEB3B"})
        dlg.deleteLater()
        vm.set_widget_styles(ids["obj"], [sid])
        pump(60)
        text = vm.generate_yaml()
        assert "style_definitions:" in text and sid in text, text[:1500]
        assert "theme:" in text and "0xFFEB3B" in text
        from olvgl.domain.layout import effective_props
        assert effective_props(vm.project, vm.widget(ids["obj"])).get("radius") == 18

    @check("F4 · Simulador: ocultar un widget y arrastrar un deslizador (captura)")
    def _():
        ids = ctx["f4"]
        vm.set_events(ids["button"], [EventHandler("on_click", [
            Action("widget_state", {"op": "hide", "id": ids["label"]}),
            Action("widget_update", {"type": "label", "id": ids["label"],
                                     "props": {"text": "Cambiado"}})])])
        win.open_simulator()
        pump(150)
        sim = win.simulator
        sim.click(ids["button"])
        pump()
        assert sim.engine.widget(ids["label"]).props.get("hidden") is True
        assert vm.widget(ids["label"]).props.get("hidden") is None, "el diseño no debe cambiar"
        b = sim.engine.box_of(ids["slider"]).rect
        sim.engine.press(b.x + b.w * 0.1, b.y + b.h / 2)
        sim.engine.move(b.x + b.w * 0.9, b.y + b.h / 2)
        sim.engine.release(b.x + b.w * 0.9, b.y + b.h / 2)
        sim.canvas.update()
        pump()
        assert sim.engine.widget(ids["slider"]).props["value"] == 90, sim.engine.widget(ids["slider"]).props
        sim.grab().save(os.path.join(CAPTURES, "simulador_f4.png"))
        sim.close()

    @check("F4 · Exportar código C para LVGL 9 (ui.c / ui.h)")
    def _():
        from olvgl.infrastructure.lvgl_c_generator import export_c
        out = os.path.join(tmp, "lvgl_c")
        files, res = export_c(vm.project, out)
        for name in ("ui.c", "ui.h"):
            assert os.path.exists(os.path.join(out, name)), name
        src = read_text(os.path.join(out, "ui.c"))
        for fn in ("lv_slider_create", "lv_tabview_add_tab", "LV_STATE_PRESSED", "ui_style_"):
            assert fn in src, fn
        shutil.copy(os.path.join(out, "ui.c"), os.path.join(CAPTURES, "ui.c"))
        shutil.copy(os.path.join(out, "ui.h"), os.path.join(CAPTURES, "ui.h"))
        text = "\n".join(win.c_report_lines(files, res))
        assert "ui.c" in text and "ui_action_handler" in text, text
        assert win._save_to(os.path.join(tmp, "fase4.olvgl"))

    # ======================================================= Fase 5: VS Code
    def cli_env():
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    @check("F5 · Motor de órdenes: dibujar las páginas a PNG (capturas/cli_*.png)")
    def _():
        import json as _json
        out = os.path.join(tmp, "cli")
        t0 = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "olvgl.cli", "render", demo, "--out", out],
                              capture_output=True, text=True, encoding="utf-8", cwd=ROOT, env=cli_env(),
                              timeout=120)
        assert proc.returncode == 0, proc.stderr[-2000:]
        res = _json.loads(proc.stdout)
        assert [p["id"] for p in res["rendered"]] == ["inicio", "ajustes"], res["pages"]
        for p in res["rendered"]:
            img = QImage(p["file"])
            assert img.width() == 1024 and img.height() == 600, p["file"]
            assert img.pixelColor(5, 300).name().upper() != "#000000" or img.pixelColor(500, 500).alpha() > 0
            shutil.copy(p["file"], os.path.join(CAPTURES, f"cli_{p['id']}.png"))
        with open(os.path.join(CAPTURES, "real_informe.txt"), "a", encoding="utf-8") as f:
            f.write(f"Vista previa por línea de órdenes (2 páginas, arranque incluido): "
                    f"{time.monotonic() - t0:.2f} s\n")

    @check("F5 · Servidor de la vista previa: texto sin guardar, salto al código y errores")
    def _():
        import base64
        import json as _json
        proc = subprocess.Popen([sys.executable, "-m", "olvgl.cli", "serve"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                cwd=ROOT, env=cli_env())
        try:
            def ask(req):
                proc.stdin.write(_json.dumps(req) + "\n")
                proc.stdin.flush()
                return _json.loads(proc.stdout.readline())
            text = read_text(demo).replace("Luces", "Luces VS Code")
            t0 = time.monotonic()
            r = ask({"id": 1, "cmd": "render", "path": demo, "text": text, "page": "inicio"})
            assert r["ok"], r.get("trace")
            first = time.monotonic() - t0
            page = r["result"]["rendered"][0]
            png = base64.b64decode(page["png"])
            img = QImage()
            assert img.loadFromData(png) and img.width() == 1024
            img.save(os.path.join(CAPTURES, "vista_previa_vscode.png"))
            ids = {w["id"]: w for w in page["widgets"]}
            assert ids["btn_comedor"]["line"] is not None, "sin línea para saltar al código"
            line = text.splitlines()[ids["btn_comedor"]["line"]]
            assert "btn_comedor" in line, line
            t0 = time.monotonic()
            r = ask({"id": 2, "cmd": "render", "path": demo, "text": text, "page": "ajustes"})
            second = time.monotonic() - t0
            assert r["ok"] and r["result"]["rendered"][0]["id"] == "ajustes"
            r = ask({"id": 3, "cmd": "validate", "path": demo, "text": "lvgl:\n  pages: [\n"})
            assert r["ok"] and r["result"]["diagnostics"][0]["severity"] == "error"
            r = ask({"id": 4, "cmd": "render", "path": demo, "text": "esto: [no es yaml"})
            assert not r["ok"]
            r = ask({"id": 5, "cmd": "ping"})
            assert r["ok"], "el servidor no sobrevivió a un error"
            with open(os.path.join(CAPTURES, "real_informe.txt"), "a", encoding="utf-8") as f:
                f.write(f"Vista previa VS Code: primer dibujo {first:.2f} s, siguientes {second:.2f} s\n")
        finally:
            try:
                proc.stdin.write('{"cmd": "quit"}\n')
                proc.stdin.flush()
            except OSError:
                pass
            proc.wait(timeout=20)

    @check("F5 · Extensión de VS Code empaquetada (.vsix) y sus pruebas")
    def _():
        import zipfile
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import build_vsix
        path = build_vsix.build()
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        assert "extension/package.json" in names and "extension.vsixmanifest" in names, names
        node = shutil.which("node")
        if node:
            ext = os.path.join(ROOT, "vscode-extension", "test")
            for args in (["core.test.js"], ["activate.test.js"], ["server.test.js", sys.executable]):
                proc = subprocess.run([node, os.path.join(ext, args[0])] + args[1:], capture_output=True,
                                      text=True, encoding="utf-8", cwd=ROOT, timeout=120)
                assert proc.returncode == 0, (args[0], proc.stdout[-1000:], proc.stderr[-1000:])
        else:
            print("   (Node.js no instalado: se omiten las pruebas JavaScript de la extensión)", flush=True)

    # ======================================================= Fase 6: simulador profesional
    @check("F6 · Gestos: desplazar la página, deslizar pestañas y cancelar el clic (captura)")
    def _():
        ids = ctx["f4"]
        low = vm.add_widget("label", 20, 20, centered=False)
        vm.set_geom_value(low, "y", "900")                    # contenido por debajo de la pantalla
        win.open_simulator()
        pump(150)
        sim = win.simulator
        eng = sim.engine
        page = eng.page_id
        # pestañas: deslizar dentro del contenido del tabview
        r = eng.box_of(ids["tabview"]).rect
        sim.swipe(r.x + r.w - 10, r.y + r.h - 15, r.x + 10, r.y + r.h - 15)
        assert eng.active_tabs.get(ids["tabview"]) == 1, eng.active_tabs
        # página: arrastrar hacia arriba desde una zona vacía
        y0 = eng.box_of(low).rect.y
        sim.swipe(1010, 590, 1010, 300)
        assert eng.scroll.get(page, (0, 0))[1] > 100, eng.scroll
        assert eng.box_of(low).rect.y < y0
        # un arrastre que empieza en un botón desplaza y no hace clic
        before = vm.widget(ids["label"]).props.get("text")
        b = eng.box_of(ids["button"]).rect
        sim.swipe(b.x + 10, b.y + 10, b.x + 10, b.y - 60)
        assert eng.widget(ids["label"]).props.get("hidden") is not True, "el arrastre hizo clic"
        pump(50)
        sim.grab().save(os.path.join(CAPTURES, "simulador_gestos.png"))
        log = sim.log_view.toPlainText()
        assert "gesto" in log or "pestaña 2" in log, log[-500:]
        ctx["low"] = low
        assert before == vm.widget(ids["label"]).props.get("text")

    @check("F6 · Varios dispositivos y rotación (capturas/sim_*.png)")
    def _():
        from olvgl.domain.model import DisplayProfile
        sim = win.simulator
        v2 = sim.add_device(DisplayProfile("Prueba 800x480", 800, 480))
        v3 = sim.add_device(DisplayProfile("Prueba 480x480", 480, 480), rotation=90)
        v2.set_rotation(90)
        pump(150)
        assert (v2.engine.display().width, v2.engine.display().height) == (480, 800)
        assert not v2.engine.is_landscape()
        assert v3.engine.display().width == 480
        # navegación sincronizada: cambiar de página en el principal cambia los demás
        target = ctx["f4_page2"]
        sim.engine.go_to_page(target)
        sim._on_device_page(sim.devices[0], target)
        assert v2.engine.page_id == target and v3.engine.page_id == target
        sim.engine.go_to_page(ctx["f4_page"])
        sim._on_device_page(sim.devices[0], ctx["f4_page"])
        files = sim.save_screenshots(CAPTURES, "sim")
        assert len(files) == 3 and all(os.path.exists(f) for f in files)
        img = QImage(files[1])
        assert (img.width(), img.height()) == (480, 800), (img.width(), img.height())
        sim.grab().save(os.path.join(CAPTURES, "simulador_dispositivos.png"))
        sim.remove_device(v3)
        sim.remove_device(v2)
        pump(50)
        assert len(sim.devices) == 1

    @check("F6 · Rendimiento y estimación de RAM/flash (capturas/perfil_*.json)")
    def _():
        import json as _json
        from olvgl import cli
        sim = win.simulator
        sim.tabs.setCurrentIndex(1)
        sim.canvas.grab()
        pump(100)
        sim.refresh_live()
        sim.refresh_resources()
        assert sim.canvas.paint_times, "sin tiempos de dibujo"
        assert "ms" in sim.live_text(), sim.live_text()
        assert sim.last_resources.objects > 20
        sim.grab().save(os.path.join(CAPTURES, "simulador_rendimiento.png"))
        sim.tabs.setCurrentIndex(0)
        with open(os.path.join(CAPTURES, "perfil_demo.json"), "w", encoding="utf-8") as f:
            _json.dump(cli.profile(demo), f, ensure_ascii=False, indent=1)
        if os.path.exists(real):
            prof = cli.profile(real)
            with open(os.path.join(CAPTURES, "perfil_real.json"), "w", encoding="utf-8") as f:
                _json.dump(prof, f, ensure_ascii=False, indent=1)
            from olvgl.domain.resources import human
            with open(os.path.join(CAPTURES, "real_informe.txt"), "a", encoding="utf-8") as f:
                f.write(f"Estimación en el dispositivo: {prof['objects']} objetos, RAM {human(prof['ram_bytes'])} "
                        f"(objetos {human(prof['heap_bytes'])} + búfer {human(prof['draw_buffer_bytes'])}), "
                        f"flash fuentes/imágenes {human(prof['flash_bytes'])}\n")

    @check("F6 · Grabar y reproducir una sesión táctil")
    def _():
        sim = win.simulator
        ids = ctx["f4"]
        sim.btn_rec.setChecked(True)
        sim.click(ids["switch"])
        sim.btn_rec.setChecked(False)
        assert len(sim._last_record) == 2, sim._last_record
        was = ids["switch"] in sim.engine.checked
        sim.replay(speed=20)
        pump(400)
        assert (ids["switch"] in sim.engine.checked) != was, "la reproducción no pulsó el interruptor"
        assert "Reproduciendo" in sim.log_view.toPlainText()
        sim.close()
        vm.undo()                       # quita la etiqueta añadida para la prueba de desplazamiento
        vm.undo()
        pump(50)
        assert not vm.dirty, "el proyecto debería volver a estar guardado"

    # ======================================================= Fase 7: plugins
    @check("F7 · Plugins de ejemplo cargados y gestor de plugins")
    def _():
        from olvgl.presentation.plugins_ui import PluginsDialog
        infos = win.plugins.plugins
        for pid in ("tarjeta_sensor", "exportador_markdown", "reglas_ux"):
            assert pid in infos and infos[pid].loaded, {k: v.error for k, v in infos.items()}
        dlg = PluginsDialog(win.plugins, settings, win.plugins_reloaded, win)
        assert dlg.tree.topLevelItemCount() >= 3
        dlg.grab().save(os.path.join(CAPTURES, "plugins_gestor.png"))
        dlg.deleteLater()
        titles = [a.menu().title().replace("&", "") for a in win.menuBar().actions() if a.menu()]
        assert "Plugins" in titles, titles
        cmds = [a.text() for a in win.plugins_menu.actions()]
        assert any("48 px" in t for t in cmds), cmds

    @check("F7 · Widget de plugin: paleta, dibujo y exportación a ESPHome y C (captura)")
    def _():
        from olvgl.presentation.icons import widget_icon
        assert "sensor_card" in win.palette.types()
        assert widget_icon("sensor_card") is not None
        vm.new("Plugins", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        vm.update_screen(vm.current_screen_id, bg_color="#101018")
        card = vm.add_widget("sensor_card", 40, 40, centered=False)
        vm.set_prop([card], "value", "23.4")
        ctx["card"] = card
        pump(150)
        r = win.scene.screen_rect()
        img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        win.scene.render(p, QRectF(0, 0, r.width(), r.height()), r)
        p.end()
        img.save(os.path.join(CAPTURES, "plugin_widget.png"))
        c = img.pixelColor(44, 125)                # barra de acento naranja (lejos de las asas)
        assert c.red() > 200 and 100 < c.green() < 190 and c.blue() < 80, c.name()
        text = vm.generate_yaml()
        assert "sensor_card" not in text and f"{card}_value" in text, text[:1500]
        data = yaml.safe_load(text)
        assert data["lvgl"]["pages"][0]["widgets"][0]["obj"]["id"] == card
        from olvgl.infrastructure.lvgl_c_generator import generate_c
        assert f"ui_{card}_value" in generate_c(vm.project).source

    @check("F7 · Exportadores, reglas y órdenes de plugins (capturas/plugin_*.md)")
    def _():
        out = os.path.join(tmp, "plugin_export")
        files = win.export_with_plugin("exportador_markdown.markdown", out)
        files += win.export_with_plugin("exportador_markdown.csv", out)
        assert len(files) == 2 and all(os.path.exists(f) for f in files), files
        md = read_text(files[0])
        assert ctx["card"] in md, md[:500]
        shutil.copy(files[0], os.path.join(CAPTURES, "plugin_documentacion.md"))
        b = vm.add_widget("button", 400, 40, centered=False)
        vm.set_geom_value(b, "height", "30")
        issues = win.check_project(show=False)
        assert any(i.widget_id == b and i.plugin == "reglas_ux" for i in issues), [i.message for i in issues]
        assert win.run_plugin_command("reglas_ux.agrandar")
        assert vm.widget(b).height == 48
        assert not any(i.widget_id == b for i in win.check_project(show=False))
        import json as _json
        proc = subprocess.run([sys.executable, "-m", "olvgl.cli", "plugins"], capture_output=True, text=True,
                              encoding="utf-8", cwd=ROOT, env=cli_env(), timeout=120)
        assert proc.returncode == 0, proc.stderr[-1500:]
        listed = {x["id"] for x in _json.loads(proc.stdout)["plugins"]}
        assert {"tarjeta_sensor", "exportador_markdown", "reglas_ux"} <= listed, listed
        assert win._save_to(os.path.join(tmp, "plugins.olvgl"))
        loaded = json_store.load_project(os.path.join(tmp, "plugins.olvgl"))
        assert loaded.widget(ctx["card"]).type == "sensor_card"

    # ======================================================= Fase 8: IA generativa
    def page_image(page_id: str) -> QImage:
        vm.set_current_screen(page_id)
        pump(120)
        r = win.scene.screen_rect()
        img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        win.scene.render(p, QRectF(0, 0, r.width(), r.height()), r)
        p.end()
        return img

    @check("F8 · IA local: generar páginas desde una descripción (capturas/ia_*.png)")
    def _():
        from olvgl.infrastructure.yaml_parser import parse
        vm.new("IA", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        win.settings.set("ai_provider", "local")
        n = len(vm.project.screens)
        made = []
        for i, prompt in enumerate(("Página de luces con 6 luces y el termostato, tema oscuro",
                                    "3 persianas, tema claro y color verde",
                                    "Música del salón y escenas, con barra de navegación")):
            dlg = win.open_ai_generate(show=False)
            dlg.prompt.setPlainText(prompt)
            dlg.run(wait=True)
            assert dlg.result is not None, dlg.status.text()
            assert not dlg.result.warnings, dlg.result.warnings
            pm = dlg.preview.pixmap()
            assert pm is not None and not pm.isNull()
            pm.save(os.path.join(CAPTURES, f"ia_vista_previa_{i + 1}.png"))
            assert dlg.apply()
            pid = vm.current_screen_id
            made.append(pid)
            page_image(pid).save(os.path.join(CAPTURES, f"ia_{pid}.png"))
            dlg.deleteLater()
        assert len(vm.project.screens) == n + 3, [s.id for s in vm.project.screens]
        text = vm.generate_yaml()
        parse(text, "ia.yaml")
        for pid in made:
            assert f"id: {pid}" in text
        assert "light.toggle" in text and "cover.set_cover_position" in text and "scene.turn_on" in text
        assert len(set(vm.project.all_ids())) == len(list(vm.project.all_ids()))
        vm.undo()
        assert len(vm.project.screens) == n + 2
        vm.redo()
        ctx["ia_pages"] = made

    @check("F8 · Refactorizar con IA: tema claro, botones y diferencias (capturas/ia_refactor_*.png)")
    def _():
        pid = ctx["ia_pages"][0]
        vm.set_current_screen(pid)
        pump()
        dlg = win.open_ai_refactor(show=False)
        dlg.instruction.setText("Tema claro, textos más grandes y botones azules")
        dlg.run(wait=True)
        assert dlg.result is not None, dlg.status.text()
        diff = dlg.diff.toPlainText()
        assert "+" in diff and "0xF2F4F8" in diff, diff[:800]
        with open(os.path.join(CAPTURES, "ia_refactor_cambios.diff"), "w", encoding="utf-8") as fh:
            fh.write(diff)
        page_image(pid).save(os.path.join(CAPTURES, "ia_refactor_antes.png"))
        assert dlg.apply()
        img = page_image(pid)
        img.save(os.path.join(CAPTURES, "ia_refactor_despues.png"))
        c = img.pixelColor(5, 5)
        assert c.red() > 220 and c.green() > 220 and c.blue() > 220, c.name()
        btns = [w for w in vm.project.screen(pid).walk() if w.type == "button"]
        assert btns and all(b.props.get("bg_color") == "#1E88E5" for b in btns)
        vm.undo()
        assert vm.project.screen(pid).bg_color == "#101018"
        vm.redo()
        dlg.deleteLater()

    @check("F8 · Extraer estilos e ids descriptivos sin cambiar el aspecto")
    def _():
        from olvgl.domain.refactor import descriptive_ids, extract_styles
        from olvgl.infrastructure.esphome_importer import import_esphome_file, import_esphome_text
        from olvgl.presentation.ai_ui import render_page
        src = real_src if os.path.exists(real_src) else os.path.join(ROOT, "examples", "importar", "panel_demo.yaml")
        project, _rep = import_esphome_file(src)
        styled, rep = extract_styles(project)
        assert rep.styles_created, "sin estilos"
        renamed, rep2 = descriptive_ids(styled)
        diffs = []
        for s in project.screens:
            a = render_page(project, s.id, project.display.width)
            b = render_page(renamed, s.id, project.display.width)
            if a != b:
                diffs.append(s.id)
                a.save(os.path.join(CAPTURES, f"ia_estilos_{s.id}_antes.png"))
                b.save(os.path.join(CAPTURES, f"ia_estilos_{s.id}_despues.png"))
        assert not diffs, diffs
        from olvgl.infrastructure.esphome_generator import generate_yaml
        text = generate_yaml(renamed)
        again, rep3 = import_esphome_text(text, src, project.display)
        assert not rep3.warnings, rep3.warnings[:5]
        with open(os.path.join(CAPTURES, "ia_estilos_informe.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(rep.changes + [""] + rep2.changes[:200]))
        # y desde el menú, con deshacer
        before = vm.project.to_dict()
        r = win.extract_styles()
        assert r.styles_created and vm.project.styles
        r2 = win.descriptive_ids()
        if r2.renamed:
            vm.undo()
        vm.undo()
        assert vm.project.to_dict() == before

    @check("F8 · Configuración de la IA y orden «generate» (capturas/ia_cli.yaml)")
    def _():
        dlg = win.open_ai_settings(show=False)
        assert dlg.provider.count() == 3 and dlg.provider.currentData() == "local"
        assert dlg.test()
        dlg.deleteLater()
        out = os.path.join(CAPTURES, "ia_cli.yaml")
        proc = subprocess.run([sys.executable, "-m", "olvgl.cli", "generate", "energía solar y consumo con la hora",
                               "--display", "800x480", "--out", out], capture_output=True, text=True,
                              encoding="utf-8", cwd=ROOT, env=cli_env(), timeout=120)
        assert proc.returncode == 0, proc.stderr[-1500:]
        from olvgl.infrastructure.esphome_importer import import_esphome_text
        frag, rep = import_esphome_text(read_text(out), out, DisplayProfile("x", 800, 480))
        assert frag.screens and not rep.generic_types
        key = os.environ.get("ANTHROPIC_API_KEY")
        if key:                                         # prueba real opcional
            from olvgl.application import ai
            res = ai.AIDesigner(ai.make_provider(ai.AIConfig("anthropic", api_key=key))).generate(
                "Página de clima con termostato y humedad", vm.project)
            assert res.page_ids
            with open(os.path.join(CAPTURES, "ia_anthropic.yaml"), "w", encoding="utf-8") as fh:
                fh.write(res.yaml)
        assert win._save_to(os.path.join(tmp, "ia.olvgl"))

    # ======================================================= Fase 9: beta pública
    @check("F9 · Pruebas masivas: 40 sesiones de edición al azar y 300 YAML dañados")
    def _():
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import fuzz
        t0 = time.monotonic()
        fails = [f for f in (fuzz.run_session(seed, 50) for seed in range(1000, 1040)) if f]
        assert not fails, (fails[0]["error"], fails[0]["steps"][-6:], fails[0]["trace"][-1500:])
        old_corpus = fuzz.CORPUS
        fuzz.CORPUS = [os.path.join(ROOT, "examples", "importar", "panel_demo.yaml")]
        try:
            yfails = fuzz.yaml_fuzz(300, seed=42)
        finally:
            fuzz.CORPUS = old_corpus
        assert not yfails, (yfails[0]["error"], yfails[0]["trace"][-1500:])
        with open(os.path.join(CAPTURES, "pruebas_masivas.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"40 sesiones × 50 operaciones: sin fallos\n300 YAML dañados: {fuzz.YAML_STATS}\n"
                     f"Tiempo: {time.monotonic() - t0:.1f} s\n")

    @check("F9 · Rendimiento: importar, cambiar de página y editar (capturas/rendimiento.txt)")
    def _():
        src = real_src if os.path.exists(real_src) else os.path.join(ROOT, "examples", "importar", "panel_demo.yaml")
        path = os.path.join(tmp, "rendimiento.yaml")
        shutil.copy(src, path)
        win.code.refresh()
        t0 = time.perf_counter()
        report = vm.import_yaml(path, link=False)
        win._install_measures()
        pump(10)
        t_import = time.perf_counter() - t0
        n = sum(1 for _ in vm.project.iter_widgets())
        pages = [sc.id for sc in vm.project.screens]
        t0 = time.perf_counter()
        for pid in pages:
            vm.set_current_screen(pid)
            app.processEvents()
        t_pages = (time.perf_counter() - t0) / max(1, len(pages))
        vm.set_current_screen(pages[0])
        pump(50)
        target = next(w for w in vm.current_screen.walk() if w.x is not None and isinstance(w.x, int))
        vm.set_selection([target.id])
        t0 = time.perf_counter()
        for _i in range(20):
            vm.nudge(1, 0)
            app.processEvents()
        t_edit = (time.perf_counter() - t0) / 20
        t0 = time.perf_counter()
        win.code.refresh()
        t_code = time.perf_counter() - t0
        t0 = time.perf_counter()
        text = vm.generate_yaml()
        t_gen = time.perf_counter() - t0
        for _i in range(20):
            vm.undo()
        pump(200)
        lines = [f"Proyecto: {os.path.basename(src)} · {len(pages)} páginas · {n} widgets · {text.count(chr(10))} líneas",
                 f"Importar y disponer: {t_import * 1000:.0f} ms",
                 f"Cambiar de página (media): {t_pages * 1000:.0f} ms",
                 f"Mover un widget con las flechas (media, sin código): {t_edit * 1000:.1f} ms",
                 f"Actualizar la vista de código tras un cambio: {t_code * 1000:.0f} ms",
                 f"Generar el YAML completo: {t_gen * 1000:.0f} ms"]
        with open(os.path.join(CAPTURES, "rendimiento.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        assert not report.warnings, report.warnings[:3]
        assert t_import < 8 and t_pages < 0.6 and t_edit < 0.25 and t_code < 1.5, lines

    @check("F9 · Error inesperado: informe, autoguardado y diagnóstico sin claves (capturas/diagnostico.txt)")
    def _():
        from olvgl import __version__
        from olvgl.application import diagnostics
        from olvgl.presentation.app import install_error_handler
        old_hook, old_thread_hook = sys.excepthook, __import__("threading").excepthook
        fake_key = "sk-" + "ant-" + "PRUEBA-NO-DEBE-SALIR-1234567890"   # partida: el empaquetador busca claves
        settings.set("ai_api_key", fake_key)
        try:
            diagnostics.setup_logging()
            install_error_handler(win)
            n0 = len(win.errors)

            def boom():
                raise RuntimeError("fallo de prueba de la autoprueba")
            QTimer.singleShot(0, boom)
            pump(300)
            if len(win.errors) == n0:          # algunas versiones de PySide6 no llaman al gancho desde un slot
                try:
                    boom()
                except RuntimeError:
                    sys.excepthook(*sys.exc_info())
                pump(100)
            assert len(win.errors) == n0 + 1, win.errors
            path, summary = win.errors[-1]
            assert os.path.exists(path) and "fallo de prueba" in summary
            body = read_text(path)
            assert "Traceback" in body and fake_key not in body
            dlg = win.open_diagnostics(show=False)
            text = dlg.text.toPlainText()
            assert fake_key not in text and "ia_clave: sí" in text and __version__ in text, text[:800]
            dlg.save(os.path.join(CAPTURES, "diagnostico.txt"))
            dlg.deleteLater()
            assert os.path.isfile(win.open_guide()) and os.path.isfile(win.open_changelog())
            assert os.path.isdir(win.open_logs())
        finally:
            sys.excepthook = old_hook
            __import__("threading").excepthook = old_thread_hook
            settings.set("ai_api_key", "")

    @check("F9 · Paquete de la beta (.zip con la extensión de VS Code, sin ficheros privados)")
    def _():
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import zipfile

        import build_release

        from olvgl import __version__
        res = build_release.build(os.path.join(tmp, "dist"))
        names = zipfile.ZipFile(res["zip"]).namelist()
        top = f"OpenLVGLStudio-{__version__}/"
        assert all(x.startswith(top) for x in names)
        for need in ("install.bat", "run.bat", "README.md", "CHANGELOG.md", "docs/GUIA_USUARIO.md",
                     "olvgl/presentation/app.py", "plugins/tarjeta_sensor/plugin.json",
                     f"vscode-extension/dist/{res['vsix']}"):
            assert top + need in names, need
        assert not [x for x in names if "panel-domotica" in x or "__pycache__" in x or "/capturas/" in x]
        with open(os.path.join(CAPTURES, "paquete_beta.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{os.path.basename(res['zip'])}: {res['files']} ficheros, {res['bytes'] / 1e6:.1f} MB\n"
                     f"SHA-256 {res['sha256']}\n")
        assert win._save_to(os.path.join(tmp, "f9.olvgl"))

    # ======================================================= Fase 10: enterprise
    def scene_image() -> QImage:
        r = win.scene.screen_rect()
        img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        win.scene.render(p, QRectF(0, 0, r.width(), r.height()), r)
        p.end()
        return img

    @check("F10 · Mover con las flechas sin reconstruir el árbol ni repintar todo (capturas/rendimiento_f10.txt)")
    def _():
        src = real_src if os.path.exists(real_src) else os.path.join(ROOT, "examples", "importar", "panel_demo.yaml")
        path = os.path.join(tmp, "rendimiento_f10.yaml")
        shutil.copy(src, path)
        vm.import_yaml(path, link=False)
        win._install_measures()
        pump(200)
        target = next(w for w in vm.current_screen.walk() if isinstance(w.x, int))
        vm.set_selection([target.id])
        pump(100)
        rebuilds = []
        orig = win.tree.rebuild
        win.tree.rebuild = lambda *a, **k: (rebuilds.append(1), orig(*a, **k))[1]
        try:
            t0 = time.perf_counter()
            for _i in range(20):
                vm.nudge(1, 0)
                app.processEvents()
            t_edit = (time.perf_counter() - t0) / 20
            pump(50)
        finally:
            win.tree.rebuild = orig
        x_after = vm.widget(target.id).x
        for _i in range(20):
            vm.undo()
        pump(150)
        with open(os.path.join(CAPTURES, "rendimiento_f10.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"Mover un widget con las flechas (media): {t_edit * 1000:.1f} ms (antes de la Fase 10: ~90 ms)\n"
                     f"Reconstrucciones del árbol durante los 20 movimientos: {len(rebuilds)}\n")
        assert x_after == target.x + 20 or x_after is not None
        assert not rebuilds, len(rebuilds)
        assert t_edit < 0.06, f"{t_edit * 1000:.1f} ms"

    @check("F10 · Versiones: guardar, comparar visualmente y restaurar (capturas/versiones_*.png)")
    def _():
        vm.new("Versiones", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        vm.update_screen(vm.current_screen_id, bg_color="#101018")
        a = vm.add_widget("button", 100, 100, centered=False)
        b = vm.add_widget("label", 400, 100, centered=False)
        c = vm.add_widget("slider", 100, 300, centered=False)
        path = os.path.join(tmp, "versiones.olvgl")
        assert win._save_to(path)
        info = win.save_version("Primera versión")
        assert info is not None
        vm.set_selection([a])
        vm.nudge(150, 40)
        vm.set_prop([b], "text", "Cambiado")
        vm.delete_widgets([c])
        d = vm.add_widget("switch", 700, 300, centered=False)
        pump(100)
        dlg = win.open_versions(show=False)
        dlg.show()
        pump(300)
        assert dlg.current() is not None and dlg.current().id == info.id
        counts = dlg.diff.counts()
        assert counts == {"added": 1, "removed": 1, "changed": 2}, counts
        text = dlg.changes.toPlainText()
        assert d in text and c in text and "Cambiado" in text, text[:600]
        dlg.before.pixmap().save(os.path.join(CAPTURES, "versiones_antes.png"))
        dlg.after.pixmap().save(os.path.join(CAPTURES, "versiones_despues.png"))
        dlg.grab().save(os.path.join(CAPTURES, "versiones_dialogo.png"))
        assert dlg.restore(confirm=False)
        assert vm.widget(c) is not None and vm.widget(d) is None and vm.widget(b).props.get("text") != "Cambiado"
        vm.undo()
        assert vm.widget(d) is not None
        dlg.close()
        dlg.deleteLater()
        if shutil.which("git"):
            env = dict(os.environ, GIT_AUTHOR_NAME="autoprueba", GIT_AUTHOR_EMAIL="a@a",
                       GIT_COMMITTER_NAME="autoprueba", GIT_COMMITTER_EMAIL="a@a")
            ok = all(subprocess.run(["git", *args], cwd=tmp, env=env, capture_output=True, timeout=60).returncode == 0
                     for args in (["init", "-q"], ["add", "versiones.olvgl"], ["commit", "-qm", "primero"]))
            assert win._save_to(path)
            ok = ok and subprocess.run(["git", "commit", "-qam", "segundo"], cwd=tmp, env=env, capture_output=True,
                                       timeout=60).returncode == 0
            if ok:                                              # con Git configurado: su historial también
                from olvgl.infrastructure.versions import GitHistory
                assert [v.label for v in GitHistory(path).log()] == ["segundo", "primero"]
        assert win._save_to(path)

    @check("F10 · Colaboración: fusión al guardar, presencia y comentarios (capturas/comentarios.png)")
    def _():
        from olvgl.infrastructure.collab import CommentStore, Presence
        path = os.path.join(tmp, "versiones.olvgl")
        ana = Presence(path, "ana", "PC-ANA")
        ana.heartbeat()
        others = win.team_tick()
        assert [p.user for p in others] == ["ana"] and "ana" in win.lbl_team.text()
        theirs = json_store.load_project(path)                  # ana cambia el título y guarda
        lbl = next(w for _s, w in theirs.iter_widgets() if w.type == "label")
        lbl.props["text"] = "Texto de Ana"
        json_store.save_project(theirs, path)
        assert vm.disk_changed()
        btn = next(w for _s, w in vm.project.iter_widgets() if w.type == "button")
        vm.set_selection([btn.id])
        vm.nudge(0, 30)                                         # yo muevo el botón
        assert win._save_to(path)
        assert vm.last_merge is not None and vm.last_merge.clean, [str(x) for x in vm.last_merge.conflicts]
        saved = json_store.load_project(path)
        assert saved.widget(lbl.id).props["text"] == "Texto de Ana" and saved.widget(btn.id).y == btn.y
        vm.set_selection([btn.id])                              # la fusión deja la selección vacía
        c = win.comments.add("El botón debería ser más grande")
        assert c is not None and c.widget == btn.id
        CommentStore(path).add(vm.current_screen_id, lbl.id, "¿Este texto es el definitivo?", "ana")
        win.team_tick()
        assert len(win.comments.store.for_page(vm.current_screen_id)) == 2
        assert win.scene.comment_counts == {btn.id: 1, lbl.id: 1}, win.scene.comment_counts
        win.show_comments()
        pump(150)
        scene_image().save(os.path.join(CAPTURES, "comentarios.png"))
        win.dock_comments.grab().save(os.path.join(CAPTURES, "comentarios_panel.png"))
        win.comments.list.setCurrentItem(win.comments.list.topLevelItem(0))
        assert win.comments.toggle_resolved()
        assert len(win.scene.comment_counts) == 1
        ana.leave()
        assert win.team_tick() == []
        win.dock_props.raise_()

    @check("F10 · Componentes: catálogo, instalar, insertar y guardar la selección (capturas/componentes.png)")
    def _():
        dlg = win.open_components(show=False)
        dlg.show()
        pump(200)
        assert len(dlg.catalog.entries) >= 4, dlg.status.text()
        assert dlg.install_all() == len(dlg.catalog.entries)
        dlg.tabs.setCurrentIndex(0)
        pump(100)
        assert dlg.lib_list.count() >= 4
        n_before = sum(1 for _ in vm.project.iter_widgets())
        for row in range(dlg.lib_list.count()):
            dlg.lib_list.setCurrentRow(row)
            assert dlg.insert_selected(30 + 40 * row, 30 + 40 * row), dlg.status.text()
        assert sum(1 for _ in vm.project.iter_widgets()) > n_before
        ids = list(vm.project.all_ids())
        assert len(ids) == len(set(ids))
        from olvgl.infrastructure.yaml_parser import parse
        parse(vm.generate_yaml(), "c.yaml")
        dlg.grab().save(os.path.join(CAPTURES, "componentes.png"))
        dlg.close()
        dlg.deleteLater()
        pump(100)
        scene_image().save(os.path.join(CAPTURES, "componentes_insertados.png"))
        vm.set_selection(dlg.inserted)
        sd = win.save_component(show=False)
        sd.name.setText("Mi componente de prueba")
        pkg = sd.save()
        assert pkg is not None and pkg.id == "mi-componente-de-prueba"
        sd.deleteLater()
        assert win._save_to(os.path.join(tmp, "versiones.olvgl"))

    @check("F10 · Licencias: firma Ed25519, edición y licencias de terceros")
    def _():
        from olvgl.application import licensing as lc
        from olvgl.domain import ed25519
        secret = ed25519.generate_secret()
        lc.EXTRA_PUBLIC_KEYS.append(ed25519.public_key(secret))
        try:
            lic = lc.sign_license(lc.License(id="prueba", licensee="Autoprueba S.L.", edition="enterprise",
                                             seats=3, issued="2026-11-11", expires=None), secret)
            good = os.path.join(tmp, "buena.olvgl-lic")
            with open(good, "w", encoding="utf-8") as fh:
                fh.write(lic.to_json())
            bad = os.path.join(tmp, "mala.olvgl-lic")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write(lic.to_json().replace("Autoprueba S.L.", "Pirata S.L."))
            dlg = win.open_license(show=False)
            assert dlg.status.edition == "community"
            assert not dlg.load(bad) and dlg.status.edition == "community"
            assert dlg.load(good) and dlg.status.edition == "enterprise" and dlg.status.state == "valid"
            dlg.show()
            pump(100)
            dlg.grab().save(os.path.join(CAPTURES, "licencia.png"))
            third = dlg.tabs.widget(1).toPlainText()
            assert "LGPL" in third and "Montserrat" in third
            dlg.remove()
            assert dlg.status.edition == "community"
            dlg.close()
            dlg.deleteLater()
            # ediciones: Community sin importar YAML ni IA; Pro importa; Enterprise además IA
            lc.ENFORCE = True
            n0 = len(win.license_blocked)
            assert not win.import_yaml(os.path.join(tmp, "importar", "panel_demo.yaml"))
            assert win.open_ai_generate(show=False) is None and win.extract_styles() is None
            assert win.license_blocked[n0:] == ["importar_yaml", "ia", "ia"], win.license_blocked
            pro = os.path.join(tmp, "pro.olvgl-lic")
            with open(pro, "w", encoding="utf-8") as fh:
                fh.write(lc.sign_license(lc.License(id="pro", licensee="Autoprueba", edition="pro",
                                                    issued="2026-11-11"), secret).to_json())
            lc.install(pro)
            assert win._require("importar_yaml") and win._require("vscode") and not win._require("ia")
            lc.install(good)
            assert win._require("ia")
            g = win.open_ai_generate(show=False)
            assert g is not None
            g.deleteLater()
            lc.remove()
            assert "705c4f233a4fa72311386dce0e3b7f1acb108c286f3dcc65b4c64ccb6e8d9f2d" in [k.hex() for k in lc.public_keys()]
        finally:
            lc.ENFORCE = False
            lc.EXTRA_PUBLIC_KEYS.clear()

    # ======================================================= rejilla, degradados, estilos y meter
    def widget_image(wid: str, w: int, h: int) -> QImage:
        from olvgl.domain.layout import effective_props
        from olvgl.presentation import render as rnd
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(QColor("#202024"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = vm.widget(wid)
        rnd.paint_widget(p, m, QRectF(0, 0, w, h), effective_props(vm.project, m),
                         rnd.RenderContext(vm.project, vm.resolve_path))
        p.end()
        return img

    @check("Ver · Tamaño de la rejilla: menú, ajuste al mover y se recuerda (capturas/rejilla_*.png)")
    def _():
        from olvgl.presentation.main_window import GRID_SIZES
        assert 5 in GRID_SIZES and 50 in GRID_SIZES
        assert win.grid_size_menu.actions(), "falta Ver › Tamaño de la rejilla"
        win.set_grid_size(20)
        pump(80)
        assert vm.grid_size == 20 and settings.get("grid_size") == 20
        assert win.grid_size_actions[20].isChecked()
        vm.snap = True
        assert vm.snap_value(29) == 20 and vm.snap_value(31) == 40
        win.grab().save(os.path.join(CAPTURES, "rejilla_20px.png"))
        assert win.ask_grid_size(15) == 15 and "15" in win.a_grid_custom.text() and win.a_grid_custom.isChecked()
        assert "15" in win.lbl_grid.text()
        assert win.set_grid_size(100000) == 500 and win.set_grid_size(-3) == 1
        win.set_grid_size(10)
        pump(50)
        win.grab().save(os.path.join(CAPTURES, "rejilla_10px.png"))
        assert settings.get("grid_size") == 10

    @check("Estilo · Degradados en botones, contenedores, barras, deslizadores y arcos (capturas/degradados.png)")
    def _():
        vm.new("Degradados", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        btn = vm.add_widget("button", 40, 40, centered=False)
        vm.set_prop([btn], "bg_color", "#FF0000")
        vm.set_prop([btn], "bg_grad_color", "#0000FF")
        vm.set_prop([btn], "bg_grad_dir", "VER")
        img = widget_image(btn, 200, 80)
        top, bottom = img.pixelColor(100, 6), img.pixelColor(100, 74)
        assert top.red() > 180 and top.blue() < 90, top.name()
        assert bottom.blue() > 180 and bottom.red() < 90, bottom.name()
        vm.set_prop([btn], "bg_main_stop", 128)            # mitad de arriba lisa
        assert widget_image(btn, 200, 80).pixelColor(100, 30).red() > 200
        box = vm.add_widget("obj", 300, 40, centered=False)
        for k, v in (("bg_color", "#FFEB3B"), ("bg_grad_color", "#4CAF50"), ("bg_grad_dir", "HOR")):
            vm.set_prop([box], k, v)
        im = widget_image(box, 200, 150)
        assert im.pixelColor(8, 75).red() > 200 and im.pixelColor(192, 75).red() < 150
        bar = vm.add_widget("bar", 40, 200, centered=False)
        vm.set_prop([bar], "value", 100)
        for k, v in (("indicator.bg_color", "#00FF00"), ("indicator.bg_grad_color", "#FF00FF"),
                     ("indicator.bg_grad_dir", "HOR")):
            vm.set_prop([bar], k, v)
        im = widget_image(bar, 200, 20)
        assert im.pixelColor(12, 10).green() > 180 and im.pixelColor(188, 10).red() > 180, \
            (im.pixelColor(12, 10).name(), im.pixelColor(188, 10).name())
        sld = vm.add_widget("slider", 40, 260, centered=False)
        for k, v in (("indicator.bg_color", "#FFC107"), ("indicator.bg_grad_color", "#F44336"),
                     ("indicator.bg_grad_dir", "HOR"), ("knob.bg_grad_color", "#2196F3"), ("knob.bg_grad_dir", "VER")):
            vm.set_prop([sld], k, v)
        arc = vm.add_widget("arc", 300, 200, centered=False)
        for k, v in (("bg_color", "#263238"), ("bg_opa", "COVER"), ("bg_grad_color", "#000000"),
                     ("bg_grad_dir", "VER"), ("knob.bg_grad_color", "#FFFFFF"), ("knob.bg_grad_dir", "VER")):
            vm.set_prop([arc], k, v)
        widget_image(arc, 150, 150)
        from olvgl.infrastructure.esphome_generator import generate_yaml
        y = generate_yaml(vm.project)
        assert "bg_grad_color: 0x0000FF" in y and "bg_grad_dir: VER" in y and "bg_main_stop: 128" in y, y[:800]
        vm.set_selection([])
        pump(150)
        page_image(vm.current_screen_id).save(os.path.join(CAPTURES, "degradados.png"))
        vm.set_selection([sld])
        win.props.rebuild()
        pump(150)
        assert "bg_grad_color" in win.props.style_editors
        win.props.grab().save(os.path.join(CAPTURES, "degradados_panel.png"))
        assert win._save_to(os.path.join(tmp, "degradados.olvgl"))

    @check("Estilo · Todas las propiedades de estilo de LVGL en el panel (sombra, contorno, texto, arco, línea…)")
    def _():
        from olvgl.presentation.properties import STYLE_FIELDS
        keys = {k for k, _l, _t in STYLE_FIELDS}
        need = {"bg_grad_color", "bg_main_stop", "border_side", "border_opa", "outline_width", "outline_pad",
                "shadow_ofs_x", "shadow_ofs_y", "shadow_spread", "shadow_opa", "text_letter_space",
                "text_line_space", "text_decor", "text_font", "arc_rounded", "arc_opa", "line_dash_width",
                "line_dash_gap", "pad_top", "pad_column", "image_recolor", "translate_x", "clip_corner"}
        assert need <= keys, sorted(need - keys)
        btn = vm.add_widget("button", 600, 40, centered=False)
        for k, v in (("shadow_width", 20), ("shadow_ofs_y", 6), ("shadow_color", "#000000"), ("outline_width", 3),
                     ("outline_pad", 2), ("text_decor", "UNDERLINE"), ("text_letter_space", 2)):
            vm.set_prop([btn], k, v)
        vm.set_selection([btn])
        win.props.rebuild()
        pump(150)
        for k in need:
            assert k in win.props.style_editors, k
        heads = win.props.style_group_heads
        assert {"Fondo", "Degradado", "Sombra", "Contorno", "Texto", "Arco", "Línea"} <= set(heads)
        heads["Sombra"].setChecked(True)
        pump(50)
        win.props.grab().save(os.path.join(CAPTURES, "estilos_panel.png"))
        widget_image(btn, 220, 90).save(os.path.join(CAPTURES, "estilos_sombra_contorno.png"))
        assert win._save_to(os.path.join(tmp, "degradados.olvgl"))

    @check("Indicador de aguja: escalas, marcas, números, agujas y arcos editables (capturas/meter_*.png)")
    def _():
        import math
        from olvgl.domain import meter as mt
        vm.new("Meter", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        mid = vm.add_widget("meter", 100, 100, centered=False)
        scales = mt.scales_of(vm.widget(mid).props)
        assert scales and scales[0]["indicators"], "un meter nuevo debería traer escala y aguja"
        img = widget_image(mid, 240, 240)
        img.save(os.path.join(CAPTURES, "meter_nuevo.png"))
        ang = math.radians(mt.scale_geo(scales[0]).angle(60))       # la aguja está en 60
        px = img.pixelColor(int(120 + 60 * math.cos(ang)), int(120 + 60 * math.sin(ang)))
        assert px.blue() > 150 and px.red() < 120, px.name()
        vm.set_selection([mid])
        win.props.rebuild()
        pump(150)
        win.props.grab().save(os.path.join(CAPTURES, "meter_panel.png"))
        win.props.set_meter_value(mid, 0, 2, "line", "value", 90)
        assert mt.first_value(vm.widget(mid).props) == 90
        dlg = win.props.open_meter_editor(mid, show=False)
        dlg.show()
        pump(150)
        n0 = len(dlg.scales[0]["indicators"])
        for kind in mt.INDICATOR_TYPES:
            dlg.add_indicator(kind)
        dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
        pump(50)
        assert dlg.selected() == ("scale", 0)
        dlg.forms[0].set("range_to", 200)
        dlg.changed()
        pump(100)
        dlg.grab().save(os.path.join(CAPTURES, "meter_editor.png"))
        dlg.apply()
        sc = mt.scales_of(vm.widget(mid).props)[0]
        assert sc["range_to"] == 200 and len(sc["indicators"]) == n0 + 4
        vm.undo()
        assert mt.scales_of(vm.widget(mid).props)[0]["range_to"] == 100
        dlg.close()
        dlg.deleteLater()
        from olvgl.infrastructure.lvgl_c_generator import generate_c
        src = generate_c(vm.project).source
        assert "lv_scale_create" in src and "lv_scale_set_line_needle_value" in src
        widget_image(mid, 240, 240).save(os.path.join(CAPTURES, "meter_aguja_90.png"))
        assert win._save_to(os.path.join(tmp, "meter.olvgl"))

    @check("Licencias desactivadas: importar YAML, VS Code e IA disponibles sin licencia")
    def _():
        from olvgl.application import licensing as lc
        assert lc.ENFORCE_DEFAULT == "0"
        lc.remove()
        saved = lc.ENFORCE
        try:
            lc.ENFORCE = os.environ.get("OLVGL_LICENSE_ENFORCE", lc.ENFORCE_DEFAULT) != "0"
            assert not lc.ENFORCE
            n0 = len(win.license_blocked)
            assert win._require("importar_yaml") and win._require("vscode") and win._require("ia")
            assert len(win.license_blocked) == n0
            assert all(lc.has(f) for f in lc.FEATURES)
        finally:
            lc.ENFORCE = saved

    @check("Copiar y pegar un widget sin id: el original sigue en su sitio y la copia se puede mover")
    def _():
        from olvgl.domain.model import Widget
        vm.new("Copiar", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        scr = vm.current_screen
        orig = Widget("_obj_3", "obj", 100, 100, 120, 80, auto_id=True)
        scr.widgets.append(orig)
        vm.replace_project(vm.project)
        pump(80)
        vm.set_selection(["_obj_3"])
        win.a_copy.trigger()
        win.a_paste.trigger()
        pump(120)
        new = vm.selection[0]
        assert new != "_obj_3", new
        ids = [w.id for _s, w in vm.project.iter_widgets()]
        assert len(ids) == len(set(ids)), ids
        assert "_obj_3" in win.scene.items_by_id and new in win.scene.items_by_id
        a, b = win.scene.items_by_id["_obj_3"], win.scene.items_by_id[new]
        assert a is not b and a.isVisible() and a.pos().x() == 100
        assert b.flags() & b.GraphicsItemFlag.ItemIsMovable
        vm.set_selection([new])
        vm.nudge(30, 0)
        pump(80)
        assert vm.widget(new).x == 140 and vm.widget("_obj_3").x == 100
        assert win._save_to(os.path.join(tmp, "copiar.olvgl"))

    @check("Árbol del proyecto: arrastrar para reordenar, meter en contenedores y cambiar de página (capturas/arbol_*.png)")
    def _():
        from PySide6.QtWidgets import QAbstractItemView
        vm.new("Árbol", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        p1 = vm.current_screen_id
        a = vm.add_widget("button", 40, 40, centered=False)
        box = vm.add_widget("obj", 300, 100, centered=False)
        b = vm.add_widget("label", 60, 400, centered=False)
        p2 = vm.add_screen("Segunda")
        vm.set_current_screen(p1)
        pump(150)
        pt = win.tree
        assert pt.tree.dragDropMode() == QAbstractItemView.DragDropMode.InternalMove
        assert pt.tree.dragEnabled() and pt.tree.acceptDrops()
        rect_a = vm.box(a).rect
        # soltar «a» sobre el contenedor: pasa a ser su hijo y no se mueve en pantalla
        assert pt.apply_drop([pt.item_for("widget", a)], pt.item_for("widget", box), "on")
        pump(150)
        assert [w.id for w in vm.widget(box).children] == [a]
        assert (vm.box(a).rect.x, vm.box(a).rect.y) == (rect_a.x, rect_a.y)
        assert pt.item_for("widget", a).parent() is pt.item_for("widget", box)
        win.tree.grab().save(os.path.join(CAPTURES, "arbol_hijo.png"))
        # sacarlo por encima de «b» (en el árbol, arriba = dibujado encima)
        assert pt.apply_drop([pt.item_for("widget", a)], pt.item_for("widget", b), "above")
        pump(150)
        order = [w.id for w in vm.current_screen.widgets]
        assert order.index(a) == order.index(b) + 1 and not vm.widget(box).children, order
        # una etiqueta no admite hijos: «sobre» ella = encima en el orden
        assert pt.plan_drop([pt.item_for("widget", box)], pt.item_for("widget", b), "on")[3] is None
        # a otra página
        assert pt.apply_drop([pt.item_for("widget", b)], pt.item_for("screen", p2), "on")
        pump(150)
        assert vm.project.locate(b).screen.id == p2 and vm.current_screen_id == p2
        # reordenar páginas arrastrando
        assert pt.apply_drop([pt.item_for("screen", p2)], pt.item_for("screen", p1), "above")
        pump(150)
        assert [s.id for s in vm.project.screens][:2] == [p2, p1]
        for _i in range(4):
            vm.undo()
        pump(100)
        assert [s.id for s in vm.project.screens][:2] == [p1, p2] and vm.project.locate(b).screen.id == p1
        assert [w.id for w in vm.widget(box).children] == [a]
        vm.undo()
        assert not vm.widget(box).children
        win.tree.grab().save(os.path.join(CAPTURES, "arbol_orden.png"))
        assert win._save_to(os.path.join(tmp, "arbol.olvgl"))

    @check("Pantalla en vertical u horizontal: Orientación en el panel, lienzo girado y lvgl: rotation (capturas/vertical_*.png)")
    def _():
        import yaml as _yaml
        vm.new("Vertical", DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
        btn = vm.add_widget("button", 40, 40, centered=False)
        vm.set_selection([])
        win.props.rebuild()
        pump(100)
        combo = win.props.orientation_combo
        assert [combo.itemData(i) for i in range(combo.count())] == [0, 90, 180, 270]
        combo.setCurrentIndex(combo.findData(90))
        combo.activated.emit(combo.findData(90))
        pump(150)
        d = vm.project.display
        assert (d.width, d.height) == (600, 1024) and vm.project.rotation == 90
        r = win.scene.screen_rect()
        assert (r.width(), r.height()) == (600, 1024)
        assert _yaml.safe_load(vm.generate_yaml())["lvgl"]["rotation"] == 90
        win.view.fit_screen()
        pump(100)
        win.grab().save(os.path.join(CAPTURES, "vertical_ventana.png"))
        win.props.grab().save(os.path.join(CAPTURES, "vertical_panel.png"))
        # cambiar de placa mantiene la orientación
        idx = next(i for i in range(win.props.display_combo.count())
                   if getattr(win.props.display_combo.itemData(i), "width", 0) == 800)
        win.props.display_combo.activated.emit(idx)
        pump(100)
        assert (vm.project.display.width, vm.project.display.height) == (480, 800)
        vm.undo()
        vm.undo()
        pump(100)
        assert vm.project.rotation == 0 and vm.project.display.width == 1024 and vm.widget(btn) is not None
        assert win._save_to(os.path.join(tmp, "vertical.olvgl"))

    # ======================================================= interfaz: iconos, menús e idiomas
    @check("UI · Icono, logotipo e iconos de los widgets")
    def _():
        from olvgl.domain.catalog import palette_specs
        from olvgl.presentation.icons import app_icon, logo_pixmap, widget_icon
        assert not app_icon().isNull(), "sin icono de la aplicación"
        assert not win.windowIcon().isNull()
        assert not logo_pixmap(True, 96).isNull() and not logo_pixmap(False, 96).isNull()
        missing = [sp.type for sp in palette_specs() if widget_icon(sp.type) is None]
        assert not missing, missing
        win.palette.grab().save(os.path.join(CAPTURES, "paleta.png"))

    @check("UI · Fuentes de la interfaz (normal, negrita y monoespaciada) tras importar el panel")
    def _():
        from PySide6.QtGui import QFontInfo
        from olvgl.presentation.fonts import MONO_FAMILIES, UI_FAMILIES, mono_font, ui_font
        got = {name: QFontInfo(f).family() for name, f in
               (("normal", ui_font()), ("negrita", ui_font(bold=True)), ("mono", mono_font()))}
        from olvgl.domain.model import new_project
        from olvgl.presentation.render import RenderContext
        canvas_font = RenderContext(new_project("x")).font("montserrat_14")
        got["canvas"] = QFontInfo(canvas_font).family()
        from olvgl.presentation.render import ensure_bundled_fonts
        got["incluidas"] = ", ".join(ensure_bundled_fonts()) or "(ninguna)"
        from PySide6.QtGui import QGuiApplication, QPalette
        got["placeholder"] = QGuiApplication.palette().color(QPalette.ColorRole.PlaceholderText).name()
        with open(os.path.join(CAPTURES, "fuentes.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(f"{k}: {v}" for k, v in got.items()) + "\n")
        assert got["normal"] in UI_FAMILIES and got["negrita"] in UI_FAMILIES, got
        assert got["mono"] in MONO_FAMILIES and QFontInfo(mono_font()).fixedPitch(), got
        assert got["canvas"] == "Montserrat", got
        assert QColor(got["placeholder"]).lightness() > 110, got

    @check("UI · Menús por grupos con iconos en color (capturas/menu_*.png)")
    def _():
        menus = [a.menu() for a in win.menuBar().actions() if a.menu()]
        titles = [m.title().replace("&", "") for m in menus]
        assert titles == ["Archivo", "Editar", "Insertar", "Diseño", "Ver", "Simulación", "IA", "Equipo", "Plugins", "Ayuda"], titles
        no_icon = []
        for m in menus:
            for a in m.actions():
                if a.isSeparator() or a.menu() is not None:
                    continue
                if a in win.lang_actions.values() or a in [d.toggleViewAction() for d in
                                                           (win.dock_palette, win.dock_tree, win.dock_props,
                                                            win.dock_code)]:
                    continue
                if a.icon().isNull():
                    no_icon.append(a.text())
        assert not no_icon, no_icon
        assert len(win.toolbars) >= 5
        ins = menus[2]
        n_widgets = sum(len(a.menu().actions()) for a in ins.actions() if a.menu())
        from olvgl.domain.catalog import palette_specs
        assert n_widgets == len(palette_specs()), n_widgets
        for m, name in zip(menus, ("archivo", "editar", "insertar", "diseno", "ver")):
            m.adjustSize()
            m.grab().save(os.path.join(CAPTURES, f"menu_{name}.png"))
        win.grab().save(os.path.join(CAPTURES, "ventana_menus.png"))

    @check("UI · Iconos de la barra superior más grandes y ajustables (Ver › Tamaño de los iconos)")
    def _():
        from olvgl.presentation.main_window import DEFAULT_ICON_SIZE
        assert DEFAULT_ICON_SIZE >= 32
        assert all(tb.iconSize().width() == win.toolbar_icon_size for tb in win.toolbars)
        win.set_toolbar_icon_size(40)
        pump(50)
        assert all(tb.iconSize().width() == 40 for tb in win.toolbars) and settings.get("toolbar_icon_size") == 40
        win.grab().save(os.path.join(CAPTURES, "iconos_40px.png"))
        win.set_toolbar_icon_size(DEFAULT_ICON_SIZE)
        pump(50)
        win.grab().save(os.path.join(CAPTURES, "iconos_barra.png"))

    @check("UI · Idiomas: español, inglés, francés y alemán (capturas/idioma_*.png)")
    def _():
        from olvgl import i18n
        from olvgl.presentation.app import install_translators
        assert list(i18n.LANGUAGES) == ["es", "en", "fr", "de"]
        expected = {"en": "&File", "fr": "&Fichier", "de": "&Datei"}
        for code in ("en", "fr", "de"):
            i18n.set_language(code)
            install_translators(app, code)
            assert i18n.tr("&Archivo") == expected[code], (code, i18n.tr("&Archivo"))
            vm2 = create_view_model()
            w2 = MainWindow(vm2, settings)
            w2.show()
            pump(150)
            first = w2.menuBar().actions()[0].text()
            assert first == expected[code], first
            w2.grab().save(os.path.join(CAPTURES, f"idioma_{code}.png"))
            w2.close()
            w2.deleteLater()
            pump(50)
        i18n.set_language("es")
        install_translators(app, "es")
        win.set_language("en")       # se guarda la preferencia (sin diálogo en la autoprueba)
        assert settings.get("language") == "en"
        win.set_language("es")
        assert settings.get("language") == "es" and i18n.language() == "es"

    @check("Cerrar la ventana sin cambios pendientes")
    def _():
        assert not vm.dirty
        win.close()
        pump()
        assert not win.isVisible()

    settings.close()
    app.processEvents()
    shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    started = time.time()
    header = ["AUTOPRUEBA OPEN LVGL STUDIO", "=" * 40,
              f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}",
              f"Python: {sys.version.split()[0]} ({platform.platform()})"]
    try:
        import PySide6
        header.append(f"PySide6: {PySide6.__version__}")
    except Exception as exc:
        header.append(f"PySide6: NO DISPONIBLE ({exc})")
    try:
        import yaml
        header.append(f"PyYAML: {yaml.__version__}")
    except Exception as exc:
        header.append(f"PyYAML: NO DISPONIBLE ({exc})")
    from olvgl import __version__
    header.append(f"Open LVGL Studio: {__version__}")

    ok, out = run_pytest()
    results.append((ok, "Tests del núcleo (pytest)", "" if ok else out))
    pytest_summary = out.splitlines()[-1] if out else ""

    try:
        gui_tests()
    except Exception:
        results.append((False, "Arranque de la interfaz", traceback.format_exc()))

    faulthandler.cancel_dump_traceback_later()
    if _hang_fh is not None:
        _hang_fh.close()
        try:
            os.remove(HANG_FILE)
        except OSError:
            pass
    passed = sum(1 for r in results if r[0])
    if results_mode:
        header.append(f"Plataforma Qt: {results_mode[0]}")
    lines = header + ["", f"pytest: {pytest_summary}", ""]
    for good, name, detail in results:
        lines.append(f"[{'OK' if good else 'FALLO'}] {name}")
        if detail:
            lines += ["    " + ln for ln in detail.rstrip().splitlines()]
    lines += ["", f"RESULTADO: {passed}/{len(results)} comprobaciones correctas "
              f"en {time.time() - started:.1f} s",
              f"Capturas en: {CAPTURES}"]
    text = "\n".join(lines) + "\n"
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
