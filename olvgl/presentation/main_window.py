"""Ventana principal de Open LVGL Studio."""
from __future__ import annotations

import os

import threading

from PySide6.QtCore import QByteArray, QFileSystemWatcher, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QInputDialog, QLabel, QMainWindow, QMenu,
                               QMessageBox, QToolBar)

from olvgl import APP_NAME, __version__
from olvgl import i18n
from olvgl.domain import catalog
from olvgl.i18n import tr, trf
from olvgl.application.viewmodel import ProjectViewModel
from olvgl.infrastructure import json_store
from olvgl.infrastructure.exporter import export_esphome
from olvgl.infrastructure.settings_db import SettingsDB, app_data_dir
from olvgl.presentation.canvas import DesignScene, DesignView
from olvgl.presentation.code_view import CodeView
from olvgl.presentation import render
from olvgl.presentation.dialogs import DisplayDialog, NewProjectDialog
from olvgl.presentation.icons import action_icon, app_icon, logo_pixmap, widget_icon
from olvgl.presentation.palette import WidgetPalette
from olvgl.presentation.properties import PropertiesPanel
from olvgl.presentation.simulator import SimulatorWindow
from olvgl.presentation.tree import ProjectTree

class FontFetcher(QObject):
    """Descarga en segundo plano las fuentes web/Google del proyecto (una sola vez)."""
    finished = Signal(int)

    def start(self, files: list) -> None:
        def run():
            from olvgl.infrastructure import font_cache
            ok = sum(1 for f in files if font_cache.fetch(f))
            self.finished.emit(ok)
        threading.Thread(target=run, daemon=True).start()


PROJECT_FILTER_ES = "Proyecto Open LVGL Studio (*{ext})"
SYNC_DELAY_MS = 800
YAML_FILTER = "YAML de ESPHome (*.yaml *.yml)"
ICON_SIZES = ((22, "Pequeños"), (28, "Medianos"), (32, "Grandes"), (40, "Muy grandes"))
DEFAULT_ICON_SIZE = 32
GRID_SIZES = (2, 4, 5, 8, 10, 16, 20, 25, 32, 50)
GRID_MAX = 500
AUTOSAVE_MS = 60_000


