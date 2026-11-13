"""Motor del simulador (sin Qt).

Trabaja sobre una **copia** del proyecto, de modo que las acciones de los
eventos pueden cambiarlo durante la simulación sin tocar el diseño:
mostrar/ocultar widgets, `lvgl.*.update`, navegación entre páginas y
pestañas, interruptores, casillas, deslizadores, arcos, desplegables,
rodillos y spinbox. Las acciones que dependen del dispositivo (Home
Assistant, scripts, lambdas…) se registran en el log.

Fase 6 (simulador profesional):
- gestos táctiles como LVGL: desplazamiento de contenedores y páginas con
  arrastre (umbral `scroll_limit` 10 px), deslizamientos (`gesture_limit`
  50 px) con `on_gesture` / `on_swipe_left|right|up|down|top|bottom`,
  mosaicos (tileview) y pestañas que cambian deslizando, doble clic y
  pulsación larga repetida;
- rotación del dispositivo (0/90/180/270) y cualquier resolución, para
  probar el mismo proyecto en varias pantallas a la vez;
- `page_wrap` y `skip` de las páginas, disparadores `on_load` / `on_unload`
  de página, `on_idle` (reposo) y `on_landscape` / `on_portrait`.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import replace

from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain import catalog
from olvgl.domain.layout import Box, LayoutContext, Rect, compute_layout
from olvgl.domain.model import TOP_LAYER_ID, Action, DisplayProfile, Project, Widget

LONG_PRESS_MS = 400          # LV_INDEV_DEF_LONG_PRESS_TIME
LONG_PRESS_REPEAT_MS = 100   # LV_INDEV_DEF_LONG_PRESS_REP_TIME
SCROLL_LIMIT = 10            # LV_INDEV_DEF_SCROLL_LIMIT
GESTURE_LIMIT = 50           # LV_INDEV_DEF_GESTURE_LIMIT
DOUBLE_CLICK_S = 0.4
TOGGLE_TYPES = {"switch", "checkbox"}
DRAG_TYPES = {"slider", "arc"}
CYCLE_TYPES = {"dropdown", "roller"}
CLICKABLE_TYPES = {"button", "switch", "checkbox", "slider", "arc", "dropdown", "roller", "textarea",
                   "spinbox", "buttonmatrix", "keyboard"}
# dirección del dedo → triggers de ESPHome (up/top y down/bottom son sinónimos)
SWIPE_TRIGGERS = {"left": ("on_swipe_left",), "right": ("on_swipe_right",),
                  "up": ("on_swipe_up", "on_swipe_top"), "down": ("on_swipe_down", "on_swipe_bottom")}
# el dedo va a la izquierda → se pasa al mosaico de la derecha, etc.
TILE_STEP = {"left": (0, 1, "RIGHT"), "right": (0, -1, "LEFT"), "up": (1, 0, "BOTTOM"), "down": (-1, 0, "TOP")}
ARROWS = {"left": "←", "right": "→", "up": "↑", "down": "↓"}
ROTATIONS = (0, 90, 180, 270)


def parse_duration(value) -> float | None:
    """'500ms', '30s', '1min', '2h' o milisegundos → segundos."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    m = re.match(r"^\s*([\d.]+)\s*(ms|s|min|h)?\s*$", str(value))
    if not m:
        return None
    n = float(m.group(1))
    return n * {"ms": 0.001, "s": 1, "min": 60, "h": 3600, None: 0.001}[m.group(2)]


def _dirs(value) -> set[str]:
    """Valor de `dir`/`scroll_dir` de ESPHome → conjunto LEFT/RIGHT/TOP/BOTTOM."""
    vals = value if isinstance(value, list) else [value]
    out: set[str] = set()
    for v in vals:
        v = str(v or "ALL").upper()
        out |= {"HOR": {"LEFT", "RIGHT"}, "VER": {"TOP", "BOTTOM"},
                "ALL": {"LEFT", "RIGHT", "TOP", "BOTTOM"}, "NONE": set()}.get(v, {v})
    return out


def _describe_raw(value) -> str:
    """Resumen de una lista de acciones en bruto (YAML conservado)."""
    items = value if isinstance(value, list) else [value]
    parts = []
    for it in items:
        if isinstance(it, dict):
            for k, v in it.items():
                if k == "lambda":
                    code = v.get("value") if isinstance(v, dict) else v
                    first = str(code or "").strip().splitlines()
                    parts.append(f"λ {first[0][:60] if first else ''}")
                else:
                    parts.append(f"{k}: {v}" if isinstance(v, (str, int, float)) else str(k))
        elif it is not None:
            parts.append(str(it))
    return " · ".join(parts)


