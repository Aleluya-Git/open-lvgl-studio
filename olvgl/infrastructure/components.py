"""Componentes reutilizables y su marketplace (Fase 10).

Un componente es un grupo de widgets (con sus estilos, fuentes e imágenes)
empaquetado en un `.olvglc` (zip):

    manifest.json   id, name, version, author, description, tags, license, app_min, widgets, size
    component.json  widgets, styles, fonts, images (con la ruta dentro del zip)
    images/…        ficheros de las imágenes

- `extract_component` + `write_package`: «Guardar selección como componente».
- `Library`: componentes instalados (%APPDATA%/OpenLVGLStudio/componentes).
- `Catalog`: un índice JSON (fichero local o URL http/https) con los
  componentes publicados; cada entrada lleva su SHA-256 y no se instala nada
  que no coincida.
- `insert_component`: lo añade a una página con ids únicos (renombrando
  también las referencias de sus eventos) y fusiona estilos y fuentes.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from typing import Any

from olvgl import __version__
from olvgl.domain.model import FontResource, ImageResource, Project, Screen, StyleDef, Widget, sanitize_id, unique_id

FORMAT = "olvgl-component"
FORMAT_VERSION = 1
EXT = ".olvglc"
MAX_PACKAGE = 20 * 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class ComponentError(Exception):
    pass


@dataclass
class Package:
    manifest: dict
    component: dict
    files: dict[str, bytes] = field(default_factory=dict)
    path: str | None = None

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def name(self) -> str:
        return self.manifest.get("name") or self.id

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", "1.0.0"))


# --------------------------------------------------------------------------- crear
def _top_selection(project: Project, ids: list[str]) -> list[Widget]:
    chosen = set(ids)
    out = []
    for _s, w in project.iter_widgets():
        if w.id in chosen:
            loc = project.locate(w.id)
            parents = set()
            p = loc.parent if loc else None
            while p is not None:
                parents.add(p.id)
                pl = project.locate(p.id)
                p = pl.parent if pl else None
            if not parents & chosen:
                out.append(w)
    return out


def extract_component(project: Project, ids: list[str]) -> dict:
    """Los widgets elegidos (con sus hijos) y lo que necesitan, con el origen en (0, 0)."""
    tops = _top_selection(project, ids)
    if not tops:
        raise ComponentError("No hay widgets seleccionados")
    widgets = [w.to_dict() for w in tops]
    xs = [w.x for w in tops if isinstance(w.x, int)]
    ys = [w.y for w in tops if isinstance(w.y, int)]
    dx, dy = (min(xs) if xs else 0), (min(ys) if ys else 0)
    for d in widgets:
        if isinstance(d.get("x"), int):
            d["x"] -= dx
        if isinstance(d.get("y"), int):
            d["y"] -= dy
    sub = [x for w in tops for x in w.walk()]
    used_styles = set()
    for w in sub:
        v = w.props.get("styles")
        used_styles |= {v} if isinstance(v, str) else set(v) if isinstance(v, list) else set()
    fonts = {str(w.props.get("text_font")) for w in sub if w.props.get("text_font")}
    images = {str(w.props.get("src")) for w in sub if isinstance(w.props.get("src"), str)}
    right = max((w.x + (w.width if isinstance(w.width, int) else 0) for w in tops if isinstance(w.x, int)), default=0)
    bottom = max((w.y + (w.height if isinstance(w.height, int) else 0) for w in tops if isinstance(w.y, int)),
                 default=0)
    return {"widgets": widgets,
            "styles": [s.to_dict() for s in project.styles if s.id in used_styles],
            "fonts": [f.to_dict() for f in project.fonts if f.id in fonts],
            "images": [i.to_dict() for i in project.images if i.id in images],
            "size": [max(1, right - dx), max(1, bottom - dy)]}


def make_manifest(name: str, comp: dict, author: str = "", description: str = "", tags: list[str] | None = None,
                  version: str = "1.0.0", license: str = "", cid: str | None = None) -> dict:
    cid = cid or sanitize_id(name, "componente").replace("_", "-")
    if not ID_RE.match(cid):
        raise ComponentError(f"id de componente no válido: {cid}")
    return {"format": FORMAT, "format_version": FORMAT_VERSION, "id": cid, "name": name.strip() or cid,
            "version": version, "author": author, "description": description, "tags": tags or [],
            "license": license, "app_min": __version__.split("b")[0],
            "widgets": sum(1 for d in comp["widgets"] for _ in _walk_dicts(d)), "size": comp.get("size")}


def _walk_dicts(d: dict):
    yield d
    for c in d.get("children", []):
        yield from _walk_dicts(c)


def write_package(path: str, manifest: dict, comp: dict, preview_png: bytes | None = None) -> str:
    comp = copy.deepcopy(comp)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for img in comp.get("images", []):
            src = img.get("path", "")
            if src and os.path.isfile(src):
                name = "images/" + sanitize_id(img["id"]) + os.path.splitext(src)[1].lower()
                z.write(src, name)
                img["path"] = name
            else:
                img["path"] = ""
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        z.writestr("component.json", json.dumps(comp, ensure_ascii=False, indent=1))
        if preview_png:
            z.writestr("preview.png", preview_png)
    return path


def read_package(source: str | bytes) -> Package:
    data = source if isinstance(source, (bytes, bytearray)) else open(source, "rb").read()
    if len(data) > MAX_PACKAGE:
        raise ComponentError("El componente es demasiado grande")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        comp = json.loads(z.read("component.json").decode("utf-8"))
        files = {}
        for n in z.namelist():
            if n.startswith("images/") and not n.endswith("/") and ".." not in n and not n.startswith("/"):
                files[n] = z.read(n)
        if "preview.png" in z.namelist():
            files["preview.png"] = z.read("preview.png")
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError) as exc:
        raise ComponentError(f"No es un componente válido: {exc}") from exc
    if manifest.get("format") != FORMAT or not ID_RE.match(str(manifest.get("id", ""))):
        raise ComponentError("No es un componente de Open LVGL Studio")
    if int(manifest.get("format_version", 1)) > FORMAT_VERSION:
        raise ComponentError("El componente es de una versión más nueva de Open LVGL Studio")
    if not isinstance(comp.get("widgets"), list) or not comp["widgets"]:
        raise ComponentError("El componente no tiene widgets")
    try:                                        # comprobación de que los widgets se pueden leer
        [Widget.from_dict(w) for w in comp["widgets"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise ComponentError(f"Widgets dañados: {exc}") from exc
    return Package(manifest, comp, files, source if isinstance(source, str) else None)


# --------------------------------------------------------------------------- insertar
def preview_project(pkg: Package, bg: str = "#101018") -> Project:
    """Un proyecto mínimo con el componente, para dibujar su vista previa."""
    w, h = (pkg.component.get("size") or [320, 200])
    p = Project(name=pkg.name)
    p.display.width, p.display.height = max(40, int(w) + 20), max(40, int(h) + 20)
    p.styles = [StyleDef.from_dict(s) for s in pkg.component.get("styles", [])]
    p.fonts = [FontResource.from_dict(f) for f in pkg.component.get("fonts", [])]
    ws = [Widget.from_dict(d) for d in pkg.component["widgets"]]
    for x in ws:
        if isinstance(x.x, int):
            x.x += 10
        if isinstance(x.y, int):
            x.y += 10
    p.screens = [Screen("preview", pkg.name, bg, ws)]
    return p


def insert_component(project: Project, pkg: Package, screen_id: str, parent_id: str | None = None,
                     x: int = 0, y: int = 0, images_dir: str | None = None) -> tuple[Project, list[str]]:
    from olvgl.domain.refactor import rename_references
    p = project.clone()
    taken = set(p.all_ids()) | {s.id for s in p.styles} | {f.id for f in p.fonts} | {i.id for i in p.images}
    tmp = Project(name="c")
    tmp.screens = [Screen("c", "c", None, [Widget.from_dict(d) for d in pkg.component["widgets"]])]
    mapping: dict[str, str] = {}
    for _s, w in tmp.iter_widgets():
        new = unique_id(w.id, taken) if w.id in taken else w.id
        taken.add(new)
        if new != w.id:
            mapping[w.id] = new
    # estilos, fuentes e imágenes: si ya existe uno igual se reutiliza; si no, se renombra
    res_map: dict[str, str] = {}
    for kind, items, existing, ctor in (("style", pkg.component.get("styles", []), p.styles, StyleDef.from_dict),
                                        ("font", pkg.component.get("fonts", []), p.fonts, FontResource.from_dict)):
        for d in items:
            obj = ctor(d)
            same = next((e for e in existing if e.id == obj.id), None)
            if same is not None and same.to_dict() == obj.to_dict():
                continue
            if same is not None or obj.id in taken:
                new = unique_id(obj.id, taken)
                res_map[obj.id] = new
                obj.id = new
            taken.add(obj.id)
            existing.append(obj)
    for d in pkg.component.get("images", []):
        img = ImageResource.from_dict(d)
        data = pkg.files.get(d.get("path", ""))
        if data and images_dir:
            os.makedirs(images_dir, exist_ok=True)
            target = os.path.join(images_dir, f"{pkg.id}_{os.path.basename(d['path'])}")
            with open(target, "wb") as f:
                f.write(data)
            img.path = target
        same = p.image(img.id)
        if same is not None and same.path == img.path:
            continue
        if same is not None or img.id in taken:
            new = unique_id(img.id, taken)
            res_map[img.id] = new
            img.id = new
        taken.add(img.id)
        p.images.append(img)
    tmp = rename_references(tmp, mapping)
    for _s, w in tmp.iter_widgets():
        st = w.props.get("styles")
        if isinstance(st, str) and st in res_map:
            w.props["styles"] = res_map[st]
        elif isinstance(st, list):
            w.props["styles"] = [res_map.get(v, v) for v in st]
        for k in ("text_font", "src"):
            if isinstance(w.props.get(k), str) and w.props[k] in res_map:
                w.props[k] = res_map[w.props[k]]
    tops = tmp.screens[0].widgets
    for w in tops:
        if isinstance(w.x, int):
            w.x += int(x)
        if isinstance(w.y, int):
            w.y += int(y)
    container = p.container(screen_id, parent_id)
    container.extend(tops)
    return p, [w.id for w in tops]


# --------------------------------------------------------------------------- biblioteca
def default_library_dir() -> str:
    from olvgl.infrastructure.settings_db import app_data_dir
    return os.path.join(app_data_dir(), "componentes")


class Library:
    def __init__(self, directory: str | None = None):
        self.dir = directory or default_library_dir()

    def list(self) -> list[Package]:
        out = []
        if not os.path.isdir(self.dir):
            return out
        for name in sorted(os.listdir(self.dir)):
            if name.endswith(EXT):
                try:
                    out.append(read_package(os.path.join(self.dir, name)))
                except (ComponentError, OSError):
                    continue
        return sorted(out, key=lambda p: p.name.lower())

    def get(self, cid: str) -> Package | None:
        return next((p for p in self.list() if p.id == cid), None)

    def install(self, source: str | bytes, sha256: str | None = None) -> Package:
        data = source if isinstance(source, (bytes, bytearray)) else open(source, "rb").read()
        if sha256 and hashlib.sha256(data).hexdigest().lower() != sha256.lower():
            raise ComponentError("La suma SHA-256 no coincide: el componente no se instala")
        pkg = read_package(bytes(data))
        os.makedirs(self.dir, exist_ok=True)
        for old in os.listdir(self.dir):                 # una sola versión instalada por id
            if old.startswith(pkg.id + "@") and old.endswith(EXT):
                os.remove(os.path.join(self.dir, old))
        path = os.path.join(self.dir, f"{pkg.id}@{re.sub(r'[^0-9A-Za-z.]', '_', pkg.version)}{EXT}")
        with open(path, "wb") as f:
            f.write(data)
        pkg.path = path
        return pkg

    def remove(self, cid: str) -> bool:
        p = self.get(cid)
        if p is None or not p.path:
            return False
        os.remove(p.path)
        return True


# --------------------------------------------------------------------------- catálogo
@dataclass
class CatalogEntry:
    id: str
    name: str
    version: str
    url: str
    sha256: str
    author: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    license: str = ""
    widgets: int = 0


def default_catalog() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "marketplace", "index.json")


def _fetch(location: str, timeout: float = 20) -> bytes:
    if re.match(r"^https?://", location):
        req = urllib.request.Request(location, headers={"User-Agent": f"OpenLVGLStudio/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:     # noqa: S310 - URL elegida por el usuario
            data = r.read(MAX_PACKAGE + 1)
    else:
        path = urllib.parse.unquote(location[7:]) if location.startswith("file://") else location
        with open(path, "rb") as f:
            data = f.read(MAX_PACKAGE + 1)
    if len(data) > MAX_PACKAGE:
        raise ComponentError("Fichero demasiado grande")
    return data


class Catalog:
    def __init__(self, location: str | None = None):
        self.location = location or default_catalog()
        self.title = ""
        self.entries: list[CatalogEntry] = []

    def load(self) -> list[CatalogEntry]:
        try:
            data = json.loads(_fetch(self.location).decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise ComponentError(f"No se pudo leer el catálogo {self.location}: {exc}") from exc
        if data.get("format") != "olvgl-catalog":
            raise ComponentError("No es un catálogo de componentes de Open LVGL Studio")
        self.title = str(data.get("title", ""))
        self.entries = []
        for e in data.get("components", []):
            try:
                self.entries.append(CatalogEntry(str(e["id"]), str(e.get("name", e["id"])), str(e.get("version", "")),
                                                 str(e["url"]), str(e["sha256"]), str(e.get("author", "")),
                                                 str(e.get("description", "")), list(e.get("tags", [])),
                                                 str(e.get("license", "")), int(e.get("widgets", 0))))
            except (KeyError, TypeError, ValueError):
                continue
        return self.entries

    def resolve(self, url: str) -> str:
        if re.match(r"^(https?|file)://", url) or os.path.isabs(url):
            return url
        if re.match(r"^https?://", self.location):
            return urllib.parse.urljoin(self.location, url)
        return os.path.join(os.path.dirname(os.path.abspath(self.location)), url)

    def download(self, entry: CatalogEntry) -> bytes:
        data = _fetch(self.resolve(entry.url))
        if hashlib.sha256(data).hexdigest().lower() != entry.sha256.lower():
            raise ComponentError(f"«{entry.name}»: la suma SHA-256 no coincide; no se instala")
        return data

    def search(self, text: str) -> list[CatalogEntry]:
        t = text.lower().strip()
        if not t:
            return list(self.entries)
        return [e for e in self.entries if t in e.name.lower() or t in e.description.lower()
                or any(t in x.lower() for x in e.tags)]


def build_index(folder: str, title: str = "Catálogo de Open LVGL Studio") -> dict[str, Any]:
    """index.json para los .olvglc de una carpeta (para publicar un catálogo propio)."""
    comps = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(EXT):
            continue
        path = os.path.join(folder, name)
        data = open(path, "rb").read()
        pkg = read_package(data)
        m = pkg.manifest
        comps.append({"id": pkg.id, "name": pkg.name, "version": pkg.version, "url": name,
                      "sha256": hashlib.sha256(data).hexdigest(), "author": m.get("author", ""),
                      "description": m.get("description", ""), "tags": m.get("tags", []),
                      "license": m.get("license", ""), "widgets": m.get("widgets", 0)})
    return {"format": "olvgl-catalog", "title": title, "components": comps}
