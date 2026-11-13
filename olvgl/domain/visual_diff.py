"""Diferencias entre dos versiones de un proyecto, por página y por widget.

Base del control de versiones visual (Fase 10): cada widget se identifica por
su id; se marca como añadido, eliminado o cambiado (geometría, propiedades,
eventos, contenedor u orden). También se resumen los cambios de páginas,
estilos, fuentes, imágenes y pantalla.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from olvgl.domain.model import Project, Screen, Widget

GEOMETRY = ("x", "y", "width", "height")


@dataclass
class WidgetChange:
    id: str
    type: str
    status: str                       # added | removed | changed
    aspects: list[str] = field(default_factory=list)   # geometría, propiedades, eventos, contenedor, orden
    details: list[str] = field(default_factory=list)


@dataclass
class PageDiff:
    id: str
    name: str
    status: str                       # added | removed | changed | same
    widgets: list[WidgetChange] = field(default_factory=list)
    page_props: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.status != "same"

    def by_status(self, status: str) -> list[WidgetChange]:
        return [w for w in self.widgets if w.status == status]


@dataclass
class ProjectDiff:
    pages: list[PageDiff] = field(default_factory=list)
    project: list[str] = field(default_factory=list)    # cambios generales

    @property
    def empty(self) -> bool:
        return not self.project and not any(p.changed for p in self.pages)

    def page(self, page_id: str) -> PageDiff | None:
        return next((p for p in self.pages if p.id == page_id), None)

    def counts(self) -> dict[str, int]:
        c = {"added": 0, "removed": 0, "changed": 0}
        for p in self.pages:
            for w in p.widgets:
                c[w.status] += 1
        return c

    def summary(self) -> list[str]:
        lines = list(self.project)
        for p in self.pages:
            if p.status == "added":
                lines.append(f"+ página «{p.name}» ({p.id}) con {len(p.widgets)} widgets")
            elif p.status == "removed":
                lines.append(f"− página «{p.name}» ({p.id})")
            elif p.status == "changed":
                lines.append(f"~ página «{p.name}» ({p.id})")
                lines += [f"    página: {x}" for x in p.page_props]
                for w in p.widgets:
                    mark = {"added": "+", "removed": "−", "changed": "~"}[w.status]
                    extra = f": {', '.join(w.details[:4])}" if w.details else ""
                    lines.append(f"    {mark} {w.id} ({w.type}){extra}")
        return lines


def _flat(screen: Screen) -> dict[str, tuple[Widget, str | None, int]]:
    out: dict[str, tuple[Widget, str | None, int]] = {}

    def visit(ws: list[Widget], parent: str | None) -> None:
        for i, w in enumerate(ws):
            out[w.id] = (w, parent, i)
            visit(w.children, w.id)
    visit(screen.widgets, None)
    return out


def _short(v: Any) -> str:
    s = str(v)
    return s if len(s) <= 24 else s[:21] + "…"


def _widget_change(a: Widget, pa: str | None, ia: int, b: Widget, pb: str | None, ib: int) -> WidgetChange | None:
    aspects, details = [], []
    geo = [g for g in GEOMETRY if getattr(a, g) != getattr(b, g)]
    if geo:
        aspects.append("geometría")
        details += [f"{g} {_short(getattr(a, g))}→{_short(getattr(b, g))}" for g in geo]
    keys = sorted(k for k in set(a.props) | set(b.props) if a.props.get(k) != b.props.get(k))
    if keys:
        aspects.append("propiedades")
        for k in keys:
            if k not in a.props:
                details.append(f"+{k}={_short(b.props[k])}")
            elif k not in b.props:
                details.append(f"−{k}")
            else:
                details.append(f"{k} {_short(a.props[k])}→{_short(b.props[k])}")
    if [e.to_dict() for e in a.events] != [e.to_dict() for e in b.events]:
        aspects.append("eventos")
        details.append("eventos")
    if a.type != b.type:
        aspects.append("tipo")
        details.append(f"tipo {a.type}→{b.type}")
    if pa != pb:
        aspects.append("contenedor")
        details.append(f"dentro de {pb or 'la página'}")
    elif ia != ib:
        aspects.append("orden")
    if not aspects:
        return None
    return WidgetChange(b.id, b.type, "changed", aspects, details)


def diff_pages(a: Screen | None, b: Screen | None) -> PageDiff:
    if a is None and b is not None:
        fb = _flat(b)
        return PageDiff(b.id, b.name, "added", [WidgetChange(i, w.type, "added") for i, (w, _p, _i) in fb.items()])
    if b is None and a is not None:
        fa = _flat(a)
        return PageDiff(a.id, a.name, "removed", [WidgetChange(i, w.type, "removed") for i, (w, _p, _i) in fa.items()])
    assert a is not None and b is not None
    fa, fb = _flat(a), _flat(b)
    changes: list[WidgetChange] = []
    for wid, (w, _p, _i) in fb.items():
        if wid not in fa:
            changes.append(WidgetChange(wid, w.type, "added"))
    for wid, (w, _p, _i) in fa.items():
        if wid not in fb:
            changes.append(WidgetChange(wid, w.type, "removed"))
    for wid in fa.keys() & fb.keys():
        c = _widget_change(*fa[wid], *fb[wid])
        if c:
            changes.append(c)
    order = {w: n for n, w in enumerate(list(fb) + [x for x in fa if x not in fb])}
    changes.sort(key=lambda c: order.get(c.id, 0))
    page_props = []
    if a.name != b.name:
        page_props.append(f"nombre «{a.name}»→«{b.name}»")
    if a.bg_color != b.bg_color:
        page_props.append(f"fondo {a.bg_color}→{b.bg_color}")
    for k in sorted(set(a.props) | set(b.props)):
        if a.props.get(k) != b.props.get(k):
            page_props.append(f"{k} {_short(a.props.get(k))}→{_short(b.props.get(k))}")
    status = "changed" if changes or page_props else "same"
    return PageDiff(b.id, b.name, status, changes, page_props)


def diff_projects(a: Project, b: Project) -> ProjectDiff:
    """Cambios para pasar de `a` (antes) a `b` (después)."""
    out = ProjectDiff()
    ids_b = [s.id for s in b.all_screens()]
    ids_a = [s.id for s in a.all_screens()]
    for sid in ids_b + [x for x in ids_a if x not in ids_b]:
        out.pages.append(diff_pages(a.screen(sid), b.screen(sid)))
    if a.display.to_dict() != b.display.to_dict():
        out.project.append(f"pantalla {a.display.width}×{a.display.height}→{b.display.width}×{b.display.height}")
    for what, la, lb in (("estilo", a.styles, b.styles), ("fuente", a.fonts, b.fonts), ("imagen", a.images, b.images)):
        da = {x.id: x.to_dict() for x in la}
        db = {x.id: x.to_dict() for x in lb}
        for i in db.keys() - da.keys():
            out.project.append(f"+ {what} {i}")
        for i in da.keys() - db.keys():
            out.project.append(f"− {what} {i}")
        for i in sorted(da.keys() & db.keys()):
            if da[i] != db[i]:
                out.project.append(f"~ {what} {i}")
    if a.lvgl_extra.get("theme") != b.lvgl_extra.get("theme"):
        out.project.append("~ tema")
    return out
