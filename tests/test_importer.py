import os

import yaml

from olvgl.domain.model import TOP_LAYER_ID, Project
from olvgl.infrastructure import json_store
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_file, import_esphome_text


class _AnyTag(yaml.SafeLoader):
    pass


_AnyTag.add_multi_constructor("!", lambda loader, suffix, node: {"!" + suffix: loader.construct_scalar(node)
                                                                 if isinstance(node, yaml.ScalarNode) else None})


def load(text):
    return yaml.load(text, Loader=_AnyTag)


def test_import_demo(demo_path):
    p, rep = import_esphome_file(demo_path)
    assert (p.display.width, p.display.height) == (1024, 600)
    assert p.name == "Panel demo" and p.esphome.device_name == "${nombre}"
    assert [s.id for s in p.screens] == ["inicio", "ajustes"]
    assert p.top_layer is not None and p.top_layer.id == TOP_LAYER_ID
    assert [w.id for w in p.top_layer.walk()] == ["barra_superior", "lbl_hora", "lbl_temp_ext"]
    assert [f.id for f in p.fonts] == ["roboto_20", "roboto_36"]
    assert p.styles[0].id == "tarjeta" and p.styles[0].props["pressed"] == {"bg_color": "#2A2A38"}
    assert p.lvgl_extra["byte_order"] == "big_endian"
    assert p.lvgl_extra["bg_color"] == "#101018"
    assert p.extra_sections["color"][0] == {"id": "morado", "hex": "7E57C2"}
    img = p.images[0]
    assert os.path.isabs(img.path) and os.path.exists(img.path)
    assert rep.raw_actions == 1 and rep.widgets == 26 and not rep.warnings
    assert not rep.generic_types   # Fase 4: todos los widgets tienen editor


def test_import_semantics(demo_path):
    p, _ = import_esphome_file(demo_path)
    comedor = p.widget("btn_comedor")
    # botón con label centrado → botón con texto
    assert comedor.props["text"] == "Comedor" and not comedor.children
    assert comedor.events[0].actions[0].kind == "ha_action"
    assert comedor.events[0].actions[0].params == {"action": "light.toggle", "entity_id": "light.comedor"}
    assert p.widget("btn_salon").props["text"] == "Salón"
    # botón con imagen: se mantiene el hijo
    assert p.widget("btn_escritorio").children[0].type == "image"
    sw = p.widget("sw_ventilador")
    assert sw.events[0].trigger == "on_value" and sw.events[0].actions[0].kind == "raw"
    assert sw.events[0].actions[0].params["yaml"].startswith("if:")
    lam = p.widget("lbl_temp_ext").props["text"]
    assert lam["__tag__"] == "!lambda" and "temp_ext" in lam["value"]
    assert p.widget("lbl_humedad").props["text"]["format"] == "%.0f %%"
    tabs = p.widget("pestanas")
    assert [(t.type, t.id, t.props["name"]) for t in tabs.children] == [
        ("tab", "tab_pb", "Planta baja"), ("tab", "tab_pp", "Primera planta")]
    clima = p.widget("panel_clima")
    assert (clima.x, clima.width, clima.props["align"], clima.props["layout"]) == (-20, "45%", "TOP_RIGHT", "2x2")
    anon = clima.children[0]
    assert anon.auto_id and anon.id.startswith("_label")
    assert p.widget("btn_volver").events[0].actions[0].kind == "page_prev"
    aj = p.screen("ajustes")
    assert aj.bg_color == "#3E2723" and aj.props["on_load"] == [{"logger.log": "Entrando en ajustes"}]


def test_roundtrip_is_stable(demo_path):
    p, _ = import_esphome_file(demo_path)
    gen1 = generate_yaml(p)
    p2, rep2 = import_esphome_text(gen1, demo_path)
    gen2 = generate_yaml(p2)
    assert gen1 == gen2
    assert not rep2.warnings


def test_roundtrip_matches_original(demo_path):
    with open(demo_path, encoding="utf-8") as f:
        original = load(f.read())
    p, _ = import_esphome_file(demo_path)
    regenerated = load(generate_yaml(p))

    def strip_label_ids(node):
        """El generador da id a los labels de botón; el original no siempre los tenía."""
        if isinstance(node, dict):
            if "label" in node and isinstance(node["label"], dict) and str(node["label"].get("id", "")).endswith("_label"):
                node["label"] = {k: v for k, v in node["label"].items() if k != "id"}
            for v in node.values():
                strip_label_ids(v)
        elif isinstance(node, list):
            for v in node:
                strip_label_ids(v)
        return node

    def norm_events(node):
        """`on_x: then: [...]` y `on_x: [...]` son equivalentes en ESPHome."""
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k.startswith("on_") and isinstance(v, dict) and list(v) == ["then"]:
                    node[k] = v["then"]
                norm_events(node[k])
        elif isinstance(node, list):
            for v in node:
                norm_events(v)
        return node

    a = norm_events(strip_label_ids(original["lvgl"]))
    b = norm_events(strip_label_ids(regenerated["lvgl"]))
    assert a == b
    assert original["font"] == regenerated["font"]
    assert original["color"][0]["id"] == regenerated["color"][0]["id"]


