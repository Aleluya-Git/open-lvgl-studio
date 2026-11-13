"""Componentes reutilizables y catálogo (marketplace)."""
import hashlib
import json
import os
import shutil

import pytest

from olvgl.domain.model import Action, EventHandler, StyleDef, Widget, new_project
from olvgl.infrastructure.components import (Catalog, ComponentError, Library, build_index, extract_component,
                                             insert_component, make_manifest, read_package, write_package)
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _source():
    p = new_project("src")
    p.styles = [StyleDef("tarjeta", {"radius": 12})]
    card = Widget("card", "obj", 100, 50, 200, 120, props={"styles": "tarjeta"}, children=[
        Widget("lbl", "label", 0, 0, None, None, props={"text": "Hola"}),
        Widget("btn", "button", 0, 60, 80, 40, props={"text": "OK"},
               events=[EventHandler("on_click", [Action("widget_state", {"op": "hide", "id": "lbl"})])])])
    p.screens[0].widgets = [card, Widget("otro", "label", 0, 0, None, None)]
    return p


def test_package_roundtrip_and_insert_with_unique_ids(tmp_path):
    src = _source()
    comp = extract_component(src, ["card", "lbl"])           # lbl ya va dentro de card
    assert len(comp["widgets"]) == 1 and comp["widgets"][0]["x"] == 0 and comp["styles"][0]["id"] == "tarjeta"
    m = make_manifest("Mi tarjeta", comp, "ana", "desc", ["x"])
    path = write_package(str(tmp_path / "c.olvglc"), m, comp)
    pkg = read_package(path)
    assert pkg.id == "mi-tarjeta" and pkg.manifest["widgets"] == 3
    target = _source()                                       # ya tiene card, lbl, btn y el estilo
    target.styles[0].props["radius"] = 4                     # mismo id, distinto contenido
    new, tops = insert_component(target, pkg, target.screens[0].id, None, 300, 200)
    ids = list(new.all_ids())
    assert len(ids) == len(set(ids)) and len(tops) == 1 and tops[0] != "card"
    w = new.widget(tops[0])
    assert (w.x, w.y) == (300, 200) and w.props["styles"] != "tarjeta"
    btn = w.children[1]
    assert btn.events[0].actions[0].params["id"] == w.children[0].id      # referencia renombrada
    again, rep = import_esphome_text(generate_yaml(new), "x.yaml", new.display)
    assert not rep.warnings


def test_library_and_sha256(tmp_path):
    src = _source()
    comp = extract_component(src, ["card"])
    path = write_package(str(tmp_path / "c.olvglc"), make_manifest("Tarjeta", comp), comp)
    lib = Library(str(tmp_path / "lib"))
    with pytest.raises(ComponentError):
        lib.install(path, sha256="0" * 64)
    data = open(path, "rb").read()
    pkg = lib.install(path, sha256=hashlib.sha256(data).hexdigest())
    assert [p.id for p in lib.list()] == [pkg.id]
    lib.install(path)                                        # reinstalar no duplica
    assert len(lib.list()) == 1
    assert lib.remove(pkg.id) and lib.list() == []
    with pytest.raises(ComponentError):
        read_package(b"no es un zip")


def test_bundled_catalog_installs_everything(tmp_path):
    cat = Catalog(os.path.join(ROOT, "marketplace", "index.json"))
    entries = cat.load()
    assert len(entries) >= 4 and cat.search("termostato")[0].id == "termostato"
    lib = Library(str(tmp_path / "lib"))
    p = new_project("t")
    for e in entries:
        pkg = lib.install(cat.download(e), e.sha256)
        p, tops = insert_component(p, pkg, p.screens[0].id)
        assert tops
    ids = list(p.all_ids())
    assert len(ids) == len(set(ids))
    import_esphome_text(generate_yaml(p), "x.yaml", p.display)


def test_own_catalog_from_folder(tmp_path):
    folder = tmp_path / "cat"
    folder.mkdir()
    src = _source()
    comp = extract_component(src, ["otro"])
    write_package(str(folder / "a.olvglc"), make_manifest("A", comp), comp)
    idx = build_index(str(folder))
    (folder / "index.json").write_text(json.dumps(idx), encoding="utf-8")
    cat = Catalog(str(folder / "index.json"))
    assert [e.id for e in cat.load()] == ["a"]
    (folder / "a.olvglc").write_bytes(b"manipulado")
    with pytest.raises(ComponentError):
        cat.download(cat.entries[0])
    assert shutil
