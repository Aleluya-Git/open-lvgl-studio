"""Arranque de la aplicación Qt."""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from olvgl import APP_NAME, __version__
from olvgl.application.viewmodel import ProjectViewModel
from olvgl.infrastructure import json_store
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_file
from olvgl.infrastructure.sync_adapters import make_session
from olvgl.infrastructure.settings_db import SettingsDB


def dark_palette() -> QPalette:
    p = QPalette()
    base, alt, text = QColor("#2B2B30"), QColor("#323238"), QColor("#E6E6E6")
    p.setColor(QPalette.ColorRole.Window, QColor("#26262B"))
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, QColor("#1E1E22"))
    p.setColor(QPalette.ColorRole.AlternateBase, alt)
    p.setColor(QPalette.ColorRole.ToolTipBase, base)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, base)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.Highlight, QColor("#7C4DFF"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.Link, QColor("#B39DDB"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8C8C96"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#777777"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#777777"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#777777"))
    return p


def create_view_model() -> ProjectViewModel:
    return ProjectViewModel(generator=generate_yaml, saver=json_store.save_project,
                            loader=json_store.load_project, importer=import_esphome_file,
                            sync_factory=make_session)


_TRANSLATORS: list = []


def install_translators(app: QApplication, code: str) -> None:
    """Botones y diálogos estándar de Qt (Aceptar, Cancelar, Abrir…) en el idioma elegido."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    for t in _TRANSLATORS:
        app.removeTranslator(t)
    _TRANSLATORS.clear()
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    t = QTranslator(app)
    if t.load(QLocale(code), "qtbase", "_", path):
        app.installTranslator(t)
        _TRANSLATORS.append(t)


def set_windows_app_id() -> None:
    """Windows agrupa la ventana con python.exe si no se indica: así la barra
    de tareas muestra el icono de Open LVGL Studio."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenLVGLStudio.Studio")
        except Exception:
            pass


def create_app(argv: list[str] | None = None, language: str | None = None) -> QApplication:
    from olvgl import i18n
    from olvgl.presentation.icons import app_icon
    set_windows_app_id()
    app = QApplication.instance() or QApplication(argv or sys.argv)
    code = i18n.set_language(language or i18n.language())
    install_translators(app, code)
    app.setWindowIcon(app_icon())
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("OpenLVGLStudio")
    app.setStyle("Fusion")
    from olvgl.presentation.fonts import ui_font
    app.setFont(ui_font())
    app.setPalette(dark_palette())
    from olvgl.presentation.render import ensure_bundled_fonts
    ensure_bundled_fonts()
    return app


def system_language() -> str:
    """Primer arranque: el idioma del sistema si es uno de los disponibles."""
    from PySide6.QtCore import QLocale
    code = QLocale.system().name()[:2]
    return code if code in ("es", "en", "fr", "de") else "es"


def install_error_handler(win) -> None:
    """Un error no capturado no cierra la aplicación: se guarda un informe,
    se autoguarda el proyecto y se avisa (en el hilo de la interfaz)."""
    from olvgl.application import diagnostics
    from olvgl.presentation.diagnostics_ui import ErrorBridge
    bridge = ErrorBridge(win)
    bridge.error.connect(win.report_error)
    win._error_bridge = bridge
    diagnostics.install_excepthook(lambda path, summary: bridge.error.emit(path, summary),
                                   lambda: (win.settings, win.vm.project))


def main(argv: list[str] | None = None) -> int:
    from olvgl.presentation.main_window import MainWindow

    argv = list(argv if argv is not None else sys.argv)
    from olvgl.application import diagnostics
    diagnostics.setup_logging()
    settings = SettingsDB()
    app = create_app(argv, settings.get("language", None) or system_language())
    vm = create_view_model()
    win = MainWindow(vm, settings)
    install_error_handler(win)
    win.show()
    files = [a for a in argv[1:] if a.endswith(json_store.EXTENSION)]
    yamls = [a for a in argv[1:] if a.lower().endswith((".yaml", ".yml"))]
    if files:
        QTimer.singleShot(0, lambda: win.open_project(files[0]))
    elif yamls:
        QTimer.singleShot(0, lambda: win.import_yaml(yamls[0]))
    else:
        QTimer.singleShot(0, win.check_untitled_recovery)
    code = app.exec()
    settings.close()
    return code
