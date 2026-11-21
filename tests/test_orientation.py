"""Orientación de la pantalla: horizontal / vertical (lvgl: rotation:)."""
import yaml

from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain.model import DisplayProfile, new_project, parse_rotation, rotate_display
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_text
from olvgl.infrastructure.lvgl_c_generator import generate_c


def vm_with(display=DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600)):
    vm = ProjectViewModel(generator=generate_yaml)
    vm.new("Orientación", display)
    return vm


def test_helpers():
    assert [parse_rotation(v) for v in (90, "270", "180°", 45, None, True, "x")] == [90, 270, 180, 0, 0, 0, 0]
    d = DisplayProfile("P", 800, 480)
    assert (rotate_display(d, 0, 90).width, rotate_display(d, 0, 90).height) == (480, 800)
    assert (rotate_display(d, 0, 180).width, rotate_display(d, 90, 270).width) == (800, 800)
    p = new_project("V", DisplayProfile("P", 480, 800), rotation=90)
    assert p.rotation == 90 and p.lvgl_extra["rotation"] == 90


def test_set_orientation_swaps_size_and_writes_rotation():
    vm = vm_with()
    assert vm.set_orientation(90)
    d = vm.project.display
    assert (d.name, d.width, d.height) == ("Waveshare ESP32-S3-Touch-LCD-7B", 600, 1024)
    assert vm.project.rotation == 90
    assert not vm.set_orientation(90)                       # ya lo está
    assert vm.set_orientation(270) and (vm.project.display.width, vm.project.display.height) == (600, 1024)
    assert vm.set_orientation(180) and (vm.project.display.width, vm.project.display.height) == (1024, 600)
    vm.set_orientation(0)
    assert "rotation" not in vm.project.lvgl_extra
    for _i in range(4):
        vm.undo()
    assert vm.project.rotation == 0 and vm.project.display.width == 1024


def test_change_board_keeps_orientation():
    vm = vm_with()
    vm.set_orientation(90)
    vm.set_display_keep_orientation(DisplayProfile("Sunton ESP32-8048S070 (7\")", 800, 480))
    d = vm.project.display
    assert (d.width, d.height) == (480, 800) and vm.project.rotation == 90


def test_yaml_and_c():
    vm = vm_with()
    vm.add_widget("button", 20, 900, centered=False)
    vm.set_orientation(90)
    text = generate_yaml(vm.project)
    data = yaml.safe_load(text)
    assert data["lvgl"]["rotation"] == 90
    assert "page_wrap" not in str(vm.layout())               # el giro no se cuela como estilo de la página
    src = generate_c(vm.project).source
    assert "lv_display_set_rotation(lv_display_get_default(), LV_DISPLAY_ROTATION_90);" in src
    back, _r = import_esphome_text(text, "x.yaml", vm.project.display)
    assert back.rotation == 90 and back.display.width == 600


def test_import_guesses_portrait_from_lvgl_rotation():
    text = """
display:
  - platform: mipi_rgb
    dimensions: {width: 800, height: 480}
lvgl:
  rotation: 90
  pages:
    - id: p
      widgets:
        - label: {text: hola}
"""
    p, _r = import_esphome_text(text, "v.yaml")
    assert p.rotation == 90 and (p.display.width, p.display.height) == (480, 800)
