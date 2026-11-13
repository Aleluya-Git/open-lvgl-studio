# Fase 3 — Sincronización bidireccional con el YAML

## Qué hace

Un proyecto puede estar **vinculado** a un YAML de ESPHome (se vincula solo al importar, o con
*Archivo → Sincronización con YAML → Vincular…*). Desde ese momento:

| Dirección | Cuándo | Cómo |
|---|---|---|
| Editor → YAML | 0,8 s después de dejar de editar (o Ctrl+S / Ctrl+Mayús+Y si la escritura automática está desactivada) | Sólo se reescriben las líneas afectadas |
| YAML → editor | En cuanto el fichero cambia en disco (VS Code, ESPHome Builder…) | Se reimporta y el cambio queda en el historial: **Ctrl+Z lo deshace** (y se vuelve a escribir) |
| Ambos a la vez | Si editas en los dos sitios antes de sincronizar | Merge a tres bandas: se conservan los dos cambios |

La barra de estado muestra `⇄ fichero.yaml · sincronizado` o `· cambios pendientes`. La primera escritura de cada sesión guarda una copia `fichero.yaml.olvgl.bak`.

## Motor Diff/Merge (`infrastructure/yaml_sync.py`)

1. **Tres versiones** de las secciones gestionadas (`lvgl:`, `font:`, `image:`, `color:`):
   - **B**: el fichero en la última sincronización;
   - **O**: el fichero ahora;
   - **C**: lo que genera el editor.
2. **Comparación semántica** (`canon`): ignora estilo, comillas, hexadecimal/decimal y las equivalencias del generador. Por ejemplo, `on_click: then: [...]` ≡ `on_click: [...]`, y el id de los labels de botón se ignora.
3. **Merge nodo a nodo**:
   - si B = C, se queda lo del fichero;
   - si O = B, se aplica el editor;
   - si O = C, no hay nada que hacer;
   - si cambiaron los dos, se baja al detalle (claves de mapas, elementos de listas identificados por `id`);
   - si cambiaron el mismo valor, gana el editor y se avisa en la barra de estado.
4. **Ediciones de texto mínimas** usando las posiciones (Span) del AST:
   - cambiar un valor sustituye solo ese valor, conservando el comentario de la línea;
   - insertar o borrar claves y elementos de lista afecta a líneas completas;
   - las listas se emparejan por `id` (como `difflib`, para detectar inserciones y borrados);
   - las colecciones en línea (`[a, b]`) se reescriben en línea;
   - un `on_x: then:` se mantiene con `then:`;
   - no se añaden ids de label que el original no tenía.
5. **Red de seguridad**: el resultado se vuelve a analizar y se comprueba que coincide con lo esperado. Si no coincide (no ha pasado en las pruebas), se reescribe entera solo la sección afectada y se avisa.

Se conservan los finales de línea CRLF y el BOM del fichero.

## Rendimiento

En el panel real de pruebas (11 000 líneas, 680 widgets) sincronizar un cambio tarda unas décimas de segundo con libyaml. Con 200 combinaciones aleatorias de ediciones sobre un panel de prueba y 30 sobre el panel real no hubo ningún repliegue ni resultado incorrecto.

## Limitaciones

- No se sincronizan directamente ficheros con `packages:` o `!include` (el proyecto se importa igualmente y se puede exportar).
- Los comentarios **dentro** de un bloque que el editor sustituye entero (p. ej. un widget sin `id` cuyo tipo cambia) se pierden; el resto del fichero no se toca.
- Las rutas de imágenes y fuentes locales se escriben relativas al YAML.
