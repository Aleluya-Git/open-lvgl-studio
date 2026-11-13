import difflib
import os
import time

import pytest

from olvgl.domain.model import Action, EventHandler, Widget
from olvgl.domain.yaml_ast import YMap
from olvgl.infrastructure.esphome_generator import generate_ast
from olvgl.infrastructure.esphome_importer import import_esphome_text
from olvgl.infrastructure.yaml_parser import parse
from olvgl.infrastructure.yaml_sync import canon, same, sync_text

SRC = """# Mi panel — comentario de cabecera
substitutions:
  luz: light.salon   # entidad

sensor:
  - platform: homeassistant
    id: temp
    entity_id: sensor.t   # no tocar

font:
- file: gfonts://Roboto
  id: r20
  size: 20
  glyphs: [a, b, c]

lvgl:
  byte_order: big_endian   # pantalla Waveshare
  # --- páginas ---
  pages:
    - id: inicio
      bg_color: 0x101018
      widgets:
        # título
        - label:
            id: titulo
            x: 10
            y: 10
            text: 'Hola'   # saludo
            text_color: 0xFFFFFF
        - button:
            id: btn_luz
            x: 10
            y: 60
            widgets:
              - label:
                  align: CENTER
                  text: Luz
            on_click:
              then:
                - homeassistant.action:
                    action: light.toggle
                    data:
                      entity_id: ${luz}
        - obj:
            id: tarjeta
            x: 300
            y: 10
            width: 200
            height: 100
            widgets:
              - label: {id: dentro, text: Dentro}
    - id: ajustes
      widgets:
        - label:
            id: lbl_aj
            text: Ajustes
"""


def load(text=SRC):
    p, _ = import_esphome_text(text, "panel.yaml")
    return p


def diff_lines(a, b):
    return [ln for ln in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
            if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]


def test_noop_changes_nothing():
    p = load()
    r = sync_text(SRC, SRC, generate_ast(p))
    assert not r.changed and r.text == SRC and not r.rewritten


def test_scalar_edits_are_minimal_and_keep_comments():
    p = load()
    p.widget("titulo").props["text"] = "Buenos días"
    p.widget("titulo").x = 20
    p.widget("btn_luz").props["text"] = "Luz salón"
    r = sync_text(SRC, SRC, generate_ast(p))
    d = diff_lines(SRC, r.text)
    assert d == ["-            x: 10", "+            x: 20",
                 "-            text: 'Hola'   # saludo", "+            text: Buenos días   # saludo",
                 "-                  text: Luz", "+                  text: Luz salón"]
    assert "# --- páginas ---" in r.text and "# título" in r.text
    assert not r.rewritten


def test_insert_delete_and_reorder_widgets():
    p = load()
    s = p.screen("inicio")
    s.widgets.append(Widget("nuevo", "label", x=5, y=200, width=None, height=None, props={"text": "Nuevo"}))
    p.widget("tarjeta").children.clear()
    p.screen("ajustes").widgets.pop()
    r = sync_text(SRC, SRC, generate_ast(p))
    assert not r.rewritten
    out = parse(r.text)
    assert same(out.get("lvgl"), generate_ast(p).get("lvgl"), "lvgl")
    assert "id: nuevo" in r.text and "id: dentro" not in r.text and "lbl_aj" not in r.text
    assert "# título" in r.text and "entity_id: sensor.t   # no tocar" in r.text


def test_events_flow_and_new_section():
    p = load()
    btn = p.widget("btn_luz")
    btn.events[0].actions.append(Action("page_show", {"page": "ajustes"}))
    p.fonts[0].data["glyphs"] = ["a", "b", "c", "d"]
    p.extra_sections["color"] = [{"id": "morado", "hex": "7E57C2"}]
    r = sync_text(SRC, SRC, generate_ast(p))
    out = parse(r.text)
    assert same(out.get("font"), generate_ast(p).get("font"), "font")
    assert "glyphs: [a, b, c, d]" in r.text          # se conserva el estilo en línea
    on_click = out.get("lvgl").get("pages").items[0].get("widgets").items[1].get("button").get("on_click")
    assert isinstance(on_click, YMap) and len(on_click.get("then").items) == 2   # sigue usando then:
    assert out.get("color") is not None
    assert "sensor:" in r.text and "# Mi panel" in r.text


