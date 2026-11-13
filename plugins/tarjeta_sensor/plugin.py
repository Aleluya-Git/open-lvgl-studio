"""Tarjeta de sensor: ejemplo de widget compuesto del SDK de plugins.

En el diseñador se dibuja con `paint`; al exportar (ESPHome, C, perfil) se
convierte con `expand` en widgets estándar:

    obj (tarjeta, con los eventos)
      ├─ obj    <id>_accent  barra de color a la izquierda
      ├─ label  <id>_title   título
      ├─ label  <id>_value   valor (texto o lambda/format de ESPHome)
      └─ label  <id>_unit    unidad
"""

FONTS = [f"montserrat_{n}" for n in range(14, 50, 2)]


def register(ctx):
    P = ctx.P

    def props_of(w):
        p = w.props
        return {
            "title": p.get("title", "Sensor"),
            "value": p.get("value", "--"),
            "unit": p.get("unit", ""),
            "accent": p.get("accent", "#FF9800"),
            "bg": p.get("bg", "#1F1F29"),
            "font": p.get("value_font", "montserrat_28"),
        }

    def expand(w):
        v = props_of(w)
        card = ctx.Widget(w.id, "obj", w.x, w.y, w.width, w.height, auto_id=w.auto_id,
                          props={"bg_color": v["bg"], "radius": 14, "border_width": 0, "pad_all": 0,
                                 "scrollable": False}, events=w.events)
        for k in ("align", "hidden", "styles"):
            if k in w.props:
                card.props[k] = w.props[k]
        card.children = [
            ctx.Widget(f"{w.id}_accent", "obj", 0, 0, 6, "100%",
                       props={"bg_color": v["accent"], "radius": 0, "border_width": 0}),
            ctx.Widget(f"{w.id}_title", "label", 18, 10, None, None,
                       props={"text": v["title"], "text_color": "#A8A8B8", "text_font": "montserrat_14"}),
            ctx.Widget(f"{w.id}_value", "label", 18, 8, None, None,
                       props={"text": v["value"], "text_color": "#FFFFFF", "text_font": v["font"],
                              "align": "LEFT_MID"}),
            ctx.Widget(f"{w.id}_unit", "label", -12, -10, None, None,
                       props={"text": v["unit"], "text_color": v["accent"], "text_font": "montserrat_16",
                              "align": "BOTTOM_RIGHT"}),
        ]
        return [card]

    def paint(p, rect, w, props, rctx, state):
        from PySide6.QtCore import QRectF
        from olvgl.domain.values import display_text
        from olvgl.presentation import render
        v = {**props_of(w), **{k: props[k] for k in ("title", "value", "unit", "accent", "bg") if k in props}}
        render.paint_box(p, rect, {"bg_color": v["bg"], "radius": 14, "border_width": 0}, rctx)
        p.save()
        p.setClipRect(rect)
        p.fillRect(QRectF(rect.x(), rect.y(), 6, rect.height()), rctx.color(v["accent"]))
        p.restore()
        inner = QRectF(rect.x() + 18, rect.y() + 10, rect.width() - 30, rect.height() - 20)
        render.paint_text(p, inner, display_text(v["title"]), {"text_color": "#A8A8B8",
                          "text_font": "montserrat_14"}, rctx)
        render.paint_text(p, QRectF(inner.x(), rect.y() + 8, inner.width(), rect.height() - 8),
                          display_text(v["value"]), {"text_color": "#FFFFFF", "text_font": v["font"]},
                          rctx, v_center=True)
        render.paint_text(p, QRectF(rect.x(), rect.y(), rect.width() - 12, rect.height() - 10),
                          display_text(v["unit"]), {"text_color": v["accent"], "text_font": "montserrat_16",
                                                    "text_align": "RIGHT"}, rctx, v_center=False)

    ctx.register_widget(
        "sensor_card", "Tarjeta de sensor", description="Título, valor y unidad de un sensor",
        default_size=(220, 110), id_prefix="card",
        props=(P("title", "Título", ctx.STR, "Sensor", group="Contenido"),
               P("value", "Valor", ctx.STR, "--", group="Contenido"),
               P("unit", "Unidad", ctx.STR, "", group="Contenido"),
               P("accent", "Color de acento", ctx.COLOR, "#FF9800"),
               P("bg", "Fondo de la tarjeta", ctx.COLOR, "#1F1F29"),
               P("value_font", "Fuente del valor", ctx.ENUM, "montserrat_28", FONTS)),
        initial_props={"title": "Temperatura", "value": "21.5", "unit": "°C"},
        expand=expand, paint=paint, icon="icon.png")
