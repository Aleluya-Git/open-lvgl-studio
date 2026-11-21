# Open LVGL Studio

Diseñador visual de interfaces **LVGL para ESPHome**: dibujas la pantalla y obtienes el YAML listo para tu dispositivo.

Versión **0.10.0b3 — beta pública con funciones Enterprise** (Fases 0 a 10: versiones visuales, colaboración en carpetas compartidas, marketplace de componentes y licencias; pruebas masivas, informes de error y paquete de la beta; IA generativa, SDK de plugins, simulador profesional, extensión de VS Code, MVP, importación de YAML existente, sincronización bidireccional con el YAML, todos los widgets de LVGL con estilos, temas y eventos avanzados, y generador de código C para LVGL 9).

## Instalación (Windows)

**Con el instalador** (recomendado): descarga `OpenLVGLStudio-<versión>-Setup.exe` de las *Releases* y ejecútalo. No pide permisos de administrador: busca Python 3.11+ (si no lo tienes, ofrece instalarlo con winget), instala la aplicación en `%LOCALAPPDATA%\Programs\Open LVGL Studio` con sus dependencias, crea los accesos directos del menú Inicio y del escritorio y la entrada para desinstalarla en *Aplicaciones instaladas*. Para actualizar, ejecuta el instalador nuevo encima. Opciones: `/S` (sin preguntas) y `/D=carpeta`. Se genera con `python tools/build_installer.py` (necesita Go 1.21+).

**Con el .zip** (o el código fuente):

1. Python 3.11 o superior.
2. `install.bat` → crea `.venv` e instala PySide6, PyYAML y pytest.
3. `run.bat` → abre la aplicación (`run.bat ruta\proyecto.olvgl` abre un proyecto).
4. `autoprueba.bat` → ejecuta los tests y recorre la interfaz sin ventana; deja `autoprueba_resultado.txt` y capturas en `capturas\`.

Guía de usuario: [`docs/GUIA_USUARIO.md`](docs/GUIA_USUARIO.md) (también en **Ayuda › Guía de usuario**, F1). Novedades: [`CHANGELOG.md`](CHANGELOG.md).

## Equipo (Fase 10)

- **Versiones** (Ctrl+Alt+V): instantáneas con nombre e historial de Git, comparadas visualmente con el proyecto actual (añadido/eliminado/cambiado) y restaurables.
- **Colaboración** en una carpeta compartida: fusión automática al guardar si otra persona guardó antes, quién más lo tiene abierto y **comentarios** de revisión sobre los widgets (Ctrl+Alt+C).
- **Componentes** (Ctrl+Alt+K): guarda una selección como componente, instálalos desde un catálogo (local o URL, verificados con SHA-256) e insértalos con ids únicos.
- **Licencia** (Ayuda): ediciones Community/Pro/Enterprise con licencias firmadas (Ed25519) y licencias de terceros (las comprobaciones están desactivadas: todo está disponible).
- **Estilo completo**: degradados (botones, contenedores, barras, deslizadores, arcos), sombra, contorno, texto, relleno, arco, línea…; indicador de aguja con escalas, marcas, agujas y arcos editables; tamaño de rejilla ajustable.

Detalles en [`docs/13_enterprise.md`](docs/13_enterprise.md).

## Beta pública: informar de un problema

**Ayuda › Informe de diagnóstico… › Copiar** y adjúntalo junto con lo que hacías (y, si puedes, el YAML que lo provoca). Si apareció un aviso de *error inesperado*, añade el `error_*.txt` de **Ayuda › Abrir carpeta de registros**. El informe no contiene claves ni el contenido de tus ficheros. Detalles, pruebas masivas y limitaciones conocidas en [`docs/12_beta.md`](docs/12_beta.md).

Para generar el paquete de la beta: `python tools/build_release.py` → `dist/OpenLVGLStudio-<versión>.zip`.

## Uso rápido

| Acción | Cómo |
|---|---|
| Añadir widget | Arrastra desde **Widgets** al canvas, o doble clic |
| Mover / redimensionar | Arrastra el widget / sus tiradores |
| Selección múltiple | Recuadro con el ratón o Ctrl+clic |
| Mover fino | Flechas (Mayús = 10 px) |
| Zoom | Ctrl+rueda, Ctrl+0 ajustar, Ctrl+1 100 % |
| Desplazar el lienzo | Botón central o Espacio+arrastrar |
| Duplicar / eliminar | Ctrl+D / Supr |
| Deshacer / rehacer | Ctrl+Z / Ctrl+Y (ilimitado) |
| Simulador | F5 |
| Importar YAML de ESPHome | Ctrl+I (o `run.bat mi_panel.yaml`) |
| Exportar ESPHome | Ctrl+E |
| Escribir en el YAML vinculado | Automático (o Ctrl+S / Ctrl+Mayús+Y) |

Abre `examples\demo_salon.olvgl` para ver un ejemplo con dos páginas, una acción de Home Assistant y navegación.

Para probar la importación: **Archivo → Importar YAML de ESPHome…** y elige `examples\importar\panel_demo.yaml` (capa superior, tarjetas con flex y grid, pestañas, estilos, colores con nombre, lambdas). Detalles en [`docs/05_importacion.md`](docs/05_importacion.md).

## Trabajar sobre tu YAML (sincronización)

Al importar un YAML queda **vinculado**: lo que cambies en el editor se escribe en ese fichero tocando sólo las líneas afectadas (comentarios, formato y el resto de secciones intactos), y si lo editas a mano la app se actualiza sola (Ctrl+Z deshace el cambio externo). La primera escritura guarda `tu_fichero.yaml.olvgl.bak`. Detalles en [`docs/06_sincronizacion.md`](docs/06_sincronizacion.md).

## Llevarlo a ESPHome

**Exportar ESPHome…** escribe en la carpeta elegida:

- `ui_lvgl.yaml` — páginas y widgets (se regenera en cada exportación).
- `images/` — las imágenes usadas.
- `main.yaml` — plantilla de dispositivo, **sólo si no existe** (nunca se sobrescribe).

En tu YAML de dispositivo (con `display:` y `touchscreen:` de tu placa):

```yaml
packages:
  ui: !include ui_lvgl.yaml
