"""Fase 7: SDK de plugins (los tres de ejemplo, aislamiento de errores, plantilla)."""
import json
import os

import pytest
import yaml

from olvgl.application.plugins import BUILTIN_DIR, PluginManager, create_plugin
from olvgl.domain import catalog
from olvgl.domain.extensions import REGISTRY, expand_project, validate
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_text
from olvgl.infrastructure.lvgl_c_generator import generate_c


@pytest.fixture
def manager(tmp_path):
    m = PluginManager([(BUILTIN_DIR, "integrado"), (str(tmp_path / "user"), "usuario")])
    os.makedirs(tmp_path / "user", exist_ok=True)
    m.load_all()
    yield m
    for pid in list(m.plugins):
        m.unload(pid)
    assert "sensor_card" not in catalog.CATALOG       # nada se queda registrado


def test_examples_load(manager):
    p = manager.plugins
    assert {"tarjeta_sensor", "exportador_markdown", "reglas_ux"} <= set(p)
    assert all(i.loaded and not i.error for i in p.values()), {k: i.error for k, i in p.items()}
    assert "sensor_card" in catalog.CATALOG and "Plugins" in catalog.CATEGORIES
    assert {"exportador_markdown.markdown", "exportador_markdown.csv"} <= set(REGISTRY.exporters)
    assert "reglas_ux.agrandar" in REGISTRY.commands


def test_plugin_widget_expands_to_valid_esphome_and_c(manager, vm):
    card = vm.add_widget("sensor_card", 40, 40, centered=False)
    vm.set_prop([card], "value", "23.4")
    w = vm.widget(card)
    assert w.props["title"] == "Temperatura" and (w.width, w.height) == (220, 110)
    text = generate_yaml(vm.project)
    assert "sensor_card" not in text                     # ESPHome sólo ve widgets estándar
    data = yaml.safe_load(text)
    obj = data["lvgl"]["pages"][0]["widgets"][0]["obj"]
    assert obj["id"] == card and len(obj["widgets"]) == 4
    assert any(x.get("label", {}).get("text") == "23.4" for x in obj["widgets"])
    project, report = import_esphome_text(text, "x.yaml")      # vuelve a importarse sin avisos
    assert not [x for x in report.warnings if "reconoc" in x]
    src = generate_c(vm.project).source
    assert f"ui_{card}_value" in src and "lv_label_create" in src
    assert vm.widget(card).type == "sensor_card"          # el diseño conserva el widget de plugin


def test_exporters(manager, vm, tmp_path, demo_path):
    vm.import_yaml(demo_path)
    md = manager.export("exportador_markdown.markdown", vm.project, str(tmp_path))
    text = open(md[0], encoding="utf-8").read()
    assert "## inicio" in text and "btn_comedor" in text and "light.comedor" in text
    csv_files = manager.export("exportador_markdown.csv", vm.project, str(tmp_path))
    rows = open(csv_files[0], encoding="utf-8-sig").read().splitlines()
    assert rows[0].startswith("pagina;id;tipo") and len(rows) > 20


def test_validator_and_command(manager, vm):
    b = vm.add_widget("button", 10, 10, centered=False)
    vm.set_geom_value(b, "height", "30")
    lbl = vm.add_widget("label", 10, 100, centered=False)
    vm.set_prop([lbl], "text_color", "#EEEEEE")              # gris claro sobre blanco
    issues = validate(vm.project)
    msgs = " ".join(i.message for i in issues)
    assert f"{b}: alto de 30 px" in msgs and "contraste" in msgs
    assert all(i.plugin == "reglas_ux" for i in issues)
    log = []
    assert manager.run_command("reglas_ux.agrandar", vm, log.append)
    assert vm.widget(b).height == 48 and "ampliadas" in log[0]
    vm.undo()
    assert vm.widget(b).height == 30


def test_broken_and_incompatible_plugins_are_isolated(tmp_path):
    base = tmp_path / "pl"
    for pid, manifest, code in (
        ("roto", {"id": "roto", "name": "Roto", "api": 1}, "def register(ctx):\n    raise RuntimeError('fallo')\n"),
        ("viejo", {"id": "viejo", "name": "Viejo", "api": 99}, "def register(ctx):\n    pass\n"),
        ("sin_expand", {"id": "sin_expand", "name": "X", "api": 1},
         "def register(ctx):\n    ctx.register_widget('cosa', 'Cosa')\n"),
    ):
        d = base / pid
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        (d / "plugin.py").write_text(code, encoding="utf-8")
    m = PluginManager([(str(base), "usuario")])
    p = m.load_all()
    assert "fallo" in p["roto"].error and not p["roto"].loaded
    assert "API 99" in p["viejo"].error
    assert "expand" in p["sin_expand"].error and "cosa" not in catalog.CATALOG


def test_disable_and_scaffold(tmp_path, vm):
    path = create_plugin(str(tmp_path), "mi_plugin", "Mi plugin")
    m = PluginManager([(str(tmp_path), "usuario")])
    p = m.load_all(disabled={"mi_plugin"})
    assert not p["mi_plugin"].loaded and "mi_plugin_widget" not in catalog.CATALOG
    p = m.load_all()
    assert p["mi_plugin"].loaded, p["mi_plugin"].error
    wid = vm.add_widget("mi_plugin_widget", 0, 0, centered=False)
    expanded = expand_project(vm.project)
    assert expanded.widget(wid).type == "obj" and expanded.widget(f"{wid}_text").type == "label"
    m.unload("mi_plugin")
    assert "mi_plugin_widget" not in catalog.CATALOG
    assert os.path.exists(os.path.join(path, "plugin.json"))


def test_plugin_translations(manager):
    from olvgl import i18n
    try:
        i18n.set_language("en")
        assert i18n.tr("Tarjeta de sensor") == "Sensor card"
        assert i18n.tr("&Archivo") == "&File"
    finally:
        i18n.set_language("es")
