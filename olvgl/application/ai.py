"""IA generativa (Fase 8): diseñar páginas a partir de una descripción y
refactorizarlas con instrucciones.

Flujo (igual para todos los proveedores):

1. se construye un *prompt* con las reglas de ESPHome LVGL, el catálogo de
   widgets, la pantalla y el contexto del proyecto;
2. el proveedor devuelve texto; se extrae el bloque YAML (`lvgl: pages:`);
3. se importa con el mismo importador que los YAML de los usuarios y se
   valida: widgets desconocidos, fuera de la pantalla, fuentes inexistentes,
   avisos del importador…; si hay problemas, se le pide al modelo que los
   corrija (hasta 2 veces más);
4. el resultado se integra en el proyecto con ids únicos y se aplica como un
   único cambio que se puede deshacer.

Proveedores:
- **local**: generador por plantillas, sin red ni claves. Entiende peticiones
  típicas de domótica (luces, persianas, clima, energía, música, escenas,
  ajustes, reloj, navegación…) y algunas refactorizaciones;
- **anthropic**: API de Claude;
- **openai**: cualquier API compatible con OpenAI (OpenAI, LM Studio, Ollama,
  llama.cpp server…).

Sólo se envía el diseño (YAML de LVGL y nombres de páginas, estilos, fuentes);
nunca claves de Wi‑Fi ni otras secciones del YAML del dispositivo.
"""
from __future__ import annotations

import json
import re
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from olvgl.domain import catalog
from olvgl.domain.model import (Action, DisplayProfile, EventHandler, Project, Screen, Widget,
                                is_valid_id, sanitize_id, unique_id)
from olvgl.domain.refactor import descriptive_ids, extract_styles, rename_references

PROVIDERS = {
    "local": "Generador local (sin IA, plantillas)",
    "anthropic": "Claude (Anthropic)",
    "openai": "Compatible con OpenAI (OpenAI, LM Studio, Ollama…)",
}
DEFAULT_MODEL = {"local": "", "anthropic": "claude-sonnet-5-5", "openai": ""}
DEFAULT_URL = {"anthropic": "https://api.anthropic.com/v1/messages", "openai": "http://localhost:11434/v1"}
MAX_REPAIRS = 2


class AIError(Exception):
    pass


@dataclass
class AIConfig:
    provider: str = "local"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    timeout: float = 180.0
    max_tokens: int = 8000

    @classmethod
    def from_settings(cls, settings, env: dict | None = None) -> "AIConfig":
        import os
        env = env if env is not None else dict(os.environ)
        c = cls(provider=settings.get("ai_provider", "local") or "local",
                model=settings.get("ai_model", "") or "",
                api_key=settings.get("ai_api_key", "") or "",
                base_url=settings.get("ai_base_url", "") or "")
        if not c.api_key:
            c.api_key = env.get("ANTHROPIC_API_KEY" if c.provider == "anthropic" else "OPENAI_API_KEY", "")
        return c

    def save(self, settings) -> None:
        settings.set("ai_provider", self.provider)
        settings.set("ai_model", self.model)
        settings.set("ai_api_key", self.api_key)
        settings.set("ai_base_url", self.base_url)


