# Fase 7 — SDK de plugins

Un plugin amplía Open LVGL Studio sin tocar su código. Puede aportar cuatro cosas:

| Extensión | Dónde aparece |
|---|---|
| **Widgets compuestos** | paleta (categoría «Plugins»), menú Insertar, panel de propiedades, canvas, simulador; al exportar se convierten en widgets estándar de LVGL |
| **Exportadores** | Archivo › Exportar, y `python -m olvgl.cli export --format PLUGIN.ID` |
| **Validadores** | Plugins › Comprobar el proyecto, `cli validate` y el panel «Problemas» de VS Code |
| **Órdenes** | menú Plugins (con deshacer) |

## Dónde se instalan

1. `plugins/` dentro de la aplicación, donde están los tres de ejemplo.
2. **Tu carpeta de plugins**: `%APPDATA%\OpenLVGLStudio\plugins`. Se abre desde Plugins › Gestionar plugins › «Abrir carpeta de plugins».
3. Las carpetas indicadas en la variable de entorno `OLVGL_PLUGINS`, separadas por `;`.

Si dos plugins tienen el mismo `id`, gana el de la última carpeta. Así puedes sustituir uno de ejemplo
con tu propia versión.

Desde **Plugins › Gestionar plugins** puedes:

- ver el estado, la versión, el origen, lo que aporta cada plugin y sus errores;
- activar o desactivar plugins (se recargan al momento);
- crear uno nuevo desde una plantilla.

> **Seguridad**: un plugin es código Python con los mismos permisos que la aplicación. Instala sólo
> plugins de quien te fíes.

## Estructura

```
mi_plugin/
  plugin.json
  plugin.py
  icon.png        (opcional, 96×96, icono del widget en la paleta)
```

`plugin.json`:

```json
{
  "id": "mi_plugin",
  "name": "Mi plugin",
  "version": "1.0.0",
  "api": 1,
  "entry": "plugin.py",
  "description": "Qué hace",
  "author": "Tu nombre",
  "translations": {"en": {"Texto en español": "English text"}}
}
```

- `id`: minúsculas, números y `_`.
- `api`: tiene que coincidir con la API de la aplicación, que ahora es la 1. Si no coincide, el
  plugin no se carga y el gestor lo explica.
- `translations`: opcional. Traduce los textos del plugin (etiquetas, descripciones, nombres de
  exportadores y órdenes) al inglés, francés o alemán.

`plugin.py` define `register(ctx)`. Si falla, el plugin queda marcado con su error y no deja nada
registrado; el resto de la aplicación sigue funcionando. Para empezar desde la plantilla:

```
python -m olvgl.cli new-plugin mi_plugin
```

## Referencia de `ctx` (API 1)

### Widgets

```python
ctx.register_widget(type, label, *, props=(), default_size=(160, 100), description="",
                    category="Plugins", events=(...), expand=fn, paint=fn,
                    icon="icon.png", initial_props={...}, id_prefix=None)
```

- **`props`**: propiedades editables, declaradas con `ctx.P(nombre, etiqueta, tipo, valor_por_defecto,
  opciones=(), group="Estilo")`. Los tipos son `ctx.INT`, `ctx.STR`, `ctx.TEXT`, `ctx.COLOR`,
  `ctx.BOOL` y `ctx.ENUM`. El panel de propiedades crea sus editores solo.
- **`expand(widget) → [Widget]`** es **obligatorio**. ESPHome y LVGL sólo conocen sus widgets, así
  que al exportar a ESPHome o C, y al estimar recursos, cada widget del plugin se sustituye por lo
  que devuelve `expand`.
  - Construye los widgets con `ctx.Widget(id, tipo, x, y, ancho, alto, props={...}, events=[...],
    children=[...])`.
  - Conserva `widget.id` en el widget raíz y da a los hijos ids derivados de él (`f"{w.id}_valor"`).
    Así los ids son estables, la sincronización con el YAML escribe cambios mínimos y las lambdas
    pueden referirse a ellos.
- **`paint(painter, rect, widget, props, render_ctx, state)`**: cómo se dibuja en el canvas, el
  simulador y la vista previa de VS Code.
  - `props` son las propiedades efectivas (tema y estilos aplicados) y `state` es
    `{"pressed", "checked"}`.
  - Puedes usar las funciones de `olvgl.presentation.render`: `paint_box`, `paint_text`,
    `draw_text`, `render_ctx.color()`, `render_ctx.font()`.
  - Si falla, se dibuja un aviso en lugar del widget.

En el diseño y en el `.olvgl`, el widget del plugin se guarda como tal (`type: "sensor_card"`).
Sólo lo exportado lleva la versión expandida. Si se abre el proyecto sin el plugin, el widget se
muestra como un tipo desconocido y la exportación avisa.

### Exportadores

```python
ctx.register_exporter(id, nombre, export, descripcion="")
# export(project, carpeta) -> list[str]   (ficheros escritos)
```

`project` es el modelo completo (`olvgl.domain.model.Project`): `screens`, `top_layer`, `styles`,
`fonts`, `images`, `iter_widgets()`… Para obtener lo que verá el dispositivo, usa
`olvgl.domain.extensions.expand_project(project)`.

### Validadores

```python
ctx.register_validator(fn)        # fn(project) -> list[ctx.Issue]
ctx.Issue(mensaje, severity="warning", widget_id=None, page_id=None)   # error | warning | info
```

Con `widget_id`, un doble clic en el resultado selecciona el widget. En VS Code el aviso aparece en
la línea de su `id:`.

### Órdenes

```python
ctx.register_command(id, etiqueta, run, descripcion="")
# run(c): c.vm (ProjectViewModel), c.project, c.selection, c.log(msg), c.window
```

Cambia el proyecto **a través de `c.vm`** para que el cambio se pueda deshacer, se sincronice con
el YAML y se redibuje. Por ejemplo:

- `c.vm.set_prop(ids, nombre, valor)`
- `c.vm.set_geom_value(id, "width", "48")`
- `c.vm.add_widget(tipo, x, y)`
- `c.vm.set_events(id, [...])`

### Otros

- `ctx.log(msg)`: escribe en el registro de plugins y en la barra de estado.
- `ctx.resource("fichero")`: ruta a un fichero dentro de la carpeta del plugin.
- `ctx.add_translations(idioma, {texto: traducción})`.

## Plugins de ejemplo

| Plugin | Qué muestra |
|---|---|
| `tarjeta_sensor` | Widget compuesto `sensor_card` (título, valor grande, unidad, barra de color) con `paint`, `expand`, icono y traducciones. Se exporta como `obj` + `obj` + 3 `label` |
| `exportador_markdown` | Dos exportadores: documentación Markdown (páginas, árbol de widgets, eventos, fuentes, imágenes, avisos) e inventario CSV |
| `reglas_ux` | Validador: elementos táctiles de menos de 40 px, contraste del texto (WCAG, mínimo 3:1), imágenes sin origen. Orden: «Agrandar elementos táctiles pequeños (48 px)» |

## Pruebas

- `tests/test_plugins.py`:
  - carga de los ejemplos;
  - expansión a ESPHome válido que se vuelve a importar, y a C;
  - exportadores;
  - validador y orden, con deshacer;
  - plugins rotos, de otra API o sin `expand` (quedan aislados);
  - desactivar un plugin;
  - plantilla;
  - traducciones.
- Autoprueba F7: gestor, widget del plugin en la paleta y en el canvas (captura), exportación a
  ESPHome y C, exportadores, reglas, orden y la orden `plugins` de la CLI.
