"""Refactorizaciones deterministas: estilos compartidos e ids descriptivos."""
from olvgl.domain.layout import effective_props
from olvgl.domain.model import Action, EventHandler, Screen, Widget, new_project
from olvgl.domain.refactor import descriptive_ids, extract_styles, rename_references
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_text


def _project():
    p = new_project("r")
    ws = []
    for i, name in enumerate(("Salón", "Cocina", "Baño", "Terraza")):
        b = Widget(f"button_{i + 1}", "button", 10 + i * 120, 10, 100, 60,
                   props={"bg_color": "#334455", "radius": 12, "border_width": 0, "text": name,
                          "pressed": {"bg_color": "#000000"}})
        b.auto_id = True
        ws.append(b)
    lbl = Widget("label_1", "label", 10, 100, None, None, props={"text": "Temperatura"})
    lbl.auto_id = True
    ws.append(lbl)
    ws[0].events = [EventHandler("on_click", [Action("raw", {"yaml": "lvgl.label.update:\n  id: label_1\n  text: hola"}),
                                              Action("raw", {"yaml": "lvgl.widget.hide: button_2"})])]
    ws.append(Widget("lbl_info", "label", 10, 140, None, None,
                     props={"text": {"__tag__": "!lambda", "value": "return id(label_1).get_text();"}}))
    p.screens = [Screen("main", "Principal", None, ws)]
    return p


def test_extract_styles_keeps_appearance():
    p = _project()
    before = {w.id: effective_props(p, w) for _s, w in p.iter_widgets()}
    new, rep = extract_styles(p)
    assert rep.styles_created == ["estilo_btn_fondo_334455_r12"]
    sid = rep.styles_created[0]
    assert new.style(sid).props == {"bg_color": "#334455", "radius": 12, "border_width": 0}
    for _s, w in new.iter_widgets():
        eff = effective_props(new, w)
        for k, v in before[w.id].items():
            assert eff.get(k) == v, (w.id, k)
        if w.type == "button":
            assert w.props["styles"] == sid and "pressed" in w.props
    # el YAML resultante se vuelve a importar igual
    text = generate_yaml(new)
    again, rep2 = import_esphome_text(text, "r.yaml", new.display)
    assert sid in {s.id for s in again.styles}


def test_rename_references_everywhere():
    p = rename_references(_project(), {"label_1": "lbl_temp", "button_2": "btn_cocina"})
    w0 = p.widget("button_1")
    assert "id: lbl_temp" in w0.events[0].actions[0].params["yaml"]
    assert w0.events[0].actions[1].params["yaml"] == "lvgl.widget.hide: btn_cocina"
    assert "id(lbl_temp)" in p.widget("lbl_info").props["text"]["value"]
    assert p.widget("lbl_temp") is not None and p.widget("label_1") is None


def test_descriptive_ids():
    p, rep = descriptive_ids(_project())
    assert rep.renamed["button_1"] == "btn_salon"
    assert rep.renamed["label_1"] == "lbl_temperatura"
    assert "lbl_info" not in rep.renamed               # ya era descriptivo
    assert "id(lbl_temperatura)" in p.widget("lbl_info").props["text"]["value"]
    assert p.widget("btn_salon").events[0].actions[1].params["yaml"] == "lvgl.widget.hide: btn_cocina"