# --------------------------------------------------------------------------- proveedores
class Provider:
    name = ""

    def complete(self, system: str, messages: list[dict]) -> str:
        raise NotImplementedError


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 - URL configurada por el usuario
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:600]
        raise AIError(f"El servicio respondió {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise AIError(f"No se pudo conectar con {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AIError(f"Sin respuesta de {url} en {timeout:.0f} s") from exc


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, cfg: AIConfig):
        if not cfg.api_key:
            raise AIError("Falta la clave de la API de Anthropic (Configurar IA o variable ANTHROPIC_API_KEY)")
        self.cfg = cfg

    def complete(self, system: str, messages: list[dict]) -> str:
        res = _post_json(self.cfg.base_url or DEFAULT_URL["anthropic"],
                         {"model": self.cfg.model or DEFAULT_MODEL["anthropic"], "max_tokens": self.cfg.max_tokens,
                          "system": system, "messages": messages},
                         {"x-api-key": self.cfg.api_key, "anthropic-version": "2023-06-01"}, self.cfg.timeout)
        parts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        if not parts:
            raise AIError(f"Respuesta sin texto: {str(res)[:300]}")
        return "".join(parts)


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, cfg: AIConfig):
        if not cfg.model:
            raise AIError("Indica el modelo (p. ej. «qwen2.5-coder:14b» en Ollama o el de tu servicio)")
        self.cfg = cfg

    def complete(self, system: str, messages: list[dict]) -> str:
        base = (self.cfg.base_url or DEFAULT_URL["openai"]).rstrip("/")
        url = base if base.endswith("/chat/completions") else base + "/chat/completions"
        headers = {"authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        res = _post_json(url, {"model": self.cfg.model, "temperature": 0.2, "max_tokens": self.cfg.max_tokens,
                               "messages": [{"role": "system", "content": system}] + messages},
                         headers, self.cfg.timeout)
        try:
            return res["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError(f"Respuesta inesperada: {str(res)[:300]}") from exc


def make_provider(cfg: AIConfig) -> Provider:
    if cfg.provider == "anthropic":
        return AnthropicProvider(cfg)
    if cfg.provider == "openai":
        return OpenAIProvider(cfg)
    return LocalProvider()


# --------------------------------------------------------------------------- prompt
SYSTEM_RULES = """Eres un diseñador experto de interfaces LVGL para ESPHome (componente `lvgl:` de ESPHome, LVGL 9).
Respondes SIEMPRE con un único bloque ```yaml que contiene `lvgl:` → `pages:` y nada más fuera del bloque
salvo, como mucho, una frase de explicación.

Reglas:
- Pantalla de {w}×{h} px: ningún widget puede salirse. Usa x/y/width/height en píxeles o porcentajes, o
  contenedores `obj` con `layout: {{type: FLEX, flex_flow: ROW_WRAP}}` o `layout: {{type: GRID, ...}}`.
- Cada widget al que se refieran acciones lleva `id` único en snake_case (prefijos: btn_, lbl_, sw_, sl_,
  arc_, panel_…). Las páginas llevan `id`.
- Sólo estos tipos de widget y sus propiedades de ESPHome:
{catalog}
- Propiedades de estilo comunes: bg_color, bg_opa, border_color, border_width, radius, pad_all, pad_row,
  pad_column, text_color, text_font, text_align, shadow_width, shadow_color, opa; estados con
  `pressed:`, `checked:`, `disabled:`; partes con `indicator:`, `knob:`, `items:`.
- Colores como 0xRRGGBB. Fuentes: montserrat_N (N par de 10 a 48){fonts}.
- Eventos: on_click, on_press, on_release, on_long_press, on_value, on_swipe_left/right/up/down…
  Acciones: `lvgl.page.show: id`, `lvgl.page.next`, `lvgl.widget.hide: id`, `lvgl.widget.show: id`,
  `lvgl.label.update: {{id: x, text: ...}}`, `homeassistant.action: {{action: light.toggle, data: {{entity_id: light.x}}}}`,
  `delay: 1s`, `logger.log: "..."`.
- Los textos visibles en español salvo que se pida otro idioma. Diseño moderno, legible y táctil
  (botones de al menos 48 px de alto), contraste suficiente.
- No uses lambdas salvo que la petición lo exija. No añadas secciones fuera de `lvgl:`."""


def catalog_reference() -> str:
    lines = []
    for sp in catalog.ALL_SPECS:
        if sp.type in catalog.PSEUDO_TYPES or sp.type not in catalog.BUILTIN_SPECS_TYPES:
            continue
        props = ", ".join(sorted({p.name.split(".")[0] for p in sp.props if p.name != "hidden"}))
        extra = {"tabview": " (hijos en `tabs:` con name y widgets)",
                 "tileview": " (hijos en `tiles:` con row, column, dir y widgets)",
                 "buttonmatrix": " (rows: - buttons: - text: …)", "obj": " (contenedor: widgets:)",
                 "button": " (el texto va en un label hijo: widgets: - label: {text: …, align: CENTER})"}.get(sp.type, "")
        lines.append(f"  - {sp.type}: {props}{extra}")
    return "\n".join(lines)


def system_prompt(project: Project) -> str:
    d = project.display
    fonts = (" o las fuentes del proyecto: " + ", ".join(f.id for f in project.fonts)) if project.fonts else ""
    return SYSTEM_RULES.format(w=d.width, h=d.height, catalog=catalog_reference(), fonts=fonts)


def page_yaml(project: Project, page_id: str) -> str:
    """YAML (`lvgl: pages:`) de una sola página, para enviarla al modelo."""
    from olvgl.infrastructure.esphome_generator import page_node
    from olvgl.infrastructure.yaml_emitter import emit
    from olvgl.domain.yaml_ast import YMap, YSeq
    from olvgl.domain.extensions import expand_project
    p = expand_project(project)
    s = p.screen(page_id)
    if s is None:
        raise AIError(f"No existe la página «{page_id}»")
    return emit(YMap().set("lvgl", YMap().set("pages", YSeq([page_node(s)]))))


def context_text(project: Project) -> str:
    d = project.display
    parts = [f"### PANTALLA: {d.width}x{d.height}",
             "### PÁGINAS EXISTENTES: " + (", ".join(f"{s.id} («{s.name}»)" for s in project.screens) or "ninguna")]
    if project.styles:
        parts.append("### ESTILOS DISPONIBLES: " + ", ".join(s.id for s in project.styles))
    colors = project.extra_sections.get("color")
    if isinstance(colors, list) and colors:
        names = [str(c.get("id")) for c in colors if isinstance(c, dict) and c.get("id")]
        if names:
            parts.append("### COLORES CON NOMBRE: " + ", ".join(names[:30]))
    if project.screens:
        bg = next((s.bg_color for s in project.screens if s.bg_color), None)
        if bg:
            parts.append(f"### COLOR DE FONDO HABITUAL: {bg}")
    return "\n".join(parts)


# --------------------------------------------------------------------------- respuesta → páginas
_FENCE = re.compile(r"```(?:yaml|yml|YAML)?\s*\n(.*?)```", re.S)


def extract_yaml(text: str) -> str:
    """El YAML de la respuesta, normalizado a `lvgl: pages: [...]`."""
    blocks = _FENCE.findall(text or "")
    body = next((b for b in blocks if re.search(r"^\s*(lvgl:|pages:|- id:|widgets:)", b, re.M)), None)
    if body is None:
        body = blocks[0] if blocks else (text or "")
    body = textwrap.dedent(body).strip("\n")
    if re.search(r"^lvgl:", body, re.M):
        return body + "\n"
    if re.search(r"^pages:", body, re.M):
        return "lvgl:\n" + textwrap.indent(body, "  ") + "\n"
    if body.lstrip().startswith("- "):
        return "lvgl:\n  pages:\n" + textwrap.indent(body, "    ") + "\n"
    if re.search(r"^(id|widgets):", body, re.M):     # una sola página sin guion
        lines = body.splitlines()
        return "lvgl:\n  pages:\n    - " + lines[0] + "\n" + textwrap.indent("\n".join(lines[1:]), "      ") + "\n"
    raise AIError("La respuesta no contiene YAML de LVGL")


@dataclass
class DesignResult:
    project: Project                     # proyecto completo ya con el cambio
    page_ids: list[str]                  # páginas creadas o cambiadas
    yaml: str                            # YAML generado (el último intento)
    warnings: list[str] = field(default_factory=list)
    attempts: int = 1
    notes: str = ""                      # explicación del modelo, si la hay
    raw: str = ""


def parse_fragment(yaml_text: str, project: Project) -> tuple[Project, list[str]]:
    from olvgl.infrastructure.esphome_importer import import_esphome_text
    path = project.source.get("path", "") if project.source else ""
    try:
        frag, report = import_esphome_text(yaml_text, path or "ia.yaml", project.display)
    except Exception as exc:
        raise AIError(f"YAML no válido: {exc}") from exc
    problems = [w for w in report.warnings if "resolución" not in w]
    for t, n in (report.generic_types or {}).items():
        problems.append(f"tipo de widget no admitido: «{t}» ({n}); usa sólo los del catálogo")
    return frag, problems


def check_fragment(frag: Project, project: Project) -> list[str]:
    problems: list[str] = []
    if not frag.screens:
        return ["no hay ninguna página en `lvgl: pages:`"]
    d = project.display
    fonts = {f.id for f in project.fonts} | {f.id for f in frag.fonts}
    for s in frag.screens:
        for w in s.widgets:
            for a, b, lim in (("x", "width", d.width), ("y", "height", d.height)):
                pos, size = getattr(w, a), getattr(w, b)
                if isinstance(pos, int) and isinstance(size, int) and not w.props.get("align"):
                    if pos < 0 or pos + size > lim + 2:
                        problems.append(f"«{w.id}» se sale de la pantalla ({a}={pos}, {b}={size}, máximo {lim})")
        for _w in s.walk():
            f = _w.props.get("text_font")
            if isinstance(f, str) and not re.match(r"^montserrat_\d+$", f) and f not in fonts:
                problems.append(f"«{_w.id}» usa la fuente «{f}», que no existe")
    return problems


def merge_pages(project: Project, frag: Project, mode: str = "new", page_id: str | None = None,
                name: str | None = None) -> tuple[Project, list[str]]:
    """Integra las páginas generadas en una copia del proyecto con ids únicos."""
    p = project.clone()
    taken = set(p.all_ids())
    if mode == "replace" and page_id:
        old = p.screen(page_id)
        if old is not None:
            taken -= {w.id for w in old.walk()}
            taken -= {f"{w.id}_label" for w in old.walk()}
    mapping: dict[str, str] = {}
    for s in frag.screens:
        for w in s.walk():
            new = unique_id(w.id, taken) if w.id in taken else w.id
            taken.add(new)
            if w.type == "button":
                taken.add(f"{new}_label")
            if new != w.id:
                mapping[w.id] = new
    style_map: dict[str, str] = {}
    for st in frag.styles:
        existing = p.style(st.id)
        if existing is not None and existing.props == st.props:
            continue
        sid = unique_id(st.id, taken) if (existing is not None or st.id in taken) else st.id
        taken.add(sid)
        if sid != st.id:
            style_map[st.id] = sid
        p.styles.append(type(st)(sid, dict(st.props)))
    frag = rename_references(frag, mapping)
    if style_map:
        for _s, w in frag.iter_widgets():
            v = w.props.get("styles")
            if isinstance(v, str) and v in style_map:
                w.props["styles"] = style_map[v]
            elif isinstance(v, list):
                w.props["styles"] = [style_map.get(x, x) for x in v]
    for f in frag.fonts:
        if p.font(f.id) is None:
            p.fonts.append(f)
    changed: list[str] = []
    if mode == "replace" and page_id and p.screen(page_id) is not None:
        target = p.screen(page_id)
        src = frag.screens[0]
        target.widgets = src.widgets
        target.props = {k: v for k, v in src.props.items()}
        if src.bg_color:
            target.bg_color = src.bg_color
        changed.append(page_id)
    else:
        page_ids = {s.id for s in p.all_screens()}
        for i, s in enumerate(frag.screens):
            sid = s.id if is_valid_id(s.id) else "pagina"
            if sid in page_ids or sid in taken:
                sid = unique_id(sid, page_ids | taken)
            s.id = sid
            page_ids.add(sid)
            taken.add(sid)
            if name and i == 0:
                s.name = name
            elif not s.name or s.name == s.id:
                title = next((w.props.get("text") for w in s.walk() if w.type == "label"
                              and re.search(r"(titulo|title)$", w.id) and isinstance(w.props.get("text"), str)), None)
                s.name = title.strip()[:30] if title and title.strip() else re.sub(r"^(p|pg|page|pagina)_", "", re.sub(r"_\d+$", "", s.id)).replace("_", " ").capitalize()
            p.screens.append(s)
            changed.append(sid)
    return p, changed


# --------------------------------------------------------------------------- diseñador
class AIDesigner:
    def __init__(self, provider: Provider, log: Callable[[str], None] | None = None):
        self.provider = provider
        self.log = log or (lambda m: None)

    def _run(self, project: Project, user: str, finish: Callable[[Project], tuple[Project, list[str]]],
             ignore: set[str] | None = None) -> DesignResult:
        system = system_prompt(project)
        messages = [{"role": "user", "content": user}]
        last_problems: list[str] = []
        answer = ""
        for attempt in range(1, MAX_REPAIRS + 2):
            self.log(f"IA: petición {attempt} a {self.provider.name or 'local'}…")
            answer = self.provider.complete(system, messages)
            try:
                text = extract_yaml(answer)
                frag, problems = parse_fragment(text, project)
                problems += check_fragment(frag, project)
                problems = [x for x in problems if x not in (ignore or set())]
            except AIError as exc:
                text, frag, problems = "", None, [str(exc)]
            if frag is not None and not problems:
                new_project, pages = finish(frag)
                return DesignResult(new_project, pages, text, [], attempt, _notes(answer), answer)
            last_problems = problems
            self.log("IA: hay que corregir: " + "; ".join(problems[:5]))
            messages += [{"role": "assistant", "content": answer},
                         {"role": "user", "content": "El YAML tiene estos problemas:\n- " + "\n- ".join(problems[:15])
                          + "\nDevuelve el YAML completo corregido (un único bloque ```yaml con lvgl: pages:)."}]
        if frag is not None and frag.screens:
            new_project, pages = finish(frag)      # se aplica lo que hay, con avisos
            return DesignResult(new_project, pages, text, last_problems, MAX_REPAIRS + 1, _notes(answer), answer)
        raise AIError("La IA no devolvió un diseño válido: " + "; ".join(last_problems[:5]))

    def generate(self, prompt: str, project: Project, mode: str = "new", page_id: str | None = None,
                 name: str | None = None) -> DesignResult:
        if not prompt.strip():
            raise AIError("Describe la página que quieres")
        user = (f"### TAREA: generar\n{context_text(project)}\n"
                + (f"### PÁGINA QUE SE SUSTITUYE: {page_id}\n" if mode == "replace" and page_id else "")
                + f"### PETICIÓN\n{prompt.strip()}\n\nDevuelve UNA página nueva completa.")
        return self._run(project, user, lambda frag: merge_pages(project, frag, mode, page_id, name))

    def refactor(self, instruction: str, project: Project, page_id: str) -> DesignResult:
        if not instruction.strip():
            raise AIError("Escribe qué quieres cambiar")
        current = page_yaml(project, page_id)
        user = (f"### TAREA: refactorizar\n{context_text(project)}\n### PÁGINA ACTUAL ({page_id})\n"
                f"```yaml\n{current}```\n### INSTRUCCIÓN\n{instruction.strip()}\n\n"
                "Devuelve la página COMPLETA modificada, conservando los ids que no cambien y la misma `id` de página.")

        def finish(frag: Project):
            if frag.screens:
                frag.screens[0].id = page_id
            return merge_pages(project, frag, "replace", page_id)
        # lo que ya estaba mal en la página original no se le pide corregir al modelo
        try:
            orig, known = parse_fragment(current, project)
            known += check_fragment(orig, project)
        except AIError:
            known = []
        res = self._run(project, user, finish, set(known))
        res.warnings += dangling_references(project, res.project, page_id)
        return res


def dangling_references(before: Project, after: Project, page_id: str) -> list[str]:
    """Ids que desaparecen de la página pero se siguen usando en otra parte."""
    from olvgl.infrastructure.esphome_generator import generate_yaml
    old, new = before.screen(page_id), after.screen(page_id)
    if old is None or new is None:
        return []
    gone = {w.id for w in old.walk()} - set(after.all_ids())
    if not gone:
        return []
    text = generate_yaml(after)
    return [f"«{x}» ya no existe pero se sigue usando en el proyecto" for x in sorted(gone)
            if re.search(rf"(?<![\w.]){re.escape(x)}(?![\w])", text)]


def _notes(answer: str) -> str:
    rest = _FENCE.sub("", answer or "").strip()
    return rest[:600]


def page_diff(before: str, after: str) -> str:
    import difflib
    before, after = before.rstrip("\n") + "\n", after.rstrip("\n") + "\n"
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), "antes", "después", n=2))


