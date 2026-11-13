"""Fusión a tres bandas de proyectos (colaboración, Fase 10).

Dos personas abren el mismo proyecto (por ejemplo en una carpeta compartida),
cada una cambia cosas y guarda. Con la versión común (`base`), lo mío (`mine`)
y lo suyo (`theirs`) se obtiene un proyecto con los cambios de ambos:

- por widget (por id): propiedades, geometría, eventos, contenedor y orden;
  si sólo cambió un lado se toma ese; si cambiaron los dos, propiedad a
  propiedad; si la misma propiedad cambió distinto en cada lado → conflicto
  (se queda lo mío y se informa);
- widgets añadidos en cualquier lado se conservan; eliminados en un lado y
  sin cambios en el otro se eliminan; eliminado en un lado y cambiado en el
  otro → conflicto (se conserva el cambiado);
- igual para páginas, estilos, fuentes e imágenes (por id) y para los datos
  del proyecto (pantalla, ESPHome, secciones extra).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from olvgl.domain.model import Project

MISSING = object()


@dataclass
class Conflict:
    where: str              # «widget btn_1», «página main_page», «estilo x», «proyecto»
    key: str
    mine: Any
    theirs: Any

    def __str__(self) -> str:
        def s(v):
            return "(eliminado)" if v is MISSING else repr(v)[:40]
        return f"{self.where} · {self.key}: mío {s(self.mine)} / suyo {s(self.theirs)} → se queda el mío"


@dataclass
class MergeResult:
    project: Project
    conflicts: list[Conflict] = field(default_factory=list)
    from_theirs: int = 0        # cambios incorporados del otro lado

    @property
    def clean(self) -> bool:
        return not self.conflicts


def _merge_value(where: str, key: str, b: Any, m: Any, t: Any, conflicts: list[Conflict], stats: list[int]) -> Any:
    if m == t:
        return m
    if m == b:
        stats[0] += 1
        return t
    if t == b:
        return m
    if isinstance(b, dict) and isinstance(m, dict) and isinstance(t, dict):
        return _merge_dict(where, b, m, t, conflicts, stats, prefix=key + ".")
    conflicts.append(Conflict(where, key, m, t))
    return m


def _merge_dict(where: str, b: dict, m: dict, t: dict, conflicts: list[Conflict], stats: list[int],
                prefix: str = "") -> dict:
    out: dict = {}
    for k in list(m) + [k for k in t if k not in m]:
        bv, mv, tv = b.get(k, MISSING), m.get(k, MISSING), t.get(k, MISSING)
        v = _merge_value(where, prefix + k, bv, mv, tv, conflicts, stats)
        if v is not MISSING:
            out[k] = v
    return out


# --------------------------------------------------------------------------- widgets
def _flatten(project_dict: dict) -> tuple[dict, dict]:
    """id → (registro sin hijos) y id de página → lista de raíces (para el orden)."""
    rec: dict[str, dict] = {}

    def visit(ws: list[dict], screen: str, parent: str | None) -> None:
        for i, w in enumerate(ws):
            body = {k: copy.deepcopy(v) for k, v in w.items() if k != "children"}
            body["__screen"], body["__parent"], body["__index"] = screen, parent, i
            rec[w["id"]] = body
            visit(w.get("children", []), screen, w["id"])

    screens = list(project_dict.get("screens", []))
    if project_dict.get("top_layer"):
        screens.append(project_dict["top_layer"])
    for s in screens:
        visit(s.get("widgets", []), s["id"], None)
    return rec, {s["id"]: s for s in screens}


def _rebuild(screens: dict[str, dict], records: dict[str, dict]) -> None:
    """Coloca los widgets fusionados en sus páginas y contenedores."""
    by_parent: dict[tuple[str, str | None], list[tuple[float, str]]] = {}
    for wid, r in records.items():
        key = (r["__screen"], r["__parent"] if r["__parent"] in records else None)
        by_parent.setdefault(key, []).append((r["__index"], wid))

    def build(screen: str, parent: str | None) -> list[dict]:
        out = []
        for _i, wid in sorted(by_parent.get((screen, parent), []), key=lambda x: (x[0], x[1])):
            r = records[wid]
            w = {k: v for k, v in r.items() if not k.startswith("__")}
            w["children"] = build(screen, wid)
            out.append(w)
        return out

    for sid, s in screens.items():
        s["widgets"] = build(sid, None)


def _merge_by_id(where: str, b: list[dict], m: list[dict], t: list[dict], conflicts: list[Conflict],
                 stats: list[int]) -> list[dict]:
    bd, md, td = ({x["id"]: x for x in lst} for lst in (b, m, t))
    out = []
    for i in list(md) + [i for i in td if i not in md]:
        bv, mv, tv = bd.get(i, MISSING), md.get(i, MISSING), td.get(i, MISSING)
        if mv is MISSING and tv is MISSING:
            continue
        if bv is MISSING:
            if mv is MISSING:
                stats[0] += 1
            v = tv if mv is MISSING else (mv if tv is MISSING or mv == tv else
                                         _merge_dict(f"{where} {i}", {}, mv, tv, conflicts, stats))
        elif mv is MISSING or tv is MISSING:
            other = tv if mv is MISSING else mv
            if other == bv:                       # el otro lado no lo cambió: se elimina
                if tv is MISSING:
                    stats[0] += 1
                continue
            conflicts.append(Conflict(f"{where} {i}", "(eliminado en un lado, cambiado en el otro)", mv, tv))
            v = other
        else:
            v = _merge_dict(f"{where} {i}", bv, mv, tv, conflicts, stats)
        out.append(v)
    return out


def merge_projects(base: Project, mine: Project, theirs: Project) -> MergeResult:
    b, m, t = base.to_dict(), mine.to_dict(), theirs.to_dict()
    conflicts: list[Conflict] = []
    stats = [0]
    # widgets (planos, por id)
    rb, sb = _flatten(b)
    rm, sm = _flatten(m)
    rt, st = _flatten(t)
    records: dict[str, dict] = {}
    for wid in list(rm) + [w for w in rt if w not in rm]:
        bv, mv, tv = rb.get(wid, MISSING), rm.get(wid, MISSING), rt.get(wid, MISSING)
        if bv is MISSING:
            if mv is MISSING:
                stats[0] += 1
                records[wid] = tv
            elif tv is MISSING or tv == mv:
                records[wid] = mv
            else:
                records[wid] = _merge_dict(f"widget {wid}", {}, mv, tv, conflicts, stats)
            continue
        if mv is MISSING or tv is MISSING:
            other = tv if mv is MISSING else mv
            if other == bv:
                if tv is MISSING:
                    stats[0] += 1
                continue
            conflicts.append(Conflict(f"widget {wid}", "(eliminado en un lado, cambiado en el otro)", mv, tv))
            records[wid] = other
            continue
        records[wid] = _merge_dict(f"widget {wid}", bv, mv, tv, conflicts, stats)
    # los hijos de un widget eliminado se van con él (si nadie los movió fuera)
    removed = set(rb) - set(records)
    changed = True
    while changed:
        changed = False
        for wid in list(records):
            if records[wid]["__parent"] in removed:
                removed.add(wid)
                del records[wid]
                changed = True
    # páginas: propiedades por clave, lista por id
    pb = {k: {x: y for x, y in v.items() if x != "widgets"} for k, v in sb.items()}
    pm = {k: {x: y for x, y in v.items() if x != "widgets"} for k, v in sm.items()}
    pt = {k: {x: y for x, y in v.items() if x != "widgets"} for k, v in st.items()}
    top_id = (m.get("top_layer") or t.get("top_layer") or b.get("top_layer") or {}).get("id")
    order = [s["id"] for s in m.get("screens", [])]
    order += [s["id"] for s in t.get("screens", []) if s["id"] not in order]
    merged_pages = {}
    for p in _merge_by_id("página", [pb[k] for k in pb], [pm[k] for k in pm], [pt[k] for k in pt],
                          conflicts, stats):
        merged_pages[p["id"]] = dict(p, widgets=[])
    records = {k: v for k, v in records.items() if v["__screen"] in merged_pages}
    _rebuild(merged_pages, records)
    out = _merge_dict("proyecto", {k: v for k, v in b.items() if k not in ("screens", "top_layer", "styles",
                                                                         "fonts", "images")},
                      {k: v for k, v in m.items() if k not in ("screens", "top_layer", "styles", "fonts", "images")},
                      {k: v for k, v in t.items() if k not in ("screens", "top_layer", "styles", "fonts", "images")},
                      conflicts, stats)
    for key, label in (("styles", "estilo"), ("fonts", "fuente"), ("images", "imagen")):
        out[key] = _merge_by_id(label, b.get(key, []), m.get(key, []), t.get(key, []), conflicts, stats)
    out["screens"] = [merged_pages[i] for i in order if i in merged_pages and i != top_id]
    out["top_layer"] = merged_pages.get(top_id) if top_id else None
    project = Project.from_dict(out)
    # ids repetidos (un widget añadido con el mismo id en los dos lados con otro contenido) → se renombra el suyo
    seen: set[str] = set()
    for _s, w in project.iter_widgets():
        if w.id in seen:
            from olvgl.domain.model import unique_id
            new = unique_id(w.id, set(project.all_ids()))
            conflicts.append(Conflict(f"widget {w.id}", "id repetido", w.id, new))
            w.id = new
        seen.add(w.id)
    return MergeResult(project, conflicts, stats[0])
