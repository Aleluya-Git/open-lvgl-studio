# Fase 2 — Importación y parser YAML

## Flujo

```
fichero.yaml ──► yaml_parser (PyYAML compose) ──► AST con Span y etiquetas
             ──► expand_includes + merge_packages (como ESPHome)
             ──► esphome_importer ──► Proyecto (modelo v2) ──► canvas
                                                   └──► esphome_generator ──► ui_lvgl.yaml
```

**Archivo → Importar YAML de ESPHome…** (Ctrl+I), o `run.bat mi_panel.yaml`.

## Qué se entiende y qué se conserva

| Del YAML | En el editor |
|---|---|
| `lvgl: pages:` | Pantallas (id, color de fondo y resto de claves de la página) |
| `lvgl: widgets:` sin páginas | Una página implícita |
| `lvgl: top_layer:` | **Capa superior**: se dibuja sobre todas las páginas y se edita aparte |
| `widgets:` anidados | Widgets hijos con su propio árbol |
| `tabview: tabs:` / `tileview: tiles:` | Pestañas / mosaicos como hijos; se muestra la activa |
| `button` con un único `label` centrado | Botón con texto (se edita como en la Fase 1) |
| `on_*` con acciones | Eventos: `lvgl.page.show/next/previous`, `homeassistant.action`, `logger.log`; el resto (if, delay, lambda…) como **YAML libre** sin pérdidas |
| `on_*: then:` con opciones extra | Se conserva tal cual |
| `style_definitions`, `theme` | Estilos del proyecto y tema, aplicados en el dibujo |
| `font:`, `image:` (lista o agrupada por tipo), `color:` | Recursos del proyecto; colores con nombre resueltos al dibujar |
| `!lambda`, `!secret`, `!include`, `!extend` | Etiquetas conservadas |
| `packages:` locales y `<<: !include` | Se cargan y mezclan como hace ESPHome (paquetes primero) |
| Resto de claves de `lvgl:` (byte_order, buffer_size, default_font…) | Conservadas y regeneradas |
| `display: dimensions` (+ rotation) | Resolución del proyecto |

Widgets sin id reciben un id interno (`_label_3`) que **no** se escribe en el YAML; al darles un id en el panel de propiedades pasa a escribirse.

## Garantía de ida y vuelta

Probado en `tests/test_importer.py` con `examples/importar/panel_demo.yaml`:

1. `importar → generar → importar → generar` produce exactamente el mismo texto.
2. La sección `lvgl:` regenerada es semánticamente igual a la original (salvo que los labels de botón reciben id y `on_x: then: [...]` se escribe como `on_x: [...]`, equivalentes en ESPHome).

Lo que **no** se conserva todavía: comentarios del YAML y el formato exacto del fichero original. Eso es la Fase 3 (sincronización sobre el texto original usando los `Span` del AST).

## Reconstrucción visual (`domain/layout.py`)

- Tamaños: px, `%`, `SIZE_CONTENT` (medido con las fuentes reales) y tamaños por defecto de cada tipo.
- Posición: `align` (9 posiciones) + `x/y` en px o %, `align_to` con alineaciones `OUT_*`.
- `layout:` **flex** (ROW/COLUMN, WRAP, REVERSE, `flex_grow`, alineaciones main/cross/track, `pad_row/pad_column`) y **grid** (px, `FR(n)`, `CONTENT`, %, spans, alineación de celda, atajo `layout: 2x3`).
- `hidden`, `floating`, `ignore_layout`, recorte de hijos al padre (`overflow_visible`).
- Estilo efectivo: tema por defecto aproximado de LVGL 9 → `theme:` → `styles:` → propiedades propias, con herencia de las propiedades de texto, y propiedades de `lvgl:` como valores por defecto de las páginas.

## Fuentes reales en el canvas

Las fuentes `gfonts://Familia@peso` y las de tipo `web` (p. ej. Material Design Icons) se descargan **una vez**, en segundo plano, a `%APPDATA%\OpenLVGLStudio\fonts`, para que el canvas y el simulador usen la misma tipografía y los mismos iconos que el dispositivo. Sin red se usa una fuente de sustitución. Las etiquetas con `recolor: true` muestran el texto sin el marcado `#RRGGBB …#`.

## Validado con un panel real

`tests/test_importer.py::test_real_panel_roundtrip` usa `examples/panel-domotica_final.yaml` si existe (≈11 000 líneas, 8 páginas, 680 widgets, 43 en la capa superior, 25 fuentes, 120 acciones complejas): la importación no da avisos y `lvgl:`, `font:` e `image:` regenerados son semánticamente idénticos al original.

## Sistema de propiedades

- **Registro** (`domain/values.py`): tipo de cada propiedad LVGL conocida (color, opacidad, entero, fuente, enumerado…). Los colores se guardan como `#RRGGBB` y se escriben como `0xRRGGBB`; los nombres de `color:` se respetan.
- **Panel de propiedades**:
  - id (vacío = sin id), geometría tal como se escribe en ESPHome (`120`, `50%`, `SIZE_CONTENT` o vacío), alineación;
  - editores visuales para Label, Button e Image;
  - eventos de cualquier widget;
  - bloque **«Más propiedades (YAML)»** con todo lo demás (estados `pressed:`/`checked:`, partes `indicator:`/`knob:`, `styles:`, `layout:`, lambdas…), con lista de propiedades conocidas para añadir. Ctrl+Intro aplica; deshacer funciona igual.

## Limitaciones conocidas (para las fases siguientes)

- Los widgets sin editor propio (arc, slider, switch, dropdown…) se dibujan de forma aproximada y se editan por YAML: Fase 4.
- El dibujo aproxima el tema de LVGL; el simulador con LVGL real es la Fase 6.
- Las sustituciones `${...}` no se expanden (se conservan tal cual).
- `!include` con `vars:` se carga sin sustituir variables.