```

Si usas acciones de Home Assistant, activa en HA → ESPHome → *Configurar* la opción que permite al dispositivo realizar acciones.

## Plugins

**Plugins › Gestionar plugins** activa, desactiva, recarga y crea plugins. Un plugin puede añadir:

- **widgets compuestos**, que se exportan como widgets estándar de LVGL;
- **exportadores**, en Archivo › Exportar;
- **reglas** para revisar el proyecto (Plugins › Comprobar el proyecto, y también en VS Code);
- **órdenes** que cambian el proyecto, con deshacer.

Vienen tres de ejemplo: la *tarjeta de sensor*, la *documentación Markdown/CSV* y las *reglas de usabilidad*. El SDK se explica en [`docs/10_plugins.md`](docs/10_plugins.md); para empezar uno desde la plantilla: `python -m olvgl.cli new-plugin mi_plugin`.

## Simulador (F5)

- **Gestos de pantalla táctil como en LVGL**:
  - arrastrar desplaza páginas y contenedores (y cancela el clic, como en el equipo);
  - deslizar cambia de mosaico o de pestaña y dispara `on_swipe_*`;
  - pulsación larga con repetición y doble clic.
- **Varios dispositivos a la vez**, cada uno con su resolución y giro (0/90/180/270°), con navegación sincronizada. Cada uno guarda capturas a resolución real.
- **Grabar y reproducir** una sesión de toques.
- **Reposo** (`on_idle`), `page_wrap`/`skip` y `on_load` de las páginas.
- Pestaña **Rendimiento**: tiempos de dibujo y estimación de RAM, búfer y flash en el ESP32, con avisos (también con `python -m olvgl.cli profile panel.yaml`). Detalles en [`docs/09_simulador.md`](docs/09_simulador.md).

## VS Code

Ejecuta **`install_vscode.bat`**: empaqueta e instala la extensión y le dice dónde está la aplicación. En un YAML con `lvgl:`:

- **Ctrl+Alt+D** — abrir en el diseñador. Live Sync: lo que cambies en un lado aparece en el otro.
- **Ctrl+K V** — vista previa al lado. Sigue lo que escribes aunque no lo guardes; un clic en un widget salta a su línea.
- Los avisos aparecen en **Problemas**, y hay fragmentos `lvgl-…` y la orden «LVGL: Exportar código C».

También funciona sin VS Code: `python -m olvgl.cli render panel.yaml --out carpeta` dibuja todas las páginas a PNG (detalles en [`docs/08_vscode.md`](docs/08_vscode.md)).

## Interfaz

- **Idioma**: español, inglés, francés y alemán (**Ver › Idioma**). El primer arranque usa el idioma del sistema si es uno de los cuatro; el cambio se aplica al reiniciar (la aplicación ofrece reiniciar al momento).
- **Menús por función**: Archivo · Editar · Insertar · Diseño · Ver · Simulación · IA · Equipo · Plugins · Ayuda, con iconos en color y separadores por grupos. **Insertar** contiene todos los widgets por categoría.
- **Barras de herramientas** por grupos (archivo, edición, diseño, vista, ESPHome, simulación) que se pueden mover u ocultar.
- **Icono y logotipo** propios; `install.bat` crea el acceso directo «Open LVGL Studio» con el icono. Los iconos de los widgets se usan en la paleta, el árbol y el menú Insertar.
- El canvas dibuja con **Montserrat** (la fuente por defecto de LVGL), incluida en `olvgl/resources/fonts` bajo licencia SIL OFL, así que se ve igual en cualquier equipo.
- Los recursos gráficos se regeneran con `python tools/build_assets.py` y las traducciones con `python tools/translations.py` (comprueba con `python tools/i18n_keys.py` que no falta ninguna).

## Estilos, temas y eventos

- **Paleta**: los 24 widgets de LVGL agrupados en Básicos, Controles, Indicadores, Contenedores y Media.
- **Estilo por parte y estado** en el panel de propiedades: elige la parte (principal, indicador, tirador…) y el estado (pulsado, activado, desactivado…) y ajusta fondo, borde, radio, texto, sombra, relleno y opacidad.
- **Diseño › Estilos y tema…**: estilos reutilizables (`style_definitions`) y tema por tipo de widget (`theme`); cada widget marca en «Estilos aplicados» los que usa.
- **Eventos**: mostrar/ocultar/activar widgets, cambiar sus propiedades (`lvgl.<tipo>.update`), acciones de componentes (`light.toggle`, `script.execute`…), esperas, lambdas y YAML libre. El simulador ejecuta las acciones de LVGL sobre una copia: el diseño no cambia.

## IA generativa

- **IA › Generar página con IA… (Ctrl+G)**: describe la página («luces del salón y la cocina, termostato, tema oscuro») y la aplicación la diseña, la valida (widgets del catálogo, dentro de la pantalla, fuentes existentes) y la muestra en una vista previa antes de añadirla. Se puede deshacer con Ctrl+Z.
- **IA › Refactorizar página con IA… (Ctrl+Shift+G)**: una instrucción («tema claro y botones más grandes») sobre la página actual, con las diferencias del YAML antes de aplicar.
- **Extraer estilos repetidos** e **Ids descriptivos**: refactorizaciones sin IA, deterministas, que no cambian el aspecto y actualizan todas las referencias.
- Proveedores: **generador local** (plantillas, sin conexión ni clave), **Claude** (Anthropic) o cualquier API **compatible con OpenAI** (OpenAI, LM Studio, Ollama). Se configuran en **IA › Configurar IA…**. Sólo se envía el diseño de LVGL.
- Línea de órdenes: `python -m olvgl.cli generate "página de luces" --out pagina.yaml`. Detalles en [`docs/11_ia.md`](docs/11_ia.md).

## Código C para LVGL 9 (sin ESPHome)

**Archivo › Exportar código C (LVGL 9)…** escribe `ui.c` y `ui.h` para LVGL 9.5 o superior (probado sin avisos con 9.5 y 9.6). Llama a `ui_init()` tras inicializar LVGL y el driver de pantalla. El informe indica qué fuentes Montserrat activar en `lv_conf.h` y qué fuentes e imágenes propias convertir. Las acciones que sólo existen en ESPHome llaman a `ui_action_handler(id, evento, acción)`, que puedes asignar en tu código. Detalles en [`docs/07_fase4.md`](docs/07_fase4.md).

## Estructura

```
olvgl/
  domain/          modelo, catálogo de widgets, AST YAML
  application/     ViewModel (MVVM), historial, comandos, motor del simulador
  infrastructure/  JSON, SQLite, parser/emitter YAML, generadores ESPHome y C, sincronización
  presentation/    PySide6: canvas, paneles, simulador, diálogos