def test_json_roundtrip_of_imported(demo_path, tmp_path):
    p, _ = import_esphome_file(demo_path)
    path = str(tmp_path / "importado.olvgl")
    json_store.save_project(p, path)
    q = json_store.load_project(path)
    assert generate_yaml(q) == generate_yaml(p)
    assert q.to_dict() == Project.from_dict(p.to_dict()).to_dict()


def test_packages_includes_and_display(fixtures_dir):
    p, rep = import_esphome_file(os.path.join(fixtures_dir, "dispositivo.yaml"))
    assert (p.display.width, p.display.height) == (320, 480)  # rotación 90
    assert [s.id for s in p.screens] == ["desde_paquete", "principal"]
    assert p.widget("btn_incluido").props["text"] == "Incluido"
    assert p.images[0].type == "RGB565"
    joined = "\n".join(rep.warnings)
    assert "remoto" in joined and "no_existe.png" in joined


def test_implicit_page_and_errors():
    p, rep = import_esphome_text("lvgl:\n  widgets:\n    - label:\n        text: Hola\n")
    assert [s.id for s in p.screens] == ["main_page"]
    assert p.screens[0].widgets[0].props["text"] == "Hola"
    assert any("resolución" in w for w in rep.warnings)
    import pytest
    from olvgl.infrastructure.esphome_importer import ImportError_
    with pytest.raises(ImportError_):
        import_esphome_text("esphome:\n  name: x\n")


def test_duplicate_ids_are_renamed():
    text = ("lvgl:\n  pages:\n    - id: p\n      widgets:\n"
            "        - label:\n            id: a\n        - label:\n            id: a\n")
    p, rep = import_esphome_text(text)
    ids = [w.id for w in p.screens[0].widgets]
    assert ids[0] == "a" and ids[1] != "a"
    assert any("repetido" in w for w in rep.warnings)
    assert not [x for x in p.validate() if "duplicado" in x]


REAL_PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "examples", "panel-domotica_final.yaml")


def _semantic_diff(a, b, path="", out=None):
    out = [] if out is None else out
    if len(out) > 20:
        return out
    if type(a) is not type(b):
        out.append((path, a, b))
    elif isinstance(a, dict):
        for k in set(a) | set(b):
            if k not in a or k not in b:
                out.append((f"{path}/{k}", a.get(k), b.get(k)))
            else:
                _semantic_diff(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((path, len(a), len(b)))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                _semantic_diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append((path, a, b))
    return out


class _TagLoader(yaml.SafeLoader):
    pass


def _tagged(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {"!" + suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {"!" + suffix: loader.construct_sequence(node, deep=True)}
    return {"!" + suffix: loader.construct_mapping(node, deep=True)}


_TagLoader.add_multi_constructor("!", _tagged)


def _norm(node):
    if isinstance(node, dict):
        if "label" in node and isinstance(node["label"], dict) and str(node["label"].get("id", "")).endswith("_label"):
            node["label"] = {k: v for k, v in node["label"].items() if k != "id"}
        for k, v in list(node.items()):
            if k.startswith("on_") and isinstance(v, dict) and list(v) == ["then"]:
                node[k] = v["then"]
            _norm(node[k])
    elif isinstance(node, list):
        for v in node:
            _norm(v)
    return node


def test_real_panel_roundtrip():
    import pytest
    if not os.path.exists(REAL_PANEL):
        pytest.skip("examples/panel-domotica_final.yaml no está")
    p, rep = import_esphome_file(REAL_PANEL)
    assert not rep.warnings, rep.warnings
    assert len(p.screens) >= 1 and rep.widgets > 100
    gen = generate_yaml(p)
    p2, _ = import_esphome_text(gen, REAL_PANEL)
    assert generate_yaml(p2) == gen
    with open(REAL_PANEL, encoding="utf-8") as f:
        original = yaml.load(f, Loader=_TagLoader)
    regenerated = yaml.load(gen, Loader=_TagLoader)
    for sec in ("lvgl", "font", "image"):
        if sec in original:
            diffs = _semantic_diff(_norm(original[sec]), _norm(regenerated[sec]), sec)
            assert not diffs, diffs[:5]
