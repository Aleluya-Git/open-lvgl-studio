"""IA generativa: extracción del YAML, bucle de corrección, integración y generador local."""
import pytest

from olvgl.application import ai
from olvgl.domain.model import DisplayProfile, Screen, Widget, new_project
from olvgl.infrastructure.esphome_importer import import_esphome_text


class FakeProvider(ai.Provider):
    name = "fake"

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def complete(self, system, messages):
        self.calls.append(messages)
        return self.answers.pop(0)


GOOD = """Aquí tienes:
```yaml
lvgl:
  pages:
    - id: main_page
      widgets:
        - button:
            id: btn_1
            x: 10
            y: 10
            width: 120
            height: 50
            widgets:
              - label: {text: Hola, align: CENTER}
            on_click:
              - lvgl.widget.hide: lbl_1
        - label:
            id: lbl_1
            x: 10
            y: 80
            text: Texto
```"""

BAD = """```yaml
pages:
  - id: p
    widgets:
      - button: {id: b, x: 900, y: 10, width: 300, height: 50}
      - gauge_magic: {id: g}
```"""


def test_extract_yaml_variants():
    assert ai.extract_yaml(GOOD).startswith("lvgl:\n  pages:")
    assert ai.extract_yaml("```\npages:\n  - id: a\n```").startswith("lvgl:\n  pages:\n    - id: a")
    assert ai.extract_yaml("```yaml\n- id: a\n  widgets: []\n```").startswith("lvgl:\n  pages:\n    - id: a")
    with pytest.raises(ai.AIError):
        ai.extract_yaml("lo siento, no puedo")


def test_generate_renames_colliding_ids():
    p = new_project("t")
    p.screens[0].widgets.append(Widget("btn_1", "button", 0, 0, 50, 50))
    p.screens[0].widgets.append(Widget("lbl_1", "label", 0, 60, None, None, props={"text": "x"}))
    res = ai.AIDesigner(FakeProvider([GOOD])).generate("algo", p)
    new_id = res.page_ids[0]
    assert new_id != "main_page" and len(res.project.screens) == len(p.screens) + 1
    page = res.project.screen(new_id)
    ids = [w.id for w in page.walk()]
    assert "btn_1" not in ids and "lbl_1" not in ids
    btn = next(w for w in page.walk() if w.type == "button")
    lbl = next(w for w in page.walk() if w.type == "label" and w.props.get("text") == "Texto")
    assert btn.events[0].actions[0].params.get("id") == lbl.id        # la referencia sigue al renombrado
    assert len(set(res.project.all_ids())) == len(list(res.project.all_ids()))
    assert p.screen(new_id) is None                                  # el proyecto original no cambia


def test_repair_loop_sends_problems_back():
    prov = FakeProvider([BAD, GOOD])
    res = ai.AIDesigner(prov).generate("algo", new_project("t"))
    assert res.attempts == 2 and not res.warnings
    feedback = prov.calls[1][-1]["content"]
    assert "se sale de la pantalla" in feedback and "gauge_magic" in feedback


def test_replace_current_page_and_refactor_keeps_page_id():
    p = new_project("t")
    pid = p.screens[0].id
    res = ai.AIDesigner(FakeProvider([GOOD])).generate("algo", p, "replace", pid)
    assert res.page_ids == [pid] and len(res.project.screens) == len(p.screens)
    assert {"btn_1", "lbl_1"} <= set(res.project.all_ids())
    res2 = ai.AIDesigner(ai.LocalProvider()).refactor("tema claro y botones rojos", res.project, pid)
    assert res2.page_ids == [pid]
    btn = res2.project.widget("btn_1")
    assert btn.props["bg_color"] == "#E53935"
    assert "tema claro" in res2.notes


@pytest.mark.parametrize("prompt", [
    "Página de luces con 6 luces y el termostato",
    "3 persianas, tema claro, color verde",
    "música y escenas con barra de navegación",
    "energía solar y consumo con la hora",
    "ajustes y seguridad",
    "4 botones",
])
@pytest.mark.parametrize("size", [(1024, 600), (480, 320)])
def test_local_generator_produces_valid_pages(prompt, size):
    p = new_project("t", DisplayProfile("x", *size))
    res = ai.AIDesigner(ai.LocalProvider()).generate(prompt, p)
    assert res.attempts == 1 and not res.warnings, res.warnings
    page = res.project.screen(res.page_ids[0])
    assert len(list(page.walk())) >= 4
    text = ai.pages_yaml(res.project, res.page_ids)
    again, rep = import_esphome_text(text, "ia.yaml", p.display)
    assert not rep.generic_types and again.screens[0].id == page.id


def test_local_generator_counts_and_entities():
    p = new_project("t")
    res = ai.AIDesigner(ai.LocalProvider()).generate("cinco luces: light.salon y light.cocina", p)
    page = res.project.screen(res.page_ids[0])
    buttons = [w for w in page.walk() if w.type == "button"]
    assert len(buttons) == 5
    ents = [a.params.get("entity_id") for b in buttons for e in b.events for a in e.actions]
    assert "light.salon" in ents and "light.cocina" in ents


def test_config_from_settings_env_override():
    class S(dict):
        def set(self, k, v):
            self[k] = v
    s = S(ai_provider="anthropic")
    cfg = ai.AIConfig.from_settings(s, env={"ANTHROPIC_API_KEY": "k"})
    assert cfg.api_key == "k" and cfg.provider == "anthropic"
    with pytest.raises(ai.AIError):
        ai.make_provider(ai.AIConfig("anthropic"))


def test_prompt_mentions_display_and_catalog():
    p = new_project("t", DisplayProfile("x", 800, 480))
    sp = ai.system_prompt(p)
    assert "800×480" in sp and "- slider:" in sp and "- button:" in sp
    assert "PÁGINAS EXISTENTES" in ai.context_text(p)
    assert isinstance(Screen, type)


def test_refactor_warns_about_references_from_other_pages():
    from olvgl.domain.model import Action, EventHandler
    p = new_project("t")
    pid = p.screens[0].id
    lbl = Widget("label_7", "label", 10, 10, None, None, props={"text": "Hora"})
    lbl.auto_id = True
    p.screens[0].widgets.append(lbl)
    other = Screen("otra", "Otra", None, [Widget("btn_x", "button", 0, 0, 80, 40, events=[
        EventHandler("on_click", [Action("widget_state", {"op": "hide", "id": "label_7"})])])])
    p.screens.append(other)
    res = ai.AIDesigner(ai.LocalProvider()).refactor("ids descriptivos", p, pid)
    assert res.project.widget("lbl_hora") is not None
    assert any("label_7" in w for w in res.warnings)