docs/              Fase 0: benchmark, casos de uso, arquitectura + UML, AST, roadmap
tests/             tests del núcleo (pytest)
examples/          proyecto de ejemplo
```

Documentación de diseño en [`docs/`](docs/). Todas las fases del roadmap están entregadas (ver [`docs/ROADMAP.md`](docs/ROADMAP.md)).

## Licencia

Licencia doble: **GPL-3.0-or-later** ([`LICENSE`](LICENSE)) o **comercial** ([`COMMERCIAL-LICENSE.md`](COMMERCIAL-LICENSE.md)). Ediciones:

- **Community** (gratis): el diseñador completo, simulador, exportar ESPHome y C, plugins, versiones, colaboración y componentes.
- **Pro**: además importar y sincronizar YAML de ESPHome y la extensión de VS Code.
- **Enterprise**: además las herramientas de IA.

> **Sistema de licencias desactivado.** Ahora mismo todas las funciones (incluidas las de Pro y Enterprise) están disponibles sin licencia. El código de licencias se conserva: se reactiva con `ENFORCE_DEFAULT = "1"` en `olvgl/application/licensing.py` o arrancando con `OLVGL_LICENSE_ENFORCE=1`.

Detalles en [`LICENSING.md`](LICENSING.md). Lo que generas (YAML, C, proyectos) es tuyo.
