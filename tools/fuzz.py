"""Pruebas masivas (Fase 9): sesiones de edición aleatorias y comprobación de invariantes.

    python tools/fuzz.py --sessions 300 --steps 60 [--seed 1] [--c]

Cada sesión parte de un proyecto nuevo y hace operaciones al azar con el
ViewModel (como un usuario): añadir widgets de todos los tipos (también dentro
de contenedores, pestañas y mosaicos), cambiar propiedades con valores válidos
del catálogo, eventos con todas las acciones, mover, redimensionar, duplicar,
copiar/pegar, eliminar, alinear, páginas, estilos, tema, renombrar, deshacer y
rehacer. Cada pocos pasos se comprueba:

- ids únicos;
- el YAML generado se analiza sin error;
- importar ese YAML y volver a generarlo da exactamente el mismo texto;
- guardar en JSON y volver a abrir da el mismo proyecto;
- el código C se genera (y, con --c, compila con gcc si hay cabeceras de LVGL);
- la disposición (layout) se calcula sin error.

Al final, deshacer todo devuelve el proyecto inicial y rehacer todo el final.
Un fallo se guarda en fuzz_fallos/<semilla>.json con la secuencia que lo produce.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import tempfile
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from olvgl.application.viewmodel import ProjectViewModel  # noqa: E402
from olvgl.domain import catalog  # noqa: E402
from olvgl.domain.model import Action, DisplayProfile, EventHandler  # noqa: E402
from olvgl.infrastructure import json_store  # noqa: E402
from olvgl.infrastructure.esphome_generator import generate_yaml  # noqa: E402
from olvgl.infrastructure.esphome_importer import import_esphome_file, import_esphome_text  # noqa: E402
from olvgl.infrastructure.sync_adapters import make_session  # noqa: E402
from olvgl.infrastructure.yaml_parser import parse  # noqa: E402

DISPLAYS = [(1024, 600), (800, 480), (480, 320), (320, 240), (480, 480), (720, 1280)]
WORDS = ["Salón", "Cocina", "Luz", "ON", "OFF", "Temp: 21 °C", "50 %", "a: b", "#1", "'x'", '"y"',
         "Ñandú", "línea 1\nlínea 2", "{x}", "- guion", "yes", "no", "null", "~", "1.5", "0x10",
         "@arroba", "árbol & más", "€ 3,50", "!tag", "* estrella", "a #comentario", "  espacios  "]


def make_vm() -> ProjectViewModel:
    vm = ProjectViewModel(generator=generate_yaml, saver=json_store.save_project,
                          loader=json_store.load_project, importer=import_esphome_file,
                          sync_factory=make_session)
    vm.measure_text = lambda text, font, width=None: (8.0 * max(1, len(str(text))), 16.0)
    vm.image_size = lambda path: (64, 64)
    return vm


class Fuzzer:
    def __init__(self, seed: int, steps: int, compile_c: bool = False):
        self.rnd = random.Random(seed)
        self.seed = seed
        self.steps = steps
        self.compile_c = compile_c
        self.log: list[str] = []
        w, h = self.rnd.choice(DISPLAYS)
        self.vm = make_vm()
        self.vm.new("Fuzz", DisplayProfile("fuzz", w, h))
        self.initial = self.vm.project.to_dict()
        self.types = [sp.type for sp in catalog.palette_specs()]

    # ------------------------------------------------------------ valores
    def text(self) -> str:
        r = self.rnd.random()
        if r < 0.6:
            return self.rnd.choice(WORDS)
        return "".join(self.rnd.choice(string.ascii_letters + " áéíóúñ:#-'\"") for _ in range(self.rnd.randint(0, 12)))

    def color(self) -> str:
        return "#%06X" % self.rnd.randrange(0x1000000)

    def value_for(self, p: catalog.PropSpec, wid: str):
        k = p.kind
        if k == catalog.KIND_INT:
            lo, hi = p.minimum, min(p.maximum, 2000)
            return self.rnd.randint(lo, max(lo, hi))
        if k in (catalog.KIND_STR, catalog.KIND_TEXT):
            if p.options:
                return self.rnd.choice(p.options)
            return self.text()
        if k == catalog.KIND_COLOR:
            return self.color()
        if k == catalog.KIND_BOOL:
            return self.rnd.random() < 0.5
        if k == catalog.KIND_ENUM:
            return self.rnd.choice(p.options) if p.options else None
        if k == catalog.KIND_LINES:
            return [self.text() or "x" for _ in range(self.rnd.randint(1, 4))]
        if k == catalog.KIND_WIDGET:
            ids = [i for i in self.vm.project.all_ids() if i != wid]
            return self.rnd.choice(ids) if ids else None
        return None                       # imágenes: no hay ficheros en la prueba

    def action(self) -> Action:
        ids = list(self.vm.project.all_ids()) or ["x"]
        pages = [s.id for s in self.vm.project.screens]
        kind = self.rnd.choice(["page_show", "page_next", "page_prev", "ha_action", "logger", "widget_state",
                                "widget_update", "delay", "lambda", "raw"])
        if kind == "page_show":
            return Action(kind, {"page": self.rnd.choice(pages)})
        if kind in ("page_next", "page_prev"):
            return Action(kind, {})
        if kind == "ha_action":
            return Action(kind, {"action": self.rnd.choice(["light.toggle", "switch.turn_on", "script.turn_on"]),
                                 "entity_id": self.rnd.choice(["light.salon", "switch.bomba", "script.x"])})
        if kind == "logger":
            return Action(kind, {"message": self.text()})
        if kind == "widget_state":
            return Action(kind, {"op": self.rnd.choice(["show", "hide", "enable", "disable"]),
                                 "id": self.rnd.choice(ids)})
        if kind == "widget_update":
            return Action(kind, {"type": "label", "id": self.rnd.choice(ids), "props": {"text": self.text() or "t"}})
        if kind == "delay":
            return Action(kind, {"duration": self.rnd.choice(["100ms", "1s", "2s"])})
        if kind == "lambda":
            return Action(kind, {"code": self.rnd.choice(['ESP_LOGD("x", "hola");', "id(x).turn_on();\nreturn;"])})
        return Action("raw", {"yaml": self.rnd.choice(["script.execute: s1", "light.turn_off: light.x",
                                                       "lvgl.widget.redraw:"])})

    # ------------------------------------------------------------ operaciones
    def widgets(self):
        return [w for _s, w in self.vm.project.iter_widgets()]

    def pick_widget(self):
        ws = self.widgets()
        return self.rnd.choice(ws) if ws else None

    def op(self) -> str:
        vm, rnd = self.vm, self.rnd
        r = rnd.random()
        w = self.pick_widget()
        if r < 0.25 or w is None:
            t = rnd.choice(self.types)
            parent = None
            containers = [x for x in self.widgets() if x.type in ("obj", "tab", "tile", "button")]
            if containers and rnd.random() < 0.4:
                parent = rnd.choice(containers)
                loc = vm.project.locate(parent.id)
                vm.set_current_screen(loc.screen.id)
            wid = vm.add_widget(t, rnd.randint(0, 900), rnd.randint(0, 500), parent_id=parent.id if parent else None)
            return f"add {t} {wid} en {parent.id if parent else '-'}"
        if r < 0.50:
            sp = catalog.spec(w.type)
            props = [p for p in sp.props if p.kind != catalog.KIND_IMAGE]
            if not props:
                return "noop"
            p = rnd.choice(props)
            v = self.value_for(p, w.id)
            if v is None:
                return "noop"
            vm.set_prop([w.id], p.name, v)
            return f"prop {w.id}.{p.name}={v!r}"
        if r < 0.58:
            evs = catalog.spec(w.type).events or ("on_click",)
            handlers = [EventHandler(rnd.choice(evs), [self.action() for _ in range(rnd.randint(1, 3))])
                        for _ in range(rnd.randint(1, 2))]
            vm.set_events(w.id, handlers)
            return f"events {w.id}"
        if r < 0.64 and w.x is not None:
            vm.set_geometry(w.id, (rnd.randint(-50, 900), rnd.randint(-50, 500), rnd.randint(1, 400), rnd.randint(1, 300)))
            return f"geom {w.id}"
        if r < 0.68:
            vm.set_selection([w.id])
            new = vm.duplicate()
            return f"dup {w.id} -> {new}"
        if r < 0.71:
            vm.set_selection([w.id])
            vm.copy()
            vm.paste()
            return f"copy/paste {w.id}"
        if r < 0.76:
            vm.delete_widgets([w.id])
            return f"del {w.id}"
        if r < 0.79:
            ws = [x.id for x in self.widgets()]
            vm.set_selection(rnd.sample(ws, min(len(ws), 3)))
            vm.align(rnd.choice(["left", "right", "top", "bottom", "hcenter", "vcenter"]))
            return "align"
        if r < 0.81:
            vm.set_selection([w.id])
            vm.change_order(rnd.choice(["front", "back", "forward", "backward"]))
            return "order"
        if r < 0.83:
            sid = vm.add_screen(self.text() or "P")
            vm.set_current_screen(sid)
            return f"screen+ {sid}"
        if r < 0.84 and len(vm.project.screens) > 1:
            sid = rnd.choice(vm.project.screens).id
            vm.remove_screen(sid)
            return f"screen- {sid}"
        if r < 0.86:
            sid = vm.add_style("estilo")
            vm.set_style_props(sid, {"bg_color": self.color(), "radius": rnd.randint(0, 30)})
            vm.set_widget_styles(w.id, [sid])
            return f"style {sid} -> {w.id}"
        if r < 0.87:
            vm.set_theme_props(rnd.choice(self.types), {"text_color": self.color()})
            return "theme"
        if r < 0.89:
            new = f"w_{rnd.randint(0, 999)}"
            err = vm.rename_widget(w.id, new)
            return f"rename {w.id}->{new} {err or ''}"
        if r < 0.90 and w.type in ("tabview", "tileview"):
            return f"child {vm.add_child(w.id)}"
        if r < 0.95:
            vm.undo()
            return "undo"
        vm.redo()
        return "redo"

    # ------------------------------------------------------------ invariantes
    def check(self) -> None:
        p = self.vm.project
        ids = list(p.all_ids())
        assert len(ids) == len(set(ids)), f"ids repetidos: {sorted(i for i in ids if ids.count(i) > 1)[:5]}"
        text = generate_yaml(p)
        parse(text, "fuzz.yaml")
        again, rep = import_esphome_text(text, "fuzz.yaml", p.display)
        text2 = generate_yaml(again)
        if text2 != text:
            import difflib
            d = "".join(list(difflib.unified_diff(text.splitlines(True), text2.splitlines(True), n=1))[:40])
            raise AssertionError("YAML no idempotente:\n" + d)
        assert not rep.generic_types, rep.generic_types
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.olvgl")
            json_store.save_project(p, path)
            loaded = json_store.load_project(path)
            a, b = p.to_dict(), loaded.to_dict()
            a.pop("source", None), b.pop("source", None)
            assert a == b, "JSON no conserva el proyecto"
        from olvgl.infrastructure.lvgl_c_generator import generate_c
        out = generate_c(p)
        if self.compile_c:
            compile_c(out.source, out.header, self.seed)
        for s in p.screens:
            self.vm.layout(s.id)

    def run(self) -> None:
        for i in range(self.steps):
            self.log.append(self.op())
            if i % 5 == 4 or i == self.steps - 1:
                self.check()
        final = self.vm.project.to_dict()
        n = 0
        while self.vm.undo():
            n += 1
        assert self.vm.project.to_dict() == self.initial, "deshacer todo no devuelve el proyecto inicial"
        for _ in range(n):
            self.vm.redo()
        assert self.vm.project.to_dict() == final, "rehacer todo no devuelve el proyecto final"


def compile_c(source: str, header: str, seed: int) -> None:
    """Compila ui.c con gcc si están las cabeceras de LVGL (OLVGL_LVGL_INC)."""
    import shutil
    import subprocess
    inc = os.environ.get("OLVGL_LVGL_INC")
    if not inc or not shutil.which("gcc"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "ui.c"), "w", encoding="utf-8") as f:
            f.write(source)
        with open(os.path.join(tmp, "ui.h"), "w", encoding="utf-8") as f:
            f.write(header)
        args = ["gcc", "-std=c99", "-fsyntax-only", "-Wall", "-Werror", "-Wno-unused-function"]
        for d in inc.split(os.pathsep):
            args += ["-I", d]
        res = subprocess.run(args + [os.path.join(tmp, "ui.c")], capture_output=True, text=True)
        if res.returncode:
            raise AssertionError("gcc:\n" + res.stderr[-2500:])


def run_session(seed: int, steps: int, compile_c: bool = False) -> dict | None:
    fz = Fuzzer(seed, steps, compile_c)
    try:
        fz.run()
        return None
    except Exception as exc:
        return {"seed": seed, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=6),
                "steps": fz.log}


# --------------------------------------------------------------------------- YAML dañado
CORPUS = [os.path.join(ROOT, "examples", "importar", "panel_demo.yaml"),
          os.path.join(ROOT, "examples", "panel-domotica_final.yaml")]
ALLOWED = ("YamlParseError", "ImportError_")


def mutate(text: str, rnd: random.Random) -> str:
    lines = text.splitlines()
    for _ in range(rnd.choice([1, 1, 1, 2, 3])):
        if not lines:
            break
        i = rnd.randrange(len(lines))
        r = rnd.random()
        if r < 0.2:
            del lines[i]
        elif r < 0.35:
            lines.insert(i, lines[rnd.randrange(len(lines))])
        elif r < 0.5:
            lines[i] = " " * rnd.choice([1, 2, 3, 4]) + lines[i]
        elif r < 0.6:
            lines[i] = lines[i].lstrip()
        elif r < 0.7:
            k = rnd.randrange(len(lines[i]) + 1)
            lines[i] = lines[i][:k] + rnd.choice([":", "- ", "#", "'", '"', "{", "[", "!", "&a", "*a", "\t", "%"]) + lines[i][k:]
        elif r < 0.8:
            lines[i] = lines[i].split(":")[0] + ": " + rnd.choice(["", "[]", "{}", "~", "-1", "0x", "999999999999",
                                                                   "!lambda return 1;", "[1, [2]]", "{a: {b: c}}", "yes"])
        elif r < 0.9:
            j = rnd.randrange(len(lines))
            lines[i], lines[j] = lines[j], lines[i]
        else:
            lines = lines[:i]
    return "\n".join(lines) + "\n"


def yaml_fuzz(n: int, seed: int = 1) -> list[dict]:
    rnd = random.Random(seed)
    sources = [open(p, encoding="utf-8").read() for p in CORPUS if os.path.exists(p)]
    fails = []
    stats = {"importados": 0, "rechazados": 0}
    for k in range(n):
        text = mutate(rnd.choice(sources), rnd)
        try:
            proj, rep = import_esphome_text(text, "mut.yaml", None)
            stats["importados"] += 1
            out = generate_yaml(proj)                          # lo importado debe poder generarse
            parse(out, "out.yaml")
            again, _ = import_esphome_text(out, "out.yaml", proj.display)
            if generate_yaml(again) != out:
                raise AssertionError("YAML no idempotente tras importar un YAML dañado")
        except Exception as exc:
            if type(exc).__name__ in ALLOWED:
                stats["rechazados"] += 1
                continue
            fails.append({"case": k, "error": f"{type(exc).__name__}: {exc}"[:300],
                          "trace": traceback.format_exc(limit=8), "yaml": text})
    YAML_STATS.update(stats)
    return fails


YAML_STATS: dict[str, int] = {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=200)
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--c", action="store_true", help="compilar el C con gcc (OLVGL_LVGL_INC)")
    ap.add_argument("--out", default=os.path.join(ROOT, "fuzz_fallos"))
    ap.add_argument("--yaml", type=int, default=0, help="además, N YAML dañados para el importador")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    fails = []
    if a.yaml:
        for i, f in enumerate(yaml_fuzz(a.yaml, a.seed)):
            f["seed"] = f"yaml_{i}"
            fails.append(f)
            os.makedirs(a.out, exist_ok=True)
            with open(os.path.join(a.out, f"yaml_{i}.json"), "w", encoding="utf-8") as fh:
                json.dump(f, fh, ensure_ascii=False, indent=1)
    for s in range(a.seed, a.seed + a.sessions):
        f = run_session(s, a.steps, a.c)
        if f:
            fails.append(f)
            os.makedirs(a.out, exist_ok=True)
            with open(os.path.join(a.out, f"{s}.json"), "w", encoding="utf-8") as fh:
                json.dump(f, fh, ensure_ascii=False, indent=1)
    secs = time.monotonic() - t0
    kinds: dict[str, int] = {}
    for f in fails:
        key = f["error"].splitlines()[0][:120]
        kinds[key] = kinds.get(key, 0) + 1
    print(json.dumps({"sessions": a.sessions, "steps": a.steps, "failures": len(fails), "seconds": round(secs, 1),
                      "yaml": YAML_STATS,
                      "kinds": kinds}, ensure_ascii=False, indent=1))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