def test_page_add_remove_and_bg():
    p = load()
    from olvgl.domain.model import Screen
    p.screens.insert(1, Screen("clima", "Clima", "#123456"))
    p.screen("ajustes").bg_color = "#3E2723"
    r = sync_text(SRC, SRC, generate_ast(p))
    out = parse(r.text)
    ids = [pg.get("id").value for pg in out.get("lvgl").get("pages").items]
    assert ids == ["inicio", "clima", "ajustes"]
    assert same(out.get("lvgl"), generate_ast(p).get("lvgl"), "lvgl")


def test_three_way_merge_keeps_external_edits():
    p = load()
    base = SRC
    # el usuario edita el fichero a mano (otra página y un comentario nuevo)
    external = SRC.replace("text: Ajustes", "text: Configuración  # editado a mano")
    # y en el editor cambia otra cosa
    p.widget("titulo").props["text"] = "Hola de nuevo"
    r = sync_text(external, base, generate_ast(p))
    assert "text: Configuración  # editado a mano" in r.text
    assert "text: Hola de nuevo" in r.text
    assert not r.conflicts


def test_conflict_editor_wins_and_is_reported():
    p = load()
    external = SRC.replace("text: 'Hola'", "text: 'Hola fichero'")
    p.widget("titulo").props["text"] = "Hola editor"
    r = sync_text(external, SRC, generate_ast(p))
    assert "Hola editor" in r.text and "Hola fichero" not in r.text
    assert r.conflicts


def test_external_only_change_is_preserved():
    p = load()
    external = SRC.replace("x: 300", "x: 320")
    r = sync_text(external, SRC, generate_ast(p))
    assert not r.changed and r.text == external


def test_label_ids_are_not_added_to_original():
    p = load()
    p.widget("btn_luz").props["text"] = "Otra"
    r = sync_text(SRC, SRC, generate_ast(p))
    assert "btn_luz_label" not in r.text


def test_canon_equivalences():
    a = parse("on_click:\n  then:\n    - logger.log: x\n")
    b = parse("on_click:\n  - logger.log: \"x\"\n")
    assert canon(a) == canon(b)
    c = parse("label:\n  id: b_label\n  text: t\n")
    d = parse("label:\n  text: t\n")
    assert canon(c) == canon(d)


REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "examples", "panel-domotica_final.yaml")


def test_real_panel_minimal_edits_and_speed():
    if not os.path.exists(REAL):
        pytest.skip("examples/panel-domotica_final.yaml no está")
    with open(REAL, encoding="utf-8") as f:
        text = f.read()
    p, _ = import_esphome_text(text, REAL)
    t = time.monotonic()
    r = sync_text(text, text, generate_ast(p))
    assert not r.changed
    first = next(w for _, w in p.iter_widgets() if w.type == "label" and isinstance(w.props.get("text"), str))
    first.props["text"] = "Cambiado"
    r = sync_text(text, text, generate_ast(p))
    elapsed = time.monotonic() - t
    d = diff_lines(text, r.text)
    assert len(d) == 2 and "Cambiado" in d[1] and not r.rewritten
    assert elapsed < 5


def test_new_key_and_nested_append_on_same_line():
    p = load()
    tarjeta = p.widget("tarjeta")
    tarjeta.children.append(Widget("dentro2", "label", x=None, y=None, width=None, height=None,
                                   props={"text": "Otro"}))
    tarjeta.props["bg_color"] = "#222222"     # clave nueva en el mismo mapa
    r = sync_text(SRC, SRC, generate_ast(p))
    assert not r.rewritten
    assert same(parse(r.text).get("lvgl"), generate_ast(p).get("lvgl"), "lvgl")


def test_many_random_edits_always_valid():
    import random
    rnd = random.Random(7)
    for _ in range(40):
        p = load()
        ws = [w for _, w in p.iter_widgets()]
        for _ in range(rnd.randint(1, 4)):
            w = rnd.choice(ws)
            op = rnd.randint(0, 4)
            if op == 0:
                w.props["text_color"] = "#%06X" % rnd.randint(0, 0xFFFFFF)
            elif op == 1:
                w.x = rnd.randint(0, 500)
            elif op == 2:
                w.props.pop(next(iter(w.props), "x"), None)
            elif op == 3:
                w.children.append(Widget(f"n{rnd.randint(0, 9999)}", "label", x=None, y=None,
                                         width=None, height=None, props={"text": "z"}))
            else:
                w.events.append(EventHandler("on_press", [Action("logger", {"message": "p"})]))
        r = sync_text(SRC, SRC, generate_ast(p))
        assert same(parse(r.text).get("lvgl"), generate_ast(p).get("lvgl"), "lvgl")
        assert "sensor:" in r.text and "# Mi panel" in r.text
