"""Línea de órdenes de Open LVGL Studio (la usa la extensión de VS Code).

    python -m olvgl.cli info     panel.yaml            → páginas, pantalla y resumen (JSON)
    python -m olvgl.cli validate panel.yaml            → diagnósticos con número de línea (JSON)
    python -m olvgl.cli profile  panel.yaml            → estimación de RAM, flash y objetos (JSON)
    python -m olvgl.cli render   panel.yaml --out DIR [--page ID] [--scale 1]
    python -m olvgl.cli export-c panel.yaml --out DIR
    python -m olvgl.cli export-esphome panel.olvgl --out DIR
    python -m olvgl.cli export   panel.yaml --format PLUGIN.ID --out DIR   (exportadores de plugins)
    python -m olvgl.cli plugins                        → plugins cargados y lo que aportan
    python -m olvgl.cli new-plugin mi_plugin [--dir D] → plantilla de un plugin nuevo
    python -m olvgl.cli generate "página de luces" [--out pagina.yaml] [--into panel.yaml]
                       [--display 1024x600] [--provider local|anthropic|openai] [--model M] [--base-url U]
    python -m olvgl.cli serve                          → peticiones JSON por stdin, una por línea

`serve` mantiene Qt cargado entre peticiones, así la vista previa responde en
décimas de segundo. Cada petición es un objeto JSON {"id", "cmd", "path",
"text"?, "page"?, "scale"?} y cada respuesta {"id", "ok", "result"|"error"}.
`text` permite trabajar con el contenido sin guardar del editor.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import traceback
from typing import Any

from olvgl import __version__
from olvgl.domain.model import TOP_LAYER_ID, Project

_ID_LINE = re.compile(r"^\s*(?:-\s+)?id:\s*['\"]?([A-Za-z_][\w]*)['\"]?\s*(?:#.*)?$")


# --------------------------------------------------------------------------- carga
def load(path: str, text: str | None = None) -> tuple[Project, Any, str]:
    """Proyecto, informe de importación (o None) y texto fuente."""
    path = os.path.abspath(path)
    if path.lower().endswith(".olvgl"):
        from olvgl.infrastructure import json_store
        return json_store.load_project(path), None, ""
    from olvgl.infrastructure.esphome_importer import import_esphome_file, import_esphome_text
    if text is None:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        project, report = import_esphome_file(path)
    else:
        project, report = import_esphome_text(text, path)
    return project, report, text


def id_lines(text: str) -> dict[str, int]:
    """Línea (base 0) de cada `id:` del YAML: para saltar del dibujo al código."""
    out: dict[str, int] = {}
    for i, line in enumerate(text.splitlines()):
        m = _ID_LINE.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = i
    return out


def _section_line(text: str, key: str = "lvgl") -> int:
    for i, line in enumerate(text.splitlines()):
        if line.startswith(f"{key}:"):
            return i
    return 0


# --------------------------------------------------------------------------- órdenes sin Qt
def info(path: str, text: str | None = None) -> dict:
    project, report, _ = load(path, text)
    out = {
        "version": __version__,
        "name": project.name,
        "display": {"name": project.display.name, "width": project.display.width,
                    "height": project.display.height},
        "pages": [{"id": s.id, "name": s.name} for s in project.screens],
        "top_layer": project.top_layer is not None,
        "widgets": sum(1 for _ in project.iter_widgets()),
    }
    if report is not None:
        out["summary"] = report.summary()
        out["warnings"] = list(report.warnings)
    return out


def validate(path: str, text: str | None = None) -> dict:
    """Errores y avisos con línea (base 0) para el panel «Problemas» de VS Code."""
    diags: list[dict] = []
    if text is None and not path.lower().endswith(".olvgl"):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    try:
        _project, report, text = load(path, text)
    except Exception as exc:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        line, col = getattr(mark, "line", None), getattr(mark, "column", 0)
        if line is None:
            m = re.search(r":(\d+):(\d+):", str(exc)) or re.search(r"line (\d+)(?:, column (\d+))?", str(exc))
            line = int(m.group(1)) - 1 if m else 0
            col = int(m.group(2)) - 1 if m and m.group(2) else 0
        diags.append({"severity": "error", "line": max(0, int(line)), "column": max(0, int(col or 0)),
                      "message": str(exc).strip()})
        return {"diagnostics": diags}
    lines = id_lines(text)
    base = _section_line(text)
    for w in (report.warnings if report else []):
        line = base
        for ident in re.findall(r"'([A-Za-z_]\w*)'", w):
            if ident in lines:
                line = lines[ident]
                break
        diags.append({"severity": "warning", "line": line, "message": w})
    # reglas de los plugins (validadores)
    try:
        from olvgl.domain.extensions import validate as plugin_validate
        for it in plugin_validate(_project):
            line = lines.get(it.widget_id, base) if it.widget_id else base
            diags.append({"severity": it.severity if it.severity in ("error", "warning", "info") else "warning",
                          "line": line, "message": f"{it.message} [{it.plugin}]"})
    except Exception as exc:
        diags.append({"severity": "info", "line": base, "message": f"validadores de plugins: {exc}"})
    if report and report.raw_actions:
        diags.append({"severity": "info", "line": base,
                      "message": f"{report.raw_actions} acción(es) se conservan como YAML libre "
                                 "(el diseñador no las edita visualmente, pero no se pierden)"})
    return {"diagnostics": diags}


def profile(path: str, text: str | None = None) -> dict:
    """Estimación de RAM, flash y objetos en el dispositivo (ver olvgl/domain/resources.py)."""
    from olvgl.domain.resources import estimate_resources
    project, _r, _t = load(path, text)

    def image_size(image_id: str):
        img = project.image(image_id)
        if img is None or not os.path.exists(img.path):
            return None
        try:
            import struct
            with open(img.path, "rb") as f:
                head = f.read(24)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
        except OSError:
            return None
        return None
    return estimate_resources(project, image_size).as_dict()


def export_c(path: str, out: str, text: str | None = None) -> dict:
    from olvgl.infrastructure.lvgl_c_generator import export_c as _export
    project, _r, _t = load(path, text)
    files, res = _export(project, out)
    return {"files": files, "warnings": res.warnings, "fonts": sorted(res.fonts),
            "custom_fonts": sorted(res.custom_fonts), "images": sorted(res.images)}


def plugins_list() -> dict:
    from olvgl.application.plugins import describe, manager
    from olvgl.domain.extensions import REGISTRY
    m = manager()
    return {"plugins": [describe(i) for i in m.plugins.values()],
            "exporters": [{"id": e.id, "name": e.name, "plugin": e.plugin} for e in REGISTRY.exporters.values()],
            "commands": [{"id": c.id, "label": c.label, "plugin": c.plugin} for c in REGISTRY.commands.values()],
            "widgets": dict(REGISTRY.widget_types)}


def export_plugin(path: str, fmt: str, out: str, text: str | None = None) -> dict:
    from olvgl.application.plugins import manager
    from olvgl.domain.extensions import REGISTRY
    if fmt not in REGISTRY.exporters:
        raise ValueError(f"exportador desconocido «{fmt}». Disponibles: {', '.join(REGISTRY.exporters) or 'ninguno'}")
    project, _r, _t = load(path, text)
    return {"files": manager().export(fmt, project, out)}


def export_esphome(path: str, out: str) -> dict:
    from olvgl.infrastructure.exporter import export_esphome as _export
    project, _r, _t = load(path)
    rep = _export(project, out, path if path.endswith(".olvgl") else None)
    return {"written": rep.written, "skipped": rep.skipped, "warnings": rep.warnings}


# --------------------------------------------------------------------------- dibujo (Qt)
_app = None


def _qt():
    """QGuiApplication sin ventana (se crea una sola vez)."""
    global _app
    if _app is not None:
        return _app
    # En Windows se usa la plataforma nativa (sin abrir ninguna ventana): su base de
    # datos de fuentes es la del sistema y es estable en procesos largos como `serve`.
    # En otros sistemas sin pantalla, «offscreen».
    if not sys.platform.startswith("win"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([sys.argv[0]])
    from olvgl.presentation.render import ensure_bundled_fonts
    ensure_bundled_fonts()
    return _app


def render(path: str, text: str | None = None, page: str | None = None, scale: float = 1.0,
           out: str | None = None) -> dict:
    """Dibuja una página (o todas con page="*") como en el canvas del diseñador."""
    _qt()
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
    from PySide6.QtGui import QImage, QPainter

    from olvgl.domain.layout import LayoutContext, compute_layout
    from olvgl.presentation import render as rnd

    project, report, src = load(path, text)
    lines = id_lines(src)
    ctx = rnd.RenderContext(project)
    lctx = LayoutContext(project, ctx.measure_text, ctx.image_size_of, {})
    d = project.display
    pages = [s for s in project.screens if s.id != TOP_LAYER_ID]
    if not pages:
        raise ValueError("El YAML no tiene páginas de LVGL (lvgl: pages:)")
    chosen = pages if page == "*" else [next((s for s in pages if s.id == page), pages[0])]
    top = project.top_layer
    top_boxes = compute_layout(project, top, lctx) if top is not None else {}
    result_pages = []
    for screen in chosen:
        boxes = compute_layout(project, screen, lctx)
        w, h = max(1, int(d.width * scale)), max(1, int(d.height * scale))
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(scale, scale)
        p.setClipRect(QRectF(0, 0, d.width, d.height))
        p.fillRect(QRectF(0, 0, d.width, d.height), rnd.page_background(project, screen, ctx))
        rnd.paint_tree(p, screen.widgets, boxes, ctx)
        if top is not None:
            rnd.paint_tree(p, top.widgets, top_boxes, ctx)
        p.end()
        entry: dict[str, Any] = {"id": screen.id, "name": screen.name}
        if out:
            os.makedirs(out, exist_ok=True)
            file = os.path.join(out, f"{screen.id}.png")
            img.save(file)
            entry["file"] = file
        else:
            data = QByteArray()
            buf = QBuffer(data)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            buf.close()
            entry["png"] = base64.b64encode(bytes(data)).decode("ascii")
        widgets = []
        for layer, bxs in ((screen, boxes), (top, top_boxes)):
            if layer is None:
                continue
            for wdg in layer.walk():
                b = bxs.get(wdg.id)
                if b is None or not b.shown or b.hidden:
                    continue
                widgets.append({"id": wdg.id, "type": wdg.type, "auto": wdg.auto_id,
                                "x": round(b.rect.x, 1), "y": round(b.rect.y, 1),
                                "w": round(b.rect.w, 1), "h": round(b.rect.h, 1),
                                "line": lines.get(wdg.id)})
        entry["widgets"] = widgets
        result_pages.append(entry)
    return {"display": {"width": d.width, "height": d.height}, "scale": scale,
            "pages": [{"id": s.id, "name": s.name} for s in pages], "rendered": result_pages,
            "warnings": list(report.warnings) if report else []}


# --------------------------------------------------------------------------- IA
def generate(prompt: str, into: str | None = None, display: str | None = None, provider: str = "local",
             model: str = "", base_url: str = "", out: str | None = None) -> dict:
    """Genera una página con IA. Con `into` se toma el contexto (pantalla, estilos,
    páginas) de ese YAML; la página se devuelve como fragmento `lvgl: pages:`."""
    from olvgl.application import ai
    from olvgl.domain.model import DisplayProfile, new_project
    if into:
        project, _report, _src = load(into, None)
    else:
        w, h = (int(v) for v in (display or "1024x600").lower().split("x"))
        project = new_project("IA", DisplayProfile("IA", w, h))
        project.screens = []
    key_env = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(provider, "")
    cfg = ai.AIConfig(provider=provider, model=model, base_url=base_url, api_key=os.environ.get(key_env, ""))
    res = ai.AIDesigner(ai.make_provider(cfg), lambda m: print(m, file=sys.stderr)).generate(prompt, project)
    text = ai.pages_yaml(res.project, res.page_ids)
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return {"pages": res.page_ids, "attempts": res.attempts, "warnings": res.warnings, "notes": res.notes,
            "file": out, "yaml": None if out else text}


# --------------------------------------------------------------------------- servidor
LICENSED = {"info": "importar_yaml", "validate": "importar_yaml", "profile": "importar_yaml",
            "render": "importar_yaml", "export-c": "importar_yaml", "export": "importar_yaml",
            "serve": "vscode", "generate": "ia"}


class LicenseRequired(Exception):
    pass


def require(feature: str) -> None:
    from olvgl.application import licensing
    if not licensing.has(feature):
        raise LicenseRequired(licensing.required_message(feature))


def handle(req: dict) -> Any:
    cmd = req.get("cmd")
    if cmd not in ("ping", "quit", "plugins"):
        require("vscode")                     # la extensión de VS Code (vista previa, Live Sync…) es Pro
        if cmd == "generate":
            require("ia")
    path = req.get("path") or ""
    text = req.get("text")
    if cmd == "ping":
        return {"version": __version__}
    if cmd == "info":
        return info(path, text)
    if cmd == "validate":
        return validate(path, text)
    if cmd == "render":
        return render(path, text, req.get("page"), float(req.get("scale") or 1.0), req.get("out"))
    if cmd == "profile":
        return profile(path, text)
    if cmd == "export-c":
        return export_c(path, req["out"], text)
    if cmd == "export":
        return export_plugin(path, req["format"], req["out"], text)
    if cmd == "plugins":
        return plugins_list()
    if cmd == "generate":
        return generate(req["prompt"], path or None, req.get("display"), req.get("provider") or "local",
                        req.get("model") or "", req.get("base_url") or "")
    raise ValueError(f"orden desconocida: {cmd}")


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            if req.get("cmd") == "quit":
                break
            resp = {"id": rid, "ok": True, "result": handle(req)}
        except Exception as exc:  # cada petición falla sola: el servidor sigue vivo
            resp = {"id": rid, "ok": False, "error": str(exc), "trace": traceback.format_exc(limit=4)}
            if isinstance(exc, LicenseRequired):
                resp["license"] = True
        stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="olvgl", description="Open LVGL Studio desde la línea de órdenes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("info", "validate", "profile"):
        sp = sub.add_parser(name)
        sp.add_argument("path")
    sp = sub.add_parser("render")
    sp.add_argument("path")
    sp.add_argument("--out", required=True)
    sp.add_argument("--page", default="*")
    sp.add_argument("--scale", type=float, default=1.0)
    for name in ("export-c", "export-esphome"):
        sp = sub.add_parser(name)
        sp.add_argument("path")
        sp.add_argument("--out", required=True)
    sp = sub.add_parser("export", help="exportar con un plugin (ver «plugins»)")
    sp.add_argument("path")
    sp.add_argument("--format", required=True)
    sp.add_argument("--out", required=True)
    sub.add_parser("plugins")
    sp = sub.add_parser("new-plugin", help="crear la plantilla de un plugin")
    sp.add_argument("id")
    sp.add_argument("--dir", default=None)
    sp.add_argument("--name", default="")
    sp = sub.add_parser("generate", help="generar una página con IA")
    sp.add_argument("prompt")
    sp.add_argument("--out", default=None)
    sp.add_argument("--into", default=None, help="YAML del proyecto (contexto)")
    sp.add_argument("--display", default="1024x600")
    sp.add_argument("--provider", default="local", choices=["local", "anthropic", "openai"])
    sp.add_argument("--model", default="")
    sp.add_argument("--base-url", default="")
    sub.add_parser("serve")
    sub.add_parser("version")
    a = ap.parse_args(argv)
    if a.cmd in LICENSED and a.cmd != "serve":
        try:
            require(LICENSED[a.cmd])
        except LicenseRequired as exc:
            print(json.dumps({"error": str(exc), "license": True}, ensure_ascii=False))
            return 3
    if not os.environ.get("OLVGL_NO_PLUGINS"):
        from olvgl.application.plugins import load_plugins
        load_plugins()
    if a.cmd == "serve":
        return serve()
    if a.cmd == "version":
        result: Any = {"version": __version__}
    elif a.cmd == "info":
        result = info(a.path)
    elif a.cmd == "validate":
        result = validate(a.path)
    elif a.cmd == "profile":
        result = profile(a.path)
    elif a.cmd == "render":
        result = render(a.path, page=a.page, scale=a.scale, out=a.out)
    elif a.cmd == "export-c":
        result = export_c(a.path, a.out)
    elif a.cmd == "export":
        result = export_plugin(a.path, a.format, a.out)
    elif a.cmd == "plugins":
        result = plugins_list()
    elif a.cmd == "generate":
        result = generate(a.prompt, a.into, a.display, a.provider, a.model, a.base_url, a.out)
    elif a.cmd == "new-plugin":
        from olvgl.application.plugins import create_plugin, user_plugins_dir
        result = {"path": create_plugin(a.dir or user_plugins_dir(), a.id, a.name)}
    else:
        result = export_esphome(a.path, a.out)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
