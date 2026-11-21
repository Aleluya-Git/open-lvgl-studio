# Guía de usuario — Open LVGL Studio (beta)

Open LVGL Studio es un diseñador visual de pantallas **LVGL para ESPHome**: dibujas la interfaz, la pruebas en el simulador y obtienes el YAML (o código C para LVGL 9) listo para tu placa. Puedes empezar de cero o abrir el YAML que ya tienes.

## 1. Instalar

**Lo más fácil:** ejecuta `OpenLVGLStudio-<versión>-Setup.exe`. Si no tienes Python 3.11 o superior te ofrece instalarlo; después copia la aplicación, instala lo que necesita (hace falta Internet) y crea los accesos directos. Se desinstala desde *Configuración › Aplicaciones*. Tus proyectos y ajustes no se borran al desinstalar ni al actualizar.

**Con el .zip:**

1. Instala **Python 3.11 o superior** (en python.org, marca «Add Python to PATH»).
2. Descomprime `OpenLVGLStudio-<versión>.zip` donde quieras.
3. Ejecuta **`install.bat`**: crea un entorno propio (`.venv`) y el acceso directo «Open LVGL Studio».
4. Abre la aplicación con el acceso directo o con **`run.bat`**.
5. Opcional: **`autoprueba.bat`** comprueba que todo funciona en tu equipo (deja capturas en `capturas\`).
6. Opcional: **`install_vscode.bat`** instala la extensión de VS Code.

## 2. Primeros pasos

| Quiero… | Cómo |
|---|---|
| Usar la pantalla en vertical | **Orientación** en el diálogo de proyecto nuevo o en Propiedades del proyecto (sin nada seleccionado): Horizontal, Vertical o invertidas. En vertical se intercambian ancho y alto y el YAML lleva `lvgl: rotation:` (ESPHome 2026.4 o posterior, que también gira el táctil). Cambiar de placa mantiene la orientación. |
| Empezar un proyecto | **Archivo › Nuevo** (Ctrl+N): elige tu pantalla de la lista o **Personalizada…** para una propia: ponle nombre y tamaño (⇄ Girar cambia horizontal/vertical) y se guarda en **Mis pantallas** (marcadas con ★) para los siguientes proyectos, las propiedades del proyecto y el simulador. Con el proyecto ya creado: panel **Propiedades** (sin nada seleccionado) › Placa › **＋ Nueva pantalla personalizada…** |
| Abrir el YAML que ya tengo | **Archivo › Importar YAML de ESPHome** (Ctrl+I) o `run.bat mi_panel.yaml` |
| Ver un ejemplo | `examples\demo_salon.olvgl` y `examples\importar\panel_demo.yaml` |
| Diseñar con una descripción | **IA › Generar página con IA** (Ctrl+G) |

## 3. La ventana

- **Widgets** (izquierda): arrastra al lienzo o doble clic. También en **Insertar**, por categorías.
- **Lienzo** (centro): la página tal como se verá. Ctrl+rueda = zoom, botón central o Espacio+arrastrar = desplazar.
- **Proyecto** (árbol): páginas, capa superior y widgets anidados. Doble clic en una página para cambiar su nombre. **Arrastra** widgets para cambiar su orden (arriba en la lista = dibujado encima), suéltalos **sobre** un contenedor (obj, botón, pestaña, mosaico) para meterlos dentro o sobre otra página para llevarlos allí; conservan su posición en pantalla. También puedes arrastrar páginas para reordenarlas. Todo se deshace con Ctrl+Z.
- **Propiedades** (derecha): las del widget seleccionado. Para estilos por **parte** (indicador, tirador…) y **estado** (pulsado, activado…) elige parte y estado arriba del editor de estilo.
- **YAML ESPHome** (abajo): el código en vivo. Avisa si hay problemas (ids repetidos, páginas que no existen, mínimos mayores que máximos…).

## 4. Editar

| Acción | Teclas |
|---|---|
| Mover fino | Flechas (Mayús = 10 px) |
| Selección múltiple | Recuadro o Ctrl+clic |
| Copiar / pegar / duplicar | Ctrl+C / Ctrl+V / Ctrl+D |
| Eliminar | Supr |
| Deshacer / rehacer (ilimitado) | Ctrl+Z / Ctrl+Y |
| Alinear, distribuir, ordenar | Menú **Diseño** |

- **Contenedores**: suelta un widget sobre un `obj`, una pestaña o un mosaico para meterlo dentro. Con *layout* FLEX o GRID las posiciones las decide LVGL.
- **Eventos**: en Propiedades › Eventos añade acciones a `on_click`, `on_value`, `on_long_press`, deslizamientos…: cambiar de página, mostrar/ocultar widgets, cambiar sus propiedades, acciones de Home Assistant, esperas, lambdas o YAML libre.
- **Estilos y tema**: **Diseño › Estilos y tema** crea estilos reutilizables y el tema por tipo de widget.
- **Rejilla**: **Ver › Tamaño de la rejilla** (de 2 a 50 px o personalizado); con **Ajustar a la rejilla** los widgets se colocan en ella al moverlos o redimensionarlos.
- **Degradados**: en botones, contenedores, barras, deslizadores y arcos, grupo **Degradado** de las propiedades (dirección, color final, inicio y fin). En el editor de estilo, el grupo **Degradado** sirve para cualquier parte (indicador, tirador…) y estado.
- **Editor de estilo**: los grupos (Fondo, Degradado, Borde, Contorno, Sombra, Texto, Relleno, Arco, Línea, Imagen, Tamaño y posición) se abren y cierran con un clic; «×» quita una propiedad para usar la heredada.
- **Indicador de aguja**: **Editar escalas, marcas y agujas…** en sus propiedades: escalas, marcas con números, agujas (línea o imagen), arcos y rangos de color de las marcas, con vista previa. El valor de cada aguja se cambia también directamente en el panel; con un *id* se puede mover desde ESPHome con `lvgl.indicator.update`.

## 5. Trabajar sobre tu YAML

Al importar, el YAML queda **vinculado**: lo que cambies en el diseñador se escribe sólo en las líneas afectadas (comentarios y el resto del fichero intactos). Si lo editas a mano, la aplicación se actualiza sola y Ctrl+Z deshace ese cambio externo. La primera vez se guarda una copia `.olvgl.bak`.

## 6. Probar: el simulador (F5)

Pulsa botones, arrastra deslizadores, desliza entre pestañas y mosaicos. Puedes abrir varios dispositivos con distinta resolución y giro, grabar una sesión de toques y ver en **Rendimiento** la RAM y la flash estimadas en el ESP32.

## 7. Llevarlo a la placa

- **Archivo › Exportar ESPHome** (Ctrl+E) escribe `ui_lvgl.yaml`, las imágenes y, si no existe, un `main.yaml` de plantilla. En tu YAML de dispositivo: `packages: ui: !include ui_lvgl.yaml`.
- **Archivo › Exportar › Código C (LVGL 9)** para proyectos sin ESPHome (`ui.c`/`ui.h`).
- Si usas acciones de Home Assistant, permite en HA que el dispositivo las realice (ESPHome › Configurar).

## 8. IA

- **IA › Generar página** (Ctrl+G): describe la página («seis luces, termostato y la hora, tema oscuro»). Revisa la vista previa y pulsa **Aplicar**; Ctrl+Z la quita.
- **IA › Refactorizar página** (Ctrl+Mayús+G): una instrucción sobre la página actual, con las diferencias antes de aplicar.
- **Extraer estilos repetidos** e **Ids descriptivos**: ordenan el proyecto sin cambiar su aspecto.
- **IA › Configurar IA**: generador local (sin conexión), Claude o un servicio compatible con OpenAI (incluidos Ollama y LM Studio en tu equipo). Sólo se envía el diseño; la clave queda en tu equipo.

## 9. Trabajo en equipo

- **Equipo › Versiones** (Ctrl+Alt+V): guarda versiones con nombre y compáralas con el proyecto actual: lo añadido en verde, lo eliminado en rojo y lo cambiado en ámbar. Si el proyecto está en Git, también ves sus commits. **Restaurar** se deshace con Ctrl+Z.
- **Carpeta compartida**: si dos personas abren el mismo proyecto, la barra de estado muestra 👥 quién más lo tiene abierto, y al guardar se fusionan los cambios de ambos (si los dos cambiasteis lo mismo, se queda lo tuyo y se te avisa).
- **Comentarios** (Ctrl+Alt+C): comenta el widget seleccionado; aparecen como globos amarillos. Responde, resuelve o elimina desde el panel.
- **Componentes** (Ctrl+Alt+K): selecciona widgets y usa **Guardar selección como componente** para reutilizarlos; instala otros desde el **Catálogo** e insértalos en cualquier página.

## 10. Plugins y VS Code

- **Plugins › Gestionar plugins**: activar, desactivar, recargar y crear plugins (widgets compuestos, exportadores, reglas, órdenes). SDK en `docs/10_plugins.md`.
- **VS Code**: Ctrl+Alt+D abre el YAML en el diseñador; Ctrl+K V muestra la vista previa al lado.

## 11. Si algo falla

- El proyecto se **autoguarda** cada minuto; al volver a abrirlo se ofrece recuperarlo.
- Un error inesperado no cierra la aplicación: se guarda un informe y se avisa.
- **Ayuda › Informe de diagnóstico** reúne versiones, plugins y el registro (sin claves ni contenido) para adjuntarlo a tu aviso. Más detalles en `docs/12_beta.md`.

## 12. Idioma

**Ver › Idioma**: español, inglés, francés y alemán (se aplica al reiniciar).

## 13. Licencia

**Ayuda › Licencia** muestra tu edición y te deja cargar una licencia (`.olvgl-lic`). **Community** (gratis) incluye todo el diseñador; **Pro** añade importar y sincronizar YAML de ESPHome y la extensión de VS Code; **Enterprise** añade las herramientas de IA. Ahora mismo el sistema de licencias está **desactivado**: todas las funciones están disponibles sin licencia.
