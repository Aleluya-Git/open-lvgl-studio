"""Exportadores de ejemplo: documentación en Markdown e inventario CSV."""
import csv
import os
import re


def _slug(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name or "proyecto").strip("_") or "proyecto"


def _text(w):
    t = w.props.get("text")
    if isinstance(t, str):
        return t.replace("\n", " ")
    if isinstance(t, dict):
        return "(dinámico)"
    return ""


def register(ctx):
    def markdown(project, folder):
        from olvgl.domain import catalog
        from olvgl.domain.resources import estimate_resources, human
        d = project.display
        rep = estimate_resources(project)
        out = [f"# {project.name}", "",
               f"Pantalla: **{d.name}** ({d.width}×{d.height}) · {len(project.screens)} página(s) · "
               f"{rep.objects} objetos · RAM estimada {human(rep.ram_bytes)} · flash {human(rep.flash_bytes)}", ""]
        out += ["## Páginas", "", "| Página | Id | Objetos | Eventos |", "|---|---|---|---|"]
        for p in rep.pages:
            out.append(f"| {p.name} | `{p.id}` | {p.objects} | {p.events} |")
        for s in project.all_screens():
            out += ["", f"## {s.name} (`{s.id}`)", ""]

            def walk(ws, level):
                for w in ws:
                    label = catalog.spec(w.type).label
                    ident = "(sin id)" if w.auto_id else f"`{w.id}`"
                    text = _text(w)
                    out.append("  " * level + f"- **{label}** {ident}" + (f" — «{text}»" if text else ""))
                    for ev in w.events:
                        for a in ev.actions:
                            out.append("  " * (level + 1) + f"- {ev.trigger}: {catalog.describe_action(a.kind, a.params)}")
                    walk(w.children, level + 1)
            walk(s.widgets, 0)
        if project.styles:
            out += ["", "## Estilos", ""] + [f"- `{st.id}`: {', '.join(st.props)}" for st in project.styles]
        if rep.fonts:
            out += ["", "## Fuentes", "", "| Fuente | Tamaño | Glifos | Flash |", "|---|---|---|---|"]
            out += [f"| `{f[0]}` | {f[1]} | {f[2]} | {human(f[4])} |" for f in rep.fonts]
        if project.images:
            out += ["", "## Imágenes", ""] + [f"- `{i.id}`: {os.path.basename(i.path)}" for i in project.images]
        if rep.warnings:
            out += ["", "## Avisos", ""] + [f"- {w}" for w in rep.warnings]
        path = os.path.join(folder, f"{_slug(project.name)}_documentacion.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        return [path]

    def inventory(project, folder):
        from olvgl.domain import catalog
        path = os.path.join(folder, f"{_slug(project.name)}_widgets.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f, delimiter=";")
            wr.writerow(["pagina", "id", "tipo", "x", "y", "ancho", "alto", "texto", "eventos"])
            for s, w in project.iter_widgets():
                wr.writerow([s.id, "" if w.auto_id else w.id, catalog.spec(w.type).label, w.x, w.y,
                             w.width, w.height, _text(w), " ".join(ev.trigger for ev in w.events)])
        return [path]

    ctx.register_exporter("markdown", "Documentación (Markdown)", markdown,
                          "Páginas, árbol de widgets, eventos, fuentes, imágenes y avisos")
    ctx.register_exporter("csv", "Inventario de widgets (CSV)", inventory,
                          "Una fila por widget (se abre con Excel o LibreOffice)")