# --------------------------------------------------------------------------- generador local
NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
           "ocho": 8, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
ROOMS = ["Salón", "Cocina", "Dormitorio", "Baño", "Comedor", "Pasillo", "Terraza", "Despacho"]
COLOR_WORDS = {"rojo": "#E53935", "azul": "#1E88E5", "verde": "#43A047", "naranja": "#FB8C00",
               "morado": "#8E24AA", "violeta": "#7C4DFF", "amarillo": "#FDD835", "rosa": "#D81B60",
               "red": "#E53935", "blue": "#1E88E5", "green": "#43A047", "orange": "#FB8C00", "purple": "#8E24AA"}
INTENTS = [
    ("lights", r"\b(luz|luces|l[aá]mpara|lights?|iluminaci[oó]n)\b"),
    ("covers", r"\b(persianas?|toldos?|cortinas?|covers?|blinds?)\b"),
    ("climate", r"\b(termostato|clima|climatizaci[oó]n|temperatura|calefacci[oó]n|aire acondicionado|thermostat)\b"),
    ("energy", r"\b(energ[ií]a|consumo|potencia|solar|kw|power|energy)\b"),
    ("media", r"\b(m[uú]sica|media|reproductor|altavoz|sonos|spotify|music|player)\b"),
    ("scenes", r"\b(escenas?|scenes?|modos?)\b"),
    ("settings", r"\b(ajustes|configuraci[oó]n|settings|interruptores|switch(es)?)\b"),
    ("clock", r"\b(reloj|hora|clock|fecha)\b"),
    ("weather", r"\b(tiempo|meteo|el clima exterior|weather|previsi[oó]n)\b"),
    ("security", r"\b(alarma|seguridad|c[aá]maras?|puerta|security)\b"),
    ("nav", r"\b(navegaci[oó]n|men[uú] inferior|barra de navegaci[oó]n|pesta[nñ]as inferiores|nav)\b"),
    ("buttons", r"\b(botones|buttons)\b"),
]


