# Fase 4 — Soporte completo de LVGL

## Widgets

El catálogo (`olvgl/domain/catalog.py`) describe los 26 tipos de LVGL que admite ESPHome: 24 en la paleta, más `tab` y `tile`, que se crean desde su contenedor.

| Categoría | Widgets |
|---|---|
| Básicos | label, button, image, obj |
| Controles | switch, checkbox, slider, arc, dropdown, roller, spinbox, textarea, keyboard, buttonmatrix |
| Indicadores | bar, led, spinner, line, qrcode, meter |
| Contenedores | tabview (tab), tileview (tile) |
| Media | canvas, animimg |

Cada tipo declara sus propiedades con editor visual, sus partes con estilo propio (`main`, `indicator`, `knob`, `items`, `selected`, `cursor`, `scrollbar`…), sus eventos y su tamaño inicial. Las propiedades pueden ir en rutas con puntos (`indicator.arc_color`, `state.checked`), que se leen y escriben con `get_path` y `set_path`. Un valor que el editor visual no sabe mostrar (una lambda o un formato) pasa al bloque YAML, que sigue aceptando cualquier propiedad de ESPHome.

Tabview y tileview tienen un botón «Añadir pestaña / mosaico» (`ProjectViewModel.add_child`).

## Estilos

Prioridad de aplicación, de menor a mayor:

1. tema por defecto de LVGL;
2. `theme:` por tipo de widget;
3. `styles:` del widget (referencias a `style_definitions`);
4. propiedades propias del widget.

`domain/layout.effective_props` aplica esta prioridad. El panel «Estilo por parte y estado» escribe en ESPHome:

```yaml
- button:
    bg_color: 0x2196F3        # parte principal, estado normal
    pressed:
      bg_color: 0x00FF00      # parte principal, pulsado
    indicator:
      checked:
        bg_color: 0x4CAF50    # parte indicador, activado
```

El diálogo **Estilos y tema** edita `style_definitions` y `theme`. Crear, renombrar o eliminar un estilo actualiza las referencias de los widgets, y todo se puede deshacer.

## Eventos avanzados

| Acción | ESPHome | Simulador |
|---|---|---|
| Mostrar / ocultar / activar / desactivar | `lvgl.widget.hide: id` … | se aplica |
| Cambiar propiedades | `lvgl.label.update: {id, text…}` | se aplica |
| Página / siguiente / anterior | `lvgl.page.show` … | se aplica |
| Acción de Home Assistant | `homeassistant.action` | se registra |
| Acción de componente | `light.toggle: luz`, `script.execute` … | se registra |
| Esperar | `delay: 1s` | se registra |
| Lambda | `lambda: \|-` | se registra |
| YAML libre | cualquier otra | se registra |

El importador reconoce estas formas simples. Si tienen parámetros extra, se conservan como YAML libre y la ida y vuelta sigue siendo exacta.

El simulador trabaja sobre una copia del proyecto. Admite arrastrar deslizadores y arcos, recorrer desplegables y rodillos, incrementar spinbox, conmutar interruptores y casillas y cambiar de pestaña. Recargar devuelve la simulación al diseño.

## Generador C (LVGL 9.5+)

`olvgl/infrastructure/lvgl_c_generator.py` traduce el mismo modelo a `ui.c` y `ui.h`:

- un `lv_style_t` por estilo y estado, y `ui_theme_<tipo>` para el tema;
- `ui_<página>_create()` por página, `ui_top_layer_create()` y `ui_init()`;
- flex y grid (incluida la forma corta `NxM`), alineación, tamaños en % y `SIZE_CONTENT`;
- eventos: navegación, mostrar/ocultar y `update` se traducen a C. Lo que sólo existe en ESPHome se delega en `ui_action_handler`;
- `ui_set_flag()` usa los setters por bandera de LVGL 9.6 y `lv_obj_add/remove_flag` en 9.5;
- `#error` si la versión de LVGL no es 9.5 o posterior.

Validación: `tests/test_c_generator.py` compila con `gcc -Wall -Wextra -Wpedantic` contra las cabeceras de LVGL si se definen `LVGL_DIR` y `LVGL_CONF_DIR`. Con LVGL 9.5 y 9.6 el resultado es 0 errores y 0 avisos para el ejemplo, para un proyecto con todos los widgets y para el panel real (7 300 líneas).

Limitaciones conocidas:

- `meter` (eliminado en LVGL 9) se genera como un objeto base con un comentario que propone `lv_scale`.
- Las lambdas y los textos con `format:` quedan como comentario.
- Las fuentes e imágenes propias hay que convertirlas con las herramientas de LVGL.
