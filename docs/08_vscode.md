# Fase 5 — Extensión de VS Code

## Piezas

```
VS Code ──(extension.js)──┬─ spawn ─▶ python main.py fichero.yaml      (diseñador, vinculado al YAML)
                          └─ stdin/stdout JSON ─▶ python -m olvgl.cli serve   (motor sin ventana)
```

- **`olvgl/cli.py`**: línea de órdenes que reutiliza el núcleo: importador, disposición, render
  del canvas y generador C. Órdenes: `info`, `validate`, `render`, `export-c`, `export-esphome`
  y `serve`.
  - `serve` mantiene Qt cargado (QGuiApplication *offscreen*) y atiende peticiones JSON, una por
    línea. Así la vista previa no paga el arranque en cada cambio.
  - Si una petición falla, el servidor sigue vivo.
- **`vscode-extension/`**: JavaScript sin compilar ni dependencias. `tools/build_vsix.py` lo
  empaqueta como `.vsix` sin Node ni `vsce`.

## Funciones

| Función | Cómo |
|---|---|
| Abrir en el diseñador | `Ctrl+Alt+D`, botón de la barra del editor, clic derecho en el editor o en el explorador |
| Live Sync diseñador → VS Code | el diseñador escribe solo las líneas cambiadas (Fase 3) y VS Code recarga el fichero |
| Live Sync VS Code → diseñador | los ficheros abiertos en el diseñador se guardan solos tras una pausa; el diseñador detecta el cambio y lo recarga (con Ctrl+Z para deshacerlo) |
| Vista previa | `Ctrl+K V`: render con el texto **sin guardar**, selector de página, ajustar/100 % |
| Del dibujo al código | clic en un widget → el editor salta a su `id:` |
| Del código al dibujo | al mover el cursor se resalta el widget de ese bloque |
| Problemas | errores de sintaxis con línea y columna, ids repetidos, widgets no reconocidos, acciones que se conservan como YAML libre |
| Exportar C | paleta de comandos › «LVGL: Exportar código C (LVGL 9)…» |
| Fragmentos | `lvgl-page`, `lvgl-label`, `lvgl-button`, `lvgl-switch`, `lvgl-slider`, `lvgl-arc`, `lvgl-flex`, `lvgl-tabview`, `lvgl-goto`, `lvgl-hide`, `lvgl-update` |

## Protocolo de `serve`

Petición (una línea):

```json
{"id": 7, "cmd": "render", "path": "C:/…/panel.yaml", "text": "…opcional…", "page": "inicio", "scale": 1}
```

Respuesta (una línea):

```json
{"id": 7, "ok": true, "result": {"display": {...}, "pages": [...], "rendered": [{"id", "png", "widgets": [{"id", "type", "x", "y", "w", "h", "line"}]}]}}
```

`line` es la línea (base 0) del `id:` del widget en el texto. Con ella funciona el salto del dibujo
al código.

## Instalación

`install_vscode.bat` hace tres cosas:

1. empaqueta la extensión;
2. guarda la carpeta de la aplicación en `%USERPROFILE%\.olvgl\studio_path.txt`;
3. instala la extensión con `code --install-extension`.

Si el comando `code` no está en el PATH, indica cómo instalar el `.vsix` desde VS Code.

## Pruebas

- `tests/test_cli.py`: órdenes, protocolo `serve` y contenido del `.vsix`. Si hay Node.js, también las
  pruebas JavaScript.
- `vscode-extension/test/`:
  - `core.test.js`: localizar la aplicación y Python, detectar `lvgl:`, mapear cursor ↔ widget;
  - `activate.test.js`: activa la extensión con un `vscode` simulado y comprueba que registra todos
    los comandos;
  - `server.test.js`: protocolo real con Python.
- Autoprueba F5: render a PNG, servidor con texto sin guardar y salto al código, `.vsix`.