def _count_near(prompt: str, pattern: str, default: int) -> int:
    m = re.search(r"(\d+|" + "|".join(NUMBERS) + r")\s+(?:\w+\s+){0,2}?" + pattern, prompt, re.I)
    if m:
        v = m.group(1).lower()
        return max(1, min(12, int(v) if v.isdigit() else NUMBERS.get(v, default)))
    return default


def _entities(prompt: str, domain: str) -> list[str]:
    return re.findall(rf"\b{domain}\.[a-z0-9_]+\b", prompt)


class LocalProvider(Provider):
    """Diseñador por plantillas: responde con YAML como lo haría un modelo, sin red."""
    name = "local"

    def complete(self, system: str, messages: list[dict]) -> str:
        msg = messages[-1]["content"] if messages else ""
        first = messages[0]["content"] if messages else ""
        if "problemas" in msg and len(messages) > 1:
            msg = first                        # una «corrección»: se vuelve a generar
        m = re.search(r"### PANTALLA: (\d+)x(\d+)", msg)
        display = DisplayProfile("IA", int(m.group(1)), int(m.group(2))) if m else DisplayProfile()
        pages = re.search(r"### PÁGINAS EXISTENTES: (.*)", msg)
        existing = re.findall(r"(\w+) \(«(.*?)»\)", pages.group(1)) if pages else []
        if "### TAREA: refactorizar" in msg:
            return self._refactor(msg, display)
        req = re.search(r"### PETICIÓN\n(.*?)\n\nDevuelve", msg, re.S)
        prompt = req.group(1) if req else msg
        frag = local_design(prompt, display, existing)
        return "Diseño generado con plantillas locales.\n```yaml\n" + _fragment_yaml(frag) + "```"

    def _refactor(self, msg: str, display: DisplayProfile) -> str:
        from olvgl.infrastructure.esphome_importer import import_esphome_text
        y = re.search(r"### PÁGINA ACTUAL \((\w+)\)\n```yaml\n(.*?)```", msg, re.S)
        ins = re.search(r"### INSTRUCCIÓN\n(.*?)\n\nDevuelve", msg, re.S)
        if not y:
            raise AIError("Falta la página actual")
        frag, _r = import_esphome_text(y.group(2), "ia.yaml", display)
        notes = local_refactor(frag, ins.group(1) if ins else "")
        return notes + "\n```yaml\n" + _fragment_yaml(frag) + "```"