class SimulatorEngine:
    last_layout_ms = 0.0

    def __init__(self, vm: ProjectViewModel, log=None, display: DisplayProfile | None = None,
                 rotation: int = 0):
        self.vm = vm
        self.log = log or (lambda msg: None)
        self.display_override = display
        self.rotation = rotation if rotation in ROTATIONS else 0
        self.project: Project = vm.project.clone()
        self.page_id = vm.current_screen_id if vm.current_screen_id != TOP_LAYER_ID else (
            self.project.screens[0].id if self.project.screens else "")
        self.checked: set[str] = set()
        self.pressed: str | None = None
        self.press_time = 0.0
        self.long_fired = False
        self.active_tabs: dict[str, int] = {}
        self.scroll: dict[str, tuple[float, float]] = {}
        self._drag_start_value: int | None = None
        self._boxes: dict[str, dict[str, Box]] = {}
        self._raw: dict[str, dict[str, Box]] = {}
        # gestos
        self.touch: tuple[float, float] | None = None     # punto de contacto actual (para dibujarlo)
        self.trail: list[tuple[float, float]] = []
        self._start: tuple[float, float] | None = None
        self._mode: str | None = None                     # None | "value" | "scroll"
        self._scroll_target: tuple[str, str] | None = None  # (contenedor, pantalla)
        self._scroll_origin = (0.0, 0.0)
        self._last_click: tuple[str, float] | None = None
        # reposo y estadísticas
        self.last_activity = time.monotonic()
        self.idle_fired: set[float] = set()
        self.events_fired = 0
        self._apply_display()
        self._page_entered(self.page_id)

    # ----------------------------------------------------------------- pantalla
    def base_display(self) -> DisplayProfile:
        d = self.display_override or self.vm.project.display
        return DisplayProfile(d.name, d.width, d.height)

    def display(self) -> DisplayProfile:
        d = self.base_display()
        if self.rotation in (90, 270):
            return DisplayProfile(d.name, d.height, d.width)
        return d

    def _apply_display(self) -> None:
        self.project.display = self.display()

    def is_landscape(self) -> bool:
        d = self.display()
        return d.width >= d.height

    def set_rotation(self, degrees: int) -> None:
        """Gira el dispositivo: la disposición se recalcula con la nueva resolución."""
        degrees = int(degrees) % 360
        if degrees not in ROTATIONS or degrees == self.rotation:
            return
        was_landscape = self.is_landscape()
        self.rotation = degrees
        self._apply_display()
        self.scroll.clear()
        self._changed()
        d = self.display()
        self.log(f"↻ {degrees}° → {d.width}×{d.height}")
        if was_landscape != self.is_landscape():
            trig = "on_landscape" if self.is_landscape() else "on_portrait"
            if trig in self.project.lvgl_extra:
                self.events_fired += 1
                self.log(f"[lvgl.{trig}] {_describe_raw(self.project.lvgl_extra[trig])}")

    def set_display(self, display: DisplayProfile | None) -> None:
        self.display_override = display
        self._apply_display()
        self.scroll.clear()
        self._changed()

    # ----------------------------------------------------------------- estado
    def reload(self) -> None:
        """El diseño ha cambiado: se vuelve a copiar (se pierde el estado simulado)."""
        self.project = self.vm.project.clone()
        self._apply_display()
        self.pressed = None
        self._mode = None
        self.scroll.clear()
        self._changed()

    def widget(self, wid: str | None) -> Widget | None:
        return self.project.widget(wid) if wid else None

    @property
    def page(self):
        p = self.project.screen(self.page_id)
        if (p is None or p.id == TOP_LAYER_ID) and self.project.screens:
            p = self.project.screens[0]
            self.page_id = p.id
        return p

    def boxes(self, screen_id: str) -> dict[str, Box]:
        cached = self._boxes.get(screen_id)
        if cached is not None:
            return cached
        screen = self.project.screen(screen_id)
        if screen is None:
            return {}
        raw = self._raw.get(screen_id)
        if raw is None:
            ctx = LayoutContext(self.project, self.vm.measure_text, self.vm.image_size, self.active_tabs)
            t0 = time.perf_counter()
            raw = compute_layout(self.project, screen, ctx)
            self.last_layout_ms = (time.perf_counter() - t0) * 1000
            self._raw[screen_id] = raw
        boxes = self._apply_scroll(screen_id, raw)
        self._boxes[screen_id] = boxes
        return boxes

    def _changed(self) -> None:
        self._boxes.clear()
        self._raw.clear()

    def layers(self) -> list[tuple[str, list[Widget]]]:
        """Capas de abajo a arriba: página y capa superior."""
        out = []
        page = self.page
        if page is not None:
            out.append((page.id, page.widgets))
        tl = self.project.top_layer
        if tl is not None:
            out.append((TOP_LAYER_ID, tl.widgets))
        return out

    # ----------------------------------------------------------------- desplazamiento
    def _children_of(self, cid: str, screen_id: str) -> list[Widget]:
        if cid == screen_id:
            scr = self.project.screen(screen_id)
            return list(scr.widgets) if scr else []
        w = self.project.widget(cid)
        return list(w.children) if w else []

    def _descendants(self, cid: str, screen_id: str):
        for child in self._children_of(cid, screen_id):
            yield from child.walk()

    def _apply_scroll(self, screen_id: str, raw: dict[str, Box]) -> dict[str, Box]:
        active = {cid: off for cid, off in self.scroll.items() if off != (0.0, 0.0)}
        if not active:
            return raw
        boxes = dict(raw)
        for cid, (dx, dy) in active.items():
            if cid != screen_id and cid not in raw:
                continue
            for d in self._descendants(cid, screen_id):
                b = boxes.get(d.id)
                if b is None:
                    continue
                boxes[d.id] = replace(b, rect=Rect(b.rect.x - dx, b.rect.y - dy, b.rect.w, b.rect.h),
                                      content=Rect(b.content.x - dx, b.content.y - dy,
                                                   b.content.w, b.content.h))
        return boxes

    def scroll_range(self, cid: str, screen_id: str) -> tuple[float, float]:
        """Máximo desplazamiento (x, y) del contenedor según lo que sobresale su contenido."""
        self.boxes(screen_id)
        raw = self._raw.get(screen_id, {})
        if cid == screen_id:
            d = self.project.display
            content = Rect(0, 0, d.width, d.height)
        else:
            b = raw.get(cid)
            if b is None:
                return 0.0, 0.0
            content = b.content
        right, bottom = content.right, content.bottom
        for child in self._children_of(cid, screen_id):
            cb = raw.get(child.id)
            if cb is None or not cb.shown or cb.hidden:
                continue
            right = max(right, cb.rect.right)
            bottom = max(bottom, cb.rect.bottom)
        return max(0.0, right - content.right), max(0.0, bottom - content.bottom)

    def _scrollable(self, cid: str, screen_id: str) -> tuple[float, float, set[str]]:
        if cid == screen_id:
            scr = self.project.screen(screen_id)
            props = scr.props if scr else {}
        else:
            w = self.project.widget(cid)
            if w is None or w.type in catalog.CHILD_LISTS or w.type in DRAG_TYPES or not w.children:
                return 0.0, 0.0, set()
            b = self._raw.get(screen_id, {}).get(cid)
            props = b.props if b is not None else w.props
        if props.get("scrollable") is False:
            return 0.0, 0.0, set()
        mx, my = self.scroll_range(cid, screen_id)
        return mx, my, _dirs(props.get("scroll_dir", "ALL"))

    def scroll_container_at(self, x: float, y: float, horizontal: bool) -> tuple[str, str] | None:
        """El contenedor más interno bajo el dedo que se puede desplazar en ese eje."""
        for sid, widgets in reversed(self.layers()):
            boxes = self.boxes(sid)
            chain: list[str] = []
            level = widgets
            while level:
                hit = None
                for w in reversed(level):
                    b = boxes.get(w.id)
                    if b is not None and b.shown and not b.hidden and self._inside(b, x, y):
                        hit = w
                        break
                if hit is None:
                    break
                chain.append(hit.id)
                level = hit.children
            candidates = list(reversed(chain)) + ([sid] if sid != TOP_LAYER_ID else [])
            for cid in candidates:
                mx, my, dirs = self._scrollable(cid, sid)
                if horizontal and mx > 0 and dirs & {"LEFT", "RIGHT"}:
                    return cid, sid
                if not horizontal and my > 0 and dirs & {"TOP", "BOTTOM"}:
                    return cid, sid
            if chain and sid == TOP_LAYER_ID:
                return None   # tocar un widget de la capa superior no desplaza la página
        return None

    def set_scroll(self, cid: str, screen_id: str, x: float, y: float) -> None:
        mx, my = self.scroll_range(cid, screen_id)
        self.scroll[cid] = (max(0.0, min(mx, x)), max(0.0, min(my, y)))
        self._boxes.pop(screen_id, None)

    # ----------------------------------------------------------------- impacto
    @staticmethod
    def _inside(b: Box, x: float, y: float) -> bool:
        r = b.rect
        return r.x <= x < r.right and r.y <= y < r.bottom

    def _interactive(self, w: Widget, b: Box) -> bool:
        st = b.props.get("state")
        if b.props.get("clickable") is False or (isinstance(st, dict) and st.get("disabled") is True):
            return False
        return bool(w.events) or w.type in CLICKABLE_TYPES or b.props.get("clickable") is True

    def _hit(self, widgets: list[Widget], boxes: dict[str, Box], x: float, y: float) -> Widget | None:
        for w in reversed(widgets):
            b = boxes.get(w.id)
            if b is None or not b.shown or b.hidden or not self._inside(b, x, y):
                continue
            deeper = self._hit(w.children, boxes, x, y)
            if deeper is not None:
                return deeper
            if self._interactive(w, b):
                return w
        return None

    def widget_at(self, x: float, y: float) -> Widget | None:
        for sid, widgets in reversed(self.layers()):
            hit = self._hit(widgets, self.boxes(sid), x, y)
            if hit is not None:
                return hit
        return None

    def box_of(self, wid: str) -> Box | None:
        for sid, _ in self.layers():
            b = self.boxes(sid).get(wid)
            if b is not None:
                return b
        return None

    def tab_at(self, x: float, y: float) -> tuple[str, int] | None:
        for sid, _ in reversed(self.layers()):
            for wid, b in self.boxes(sid).items():
                if not b.shown or "tab_buttons" not in b.extra:
                    continue
                for i, (r, _name, _tid) in enumerate(b.extra["tab_buttons"]):
                    if r.x <= x < r.right and r.y <= y < r.bottom:
                        return wid, i
        return None

    def container_at(self, x: float, y: float, types: set[str]) -> str | None:
        """El contenedor del tipo pedido más interno que contiene el punto."""
        found = None
        for sid, _ in self.layers():
            for wid, b in self.boxes(sid).items():
                w = self.project.widget(wid)
                if w is not None and w.type in types and b.shown and not b.hidden and self._inside(b, x, y):
                    found = wid    # los hijos aparecen después que sus padres
        return found

    def ancestors(self, wid: str) -> list[Widget]:
        out = []
        loc = self.project.locate(wid)
        while loc is not None and loc.parent is not None:
            out.append(loc.parent)
            loc = self.project.locate(loc.parent.id)
        return out

    # ----------------------------------------------------------------- eventos
    def fire(self, w: Widget, trigger: str) -> bool:
        fired = False
        for ev in list(w.events):
            if ev.trigger == trigger:
                fired = True
                self.events_fired += 1
                for a in ev.actions:
                    self.run_action(w, trigger, a)
        return fired

    def _page_ids(self) -> list[str]:
        ids = [s.id for s in self.project.screens if s.props.get("skip") is not True]
        return ids or [s.id for s in self.project.screens]

    def go_to_page(self, target: str, how: str = "lvgl.page.show") -> None:
        old = self.page_id
        if target == old:
            return
        old_scr = self.project.screen(old)
        if old_scr is not None and "on_unload" in old_scr.props:
            self.events_fired += 1
            self.log(f"[{old}.on_unload] {_describe_raw(old_scr.props['on_unload'])}")
        self.page_id = target
        self.log(f"{how} → {target}")
        self._page_entered(target)

    def _page_entered(self, page_id: str) -> None:
        scr = self.project.screen(page_id)
        if scr is not None and "on_load" in scr.props:
            self.events_fired += 1
            self.log(f"[{page_id}.on_load] {_describe_raw(scr.props['on_load'])}")

    def run_action(self, w: Widget, trigger: str, a: Action) -> None:
        all_ids = [s.id for s in self.project.screens]
        prefix = f"[{w.id}.{trigger}]"
        p = a.params
        if a.kind == "page_show":
            target = p.get("page")
            if target in all_ids:
                self.log(prefix)
                self.go_to_page(target, "lvgl.page.show")
            else:
                self.log(f"{prefix} ⚠ página inexistente: {target}")
        elif a.kind in ("page_next", "page_prev") and all_ids:
            ids = self._page_ids()
            i = ids.index(self.page_id) if self.page_id in ids else 0
            j = i + (1 if a.kind == "page_next" else -1)
            wrap = self.project.lvgl_extra.get("page_wrap", True) is not False
            if not wrap and not 0 <= j < len(ids):
                self.log(f"{prefix} no hay más páginas (page_wrap: false)")
                return
            self.log(prefix)
            self.go_to_page(ids[j % len(ids)], f"lvgl.page.{'next' if a.kind == 'page_next' else 'previous'}")
        elif a.kind == "widget_state":
            target = self.widget(p.get("id"))
            if target is None:
                self.log(f"{prefix} ⚠ widget inexistente: {p.get('id')}")
                return
            op = p.get("op")
            if op in ("show", "hide"):
                target.props = catalog.set_path(target.props, "hidden", True if op == "hide" else None)
            else:
                target.props = catalog.set_path(target.props, "state.disabled", True if op == "disable" else None)
            self._changed()
            self.log(f"{prefix} {catalog.describe_action(a.kind, p)}")
        elif a.kind == "widget_update":
            target = self.widget(p.get("id"))
            if target is None:
                self.log(f"{prefix} ⚠ widget inexistente: {p.get('id')}")
                return
            for k, v in (p.get("props") or {}).items():
                target.props = catalog.set_path(target.props, str(k), v)
            self._changed()
            self.log(f"{prefix} {catalog.describe_action(a.kind, p)}")
        else:
            self.log(f"{prefix} {catalog.describe_action(a.kind, p)}")

    # ----------------------------------------------------------------- valores
    def _range(self, w: Widget) -> tuple[int, int]:
        lo = int(catalog.prop_value(w, "min_value") or 0)
        hi = int(catalog.prop_value(w, "max_value") or 100)
        return lo, max(lo + 1, hi)

    def value_from_point(self, w: Widget, x: float, y: float) -> int | None:
        b = self.box_of(w.id)
        if b is None:
            return None
        lo, hi = self._range(w)
        r = b.rect
        if w.type == "slider":
            if r.h > r.w:
                t = 1 - (y - r.y) / max(1.0, r.h)
            else:
                t = (x - r.x) / max(1.0, r.w)
        else:  # arco: ángulo desde el inicio del fondo
            start = float(catalog.prop_value(w, "start_angle") or 135) + float(catalog.prop_value(w, "rotation") or 0)
            end = float(catalog.prop_value(w, "end_angle") or 45) + float(catalog.prop_value(w, "rotation") or 0)
            span = (end - start) % 360 or 360
            ang = math.degrees(math.atan2(y - (r.y + r.h / 2), x - (r.x + r.w / 2))) % 360
            rel = (ang - start) % 360
            if rel > span:   # fuera del arco: el extremo más cercano
                rel = span if rel - span < (360 - rel) else 0
            t = rel / span
        return int(round(lo + max(0.0, min(1.0, t)) * (hi - lo)))

    def set_value(self, w: Widget, value: int) -> None:
        w.props = catalog.set_path(w.props, "value", value)
        self._changed()

    # ----------------------------------------------------------------- reposo
    def idle_timeouts(self) -> list[tuple[float, object]]:
        raw = self.project.lvgl_extra.get("on_idle")
        items = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
        out = []
        for it in items:
            if isinstance(it, dict):
                t = parse_duration(it.get("timeout"))
                if t:
                    out.append((t, it.get("then")))
        return sorted(out, key=lambda x: x[0])

    def idle_seconds(self, now: float | None = None) -> float:
        return (now if now is not None else time.monotonic()) - self.last_activity

    def check_idle(self, now: float | None = None) -> list[float]:
        """Registra los `on_idle` cuyo plazo ha vencido. Devuelve los nuevos."""
        idle = self.idle_seconds(now)
        new = []
        for t, then in self.idle_timeouts():
            if idle >= t and t not in self.idle_fired:
                self.idle_fired.add(t)
                self.events_fired += 1
                new.append(t)
                self.log(f"[lvgl.on_idle {t:g}s] {_describe_raw(then) if then else ''}")
        return new

    def _activity(self) -> None:
        if self.idle_fired:
            self.log("actividad: termina el reposo")
        self.idle_fired.clear()
        self.last_activity = time.monotonic()

    # ----------------------------------------------------------------- puntero
    def press(self, x: float, y: float) -> bool:
        self._activity()
        self._start = (x, y)
        self.touch = (x, y)
        self.trail = [(x, y)]
        self._mode = None
        self._scroll_target = None
        self._drag_start_value = None
        tab = self.tab_at(x, y)
        if tab is not None:
            wid, i = tab
            self.active_tabs[wid] = i
            self._changed()
            self.log(f"[{wid}] pestaña {i + 1}")
            self._start = None
            return False
        w = self.widget_at(x, y)
        if w is None:
            return False
        self.pressed = w.id
        self.press_time = time.monotonic()
        self.long_fired = False
        if w.type in DRAG_TYPES and (w.type == "slider" or catalog.prop_value(w, "adjustable")):
            self._mode = "value"
            self._drag_start_value = int(catalog.prop_value(w, "value") or 0)
            v = self.value_from_point(w, x, y)
            if v is not None:
                self.set_value(w, v)
        self.fire(w, "on_press")
        return True

    def move(self, x: float, y: float) -> None:
        if self._start is None:
            return
        self.touch = (x, y)
        self.trail.append((x, y))
        if len(self.trail) > 64:
            self.trail = self.trail[-64:]
        if self._mode == "value":
            w = self.widget(self.pressed)
            if w is None or self._drag_start_value is None:
                return
            v = self.value_from_point(w, x, y)
            if v is not None and v != catalog.prop_value(w, "value"):
                self.set_value(w, v)
            return
        dx, dy = x - self._start[0], y - self._start[1]
        if self._mode is None and max(abs(dx), abs(dy)) >= SCROLL_LIMIT:
            horizontal = abs(dx) >= abs(dy)
            target = self.scroll_container_at(self._start[0], self._start[1], horizontal)
            if target is not None:
                self._mode = "scroll"
                self._scroll_target = target
                self._scroll_origin = self.scroll.get(target[0], (0.0, 0.0))
                if self.pressed:   # LVGL cancela la pulsación al empezar a desplazar
                    w = self.widget(self.pressed)
                    if w is not None:
                        self.fire(w, "on_press_lost")
                    self.pressed = None
                cw = self.widget(target[0])
                if cw is not None:
                    self.fire(cw, "on_scroll_begin")
        if self._mode == "scroll" and self._scroll_target:
            cid, sid = self._scroll_target
            ox, oy = self._scroll_origin
            self.set_scroll(cid, sid, ox - dx, oy - dy)
            cw = self.widget(cid)
            if cw is not None:
                self.fire(cw, "on_scroll")

    def long_press(self) -> None:
        w = self.widget(self.pressed)
        if w is not None and not self.long_fired and self._mode != "scroll":
            self.long_fired = True
            self.fire(w, "on_long_press")

    def long_press_repeat(self) -> None:
        w = self.widget(self.pressed)
        if w is not None and self.long_fired:
            self.fire(w, "on_long_press_repeat")

    def gesture_direction(self, start: tuple[float, float] | None, x: float, y: float) -> str | None:
        if start is None:
            return None
        dx, dy = x - start[0], y - start[1]
        if max(abs(dx), abs(dy)) < GESTURE_LIMIT:
            return None
        if abs(dx) >= abs(dy):
            return "left" if dx < 0 else "right"
        return "up" if dy < 0 else "down"

    def swipe(self, direction: str, x: float, y: float, target: Widget | None) -> None:
        """Gesto: triggers en el widget y sus antecesores, y navegación de tileview/tabview."""
        self.log(f"gesto {ARROWS[direction]} ({direction})")
        if target is None:
            under = self.container_at(x, y, set(catalog.CONTAINER_TYPES) | set(catalog.CHILD_LISTS))
            target = self.widget(under) if under else None
        chain = ([target] + self.ancestors(target.id)) if target is not None else []
        for w in chain:
            self.fire(w, "on_gesture")
            for trig in SWIPE_TRIGGERS[direction]:
                self.fire(w, trig)
        tv = self.container_at(x, y, {"tileview", "tabview"})
        if tv is None:
            return
        w = self.widget(tv)
        cur = self.active_tabs.get(tv, 0)
        if w.type == "tabview":
            nxt = cur + (1 if direction == "left" else -1 if direction == "right" else 0)
            if nxt != cur and 0 <= nxt < len(w.children):
                self.active_tabs[tv] = nxt
                self._changed()
                self.log(f"[{tv}] pestaña {nxt + 1} (deslizando)")
                self.fire(w, "on_value")
            return
        if not w.children:
            return
        cur = max(0, min(cur, len(w.children) - 1))
        tile = w.children[cur]
        drow, dcol, need = TILE_STEP[direction]
        if need not in _dirs(tile.props.get("dir", "ALL")):
            self.log(f"[{tv}] el mosaico {tile.id} no permite ir hacia {need}")
            return
        row = int(tile.props.get("row", 0) or 0) + drow
        col = int(tile.props.get("column", 0) or 0) + dcol
        for i, t in enumerate(w.children):
            if int(t.props.get("row", 0) or 0) == row and int(t.props.get("column", 0) or 0) == col:
                self.active_tabs[tv] = i
                self._changed()
                self.log(f"[{tv}] mosaico {t.id} (fila {row}, columna {col})")
                self.fire(w, "on_value")
                return

    def release(self, x: float, y: float) -> None:
        start, mode = self._start, self._mode
        self._start = None
        self._mode = None
        self.touch = None
        if mode == "scroll":
            target = self._scroll_target
            self._scroll_target = None
            cw = self.widget(target[0]) if target else None
            if cw is not None:
                self.fire(cw, "on_scroll_end")
            self.pressed = None
            return
        w = self.widget(self.pressed) if self.pressed else None
        self.pressed = None
        if mode != "value":
            direction = self.gesture_direction(start, x, y)
            if direction is not None:
                if w is not None:
                    self.fire(w, "on_release")
                self.swipe(direction, x, y, w)
                return
        if w is None:
            return
        self.fire(w, "on_release")
        if self._drag_start_value is not None:
            if catalog.prop_value(w, "value") != self._drag_start_value:
                self.log(f"[{w.id}] valor = {catalog.prop_value(w, 'value')}")
                self.fire(w, "on_value")
            self._drag_start_value = None
            return
        if self.widget_at(x, y) is not w:
            return
        if w.type in TOGGLE_TYPES or w.props.get("checkable") is True:
            self.checked ^= {w.id}
            if w.type in TOGGLE_TYPES:
                self.log(f"[{w.id}] {'activado' if w.id in self.checked else 'desactivado'}")
                self.fire(w, "on_value")
        elif w.type in CYCLE_TYPES:
            opts = w.props.get("options")
            n = len(opts) if isinstance(opts, list) else 0
            if n:
                sel = (int(catalog.prop_value(w, "selected_index") or 0) + 1) % n
                w.props = catalog.set_path(w.props, "selected_index", sel)
                self._changed()
                self.log(f"[{w.id}] opción = {opts[sel]}")
                self.fire(w, "on_value")
        elif w.type == "spinbox":
            hi = int(catalog.prop_value(w, "range_to") or 100)
            v = int(catalog.prop_value(w, "value") or 0) + 1
            if v > hi:
                v = int(catalog.prop_value(w, "range_from") or 0) if catalog.prop_value(w, "rollover") else hi
            self.set_value(w, v)
            self.log(f"[{w.id}] valor = {v}")
            self.fire(w, "on_value")
        now = time.monotonic()
        if not self.long_fired:
            self.fire(w, "on_short_click")
        self.fire(w, "on_click")
        if self._last_click and self._last_click[0] == w.id and now - self._last_click[1] <= DOUBLE_CLICK_S:
            self.fire(w, "on_double_click")
            self._last_click = None
        else:
            self._last_click = (w.id, now)

    # ----------------------------------------------------------------- utilidades
    def drag(self, x0: float, y0: float, x1: float, y1: float, steps: int = 8) -> None:
        """Arrastre completo de (x0, y0) a (x1, y1)."""
        self.press(x0, y0)
        for i in range(1, steps + 1):
            self.move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        self.release(x1, y1)
