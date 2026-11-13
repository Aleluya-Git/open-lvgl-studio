"""Crea los componentes de ejemplo del catálogo (marketplace/*.olvglc + index.json).

    python tools/build_components.py

Para publicar un catálogo propio: pon tus .olvglc en una carpeta, genera su
index.json con `olvgl.infrastructure.components.build_index(carpeta)` y súbela
a cualquier servidor web; en Equipo › Componentes › Catálogo pega su URL.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from olvgl.domain.model import Action, EventHandler, Project, Screen, Widget  # noqa: E402
from olvgl.infrastructure.components import build_index, extract_component, make_manifest, write_package  # noqa: E402

OUT = os.path.join(ROOT, "marketplace")
AUTHOR = "Open LVGL Studio"


def card(wid, w, h, children, bg="#1F1F2B"):
    return Widget(wid, "obj", 0, 0, w, h, props={"bg_color": bg, "radius": 16, "border_width": 0, "pad_all": 14},
                  children=children)


def label(wid, text, font="montserrat_16", color="#FFFFFF", **kw):
    return Widget(wid, "label", None, None, None, None, props={"text": text, "text_font": font, "text_color": color,
                                                               **kw})


def components():
    yield ("Tarjeta de luz", "Botón conmutable con nombre y estado para una luz de Home Assistant.",
           ["luces", "home assistant", "botón"],
           [Widget("btn_luz", "button", 0, 0, 200, 110, props={
               "bg_color": "#1F1F2B", "radius": 16, "border_width": 0, "checkable": True,
               "checked": {"bg_color": "#FFB300"}},
               children=[label("lbl_luz_nombre", "Salón", "montserrat_20", align="TOP_LEFT"),
                         label("lbl_luz_estado", "Apagada", "montserrat_14", "#A8A8B8", align="BOTTOM_LEFT")],
               events=[EventHandler("on_click", [Action("ha_action", {"action": "light.toggle",
                                                                      "entity_id": "light.salon"})])])])
    yield ("Termostato", "Arco ajustable con la temperatura de consigna y la actual.",
           ["clima", "termostato", "arco"],
           [card("panel_termostato", 240, 240, [
               label("lbl_termo_titulo", "Termostato", "montserrat_16", "#A8A8B8", align="TOP_MID"),
               Widget("arc_termo", "arc", None, None, 170, 170, props={
                   "min_value": 15, "max_value": 30, "value": 21, "adjustable": True, "align": "CENTER",
                   "y": 10, "indicator": {"arc_color": "#FF7043"}, "knob": {"bg_color": "#FFFFFF"}},
                   events=[EventHandler("on_release", [Action("raw", {"yaml": (
                       "homeassistant.action:\n  action: climate.set_temperature\n  data:\n"
                       "    entity_id: climate.salon\n    temperature: !lambda return x;")})])]),
               label("lbl_termo_valor", "21 °C", "montserrat_28", align="CENTER", y=10)])])
    yield ("Barra de navegación", "Cuatro botones para cambiar de página, a lo ancho de la pantalla.",
           ["navegación", "páginas", "barra"],
           [Widget("panel_nav", "obj", 0, 0, 800, 64, props={
               "bg_color": "#1F1F2B", "radius": 0, "border_width": 0, "pad_all": 8,
               "layout": {"type": "FLEX", "flex_flow": "ROW", "pad_column": 8}},
               children=[Widget(f"btn_nav_{n}", "button", None, None, None, 48, props={
                   "flex_grow": 1, "bg_color": "#2E2E3E", "radius": 12, "text": t, "text_font": "montserrat_16"},
                   events=[EventHandler("on_click", [Action("page_show", {"page": n})])])
                   for n, t in (("inicio", "Inicio"), ("luces", "Luces"), ("clima", "Clima"), ("ajustes", "Ajustes"))])])
    yield ("Medidor de energía", "Valor grande, unidad y barra de consumo.",
           ["energía", "sensor", "barra"],
           [card("panel_energia", 260, 140, [
               label("lbl_energia_titulo", "Consumo", "montserrat_16", "#A8A8B8"),
               label("lbl_energia_valor", "1.2 kW", "montserrat_36", align="LEFT_MID"),
               Widget("bar_energia", "bar", None, None, "100%", 10, props={
                   "value": 40, "align": "BOTTOM_MID", "bg_color": "#2E2E3E", "indicator": {"bg_color": "#FFB300"}})])])


def main() -> dict:
    os.makedirs(OUT, exist_ok=True)
    for name in os.listdir(OUT):
        if name.endswith(".olvglc"):
            os.remove(os.path.join(OUT, name))
    for name, desc, tags, widgets in components():
        p = Project(name=name)
        p.screens = [Screen("p", "p", None, widgets)]
        comp = extract_component(p, [w.id for w in widgets])
        m = make_manifest(name, comp, AUTHOR, desc, tags, "1.0.0", "MIT")
        write_package(os.path.join(OUT, f"{m['id']}.olvglc"), m, comp)
    index = build_index(OUT, "Componentes de ejemplo de Open LVGL Studio")
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    return index


if __name__ == "__main__":
    idx = main()
    print(f"{len(idx['components'])} componentes en {OUT}")
