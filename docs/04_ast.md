# Fase 0 · 04 — Definición del AST y del modelo interno

Hay **dos niveles** de representación, a propósito:

1. **AST YAML** (`olvgl/domain/yaml_ast.py`): árbol sintáctico fiel al texto. Conserva orden de claves, estilo de los escalares, comentarios y posiciones. Es lo que leen los parsers y lo que escribe el emitter.
2. **Modelo interno JSON** (`olvgl/domain/model.py`): semántico, independiente del formato. Es lo que edita el canvas.

```
Texto YAML ⇄ AST YAML ⇄ Modelo interno ⇄ Editor visual
             (parser / emitter)  (importer / generator)
```

## 1. AST YAML

| Nodo | Campos | Uso |
|---|---|---|
| `YMap` | `items: list[YPair]`, `span`, `comment`, `tag` | Mapeo ordenado |
| `YPair` | `key: str`, `value: YNode`, `comment` | Una clave con comentario opcional encima |
| `YSeq` | `items: list[YNode]`, `span`, `tag` | Secuencia (`- …`) |
| `YScalar` | `value`, `style`, `span`, `tag` | Escalar. `style ∈ {plain, double, hex, literal, verbatim}`; `tag` = `!lambda`, `!secret`, `!include`… |
| `YRaw` | `text`, `span` | Bloque YAML no interpretado (acciones libres, lambdas, nodos desconocidos en la importación) |
| `Span` | `line`, `col`, `end_line`, `end_col` | Posición en el fichero de origen (Fase 2–3) |

Estilos de escalar:

- `plain`: `text: Hola` (el emitter pone comillas automáticamente si hace falta).
- `double`: `"texto"` forzado.
- `hex`: enteros como `0x1E88E5` (colores ESPHome).
- `literal`: bloque `|-` para multilínea y lambdas.
- `verbatim`: se escribe tal cual (`!include ui_lvgl.yaml`, `!secret wifi_ssid`).

### Ejemplo

YAML:

```yaml
lvgl:
  pages:
    - id: inicio
      bg_color: 0x1A1A2E
      widgets:
        - label:
            id: lbl_titulo
            text: Salón
```

AST:

```
YMap
└─ YPair "lvgl"
   └─ YMap
      └─ YPair "pages"
         └─ YSeq
            └─ YMap
               ├─ YPair "id" → YScalar("inicio")
               ├─ YPair "bg_color" → YScalar(0x1A1A2E, hex)
               └─ YPair "widgets" → YSeq
                  └─ YMap
                     └─ YPair "label" → YMap
                        ├─ YPair "id" → YScalar("lbl_titulo")
                        └─ YPair "text" → YScalar("Salón")
```

Desde la Fase 2 el parser (`infrastructure/yaml_parser.py`) produce este AST a partir de cualquier YAML de ESPHome, con `Span` (línea y columna de inicio y fin) en cada nodo.

## 2. Modelo interno (`.olvgl`, JSON)

> Esquema v2 (Fase 2): widgets de cualquier tipo LVGL y anidados (`children`), geometría tal como en ESPHome (`x/y/width/height` = entero, `"50%"`, `"SIZE_CONTENT"` o `null`), `auto_id`, `props` de página, `fonts`, `styles`, `top_layer`, `lvgl_extra` (resto de claves de `lvgl:`), `extra_sections` (`color:`) y `source` (origen de la importación). Los proyectos v1 se migran solos al abrirlos.

```json
{
  "format": "open-lvgl-studio",
  "schema_version": 1,
  "name": "Panel salón",
  "display": {"name": "Waveshare ESP32-S3-Touch-LCD-7B", "width": 1024, "height": 600},
  "esphome": {"device_name": "panel-salon", "lvgl_version": 9},
  "images": [
    {"id": "img_logo", "path": "images/logo.png", "type": "RGB565", "transparency": "alpha_channel"}
  ],
  "screens": [
    {
      "id": "inicio", "name": "Inicio", "bg_color": "#1A1A2E",
      "widgets": [
        {"id": "lbl_titulo", "type": "label", "x": 24, "y": 20, "width": 300, "height": 40,
         "props": {"text": "Salón", "text_color": "#FFFFFF", "text_font": "montserrat_28"},
         "events": [], "children": []},
        {"id": "btn_luz", "type": "button", "x": 24, "y": 100, "width": 160, "height": 60,
         "props": {"text": "Luz"},
         "events": [{"trigger": "on_click", "actions": [
            {"kind": "ha_action", "params": {"action": "light.toggle", "entity_id": "light.salon"}}]}],
         "children": []}
      ]
    }
  ]
}
```

Reglas:

- **Colores** como `"#RRGGBB"` en el modelo; el generador los convierte a `0xRRGGBB`.
- **`props`** sólo guarda valores que el usuario ha fijado; si un valor coincide con el defecto del catálogo, el generador no lo emite.
- **IDs**: `[A-Za-z_][A-Za-z0-9_]*`, únicos en todo el proyecto (pantallas, widgets e imágenes comparten espacio de nombres, igual que en ESPHome).
- **Rutas de imagen** relativas al fichero `.olvgl`.
- **`schema_version`** permite migraciones automáticas al abrir proyectos antiguos.

## 3. Correspondencia modelo → ESPHome

| Modelo | ESPHome YAML |
|---|---|
| `Screen` | `lvgl: pages: - id:` |
| `Widget(type=label)` | `- label:` con `text`, `text_color`, `text_font`, `text_align`, `long_mode` |
| `Widget(type=button)` | `- button:` + `widgets: - label:` hijo con id `<id>_label` |
| `Widget(type=image)` | `- image: src: <img_id>` |
| `ImageResource` | `image: - file: / id: / type: / transparency:` |
| `Action(page_show)` | `- lvgl.page.show: <page>` |
| `Action(page_next / page_prev)` | `- lvgl.page.next:` / `- lvgl.page.previous:` |
| `Action(ha_action)` | `- homeassistant.action: {action, data: {entity_id}}` |
| `Action(logger)` | `- logger.log: "..."` |
| `Action(raw)` | YAML literal del usuario |
