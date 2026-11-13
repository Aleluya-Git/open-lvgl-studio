from olvgl.domain.model import TOP_LAYER_ID, Project


def test_import_into_vm(vm, demo_path):
    rep = vm.import_yaml(demo_path)
    assert rep.pages == 2 and vm.path is None
    assert vm.linked and not vm.dirty          # vinculado al YAML: modelo y fichero coinciden
    assert vm.current_screen_id == "inicio"
    assert vm.box("panel_clima").rect.w > 400


def test_move_respects_align_and_percent(vm, demo_path):
    vm.import_yaml(demo_path)
    clima = vm.widget("panel_clima")   # align TOP_RIGHT, x -20
    before = vm.box("panel_clima").rect
    vm.move_by({"panel_clima": (-30, 15)})
    assert (clima.x, clima.y) == (-50, 125)
    after = vm.box("panel_clima").rect
    assert (round(after.x - before.x), round(after.y - before.y)) == (-30, 15)
    vm.undo()
    assert (clima.x, clima.y) == (-20, 110)


def test_layout_managed_children_do_not_move(vm, demo_path):
    vm.import_yaml(demo_path)
    btn = vm.widget("btn_comedor")
    assert not vm.box("btn_comedor").movable
    n = len(vm.history)
    vm.move_by({"btn_comedor": (10, 10)})
    assert len(vm.history) == n and btn.x is None


def test_nested_add_delete_duplicate(vm, demo_path):
    vm.import_yaml(demo_path)
    card = vm.box("panel_luces")
    wid = vm.add_widget("label", card.content.x + 50, card.content.y + 40, centered=False,
                        parent_id="panel_luces")
    loc = vm.project.locate(wid)
    assert loc.parent.id == "panel_luces"
    dup = vm.duplicate([wid])
    assert vm.project.locate(dup[0]).parent.id == "panel_luces"
    vm.delete_widgets(["panel_luces"])
    assert vm.widget("panel_luces") is None and vm.widget(wid) is None
    vm.undo()
    assert vm.project.locate(dup[0]).parent.id == "panel_luces"
    assert [c.id for c in vm.widget("panel_luces").children][-2:] == [wid, dup[0]]


def test_container_at_and_drop(vm, demo_path):
    vm.import_yaml(demo_path)
    b = vm.box("panel_luces").rect
    assert vm.container_at(b.x + 5, b.y + 5) == "panel_luces"
    assert vm.container_at(5, 590) is None
    tb = vm.box("tab_pb").rect
    assert vm.container_at(tb.x + 10, tb.y + 100) == "tab_pb"


def test_selecting_hidden_tab_child_reveals_it(vm, demo_path):
    changes = []
    vm.layout_changed.connect(lambda: changes.append(1))
    vm.import_yaml(demo_path)
    assert not vm.box("chk_bano").shown
    vm.set_selection(["chk_bano"])
    assert vm.active_tabs["pestanas"] == 1 and vm.box("chk_bano").shown and changes


def test_geometry_values_and_raw_props(vm, demo_path):
    vm.import_yaml(demo_path)
    assert vm.set_geom_value("panel_luces", "width", "50%") is None
    assert vm.widget("panel_luces").width == "50%"
    assert vm.set_geom_value("panel_luces", "height", "SIZE_CONTENT") is None
    assert vm.set_geom_value("panel_luces", "x", "") is None and vm.widget("panel_luces").x is None
    assert vm.set_geom_value("panel_luces", "y", "abc")
    vm.set_raw_prop(["panel_luces"], "bg_opa", "50%")
    vm.set_raw_prop(["panel_luces"], "styles", None)
    w = vm.widget("panel_luces")
    assert w.props["bg_opa"] == "50%" and "styles" not in w.props
    yaml_text = vm.generate_yaml()
    assert "bg_opa: \"50%\"" in yaml_text


def test_resize_and_align_with_layout(vm, demo_path):
    vm.import_yaml(demo_path)
    r = vm.box("lbl_titulo_luces").rect
    vm.set_geometry("lbl_titulo_luces", (r.x + 10, r.y, 200, 40))
    w = vm.widget("lbl_titulo_luces")
    assert (w.x, w.width, w.height) == (30, 200, 40)
    vm.set_selection(["panel_clima"])
    vm.align("left")  # respecto a la pantalla: x absoluta 0 con align TOP_RIGHT
    assert round(vm.box("panel_clima").rect.x) == 0


def test_top_layer_and_rename(vm, demo_path):
    vm.import_yaml(demo_path)
    assert vm.project.screen(TOP_LAYER_ID) is not None
    vm.set_current_screen(TOP_LAYER_ID)
    wid = vm.add_widget("button", 500, 30)
    assert vm.project.locate(wid).screen.id == TOP_LAYER_ID
    anon = vm.widget("panel_clima").children[0]
    assert anon.auto_id
    assert vm.rename_widget(anon.id, "lbl_salon_clima") is None
    assert not vm.widget("lbl_salon_clima").auto_id
    assert "id: lbl_salon_clima" in vm.generate_yaml()
    assert vm.remove_screen(TOP_LAYER_ID) and vm.project.top_layer is None
    vm.undo()
    assert vm.project.top_layer is not None


def test_ensure_top_layer_on_new_project(vm):
    assert vm.project.top_layer is None
    vm.ensure_top_layer()
    assert vm.current_screen_id == TOP_LAYER_ID
    vm.add_widget("label")
    assert "top_layer:" in vm.generate_yaml()


def test_migration_v1():
    v1 = {"format": "open-lvgl-studio", "schema_version": 1, "name": "viejo",
          "display": {"width": 800, "height": 480},
          "images": [{"id": "img_a", "path": "a.png"}],
          "screens": [{"id": "main_page", "name": "P", "bg_color": "#FFFFFF", "widgets": [
              {"id": "lbl_1", "type": "label", "x": 1, "y": 2, "width": 160, "height": 32, "props": {}},
              {"id": "btn_1", "type": "button", "props": {"text": "OK"}},
              {"id": "image_1", "type": "image", "width": 64, "height": 64, "props": {"src": "img_a"}}]}]}
    p = Project.from_dict(v1)
    s = p.screens[0]
    assert s.bg_color is None
    assert p.widget("lbl_1").props["text"] == "Etiqueta"
    assert p.widget("btn_1").props["text"] == "OK"
    assert p.widget("image_1").width is None
    assert p.to_dict()["schema_version"] == 2


def test_replace_props_scope_and_order(vm, demo_path):
    vm.import_yaml(demo_path)
    w = vm.widget("panel_luces")
    keys_before = list(w.props)
    vm.replace_props("panel_luces", ["styles", "layout"], {"layout": {"type": "flex"}, "bg_opa": "COVER"})
    assert "styles" not in w.props and w.props["layout"] == {"type": "flex"}
    assert list(w.props)[-1] == "bg_opa"
    assert [k for k in w.props if k in keys_before][0] == keys_before[keys_before.index("layout")]
    vm.undo()
    assert list(w.props) == keys_before
    vm.replace_screen_props("ajustes", {"on_load": [{"logger.log": "otra"}]})
    assert vm.project.screen("ajustes").props["on_load"][0]["logger.log"] == "otra"
