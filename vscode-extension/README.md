# Open LVGL Studio para VS Code

Trabaja con los YAML de ESPHome + LVGL sin salir de VS Code y con el diseñador visual a un clic.

## Funciones

- **Abrir en el diseñador** (`Ctrl+Alt+D`, botón en la barra del editor o clic derecho): abre el YAML en
  Open LVGL Studio, vinculado al fichero.
- **Live Sync**: lo que cambias en el diseñador se escribe en el YAML y VS Code lo recarga. Lo que
  escribes en VS Code se guarda solo (tras una pausa) y el diseñador lo recarga. La vista previa
  sigue el texto aunque no lo hayas guardado.
- **Vista previa** (`Ctrl+K V`): la página dibujada igual que en el canvas del diseñador.
  - Selector de página.
  - Clic en un widget: salta a su línea en el YAML.
  - Mover el cursor por el YAML: resalta el widget.
- **Problemas**: los avisos de importación (widgets no reconocidos, ids repetidos, errores de sintaxis
  con su línea) aparecen en el panel «Problemas».
- **Exportar código C (LVGL 9)**: genera `ui.c` y `ui.h` desde la paleta de comandos.
- **Fragmentos**: escribe `lvgl-` para insertar páginas, etiquetas, botones, interruptores, flex,
  pestañas y acciones.

## Requisitos

Open LVGL Studio instalado (su `install.bat`). La extensión lo encuentra de una de estas maneras:

1. el ajuste `olvgl.studioPath`;
2. el fichero `%USERPROFILE%\.olvgl\studio_path.txt`, que escribe `install_vscode.bat`;
3. la carpeta abierta en VS Code;
4. si no lo encuentra, te pide la carpeta.

Usa el Python del `.venv` de la aplicación. Si quieres otro, cámbialo en `olvgl.pythonPath`.

## Ajustes

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| `olvgl.liveSync` | `true` | Vista previa con el texto sin guardar y guardado automático de los ficheros abiertos en el diseñador |
| `olvgl.liveSyncDelay` | `600` | Pausa (ms) antes de actualizar |
| `olvgl.validateOnSave` | `true` | Diagnósticos al abrir y guardar |
| `olvgl.previewScale` | `1` | Resolución de la vista previa |