def pages_yaml(project: Project, page_ids: list[str]) -> str:
    """Las páginas indicadas (con los estilos que usan) como fragmento `lvgl:`."""
    from olvgl.domain.extensions import expand_project
    p = expand_project(project)
    frag = Project(name=p.name, display=p.display)
    frag.screens = [s for s in p.screens if s.id in page_ids]
    used = {w.props.get("styles") for s in frag.screens for w in s.walk()}
    used |= {x for s in frag.screens for w in s.walk() if isinstance(w.props.get("styles"), list)
             for x in w.props["styles"]}
    frag.styles = [st for st in p.styles if st.id in used]
    return _fragment_yaml(frag)


def _fragment_yaml(frag: Project) -> str:
    from olvgl.infrastructure.esphome_generator import page_node, _style_node
    from olvgl.infrastructure.yaml_emitter import emit
    from olvgl.domain.yaml_ast import YMap, YSeq
    lv = YMap()
    if frag.styles:
        lv.set("style_definitions", YSeq([_style_node(s.id, s.props) for s in frag.styles]))
    lv.set("pages", YSeq([page_node(s) for s in frag.screens]))
    return emit(YMap().set("lvgl", lv))


def _btn(wid, text, w, h, color, events=None, checkable=False, font="montserrat_20"):
    props = {"bg_color": color, "radius": 14, "border_width": 0, "shadow_width": 0, "text": text,
             "text_font": font, "text_color": "#FFFFFF"}
    if checkable:
        props["checkable"] = True
        props["checked"] = {"bg_color": "#FFB300", "text_color": "#1A1A1A"}
    return Widget(wid, "button", None, None, w, h, props=props, events=events or [])


def _label(wid, text, font="montserrat_16", color="#FFFFFF", **kw):
    props = {"text": text, "text_font": font, "text_color": color}
    props.update(kw)
    return Widget(wid, "label", kw.pop("x", None) if "x" in kw else None, None, None, None, props=props)


