"""Registro, informes de error y diagnóstico (beta pública).

- `setup_logging()`: registro rotativo en <datos de la app>/logs/olvgl.log.
- `write_crash_report()`: un error no capturado se guarda en logs/error_*.txt con
  el traceback y el diagnóstico; la interfaz lo ofrece para copiar.
- `diagnostic_report()`: versiones, sistema, plugins, idioma, proveedor de IA
  (nunca la clave), resumen del proyecto y las últimas líneas del registro.
  Las rutas de la carpeta personal se acortan a «~».

Nada se envía a ningún sitio: el usuario decide si adjunta el informe.
"""
from __future__ import annotations

import datetime as _dt
import logging
import logging.handlers
import os
import platform
import sys
import threading
import traceback
from typing import Any, Callable

from olvgl import APP_NAME, __version__

LOG = logging.getLogger("olvgl")
_HANDLER: logging.Handler | None = None


def logs_dir() -> str:
    from olvgl.infrastructure.settings_db import app_data_dir
    d = os.path.join(app_data_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def log_file() -> str:
    return os.path.join(logs_dir(), "olvgl.log")


def setup_logging(level: int = logging.INFO) -> str:
    """Registro en fichero (1 MB × 3). Devuelve la ruta del registro."""
    global _HANDLER
    path = log_file()
    if _HANDLER is None:
        _HANDLER = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        _HANDLER.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        LOG.addHandler(_HANDLER)
        LOG.setLevel(level)
        LOG.propagate = False
        LOG.info("%s %s · Python %s · %s", APP_NAME, __version__, platform.python_version(), platform.platform())
    return path


def _home_safe(text: str) -> str:
    home = os.path.expanduser("~")
    if home and len(home) > 3:
        text = text.replace(home, "~")
    return text


def _qt_versions() -> dict[str, str]:
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        return {"PySide6": PySide6.__version__, "Qt": qVersion()}
    except Exception:
        return {}


def _tail(path: str, lines: int = 40) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()[-lines:]
    except OSError:
        return []


def diagnostic_info(settings: Any = None, project: Any = None) -> dict:
    info: dict[str, Any] = {
        "app": f"{APP_NAME} {__version__}",
        "python": f"{platform.python_version()} ({platform.python_implementation()}, {sys.maxsize.bit_length() + 1} bits)",
        "sistema": platform.platform(),
        **_qt_versions(),
    }
    try:
        import yaml
        info["PyYAML"] = yaml.__version__
    except Exception:
        pass
    if settings is not None:
        try:
            info["idioma"] = settings.get("language", "") or "auto"
            prov = settings.get("ai_provider", "local") or "local"
            info["ia"] = prov + (f" · {settings.get('ai_model', '')}" if settings.get("ai_model", "") else "")
            info["ia_clave"] = "sí" if settings.get("ai_api_key", "") else "no"   # nunca la clave
        except Exception:
            pass
    try:
        from olvgl.application.plugins import load_plugins
        mgr = load_plugins()
        info["plugins"] = [f"{p.id} {p.version}" + ("" if p.enabled and not p.error else
                                                    f" ({'error: ' + p.error if p.error else 'desactivado'})")
                           for p in mgr.plugins.values()]
    except Exception as exc:
        info["plugins"] = [f"error al listar: {exc}"]
    if project is not None:
        try:
            n = sum(1 for _ in project.iter_widgets())
            d = project.display
            info["proyecto"] = (f"{len(project.screens)} página(s), {n} widgets, {d.width}×{d.height}, "
                                f"{len(project.styles)} estilo(s), {len(project.images)} imagen(es), "
                                f"{len(project.fonts)} fuente(s)")
            problems = project.validate()
            if problems:
                info["avisos"] = problems[:10]
        except Exception as exc:
            info["proyecto"] = f"error: {exc}"
    return info


def diagnostic_report(settings: Any = None, project: Any = None, log_lines: int = 40) -> str:
    info = diagnostic_info(settings, project)
    out = [f"=== Diagnóstico de {APP_NAME} ({_dt.datetime.now():%Y-%m-%d %H:%M}) ==="]
    for k, v in info.items():
        if isinstance(v, list):
            out.append(f"{k}:")
            out += [f"  - {x}" for x in v] or ["  (ninguno)"]
        else:
            out.append(f"{k}: {v}")
    tail = _tail(log_file(), log_lines)
    if tail:
        out.append("")
        out.append(f"--- últimas {len(tail)} líneas del registro ---")
        out += tail
    return _home_safe("\n".join(out)) + "\n"


def write_crash_report(exc_type, exc, tb, settings: Any = None, project: Any = None) -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(logs_dir(), f"error_{stamp}.txt")
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    LOG.error("Error no capturado: %s", text)
    try:
        body = (f"=== Error en {APP_NAME} {__version__} ===\n{text}\n"
                + diagnostic_report(settings, project, log_lines=60))
    except Exception:                                   # el diagnóstico no debe impedir guardar el error
        body = text
    with open(path, "w", encoding="utf-8") as f:
        f.write(_home_safe(body))
    return path


def install_excepthook(on_error: Callable[[str, str], None] | None = None,
                       context: Callable[[], tuple[Any, Any]] | None = None) -> None:
    """Errores no capturados (también en hilos) → informe en logs/ y aviso.

    `on_error(path, resumen)` se llama en el hilo del error; la interfaz debe
    pasarlo al hilo principal. `context()` devuelve (ajustes, proyecto)."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        settings, project = context() if context else (None, None)
        try:
            path = write_crash_report(exc_type, exc, tb, settings, project)
        except Exception:
            previous(exc_type, exc, tb)
            return
        summary = f"{exc_type.__name__}: {exc}"
        traceback.print_exception(exc_type, exc, tb)
        if on_error:
            try:
                on_error(path, summary)
            except Exception:
                pass

    sys.excepthook = hook

    def thread_hook(args):
        hook(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_hook