class MainWindow(QMainWindow):
    def __init__(self, vm: ProjectViewModel, settings: SettingsDB):
        super().__init__()
        self.vm = vm
        self.settings = settings
        self.simulator: SimulatorWindow | None = None
        self.resize(1500, 900)
        self.setWindowIcon(app_icon())
        self._restart_requested = False
        self._install_measures()
        vm.project_replaced.connect(self._install_measures)

        # ---------------------------------------------------------- canvas central
        self.scene = DesignScene(vm, self)
        self.view = DesignView(self.scene, self)
        self.setCentralWidget(self.view)

        # ---------------------------------------------------------- plugins (antes de la paleta)
        from olvgl.application.plugins import load_plugins
        self.plugin_log: list[str] = []
        self.errors: list[tuple[str, str]] = []    # errores inesperados (informe, resumen)
        self.license_blocked: list[str] = []       # funciones pedidas sin la edición necesaria
        self.plugins = load_plugins(set(settings.get("plugins_disabled", []) or []))
        from olvgl.application import displays
        displays.load(settings)                    # pantallas propias del usuario

        # ---------------------------------------------------------- paneles
        self.palette = WidgetPalette(vm)
        self.tree = ProjectTree(vm)
        self.props = PropertiesPanel(vm)
        self.code = CodeView(vm)
        self.code.export_requested.connect(self.export_esphome)
        self.dock_palette = self._dock(tr("Widgets"), self.palette, Qt.DockWidgetArea.LeftDockWidgetArea, "dock_palette")
        self.dock_tree = self._dock(tr("Proyecto"), self.tree, Qt.DockWidgetArea.LeftDockWidgetArea, "dock_tree")
        self.dock_props = self._dock(tr("Propiedades"), self.props, Qt.DockWidgetArea.RightDockWidgetArea, "dock_props")
        self.dock_code = self._dock(tr("YAML ESPHome"), self.code, Qt.DockWidgetArea.RightDockWidgetArea, "dock_code")
        from olvgl.presentation.comments_ui import CommentsPanel
        self.comments = CommentsPanel(vm, self._on_comments_changed)
        self.dock_comments = self._dock(tr("Comentarios"), self.comments, Qt.DockWidgetArea.RightDockWidgetArea,
                                        "dock_comments")
        self.splitDockWidget(self.dock_palette, self.dock_tree, Qt.Orientation.Vertical)
        self.tabifyDockWidget(self.dock_props, self.dock_code)
        self.tabifyDockWidget(self.dock_code, self.dock_comments)
        self.dock_props.raise_()

        # ---------------------------------------------------------- barra de estado
        self.lbl_zoom = QLabel()
        self.lbl_cursor = QLabel()
        self.lbl_sel = QLabel()
        sb = self.statusBar()
        self.lbl_sync = QLabel()
        sb.addWidget(self.lbl_sel, 1)
        sb.addPermanentWidget(self.lbl_sync)
        self.lbl_grid = QLabel()
        self.lbl_grid.setToolTip(tr("Tamaño de la rejilla (Ver › Tamaño de la rejilla)"))
        sb.addPermanentWidget(self.lbl_grid)
        sb.addPermanentWidget(self.lbl_cursor)
        sb.addPermanentWidget(self.lbl_zoom)
        self.view.zoom_changed.connect(lambda z: self.lbl_zoom.setText(f"{tr('Zoom')} {z * 100:.0f} %"))
        self.view.cursor_moved.connect(lambda x, y: self.lbl_cursor.setText(f"x {x}  y {y}"))

        size = self.settings.get("toolbar_icon_size", DEFAULT_ICON_SIZE)
        self.toolbar_icon_size = size if size in dict(ICON_SIZES) else DEFAULT_ICON_SIZE
        self._build_actions()
        self._build_menus()

        # ---------------------------------------------------------- señales del VM
        vm.dirty_changed.connect(lambda _d: self._update_title())
        vm.path_changed.connect(lambda _p: self._update_title())
        vm.history_changed.connect(self._update_actions)
        vm.selection_changed.connect(lambda _ids: self._update_actions())
        vm.selection_changed.connect(lambda _ids: self._update_status())
        vm.screen_changed.connect(lambda _id: self._update_status())
        vm.project_replaced.connect(lambda: QTimer.singleShot(0, self.view.fit_screen))

        # ---------------------------------------------------------- sincronización con el YAML (Fase 3)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)
        self.sync_timer = QTimer(self)              # escritura automática tras dejar de editar
        self.sync_timer.setSingleShot(True)
        self.sync_timer.setInterval(SYNC_DELAY_MS)
        self.sync_timer.timeout.connect(self.write_to_source)
        self.external_timer = QTimer(self)          # el fichero puede escribirse en varios pasos
        self.external_timer.setSingleShot(True)
        self.external_timer.setInterval(350)
        self.external_timer.timeout.connect(self._check_external)
        vm.project_changed.connect(self._on_model_changed_for_sync)
        vm.sync_changed.connect(self._on_sync_changed)
        vm.sync_message.connect(lambda msg: self.statusBar().showMessage(msg, 8000))
        vm.dirty_changed.connect(lambda _d: self._update_sync_label())
        self._on_sync_changed()

        # ---------------------------------------------------------- colaboración (Fase 10)
        self.presence = None
        self.lbl_team = QLabel()
        self.statusBar().addPermanentWidget(self.lbl_team)
        self.team_timer = QTimer(self)
        self.team_timer.setInterval(60_000)
        self.team_timer.timeout.connect(self.team_tick)
        self.team_timer.start()
        vm.path_changed.connect(lambda _p: self._update_presence())
        vm.project_replaced.connect(self._update_presence)
        vm.sync_changed.connect(self._update_presence)
        vm.screen_changed.connect(lambda _id: self._on_comments_changed())

        # ---------------------------------------------------------- autoguardado
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(AUTOSAVE_MS)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        self._restore_settings()
        self._update_title()
        self._update_actions()
        self._update_status()
        QTimer.singleShot(0, self.view.fit_screen)

    # ================================================================ construcción
    def _dock(self, title: str, widget, area, name: str) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setObjectName(name)
        d.setWidget(widget)
        self.addDockWidget(area, d)
        return d

    def _act(self, text: str, slot, shortcut=None, tip: str = "", icon: str = "") -> QAction:
        a = QAction(text, self)
        if icon:
            a.setIcon(action_icon(icon))
        if shortcut is not None:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setStatusTip(tip)
            a.setToolTip(tip)
        a.triggered.connect(lambda _checked=False: slot())
        return a

    def _check(self, text: str, slot, icon: str = "", checked: bool = True, tip: str = "") -> QAction:
        a = self._act(text, slot, icon=icon, tip=tip)
        a.setCheckable(True)
        a.setChecked(checked)
        return a

    def _build_actions(self) -> None:
        S = QKeySequence.StandardKey
        # --- proyecto
        self.a_new = self._act(tr("&Nuevo…"), self.new_project, S.New, tr("Nuevo proyecto"), "new")
        self.a_open = self._act(tr("&Abrir…"), self.open_project, S.Open, tr("Abrir proyecto"), "open")
        self.a_save = self._act(tr("&Guardar"), self.save, S.Save, tr("Guardar proyecto"), "save")
        self.a_save_as = self._act(tr("Guardar &como…"), self.save_as, S.SaveAs, icon="save_as")
        self.a_quit = self._act(tr("&Salir"), self.close, S.Quit, icon="quit")
        # --- importar / exportar
        self.a_import = self._act(tr("&Importar YAML de ESPHome…"), self.import_yaml, "Ctrl+I",
                                  tr("Reconstruye en el editor un YAML existente (lvgl:, fuentes, imágenes…)"),
                                  "import")
        self.a_export = self._act(tr("&Exportar ESPHome…"), self.export_esphome, "Ctrl+E",
                                  tr("Exportar ESPHome…").rstrip("…"), "export")
        self.a_export_c = self._act(tr("Exportar código &C (LVGL 9)…"), self.export_c, "Ctrl+Shift+E",
                                    tr("Genera ui.c / ui.h para LVGL 9.5+ sin ESPHome"), "export_c")
        # --- sincronización
        self.a_link = self._act(tr("&Vincular con un YAML de ESPHome…"), self.link_yaml, None,
                                tr("Los cambios del editor se escribirán en ese fichero"), "link")
        self.a_unlink = self._act(tr("Desvincular del YAML"), self.vm.unlink_source, icon="unlink")
        self.a_write = self._act(tr("Escribir cambios en el YAML ahora"),
                                 lambda: self.write_to_source(force=True), "Ctrl+Shift+Y", icon="sync")
        self.a_autosync = self._check(tr("Escritura automática en el YAML"), self._toggle_autosync, "autosync")

        # --- edición
        self.a_undo = self._act(tr("&Deshacer"), self.vm.undo, S.Undo, icon="undo")
        self.a_redo = self._act(tr("&Rehacer"), self.vm.redo, S.Redo, icon="redo")
        self.a_copy = self._act(tr("&Copiar"), self.vm.copy, S.Copy, icon="copy")
        self.a_cut = self._act(tr("Cor&tar"), self.cut, S.Cut, icon="cut")
        self.a_paste = self._act(tr("&Pegar"), self.vm.paste, S.Paste, icon="paste")
        self.a_dup = self._act(tr("D&uplicar"), self.vm.duplicate, "Ctrl+D", icon="duplicate")
        self.a_delete = self._act(tr("&Eliminar"), self.vm.delete_widgets, S.Delete, icon="delete")
        self.a_select_all = self._act(tr("Seleccionar &todo"), self.vm.select_all, S.SelectAll, icon="select_all")
        # Las acciones de edición sólo actúan con el canvas o el árbol enfocados,
        # para no interferir con los campos de texto del panel de propiedades.
        for a in (self.a_copy, self.a_cut, self.a_paste, self.a_dup, self.a_delete, self.a_select_all):
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.view.addAction(a)
            self.tree.addAction(a)

        # --- insertar
        self.a_add_page = self._act(tr("Nueva página"), self.add_page, "Ctrl+Shift+N", icon="add_page")
        self.a_toplayer = self._act(tr("Editar la capa superior (top_layer)"), self.vm.ensure_top_layer,
                                    icon="layers_edit")

        # --- diseño
        self.a_styles = self._act(tr("&Estilos y tema…"), self.open_styles, "Ctrl+Shift+T",
                                  tr("Definiciones de estilo reutilizables y tema por tipo de widget"), "styles")
        self.a_front = self._act(tr("Traer al &frente"), lambda: self.vm.change_order("front"), "Ctrl+Shift+]",
                                 icon="front")
        self.a_forward = self._act(tr("Traer &adelante"), lambda: self.vm.change_order("forward"), "Ctrl+]",
                                   icon="forward")
        self.a_backward = self._act(tr("Enviar a&trás"), lambda: self.vm.change_order("backward"), "Ctrl+[",
                                    icon="backward")
        self.a_back = self._act(tr("Enviar al &fondo"), lambda: self.vm.change_order("back"), "Ctrl+Shift+[",
                                icon="back")
        self.align_actions = [
            self._act(tr(text), lambda m=mode: self.vm.align(m), icon=f"align_{mode}")
            for text, mode in (("Alinear a la izquierda", "left"), ("Centrar horizontalmente", "hcenter"),
                               ("Alinear a la derecha", "right"), ("Alinear arriba", "top"),
                               ("Centrar verticalmente", "vcenter"), ("Alinear abajo", "bottom"))]
        self.a_dist_h = self._act(tr("Distribuir horizontalmente"), lambda: self.vm.distribute("h"), icon="dist_h")
        self.a_dist_v = self._act(tr("Distribuir verticalmente"), lambda: self.vm.distribute("v"), icon="dist_v")

        # --- ver
        self.a_zoom_in = self._act(tr("Acercar"), lambda: self.view.zoom_by(1.25), S.ZoomIn, icon="zoom_in")
        self.a_zoom_out = self._act(tr("Alejar"), lambda: self.view.zoom_by(0.8), S.ZoomOut, icon="zoom_out")
        self.a_zoom_fit = self._act(tr("Ajustar a la ventana"), self.view.fit_screen, "Ctrl+0", icon="zoom_fit")
        self.a_zoom_100 = self._act(tr("Tamaño real (100 %)"), lambda: self.view.set_zoom(1.0), "Ctrl+1",
                                    icon="zoom_100")
        self.a_grid = self._check(tr("Mostrar rejilla"), self.toggle_grid, "grid")
        self.a_snap = self._check(tr("Ajustar a la rejilla"), self.toggle_snap, "snap")
        self.a_outlines = self._check(tr("Contornos de widgets"), self.toggle_outlines, "outlines")
        self.a_toplayer_view = self._check(tr("Mostrar la capa superior sobre las páginas"),
                                           self.toggle_top_layer, "layers")

        # --- simulación y ayuda
        self.a_sim = self._act(tr("&Simulador"), self.open_simulator, "F5", tr("&Simulador").replace("&", ""),
                               "simulator")
        self.a_about = self._act(tr("&Acerca de"), self.about, icon="about")
        self.a_guide = self._act(tr("&Guía de usuario"), self.open_guide, "F1", icon="guide")
        self.a_changelog = self._act(tr("&Novedades de la versión"), self.open_changelog, icon="news")
        self.a_diagnostics = self._act(tr("Informe de &diagnóstico…"), self.open_diagnostics, icon="bug",
                                       tip=tr("Versiones, plugins y registro para adjuntar a un aviso de error"))
        self.a_logs = self._act(tr("Abrir carpeta de &registros"), self.open_logs, icon="open")

        # --- equipo (Fase 10)
        self.a_versions = self._act(tr("&Versiones…"), self.open_versions, "Ctrl+Alt+V",
                                    tr("Versiones guardadas e historial de Git, con diferencias visuales"), "history")
        self.a_save_version = self._act(tr("&Guardar versión…"), self.save_version, None,
                                        tr("Guarda una instantánea con nombre del proyecto"), "version_save")
        self.a_comments = self._act(tr("&Comentarios"), self.show_comments, "Ctrl+Alt+C",
                                    tr("Comentarios de revisión sobre los widgets"), "comment")
        self.a_components = self._act(tr("C&omponentes…"), self.open_components, "Ctrl+Alt+K",
                                      tr("Biblioteca y catálogo de componentes reutilizables"), "component")
        self.a_save_component = self._act(tr("Guardar selección como co&mponente…"), self.save_component, None,
                                          tr("Convierte los widgets seleccionados en un componente reutilizable"),
                                          "component_save")
        self.a_license = self._act(tr("&Licencia…"), self.open_license, icon="license")

        # --- IA
        self.a_ai_generate = self._act(tr("&Generar página con IA…"), self.open_ai_generate, "Ctrl+G",
                                       tr("Diseña una página a partir de una descripción"), "ai")
        self.a_ai_refactor = self._act(tr("&Refactorizar página con IA…"), self.open_ai_refactor, "Ctrl+Shift+G",
                                       tr("Cambia la página actual siguiendo una instrucción"), "refactor")
        self.a_extract_styles = self._act(tr("Extraer &estilos repetidos"), self.extract_styles, None,
                                          tr("Convierte las propiedades repetidas en estilos compartidos"), "styles")
        self.a_descriptive_ids = self._act(tr("&Ids descriptivos"), self.descriptive_ids, None,
                                           tr("Renombra btn_3, lbl_12… según su texto y actualiza las referencias"),
                                           "rename")
        self.a_ai_settings = self._act(tr("&Configurar IA…"), self.open_ai_settings, icon="settings")

        # --- idioma
        self.lang_group = QActionGroup(self)
        self.lang_group.setExclusive(True)
        self.lang_actions: dict[str, QAction] = {}
        for code, name in i18n.LANGUAGES.items():
            a = QAction(name, self)
            a.setCheckable(True)
            a.setChecked(code == i18n.language())
            a.triggered.connect(lambda _c=False, code=code: self.set_language(code))
            self.lang_group.addAction(a)
            self.lang_actions[code] = a

    def _insert_menu(self, parent: QMenu) -> None:
        """Insertar › widgets agrupados por categoría, con su icono."""
        specs = catalog.palette_specs()
        for cat in catalog.CATEGORIES:
            group = [sp for sp in specs if sp.category == cat]
            if not group:
                continue
            sm = parent.addMenu(tr(cat))
            first = widget_icon(group[0].type)
            if first is not None:
                sm.setIcon(first)
            for sp in group:
                a = sm.addAction(tr(sp.label))
                icon = widget_icon(sp.type)
                if icon is not None:
                    a.setIcon(icon)
                a.setStatusTip(tr(sp.description))
                a.triggered.connect(lambda _c=False, t=sp.type: self.vm.add_widget(t))

    def set_toolbar_icon_size(self, px: int) -> None:
        """Ver › Tamaño de los iconos: las barras de herramientas, al momento y para siempre."""
        px = int(px)
        self.toolbar_icon_size = px
        for tb in getattr(self, "toolbars", []):
            tb.setIconSize(QSize(px, px))
        if px in getattr(self, "icon_size_actions", {}):
            self.icon_size_actions[px].setChecked(True)
        self.settings.set("toolbar_icon_size", px)

    def set_grid_size(self, px: int) -> int:
        """Ver › Tamaño de la rejilla: la rejilla dibujada y el ajuste al mover o redimensionar."""
        px = max(1, min(GRID_MAX, int(px)))
        self.vm.grid_size = px
        acts = getattr(self, "grid_size_actions", {})
        if px in acts:
            acts[px].setChecked(True)
            self.a_grid_custom.setText(tr("Personalizado…"))
        elif hasattr(self, "a_grid_custom"):
            self.a_grid_custom.setText(trf("Personalizado ({px} px)…", px=px))
            self.a_grid_custom.setChecked(True)
        if hasattr(self, "scene"):
            self.scene.update()
        self.settings.set("grid_size", px)
        if hasattr(self, "lbl_grid"):
            self.lbl_grid.setText(trf("Rejilla {px} px", px=px))
        return px

    def ask_grid_size(self, value: int | None = None) -> int:
        """Tamaño de rejilla a medida (1–500 px)."""
        if value is None:
            value, ok = QInputDialog.getInt(self, tr("Tamaño de la rejilla"), tr("Separación de la rejilla (px):"),
                                            self.vm.grid_size, 1, GRID_MAX, 1)
            if not ok:
                self.set_grid_size(self.vm.grid_size)       # deja marcada la opción que estaba
                return self.vm.grid_size
        return self.set_grid_size(value)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        # ------------------------------------------------ Archivo
        m = mb.addMenu(tr("&Archivo"))
        for a in (self.a_new, self.a_open):
            m.addAction(a)
        self.recent_menu = QMenu(tr("Abrir &reciente"), self)
        self.recent_menu.setIcon(action_icon("recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addMenu(self.recent_menu)
        m.addSeparator()
        for a in (self.a_save, self.a_save_as):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_import)
        em = m.addMenu(action_icon("export"), tr("Exportar"))
        self.export_menu = em
        em.aboutToShow.connect(self._fill_export_menu)
        self._fill_export_menu()
        m.addSeparator()
        sm = m.addMenu(action_icon("link"), tr("Sincronización con YAML"))
        for a in (self.a_link, self.a_unlink):
            sm.addAction(a)
        sm.addSeparator()
        for a in (self.a_write, self.a_autosync):
            sm.addAction(a)
        m.addSeparator()
        m.addAction(self.a_quit)

        # ------------------------------------------------ Editar
        m = mb.addMenu(tr("&Editar"))
        for a in (self.a_undo, self.a_redo):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_cut, self.a_copy, self.a_paste, self.a_dup):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_delete)
        m.addSeparator()
        m.addAction(self.a_select_all)

        # ------------------------------------------------ Insertar
        m = mb.addMenu(tr("&Insertar"))
        self.insert_menu = m
        m.aboutToShow.connect(self._fill_insert_menu)
        self._fill_insert_menu()

        # ------------------------------------------------ Diseño
        m = mb.addMenu(tr("&Diseño"))
        m.addAction(self.a_styles)
        m.addSeparator()
        am = m.addMenu(action_icon("align_left"), tr("Alinear"))
        for i, a in enumerate(self.align_actions):
            if i == 3:
                am.addSeparator()
            am.addAction(a)
        dm = m.addMenu(action_icon("dist_h"), tr("Distribuir"))
        dm.addAction(self.a_dist_h)
        dm.addAction(self.a_dist_v)
        om = m.addMenu(action_icon("front"), tr("Orden"))
        for a in (self.a_front, self.a_forward, self.a_backward, self.a_back):
            om.addAction(a)

        # ------------------------------------------------ Ver
        m = mb.addMenu(tr("&Ver"))
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_zoom_fit, self.a_zoom_100):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_grid, self.a_snap, self.a_outlines, self.a_toplayer_view):
            m.addAction(a)
        gm = m.addMenu(action_icon("grid"), tr("Tamaño de la rejilla"))
        self.grid_size_menu = gm
        self.grid_size_group = QActionGroup(self)
        self.grid_size_group.setExclusive(True)
        self.grid_size_actions = {}
        for px in GRID_SIZES:
            a = gm.addAction(f"{px} px")
            a.setCheckable(True)
            a.setChecked(px == self.vm.grid_size)
            a.triggered.connect(lambda _c=False, v=px: self.set_grid_size(v))
            self.grid_size_group.addAction(a)
            self.grid_size_actions[px] = a
        gm.addSeparator()
        self.a_grid_custom = gm.addAction(tr("Personalizado…"))
        self.a_grid_custom.setCheckable(True)
        self.a_grid_custom.triggered.connect(lambda _c=False: self.ask_grid_size())
        self.grid_size_group.addAction(self.a_grid_custom)
        m.addSeparator()
        pm = m.addMenu(action_icon("panels"), tr("Paneles"))
        for d in (self.dock_palette, self.dock_tree, self.dock_props, self.dock_code, self.dock_comments):
            pm.addAction(d.toggleViewAction())
        lm = m.addMenu(action_icon("language"), tr("Idioma"))
        self.language_menu = lm
        for a in self.lang_actions.values():
            lm.addAction(a)
        im = m.addMenu(action_icon("zoom_in"), tr("Tamaño de los iconos"))
        self.icon_size_menu = im
        self.icon_size_group = QActionGroup(self)
        self.icon_size_group.setExclusive(True)
        self.icon_size_actions = {}
        for px, label in ICON_SIZES:
            a = im.addAction(f"{tr(label)} ({px} px)")
            a.setCheckable(True)
            a.setChecked(px == self.toolbar_icon_size)
            a.triggered.connect(lambda _c=False, v=px: self.set_toolbar_icon_size(v))
            self.icon_size_group.addAction(a)
            self.icon_size_actions[px] = a

        # ------------------------------------------------ Simulación
        m = mb.addMenu(tr("Si&mulación"))
        m.addAction(self.a_sim)

        # ------------------------------------------------ IA
        m = mb.addMenu(tr("I&A"))
        self.ai_menu = m
        m.addAction(self.a_ai_generate)
        m.addAction(self.a_ai_refactor)
        m.addSeparator()
        m.addAction(self.a_extract_styles)
        m.addAction(self.a_descriptive_ids)
        m.addSeparator()
        m.addAction(self.a_ai_settings)

        # ------------------------------------------------ Equipo
        m = mb.addMenu(tr("E&quipo"))
        self.team_menu = m
        for a in (self.a_versions, self.a_save_version):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_comments)
        m.addSeparator()
        for a in (self.a_components, self.a_save_component):
            m.addAction(a)

        # ------------------------------------------------ Plugins
        m = mb.addMenu(tr("&Plugins"))
        self.plugins_menu = m
        m.aboutToShow.connect(self._fill_plugins_menu)
        self._fill_plugins_menu()

        # ------------------------------------------------ Ayuda
        m = mb.addMenu(tr("A&yuda"))
        for a in (self.a_guide, self.a_changelog):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_diagnostics, self.a_logs):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_license)
        m.addAction(self.a_about)

        # ------------------------------------------------ barras de herramientas por grupos
        def bar(title: str, name: str, actions) -> QToolBar:
            tb = QToolBar(title, self)
            tb.setObjectName(name)
            tb.setIconSize(QSize(self.toolbar_icon_size, self.toolbar_icon_size))
            for a in actions:
                if a is None:
                    tb.addSeparator()
                else:
                    tb.addAction(a)
            self.addToolBar(tb)
            return tb
        self.toolbars = [
            bar(tr("Archivo"), "toolbar_file", (self.a_new, self.a_open, self.a_save)),
            bar(tr("Editar"), "toolbar_edit", (self.a_undo, self.a_redo, None, self.a_cut, self.a_copy,
                                               self.a_paste, self.a_delete)),
            bar(tr("Diseño"), "toolbar_design", (*self.align_actions, None, self.a_front, self.a_back,
                                                 None, self.a_styles)),
            bar(tr("Ver"), "toolbar_view", (self.a_zoom_out, self.a_zoom_fit, self.a_zoom_in, None,
                                            self.a_grid, self.a_snap)),
            bar(tr("ESPHome"), "toolbar_esphome", (self.a_import, self.a_export, self.a_export_c, None,
                                                   self.a_write)),
            bar(tr("Simulación"), "toolbar_run", (self.a_sim, None, self.a_ai_generate, self.a_ai_refactor)),
        ]

    # ================================================================ menús dinámicos (plugins)
    def _fill_insert_menu(self) -> None:
        m = self.insert_menu
        m.clear()
        self._insert_menu(m)
        m.addSeparator()
        m.addAction(self.a_add_page)
        m.addAction(self.a_toplayer)

    def _fill_export_menu(self) -> None:
        from olvgl.domain.extensions import REGISTRY
        em = self.export_menu
        em.clear()
        em.addAction(self.a_export)
        em.addAction(self.a_export_c)
        if REGISTRY.exporters:
            em.addSeparator()
            for ex in REGISTRY.exporters.values():
                a = em.addAction(action_icon("plugin"), tr(ex.name) + "…")
                a.setStatusTip(tr(ex.description))
                a.triggered.connect(lambda _c=False, eid=ex.id: self.export_with_plugin(eid))

    def _fill_plugins_menu(self) -> None:
        from olvgl.domain.extensions import REGISTRY
        m = self.plugins_menu
        m.clear()
        a = m.addAction(action_icon("plugin"), tr("Gestionar plugins…"))
        a.triggered.connect(lambda _c=False: self.open_plugins_dialog())
        a = m.addAction(action_icon("check"), tr("Comprobar el proyecto"))
        a.setStatusTip(tr("Ejecuta las reglas de los plugins sobre el proyecto"))
        a.triggered.connect(lambda _c=False: self.check_project())
        if REGISTRY.commands:
            m.addSeparator()
            for cmd in REGISTRY.commands.values():
                a = m.addAction(action_icon("plugin"), tr(cmd.label))
                a.setStatusTip(tr(cmd.description))
                a.triggered.connect(lambda _c=False, cid=cmd.id: self.run_plugin_command(cid))

    def plugins_reloaded(self) -> None:
        self.palette.rebuild()
        self._fill_insert_menu()
        self._fill_export_menu()
        self._fill_plugins_menu()
        self.vm.invalidate_layout()
        self.scene.update()

    def open_plugins_dialog(self) -> None:
        from olvgl.presentation.plugins_ui import PluginsDialog
        PluginsDialog(self.plugins, self.settings, self.plugins_reloaded, self).exec()

    def check_project(self, show: bool = True):
        from olvgl.domain.extensions import validate
        issues = validate(self.vm.project)
        if show:
            from olvgl.presentation.plugins_ui import IssuesDialog
            IssuesDialog(issues, self._select_widget, self).exec()
        return issues

    def _select_widget(self, widget_id: str, page_id: str | None) -> None:
        loc = self.vm.project.locate(widget_id)
        if loc is None:
            return
        self.vm.set_current_screen(loc.screen.id)
        self.vm.set_selection([widget_id])

    def run_plugin_command(self, command_id: str) -> bool:
        def log(msg: str) -> None:
            self.plugin_log.append(msg)
            self.statusBar().showMessage(msg, 8000)
        return self.plugins.run_command(command_id, self.vm, log, self)

    def export_with_plugin(self, exporter_id: str, folder: str | None = None) -> list[str]:
        from olvgl.domain.extensions import REGISTRY
        ex = REGISTRY.exporters.get(exporter_id)
        if ex is None:
            return []
        if folder is None:
            start = self.settings.get("last_plugin_export_dir") or (
                os.path.dirname(self.vm.path) if self.vm.path else os.path.expanduser("~"))
            folder = QFileDialog.getExistingDirectory(self, tr(ex.name), start)
            if not folder:
                return []
            self.settings.set("last_plugin_export_dir", folder)
            interactive = True
        else:
            interactive = False
        try:
            files = self.plugins.export(exporter_id, self.vm.project, folder)
        except Exception as exc:
            if interactive:
                QMessageBox.critical(self, tr("Error al exportar"), f"{ex.plugin}: {exc}")
            raise
        if interactive:
            QMessageBox.information(self, tr(ex.name), "\n".join([tr("Ficheros escritos:")] + [f"  • {f}" for f in files]))
        return files

    # ================================================================ equipo (Fase 10)
    def _require(self, feature: str) -> bool:
        from olvgl.application import licensing
        if licensing.has(feature):
            return True
        msg = trf("«{feature}» está disponible en la edición {edition}. Ayuda › Licencia para cargar la tuya.",
                  feature=tr(licensing.FEATURE_NAMES.get(feature, feature)),
                  edition=licensing.EDITION_NAMES[licensing.FEATURES[feature]])
        self.statusBar().showMessage(msg, 10000)
        self.license_blocked.append(feature)
        if not os.environ.get("OLVGL_AUTOPRUEBA"):
            box = QMessageBox(self)
            box.setWindowTitle(tr("Licencia"))
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(msg)
            show = box.addButton(tr("Ver mi licencia…"), QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Close)
            box.exec()
            if box.clickedButton() is show:
                self.open_license()
        return False

    def open_versions(self, show: bool = True):
        from olvgl.presentation.versions_ui import VersionsDialog
        dlg = VersionsDialog(self.vm, self)
        if show:
            dlg.exec()
        return dlg

    def save_version(self, label: str | None = None):
        from olvgl.infrastructure.versions import VersionStore
        if label is None:
            from PySide6.QtWidgets import QInputDialog
            label, ok = QInputDialog.getText(self, tr("Guardar versión"), tr("Descripción de la versión:"))
            if not ok:
                return None
        info = VersionStore(self.vm.document_path).save(self.vm.project, label)
        self.statusBar().showMessage(trf("Versión guardada: {label}", label=info.label), 6000)
        return info

    def show_comments(self) -> None:
        self.dock_comments.show()
        self.dock_comments.raise_()
        self.comments.text.setFocus()

    def _on_comments_changed(self) -> None:
        if not hasattr(self, "scene") or not hasattr(self, "comments"):
            return
        self.scene.comment_counts = self.comments.counts()
        self.scene.update()

    def open_components(self, show: bool = True):
        from olvgl.presentation.components_ui import ComponentsDialog
        dlg = ComponentsDialog(self.vm, self.settings, self)
        if show:
            dlg.exec()
        return dlg

    def save_component(self, show: bool = True):
        if not self.vm.selection:
            self.statusBar().showMessage(tr("Selecciona los widgets que formarán el componente"), 6000)
            return None
        from olvgl.presentation.components_ui import SaveComponentDialog
        dlg = SaveComponentDialog(self.vm, self.settings, self)
        if show:
            dlg.exec()
        return dlg

    def open_license(self, show: bool = True):
        from olvgl.presentation.license_ui import LicenseDialog
        dlg = LicenseDialog(self)
        if show:
            dlg.exec()
        return dlg

    def _update_presence(self) -> None:
        from olvgl.infrastructure.collab import Presence
        doc = self.vm.document_path
        if self.presence is not None and (doc is None or not self.presence.dir.startswith(doc)):
            self.presence.leave()
            self.presence = None
        if doc and self.presence is None:
            self.presence = Presence(doc)
        self.team_tick()

    def team_tick(self) -> list:
        """Cada minuto: latido de presencia, quién más lo tiene abierto y comentarios nuevos."""
        others = []
        if self.presence is not None:
            try:
                self.presence.heartbeat()
                others = self.presence.others()
            except OSError:
                others = []
        if others:
            self.lbl_team.setText("👥 " + ", ".join(p.label for p in others))
            self.lbl_team.setToolTip(tr("También tienen abierto este proyecto. Al guardar se fusionan los cambios."))
        else:
            self.lbl_team.setText("")
        if self.vm.path and self.vm.disk_changed():
            self.statusBar().showMessage(tr("Otra persona ha guardado este proyecto: sus cambios se fusionarán "
                                            "con los tuyos al guardar"), 10000)
        self.comments.reload()
        return others

    def _report_merge(self) -> None:
        r = self.vm.last_merge
        if r is None:
            return
        if r.conflicts and not os.environ.get("OLVGL_AUTOPRUEBA"):
            QMessageBox.information(self, tr("Cambios fusionados"), trf(
                "Se han incorporado {n} cambios de otra persona. En {c} casos los dos habíais cambiado lo mismo "
                "y se ha mantenido lo tuyo:", n=r.from_theirs, c=len(r.conflicts)) + "\n\n"
                + "\n".join(f"• {c}" for c in r.conflicts[:20]))

    # ================================================================ IA y refactorización
    def open_ai_generate(self, show: bool = True):
        if not self._require("ia"):
            return None
        from olvgl.presentation.ai_ui import GenerateDialog
        dlg = GenerateDialog(self.vm, self.settings, self)
        if show:
            dlg.exec()
        return dlg

    def open_ai_refactor(self, show: bool = True):
        if not self._require("ia"):
            return None
        from olvgl.presentation.ai_ui import RefactorDialog
        dlg = RefactorDialog(self.vm, self.settings, self)
        if show:
            dlg.exec()
        return dlg

    def open_ai_settings(self, show: bool = True):
        if not self._require("ia"):
            return None
        from olvgl.presentation.ai_ui import AISettingsDialog
        dlg = AISettingsDialog(self.settings, self)
        if show:
            dlg.exec()
        return dlg

    def extract_styles(self):
        if not self._require("ia"):
            return None
        from olvgl.domain.refactor import extract_styles
        project, rep = extract_styles(self.vm.project)
        if rep.styles_created:
            self.vm.apply_project(tr("Extraer estilos repetidos"), project)
            msg = trf("{n} estilo(s) creados: {ids}", n=len(rep.styles_created), ids=", ".join(rep.styles_created[:6]))
        else:
            msg = tr("No hay propiedades repetidas en 3 o más widgets")
        self.statusBar().showMessage(msg, 10000)
        return rep

    def descriptive_ids(self):
        if not self._require("ia"):
            return None
        from olvgl.domain.refactor import descriptive_ids
        project, rep = descriptive_ids(self.vm.project)
        if rep.renamed:
            self.vm.apply_project(tr("Ids descriptivos"), project)
            msg = trf("{n} id(s) renombrados (referencias actualizadas)", n=len(rep.renamed))
        else:
            msg = tr("No hay ids automáticos que renombrar")
        self.statusBar().showMessage(msg, 10000)
        return rep

    def add_page(self) -> None:
        self.vm.set_current_screen(self.vm.add_screen(trf("Pantalla {n}", n=len(self.vm.project.screens) + 1)))

    def set_language(self, code: str) -> None:
        if code == self.settings.get("language", i18n.DEFAULT) and code == i18n.language():
            return
        self.settings.set("language", code)
        i18n.set_language(code)
        if os.environ.get("OLVGL_AUTOPRUEBA"):
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("Idioma"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(tr("El idioma se aplicará al reiniciar la aplicación."))
        restart = box.addButton(tr("Reiniciar ahora"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Más tarde"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is restart:
            self._restart_requested = True
            self.close()

    # ================================================================ estado
    def _update_title(self) -> None:
        name = os.path.basename(self.vm.path) if self.vm.path else (
            self.vm.sync.name if getattr(self.vm, "sync", None) else tr("sin título"))
        star = "●" if self.vm.dirty else ""
        self.setWindowTitle(f"{star}{name} — {self.vm.project.name} — {APP_NAME}")

    def _update_actions(self) -> None:
        h = self.vm.history
        self.a_undo.setEnabled(h.can_undo)
        self.a_redo.setEnabled(h.can_redo)
        self.a_undo.setText(f"{tr('&Deshacer')} {tr(h.undo_label) if h.undo_label else ''}".strip())
        self.a_redo.setText(f"{tr('&Rehacer')} {tr(h.redo_label) if h.redo_label else ''}".strip())
        has = bool(self.vm.selection)
        for a in (self.a_copy, self.a_cut, self.a_dup, self.a_delete, self.a_front, self.a_forward,
                  self.a_backward, self.a_back, *self.align_actions):
            a.setEnabled(has)
        many = len(self.vm.selection) >= 3
        self.a_dist_h.setEnabled(many)
        self.a_dist_v.setEnabled(many)

    def _update_status(self) -> None:
        s = self.vm.current_screen
        n = len(self.vm.selection)
        sel = " · " + trf("{n} seleccionado(s)", n=n) if n else ""
        self.lbl_sel.setText(tr("Pantalla") + f": {s.name if s else '-'}{sel}")

    # ================================================================ ajustes
    def _restore_settings(self) -> None:
        geo = self.settings.get("window_geometry")
        state = self.settings.get("window_state")
        try:
            if geo:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            if state:
                self.restoreState(QByteArray.fromBase64(state.encode("ascii")))
        except Exception:
            pass
        self.a_autosync.setChecked(bool(self.settings.get("autosync", True)))
        try:
            self.set_grid_size(int(self.settings.get("grid_size", 10)))
        except (TypeError, ValueError):
            self.set_grid_size(10)
        self.vm.snap = bool(self.settings.get("snap", True))
        self.scene.show_grid = bool(self.settings.get("show_grid", True))
        self.a_snap.setChecked(self.vm.snap)
        self.a_grid.setChecked(self.scene.show_grid)

    def _save_settings(self) -> None:
        self.settings.set("window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        self.settings.set("window_state", bytes(self.saveState().toBase64()).decode("ascii"))
        self.settings.set("snap", self.vm.snap)
        self.settings.set("show_grid", self.scene.show_grid)
        self.settings.set("grid_size", self.vm.grid_size)

    def toggle_grid(self) -> None:
        self.scene.show_grid = self.a_grid.isChecked()
        self.scene.update()

    def toggle_snap(self) -> None:
        self.vm.snap = self.a_snap.isChecked()

    def toggle_top_layer(self) -> None:
        self.scene.show_top_layer = self.a_toplayer_view.isChecked()
        self.scene.update()

    def _install_measures(self) -> None:
        """El motor de disposición mide el texto y las imágenes con Qt (fuentes reales)."""
        ctx = render.RenderContext(self.vm.project, self.vm.resolve_path)
        self.vm.measure_text = ctx.measure_text
        self.vm.image_size = ctx.image_size_of
        self.vm.invalidate_layout()
        self._fetch_fonts()

    def _fetch_fonts(self) -> None:
        from olvgl.infrastructure import font_cache
        if os.environ.get("OLVGL_NO_FONT_DOWNLOAD"):
            return
        missing = font_cache.missing_fonts(self.vm.project.fonts)
        if not missing or getattr(self, "_fetching", False):
            return
        self._fetching = True
        self.statusBar().showMessage(trf("Descargando {n} fuente(s) del proyecto…", n=len(missing)))
        self._fetcher = FontFetcher()
        self._fetcher.finished.connect(self._fonts_ready)
        self._fetcher.start(missing)

    def _fonts_ready(self, ok: int) -> None:
        self._fetching = False
        if ok:
            self.statusBar().showMessage(trf("{n} fuente(s) descargada(s)", n=ok), 4000)
            ctx = render.RenderContext(self.vm.project, self.vm.resolve_path)
            self.vm.measure_text = ctx.measure_text
            self.vm.invalidate_layout()
        else:
            self.statusBar().showMessage(tr("No se pudieron descargar las fuentes: se usa una de sustitución"), 6000)

    def toggle_outlines(self) -> None:
        self.scene.show_outlines = self.a_outlines.isChecked()
        self.scene.update()

    # ================================================================ archivo
    def _confirm_discard(self) -> bool:
        if not self.vm.dirty:
            return True
        if self.vm.linked and self.a_autosync.isChecked():
            return self.write_to_source(force=True)   # escritura automática: no hace falta preguntar
        r = QMessageBox.question(
            self, APP_NAME, tr("El proyecto tiene cambios sin guardar. ¿Guardarlos?"),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        dlg = NewProjectDialog(self, self.settings)
        if dlg.exec():
            json_store.discard_autosave(self.vm.path, app_data_dir())
            name, display = dlg.result_project()
            self.vm.new(name, display, dlg.rotation())

    def open_project(self, path: str | None = None) -> bool:
        if not path:
            if not self._confirm_discard():
                return False
            start = self.settings.get("last_dir", os.path.expanduser("~"))
            path, _ = QFileDialog.getOpenFileName(self, tr("Abrir proyecto"), start, tr(PROJECT_FILTER_ES).format(ext=json_store.EXTENSION))
            if not path:
                return False
        try:
            auto = json_store.pending_autosave(path, app_data_dir())
            if auto and QMessageBox.question(
                    self, tr("Recuperar"), tr("Hay un autoguardado más reciente de este proyecto. ¿Recuperarlo?")
            ) == QMessageBox.StandardButton.Yes:
                self.vm.replace_project(json_store.load_project(auto), path)
                self.vm.mark_dirty_external()
            else:
                self.vm.open(path)
                from olvgl.application import licensing
                if self.vm.linked and not licensing.has("importar_yaml"):
                    self.vm.unlink_source()       # el proyecto se abre, sin sincronizar su YAML
                    self._require("importar_yaml")
                self._resolve_source_divergence()
        except (OSError, json_store.ProjectFormatError, ValueError) as exc:
            QMessageBox.critical(self, tr("No se pudo abrir"), str(exc))
            self.settings.remove_recent(path)
            return False
        self.settings.set("last_dir", os.path.dirname(os.path.abspath(path)))
        self.settings.add_recent(path, self.vm.project.name)
        return True

    def _resolve_source_divergence(self) -> None:
        """Al abrir un .olvgl vinculado cuyo YAML ha cambiado desde que se guardó."""
        if not self.vm.linked:
            if self.vm.project.source.get("linked") and self.vm.sync_error:
                self.statusBar().showMessage(trf("No se pudo revincular el YAML: {err}", err=self.vm.sync_error), 8000)
            return
        try:
            differs = self.vm.sync.differs(self.vm.project)
        except Exception:
            return
        if not differs:
            return
        if os.environ.get("OLVGL_AUTOPRUEBA"):
            self.vm.reload_source()
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("El YAML vinculado ha cambiado"))
        box.setText(trf("«{name}» no coincide con el proyecto guardado.", name=self.vm.sync.name))
        box.setInformativeText(tr("¿Qué versión quieres conservar?"))
        use_yaml = box.addButton(tr("Cargar desde el YAML"), QMessageBox.ButtonRole.AcceptRole)
        use_project = box.addButton(tr("Escribir el proyecto en el YAML"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Desvincular"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is use_yaml:
            self.vm.reload_source()
        elif box.clickedButton() is use_project:
            self.write_to_source(force=True)
        else:
            self.vm.unlink_source()

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recent = self.settings.recent()
        if not recent:
            a = self.recent_menu.addAction(tr("(vacío)"))
            a.setEnabled(False)
            return
        for path, name in recent:
            a = self.recent_menu.addAction(f"{name or os.path.basename(path)} — {path}")
            a.triggered.connect(lambda _c=False, p=path: self._open_recent(p))

    def _open_recent(self, path: str) -> None:
        if self._confirm_discard():
            self.open_project(path)

    def save(self) -> bool:
        """Con un YAML vinculado escribe en él (y en el .olvgl si existe)."""
        if self.vm.linked:
            ok = self.write_to_source(force=True)
            if self.vm.path:
                ok = self._save_to(self.vm.path) and ok
            return ok
        if not self.vm.path:
            return self.save_as()
        return self._save_to(self.vm.path)

    # ================================================================ sincronización
    def _toggle_autosync(self) -> None:
        if self.vm.sync is not None:
            self.vm.sync.auto = self.a_autosync.isChecked()
        self.settings.set("autosync", self.a_autosync.isChecked())
        if self.a_autosync.isChecked() and self.vm.dirty:
            self.sync_timer.start()

    def _on_model_changed_for_sync(self) -> None:
        if self.vm.linked and self.a_autosync.isChecked() and self.vm.dirty:
            self.sync_timer.start()
        self._update_sync_label()

    def write_to_source(self, force: bool = False) -> bool:
        self.sync_timer.stop()
        if not self.vm.linked:
            return False
        if not force and not self.a_autosync.isChecked():
            return False
        try:
            out = self.vm.sync_to_source()
        except Exception as exc:
            QMessageBox.critical(self, tr("No se pudo escribir en el YAML"), str(exc))
            return False
        self._rewatch()
        if out is not None and out.written:
            self.statusBar().showMessage(trf("Escrito en {name} ({n} cambio(s))", name=self.vm.sync.name, n=out.edits), 3000)
        self._update_sync_label()
        return True

    def _on_file_changed(self, _path: str) -> None:
        self.external_timer.start()

    def _check_external(self) -> None:
        self._rewatch()   # los editores que guardan reemplazando el fichero rompen la vigilancia
        if self.vm.linked:
            self.vm.check_external()
            self._update_sync_label()

    def _rewatch(self) -> None:
        files = self.watcher.files()
        if files:
            self.watcher.removePaths(files)
        if self.vm.sync is not None and os.path.exists(self.vm.sync.path):
            self.watcher.addPath(self.vm.sync.path)

    def _on_sync_changed(self) -> None:
        if self.vm.sync is not None:
            self.vm.sync.auto = self.a_autosync.isChecked() if hasattr(self, "a_autosync") else True
        self._rewatch()
        linked = self.vm.linked
        for a in (self.a_unlink, self.a_write):
            a.setEnabled(linked)
        self._update_sync_label()
        self._update_title()

    def _update_sync_label(self) -> None:
        if not hasattr(self, "lbl_sync"):
            return
        if self.vm.sync is None:
            self.lbl_sync.setText(tr("Sin vincular a YAML"))
            self.lbl_sync.setStyleSheet("color: #888;")
            self.lbl_sync.setToolTip(self.vm.sync_error or tr("Archivo → Sincronización con YAML → Vincular…"))
            return
        state = tr("cambios pendientes") if self.vm.dirty else "sincronizado"
        self.lbl_sync.setText(f"⇄ {self.vm.sync.name} · {state}")
        self.lbl_sync.setStyleSheet("color: #FFB74D;" if self.vm.dirty else "color: #81C784;")
        tip = self.vm.sync.path
        if self.vm.sync.backup_path:
            tip += f"\nCopia de seguridad: {self.vm.sync.backup_path}"
        self.lbl_sync.setToolTip(tip)

    def link_yaml(self) -> None:
        if not self._require("importar_yaml"):
            return
        start = self.settings.get("last_import_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, tr("Vincular con un YAML de ESPHome"), start, tr(YAML_FILTER))
        if not path:
            return
        if QMessageBox.question(
                self, tr("Vincular con YAML"),
                f"Las secciones lvgl:, font:, image: y color: de «{os.path.basename(path)}» pasarán a "
                "reflejar este proyecto (el resto del fichero no se toca y se guarda una copia "
                f"de seguridad {os.path.basename(path)}.olvgl.bak). ¿Continuar?"
        ) != QMessageBox.StandardButton.Yes:
            return
        if not self.vm.link_source(path):
            QMessageBox.warning(self, tr("No se puede vincular"), self.vm.sync_error or "")
            return
        self.statusBar().showMessage(trf("Vinculado con {path}", path=path), 5000)

    def save_as(self) -> bool:
        start = self.vm.path or os.path.join(self.settings.get("last_dir", os.path.expanduser("~")),
                                             self.vm.project.esphome.device_name + json_store.EXTENSION)
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar proyecto"), start, tr(PROJECT_FILTER_ES).format(ext=json_store.EXTENSION))
        if not path:
            return False
        if not path.endswith(json_store.EXTENSION):
            path += json_store.EXTENSION
        return self._save_to(path)

    def _save_to(self, path: str) -> bool:
        old_path = self.vm.path
        try:
            self.vm.save(path)
        except OSError as exc:
            QMessageBox.critical(self, tr("No se pudo guardar"), str(exc))
            return False
        self._report_merge()
        json_store.discard_autosave(path, app_data_dir())
        if old_path is None:
            json_store.discard_autosave(None, app_data_dir())
        self.settings.set("last_dir", os.path.dirname(os.path.abspath(path)))
        self.settings.add_recent(path, self.vm.project.name)
        self.statusBar().showMessage(trf("Guardado en {path}", path=path), 4000)
        return True

    def autosave(self) -> None:
        if not self.vm.dirty:
            return
        try:
            json_store.write_autosave(self.vm.project, self.vm.path, app_data_dir())
            self.statusBar().showMessage(tr("Autoguardado"), 2000)
        except OSError:
            pass

    def check_untitled_recovery(self) -> None:
        auto = json_store.pending_autosave(None, app_data_dir())
        if not auto:
            return
        if QMessageBox.question(self, tr("Recuperar"),
                                tr("Se cerró sin guardar un proyecto sin título. ¿Recuperarlo?")
                                ) == QMessageBox.StandardButton.Yes:
            try:
                self.vm.replace_project(json_store.load_project(auto), None)
                self.vm.mark_dirty_external()
                return
            except (OSError, json_store.ProjectFormatError, ValueError) as exc:
                QMessageBox.warning(self, tr("Recuperar"), trf("No se pudo recuperar: {exc}", exc=exc))
        json_store.discard_autosave(None, app_data_dir())

    def import_yaml(self, path: str | None = None) -> bool:
        if not self._require("importar_yaml"):
            return False
        if not self._confirm_discard():
            return False
        if not path:
            start = self.settings.get("last_import_dir", os.path.expanduser("~"))
            path, _ = QFileDialog.getOpenFileName(self, tr("Importar YAML de ESPHome"), start, tr(YAML_FILTER))
            if not path:
                return False
        from olvgl.infrastructure.esphome_importer import ImportError_
        from olvgl.infrastructure.yaml_parser import YamlParseError
        try:
            report = self.vm.import_yaml(path)
        except (OSError, YamlParseError, ImportError_, ValueError) as exc:
            QMessageBox.critical(self, tr("No se pudo importar"), str(exc))
            return False
        self.settings.set("last_import_dir", os.path.dirname(os.path.abspath(path)))
        self._install_measures()
        if any("resolución" in w for w in report.warnings):
            dlg = DisplayDialog(self.vm.project.display, self)
            if dlg.exec():
                self.vm.set_display_keep_orientation(dlg.result_display())
                report.warnings = [w for w in report.warnings if "resolución" not in w]
        self.show_import_report(report)
        QTimer.singleShot(0, self.view.fit_screen)
        return True

    def show_import_report(self, report) -> None:
        text = report.summary()
        if report.warnings:
            text += "\n\nAvisos:\n" + "\n".join(f"  ⚠ {w}" for w in report.warnings[:30])
            if len(report.warnings) > 30:
                text += f"\n  … y {len(report.warnings) - 30} más"
        if self.vm.linked:
            text += (f"\n\nVinculado con {os.path.basename(report.path)}: los cambios que hagas se escriben "
                     "en ese fichero tocando sólo las líneas afectadas (comentarios y resto de secciones "
                     f"intactos). La primera escritura guarda una copia en {os.path.basename(report.path)}"
                     ".olvgl.bak. Si editas el YAML a mano, la app lo recarga sola (Ctrl+Z lo deshace).")
        else:
            text += (tr("\n\nNo se puede escribir directamente en este fichero")
                     + (f" ({self.vm.sync_error})" if self.vm.sync_error else "")
                     + tr(". Guárdalo como .olvgl y usa Exportar ESPHome."))
        box = QMessageBox(self)
        box.setWindowTitle(tr("Importación completada"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(trf("Importado: {name}", name=os.path.basename(report.path)))
        box.setInformativeText(text)
        box.exec()

    def export_esphome(self) -> None:
        start = self.settings.get("last_export_dir") or (
            os.path.join(os.path.dirname(self.vm.path), "esphome") if self.vm.path else os.path.expanduser("~"))
        out = QFileDialog.getExistingDirectory(self, tr("Carpeta de exportación ESPHome"), start)
        if not out:
            return
        try:
            rep = export_esphome(self.vm.project, out, self.vm.path)
        except OSError as exc:
            QMessageBox.critical(self, tr("Error al exportar"), str(exc))
            return
        self.settings.set("last_export_dir", out)
        lines = [tr("Ficheros escritos:")] + [f"  • {p}" for p in rep.written]
        if rep.skipped:
            lines += ["", tr("No sobrescritos (ya existían):")] + [f"  • {p}" for p in rep.skipped]
        if rep.warnings:
            lines += ["", tr("Avisos:")] + [f"  ⚠ {w}" for w in rep.warnings]
        if self.vm.project.source.get("path"):
            lines += ["", tr("Este proyecto se importó de un YAML existente: en el YAML de tu dispositivo "
                      "quita las secciones lvgl:, font:, image: y color: (ahora están en ui_lvgl.yaml) "
                      "e inclúyelo con packages, o usa Archivo › Sincronización con YAML para "
                      "editar directamente el fichero original.")]
        QMessageBox.information(self, tr("Exportación ESPHome"), "\n".join(lines))

    def export_c(self) -> None:
        from olvgl.infrastructure.lvgl_c_generator import export_c
        start = self.settings.get("last_export_c_dir") or (
            os.path.join(os.path.dirname(self.vm.path), "lvgl_c") if self.vm.path else os.path.expanduser("~"))
        out = QFileDialog.getExistingDirectory(self, tr("Carpeta para ui.c / ui.h"), start)
        if not out:
            return
        try:
            files, res = export_c(self.vm.project, out)
        except OSError as exc:
            QMessageBox.critical(self, tr("Error al exportar"), str(exc))
            return
        self.settings.set("last_export_c_dir", out)
        self.show_c_report(files, res)

    def c_report_lines(self, files, res) -> list[str]:
        lines = [tr("Ficheros escritos:")] + [f"  • {p}" for p in files]
        lines += ["", tr("Requiere LVGL 9.5 o superior. Llama a ui_init() tras lv_init() y el driver de pantalla.")]
        if res.fonts:
            lines += ["", tr("Activa en lv_conf.h:")] + [f"  • {f} 1" for f in sorted(res.fonts)]
        if res.custom_fonts:
            lines += ["", tr("Fuentes propias (conviértelas con lv_font_conv y añádelas al proyecto):")]
            lines += [f"  • {f}" for f in sorted(res.custom_fonts)]
        if res.images:
            lines += ["", tr("Imágenes (conviértelas con LVGLImage.py / el conversor online):")]
            lines += [f"  • {i}" for i in sorted(res.images)]
        if res.warnings:
            lines += ["", f"{tr('Avisos:').rstrip(':')} ({len(res.warnings)}):"]
            lines += [f"  ⚠ {w}" for w in res.warnings[:25]]
            if len(res.warnings) > 25:
                lines.append(f"  … +{len(res.warnings) - 25} (TODO → ui.c)")
        lines += ["", tr("Las acciones que sólo existen en ESPHome (Home Assistant, scripts, lambdas…) "
                  "llaman a ui_action_handler(): asígnalo en tu código para atenderlas.")]
        return lines

    def show_c_report(self, files, res) -> None:
        lines = self.c_report_lines(files, res)
        box = QMessageBox(self)
        box.setWindowTitle(tr("Exportación C (LVGL)"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(trf("Generado código C para {n} página(s).", n=len(self.vm.project.screens)))
        box.setDetailedText("\n".join(lines))
        box.setInformativeText("\n".join(lines[:12]))
        box.exec()

    def open_styles(self) -> None:
        from olvgl.presentation.dialogs import StylesDialog
        StylesDialog(self.vm, self).exec()

    # ================================================================ otros
    def cut(self) -> None:
        if self.vm.copy():
            self.vm.delete_widgets()

    def open_simulator(self) -> None:
        if self.simulator is None:
            self.simulator = SimulatorWindow(self.vm)
        self.simulator.reset()
        self.simulator.show()
        self.simulator.raise_()
        self.simulator.activateWindow()

    # ================================================================ ayuda y diagnóstico
    def _open_doc(self, rel: str) -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), rel)
        if not os.environ.get("OLVGL_AUTOPRUEBA"):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return path

    def open_guide(self) -> str:
        return self._open_doc(os.path.join("docs", "GUIA_USUARIO.md"))

    def open_changelog(self) -> str:
        return self._open_doc("CHANGELOG.md")

    def open_logs(self) -> str:
        from olvgl.application import diagnostics
        d = diagnostics.logs_dir()
        if not os.environ.get("OLVGL_AUTOPRUEBA"):
            from olvgl.presentation.diagnostics_ui import open_folder
            open_folder(d)
        return d

    def open_diagnostics(self, show: bool = True):
        from olvgl.application import diagnostics
        from olvgl.presentation.diagnostics_ui import DiagnosticDialog
        dlg = DiagnosticDialog(diagnostics.diagnostic_report(self.settings, self.vm.project), self)
        if show:
            dlg.exec()
        return dlg

    def report_error(self, path: str, summary: str) -> None:
        """Error inesperado (desde el gancho de excepciones): autoguardar y avisar."""
        self.errors.append((path, summary))
        try:
            json_store.write_autosave(self.vm.project, self.vm.path, app_data_dir())
        except Exception:
            pass
        if os.environ.get("OLVGL_AUTOPRUEBA") or getattr(self, "_showing_error", False):
            return
        from olvgl.presentation.diagnostics_ui import ErrorDialog
        self._showing_error = True
        try:
            ErrorDialog(path, summary, self).exec()
        finally:
            self._showing_error = False

    def about(self) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(trf("Acerca de {app}", app=APP_NAME))
        lay = QVBoxLayout(dlg)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(True, 110))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        info = QLabel(
            f"<p align='center'><b>{APP_NAME} {__version__}</b></p>"
            f"<p align='center' style='color:#9E9E9E'>Design · Develop · Preview — for embedded UI</p>"
            "<p>" + tr("Diseñador visual de interfaces LVGL para ESPHome.") + "</p><p>"
            + tr("Todos los widgets de LVGL, estilos por parte y estado, temas, eventos avanzados, "
                 "sincronización bidireccional con ESPHome y generador de código C para LVGL 9.") + "</p>")
        info.setWordWrap(True)
        info.setMinimumWidth(460)
        lay.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.sync_timer.isActive():
            self.write_to_source()
        if not self._confirm_discard():
            event.ignore()
            return
        json_store.discard_autosave(self.vm.path, app_data_dir())
        if self.vm.path is None:
            json_store.discard_autosave(None, app_data_dir())
        self._save_settings()
        if self.presence is not None:
            self.presence.leave()
        if self.simulator:
            self.simulator.close()
        event.accept()
        if self._restart_requested:
            import sys
            from PySide6.QtCore import QProcess
            QProcess.startDetached(sys.executable, [os.path.abspath(sys.argv[0])] + sys.argv[1:])