def _card(wid, w, h, children, bg="#1F1F2B", flex=None):
    props = {"bg_color": bg, "radius": 16, "border_width": 0, "pad_all": 14} if bg else \
        {"bg_opa": "TRANSP", "border_width": 0, "pad_all": 0}
    if flex:
        props["layout"] = {"type": "FLEX", "flex_flow": flex, "pad_row": 10, "pad_column": 10}
    return Widget(wid, "obj", None, None, w, h, props=props, children=children)


def local_design(prompt: str, display: DisplayProfile, existing_pages: list | None = None) -> Project:
    """Página por plantillas a partir de una descripción en español (o inglés)."""
    text = prompt.lower()
    light = bool(re.search(r"\b(claro|clara|blanco|light theme|tema claro)\b", text))
    bg, card_bg, fg = ("#F2F4F8", "#FFFFFF", "#1F2430") if light else ("#101018", "#1F1F2B", "#FFFFFF")
    sub = "#5C6475" if light else "#A8A8B8"
    track = "#DDE1E8" if light else "#2E2E3E"
    accent = next((c for k, c in COLOR_WORDS.items() if re.search(rf"\b{k}(s|es)?\b", text)), "#7C4DFF")
    intents = [k for k, pat in INTENTS if re.search(pat, text, re.I)] or ["lights"]
    W, H = display.width, display.height
    small = W < 600
    title_font = "montserrat_20" if small else "montserrat_28"
    titles = {"lights": "Luces", "covers": "Persianas", "climate": "Clima", "energy": "Energía",
              "media": "Música", "scenes": "Escenas", "settings": "Ajustes", "clock": "Inicio",
              "weather": "Tiempo", "security": "Seguridad", "nav": "Inicio", "buttons": "Controles"}
    title = titles[intents[0]]
    page_id = sanitize_id(f"p_{title}", "pagina")
    margin = 12 if small else 20
    top = 56 if small else 72
    nav_h = 64 if "nav" in intents and existing_pages else 0
    content_w, content_h = W - 2 * margin, H - top - margin - nav_h
    cols = 2 if small else 3
    cw = int((content_w - (cols - 1) * 12) / cols)
    ch = 120 if small else 150
    cards: list[Widget] = []
    used: set[str] = set()

    def uid(base: str) -> str:
        new = unique_id(base, used)
        used.add(new)
        return new

    for intent in intents:
        if intent == "lights":
            n = _count_near(text, r"(luz|luces|l[aá]mparas?|lights?|botones)", 4)
            ents = _entities(prompt, "light")
            for i in range(max(n, len(ents))):
                name = ents[i].split(".", 1)[1].replace("_", " ").capitalize() if i < len(ents) else ROOMS[i % len(ROOMS)]
                ent = ents[i] if i < len(ents) else f"light.{sanitize_id(name)}"
                bid = uid(f"btn_luz_{sanitize_id(name)}")
                cards.append(_btn(bid, name, cw, ch // 2 + 30, card_bg if not light else "#E3E7EF", [EventHandler(
                    "on_click", [Action("ha_action", {"action": "light.toggle", "entity_id": ent})])], checkable=True))
                cards[-1].props["text_color"] = fg
        elif intent == "covers":
            n = _count_near(text, r"(persianas?|toldos?|cortinas?|covers?|blinds?)", 2)
            ents = _entities(prompt, "cover")
            bw = max(56, min(90, (cw - 28 - 16) // 3))
            for i in range(max(n, len(ents))):
                if i < len(ents):
                    ent, name = ents[i], ents[i].split(".", 1)[1].replace("_", " ").capitalize()
                else:
                    name = ROOMS[i % len(ROOMS)]
                    ent = f"cover.{sanitize_id(name)}"
                sid = sanitize_id(name)
                pct = uid(f"lbl_persiana_{sid}_pos")
                row = _card(uid(f"fila_persiana_{sid}"), "100%", 40, [
                    _btn(uid(f"btn_{verb}_{sid}"), label, bw, 36, accent, [EventHandler("on_click", [Action(
                        "ha_action", {"action": f"cover.{svc}", "entity_id": ent})])], font="montserrat_14")
                    for verb, label, svc in (("subir", "Subir", "open_cover"), ("parar", "Parar", "stop_cover"),
                                             ("bajar", "Bajar", "close_cover"))], None, "ROW")
                row.props.update({"bg_opa": "TRANSP", "pad_all": 0, "align": "LEFT_MID", "y": -4})
                cards.append(_card(uid(f"panel_persiana_{sid}"), cw, ch, [
                    _label(uid(f"lbl_persiana_{sid}"), f"Persiana {name.lower()}" if i >= len(ents) else name,
                           "montserrat_16", fg),
                    _label(pct, "50 %", "montserrat_16", sub, align="TOP_RIGHT"),
                    row,
                    Widget(uid(f"sl_persiana_{sid}"), "slider", None, None, "100%", 12,
                           props={"value": 50, "align": "BOTTOM_MID", "bg_color": track,
                                  "indicator": {"bg_color": accent}, "knob": {"bg_color": "#FFFFFF"}},
                           events=[EventHandler("on_value", [Action("raw", {"yaml": (
                               f"lvgl.label.update:\n  id: {pct}\n  text: !lambda return str_sprintf(\"%d %%\", (int) x);")})]),
                                   EventHandler("on_release", [Action("raw", {"yaml": (
                               f"homeassistant.action:\n  action: cover.set_cover_position\n  data:\n"
                               f"    entity_id: {ent}\n    position: !lambda return x;")})])]),
                ], card_bg))
        elif intent == "climate":
            arc = Widget(uid("arc_consigna"), "arc", None, None, 130 if not small else 100, 130 if not small else 100,
                         props={"min_value": 15, "max_value": 30, "value": 21, "adjustable": True, "align": "CENTER",
                                "indicator": {"arc_color": "#FF7043"}, "knob": {"bg_color": "#FFFFFF"}})
            cards.append(_card(uid("panel_clima"), cw, ch + 60, [
                _label(uid("lbl_clima_titulo"), "Termostato", "montserrat_16", sub),
                arc,
                _label(uid("lbl_consigna"), "21 °C", "montserrat_24", fg, align="CENTER"),
            ], card_bg))
        elif intent == "energy":
            for name, val, unit, color in (("Consumo", "1.2", "kW", "#FFB300"), ("Solar", "2.8", "kW", "#43A047")):
                sid = sanitize_id(name)
                cards.append(_card(uid(f"panel_{sid}"), cw, ch, [
                    _label(uid(f"lbl_{sid}_titulo"), name, "montserrat_16", sub),
                    _label(uid(f"lbl_{sid}"), f"{val} {unit}", "montserrat_28", fg, align="LEFT_MID"),
                    Widget(uid(f"bar_{sid}"), "bar", None, None, "100%", 10,
                           props={"value": 40, "align": "BOTTOM_MID", "indicator": {"bg_color": color}}),
                ], card_bg))
        elif intent == "media":
            ctrl = [_btn(uid(f"btn_{k}"), t, 64 if small else 80, 48, accent, [EventHandler("on_click", [Action(
                "ha_action", {"action": f"media_player.{k}", "entity_id": "media_player.salon"})])])
                for k, t in (("media_previous_track", "<<"), ("media_play_pause", "Play"), ("media_next_track", ">>"))]
            cards.append(_card(uid("panel_musica"), min(content_w, cw * 2 + 12), ch + 30, [
                _label(uid("lbl_cancion"), "Reproduciendo", "montserrat_20", fg),
                _card(uid("fila_controles"), "100%", 70, ctrl, None, "ROW"),
                Widget(uid("sl_volumen"), "slider", None, None, "100%", 12,
                       props={"value": 40, "align": "BOTTOM_MID", "bg_color": track,
                              "indicator": {"bg_color": accent}}),
            ], card_bg))
            cards[-1].children[1].props.update({"bg_opa": "TRANSP", "pad_all": 0, "align": "CENTER"})
        elif intent == "scenes":
            for name in ("Cine", "Cena", "Noche", "Apagar todo"):
                sid = sanitize_id(name)
                cards.append(_btn(uid(f"btn_escena_{sid}"), name, cw, 64, accent, [EventHandler("on_click", [Action(
                    "ha_action", {"action": "scene.turn_on", "entity_id": f"scene.{sid}"})])]))
        elif intent == "settings":
            rows = []
            for name in ("Modo noche", "Sonidos", "Brillo automático"):
                sid = sanitize_id(name)
                rows.append(_card(uid(f"fila_{sid}"), "100%", 52, [
                    _label(uid(f"lbl_{sid}"), name, "montserrat_16", fg, align="LEFT_MID"),
                    Widget(uid(f"sw_{sid}"), "switch", None, None, 60, 30, props={"align": "RIGHT_MID",
                                                                                 "indicator": {"checked": {"bg_color": accent}}}),
                ], card_bg))
                rows[-1].props.update({"pad_all": 8})
            cards += rows
            cards.append(_card(uid("panel_brillo"), "100%", 70, [
                _label(uid("lbl_brillo"), "Brillo de la pantalla", "montserrat_16", fg),
                Widget(uid("sl_brillo"), "slider", None, None, "100%", 12,
                       props={"value": 80, "align": "BOTTOM_MID", "indicator": {"bg_color": accent}}),
            ], card_bg))
        elif intent == "weather":
            cards.append(_card(uid("panel_tiempo"), cw, ch, [
                _label(uid("lbl_tiempo_titulo"), "Exterior", "montserrat_16", sub),
                _label(uid("lbl_tiempo_temp"), "18 °C", "montserrat_36" if not small else "montserrat_28", fg,
                       align="LEFT_MID"),
                _label(uid("lbl_tiempo_estado"), "Parcialmente nublado", "montserrat_14", sub, align="BOTTOM_LEFT"),
            ], card_bg))
        elif intent == "security":
            cards.append(_card(uid("panel_alarma"), cw, ch, [
                _label(uid("lbl_alarma"), "Alarma", "montserrat_16", sub),
                _label(uid("lbl_alarma_estado"), "Desarmada", "montserrat_24", fg, align="LEFT_MID"),
                _btn(uid("btn_armar"), "Armar", 110, 44, "#E53935", [EventHandler("on_click", [Action(
                    "ha_action", {"action": "alarm_control_panel.alarm_arm_away",
                                  "entity_id": "alarm_control_panel.casa"})])], font="montserrat_16"),
            ], card_bg))
            cards[-1].children[-1].props["align"] = "BOTTOM_RIGHT"
        elif intent == "buttons":
            n = _count_near(text, r"botones|buttons", 4)
            for i in range(n):
                cards.append(_btn(uid(f"btn_{i + 1}"), f"Botón {i + 1}", cw, 64, accent))
    header = [_label("lbl_titulo", title, title_font, fg)]
    header[0].x, header[0].y = margin, (top - (28 if not small else 22)) // 2
    if "clock" in intents or "climate" in intents or "weather" in intents:
        clock = _label("lbl_hora", "12:34", title_font, fg, align="TOP_RIGHT")
        clock.x, clock.y = -margin, header[0].y
        header.append(clock)
    content = Widget("panel_contenido", "obj", margin, top, content_w, content_h,
                     props={"bg_opa": "TRANSP", "border_width": 0, "pad_all": 0,
                            "layout": {"type": "FLEX", "flex_flow": "ROW_WRAP", "pad_row": 12, "pad_column": 12}},
                     children=cards)
    widgets = header + [content]
    if nav_h:
        pages = [(e, e) if isinstance(e, str) else e for e in (existing_pages or [])][:5]
        btns = [_btn(f"btn_nav_{sanitize_id(pid)}", (pname or pid)[:14], None, 48, card_bg,
                     [EventHandler("on_click", [Action("page_show", {"page": pid})])], font="montserrat_16")
                for pid, pname in pages]
        for b in btns:
            b.props["flex_grow"] = 1
        widgets.append(Widget("panel_nav", "obj", 0, H - nav_h, W, nav_h,
                              props={"bg_color": card_bg, "radius": 0, "border_width": 0, "pad_all": 8,
                                     "layout": {"type": "FLEX", "flex_flow": "ROW", "pad_column": 8}},
                              children=btns))
    for w in (x for top in widgets for x in top.walk()):
        if w.type in ("slider", "bar") and "bg_color" not in w.props:
            w.props["bg_color"] = track          # pista neutra (no el azul por defecto)
    p = Project(name="IA", display=display)
    p.screens = [Screen(page_id, title, bg, widgets)]
    return p


def local_refactor(frag: Project, instruction: str) -> str:
    """Refactorizaciones que el generador local sabe hacer sobre la página."""
    t = instruction.lower()
    done = []
    s = frag.screens[0] if frag.screens else None
    if s is None:
        return "Página vacía."
    widgets = list(s.walk())
    in_button = {c.id for w in widgets if w.type == "button" for c in w.children}
    if re.search(r"\b(oscuro|oscura|dark)\b", t):
        s.bg_color = "#101018"
        for w in widgets:
            if w.type == "label" and w.id not in in_button:
                w.props["text_color"] = "#FFFFFF"
            if w.type == "obj" and w.props.get("bg_opa") != "TRANSP":
                w.props["bg_color"] = "#1F1F2B"
        done.append("tema oscuro")
    if re.search(r"\b(claro|clara|light)\b", t):
        s.bg_color = "#F2F4F8"
        for w in widgets:
            if w.type == "label" and w.id not in in_button:
                w.props["text_color"] = "#1F2430"
            if w.type == "obj" and w.props.get("bg_opa") != "TRANSP":
                w.props["bg_color"] = "#FFFFFF"
        done.append("tema claro")
    if re.search(r"\b(grande|grandes|agranda|mayor|bigger|larger)\b", t):
        for w in widgets:
            f = w.props.get("text_font")
            m = re.match(r"montserrat_(\d+)$", str(f or ""))
            if m:
                w.props["text_font"] = f"montserrat_{min(48, int(m.group(1)) + 4)}"
            elif w.type in ("label", "button"):
                w.props["text_font"] = "montserrat_18"
        done.append("textos más grandes")
    if re.search(r"\b(redonde|radio|rounded)", t):
        for w in widgets:
            if w.type in ("obj", "button"):
                w.props["radius"] = 18
        done.append("esquinas redondeadas")
    color = next((c for k, c in COLOR_WORDS.items() if re.search(rf"\b{k}(s|es)?\b", t)), None)
    if color:
        for w in widgets:
            if w.type == "button":
                w.props["bg_color"] = color
                w.props["text_color"] = "#FFFFFF"
                for c in w.children:
                    if c.type == "label":
                        c.props["text_color"] = "#FFFFFF"
        done.append("color de los botones")
    if re.search(r"\b(estilos?|styles?)\b", t):
        new, rep = extract_styles(frag, min_widgets=2)
        frag.screens, frag.styles = new.screens, new.styles
        done.append(f"{len(rep.styles_created)} estilo(s) compartido(s)")
    if re.search(r"\b(ids?|nombres?|renombra)\b", t):
        new, rep = descriptive_ids(frag)
        frag.screens = new.screens
        done.append(f"{len(rep.renamed)} id(s) descriptivos")
    if not done:
        return ("El generador local no entiende esta instrucción (sabe: tema oscuro/claro, textos más grandes, "
                "redondear, color de los botones, estilos, ids). Configura un proveedor de IA para instrucciones libres.")
    return "Cambios: " + ", ".join(done) + "."


def summarize(result: DesignResult) -> str:
    n = sum(len(list(result.project.screen(p).walk())) for p in result.page_ids if result.project.screen(p))
    return f"{len(result.page_ids)} página(s), {n} widgets, {result.attempts} intento(s)"


def provider_label(code: str) -> str:
    return PROVIDERS.get(code, code)


def json_safe(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))
