"""Indicador de aguja (`meter` de ESPHome): escalas, marcas e indicadores.

El modelo guarda la configuración tal como se escribe en ESPHome:

    meter:
      scales:
        - range_from: 0            # valor mínimo
          range_to: 100            # valor máximo
          angle_range: 270         # grados que ocupa la escala
          rotation: 135            # ángulo de inicio (0° = las 3 en punto, sentido horario)
          ticks:
            count: 21  width: 2  length: 10  color: 0x808080  radial_offset: 0
            major: {stride: 5, width: 4, length: 15%, color: …, label_gap: 10, radial_offset: 0}
          indicators:
            - line: {id, value, width, color, r_mod, opa}
            - arc: {id, start_value, end_value, width, color, r_mod, opa}
            - image: {id, src, value, pivot_x, pivot_y, opa}
            - tick_style: {id, start_value, end_value, color_start, color_end, width, local}

Este módulo da los valores por defecto, normaliza lo que viene del YAML y hace
la geometría (valor → ángulo, longitudes en % del radio) para el dibujo, el
editor y el generador de C.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

INDICATOR_TYPES = ("line", "arc", "image", "tick_style")
INDICATOR_LABELS = {"line": "Aguja", "arc": "Arco", "image": "Aguja de imagen", "tick_style": "Color de marcas"}

SCALE_DEFAULTS = {"range_from": 0, "range_to": 100, "angle_range": 270}
TICKS_DEFAULTS = {"count": 12, "width": 2, "length": 10, "color": "#808080", "radial_offset": 0}
MAJOR_DEFAULTS = {"stride": 3, "width": 5, "length": "15%", "color": "#808080", "label_gap": 4,
                  "radial_offset": 0}
INDICATOR_DEFAULTS: dict[str, dict[str, Any]] = {
    "line": {"width": 4, "color": "#000000", "r_mod": 0, "opa": "COVER"},
    "arc": {"width": 4, "color": "#000000", "r_mod": 0, "opa": "COVER"},
    "image": {"pivot_x": 0, "pivot_y": 0, "opa": "COVER"},
    "tick_style": {"width": 4, "color_start": "#000000", "color_end": "#000000", "local": False},
}
NEW_INDICATOR: dict[str, dict[str, Any]] = {          # lo que se crea al pulsar «Añadir…»
    "line": {"value": 50, "width": 4, "color": "#2196F3", "r_mod": -10},
    "arc": {"start_value": 0, "end_value": 50, "width": 6, "color": "#4CAF50"},
    "image": {"value": 50, "pivot_x": 0, "pivot_y": 0},
    "tick_style": {"start_value": 70, "end_value": 100, "color_start": "#FFC107", "color_end": "#F44336",
                   "width": 4},
}
NEW_SCALE = {"range_from": 0, "range_to": 100, "angle_range": 270, "rotation": 135,
             "ticks": {"count": 21, "width": 2, "length": 10, "color": "#9E9E9E",
                       "major": {"stride": 5, "width": 4, "length": 16, "color": "#616161", "label_gap": 10}},
             "indicators": [{"line": dict(NEW_INDICATOR["line"])}]}


def num(v: Any, default: float = 0.0) -> float:
    if isinstance(v, bool) or v is None or (isinstance(v, dict) and "__tag__" in v):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().rstrip("px"))
    except ValueError:
        return default


def length(v: Any, radius: float, default: float = 0.0) -> float:
    """10 → 10 px; '15%' → 15 % del radio."""
    if isinstance(v, str) and v.strip().endswith("%"):
        try:
            return radius * float(v.strip()[:-1]) / 100
        except ValueError:
            return default
    return num(v, default)


def default_rotation(angle_range: float) -> float:
    """La de ESPHome: la escala queda simétrica con el hueco abajo."""
    return 90 + (360 - angle_range) / 2


def scales_of(props: dict) -> list[dict]:
    sc = props.get("scales")
    if isinstance(sc, dict) and "__tag__" not in sc:
        sc = [sc]
    return [s for s in sc if isinstance(s, dict)] if isinstance(sc, list) else []


def indicator_kind(item: Any) -> tuple[str, dict] | None:
    """{"line": {...}} → ("line", {...})."""
    if not isinstance(item, dict) or len(item) != 1:
        return None
    (k, v), = item.items()
    if k not in INDICATOR_TYPES:
        return None
    return k, (v if isinstance(v, dict) else {})


@dataclass
class ScaleGeo:
    range_from: float
    range_to: float
    angle_range: float
    rotation: float

    def ratio(self, value: Any) -> float:
        span = self.range_to - self.range_from
        if span == 0:
            return 0.0
        return max(0.0, min(1.0, (num(value, self.range_from) - self.range_from) / span))

    def angle(self, value: Any) -> float:
        """Ángulo LVGL (grados, 0 = las 3, horario) del valor."""
        return self.rotation + self.angle_range * self.ratio(value)


def scale_geo(scale: dict) -> ScaleGeo:
    a = num(scale.get("angle_range"), 270)
    rot = scale.get("rotation")
    return ScaleGeo(num(scale.get("range_from"), 0), num(scale.get("range_to"), 100), a,
                    num(rot, default_rotation(a)) if rot is not None else default_rotation(a))


def ticks_of(scale: dict) -> tuple[dict, dict | None]:
    """(marcas menores con sus valores por defecto, marcas principales o None)."""
    t = scale.get("ticks")
    t = t if isinstance(t, dict) else {}
    ticks = dict(TICKS_DEFAULTS, **{k: v for k, v in t.items() if k != "major"})
    major = t.get("major")
    major = dict(MAJOR_DEFAULTS, **major) if isinstance(major, dict) else None
    return ticks, major


def tick_values(scale: dict) -> list[tuple[float, bool]]:
    """[(valor, es_principal)] de cada marca."""
    g = scale_geo(scale)
    ticks, major = ticks_of(scale)
    n = int(num(ticks.get("count"), 12))
    if n <= 0:
        return []
    stride = int(num(major.get("stride"), 3)) if major else 0
    out = []
    for i in range(n):
        v = g.range_from + (g.range_to - g.range_from) * (i / (n - 1) if n > 1 else 0)
        out.append((v, bool(stride) and i % stride == 0))
    return out


def summary(props: dict) -> str:
    """«2 escalas · 3 indicadores» para el panel de propiedades."""
    scales = scales_of(props)
    n_ind = sum(len([i for i in (s.get("indicators") or []) if indicator_kind(i)]) for s in scales)
    return f"{len(scales)} · {n_ind}"


def first_value(props: dict) -> Any:
    """El valor de la primera aguja (para el editor rápido)."""
    for s in scales_of(props):
        for it in s.get("indicators") or []:
            k = indicator_kind(it)
            if k and k[0] in ("line", "image"):
                return k[1].get("value")
    return None


def set_first_value(props: dict, value: Any) -> list[dict] | None:
    """Copia de `scales` con el valor de la primera aguja cambiado (None si no hay agujas)."""
    scales = copy.deepcopy(scales_of(props))
    for s in scales:
        for it in s.get("indicators") or []:
            k = indicator_kind(it)
            if k and k[0] in ("line", "image"):
                it[k[0]] = dict(k[1], value=value)
                return scales
    return None
