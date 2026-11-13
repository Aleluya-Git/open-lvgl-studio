# Novedades

## 0.10.0b1 — Enterprise (Fase 10)

- **Pantalla personalizada desde el panel lateral**: Propiedades del proyecto › Placa › «＋ Nueva pantalla personalizada…» y «★ Guardar esta pantalla en Mis pantallas».
- **Importar YAML más robusto**: páginas de GitHub guardadas como .yaml (se recupera el YAML y no se vincula), ficheros en UTF-16/Windows-1252, caracteres nulos y mensajes claros con línea y columna para caracteres no permitidos.
- **Licencia doble** GPL-3.0-or-later o comercial; ediciones activas: Pro (importar/sincronizar YAML y extensión de VS Code) y Enterprise (IA). Clave pública del autor registrada.
- **Pantallas propias al crear un proyecto**: «Personalizada…» con nombre, tamaño y ⇄ Girar; se guardan en «Mis pantallas» (★) y aparecen también en las propiedades del proyecto, al importar y en el simulador.
- **Más rápido al mover con las flechas**: el árbol ya no se reconstruye y el lienzo sólo repinta lo que cambia (antes ~90 ms por pulsación con un panel de 600 widgets).
- **Versiones** (Equipo › Versiones): instantáneas con nombre e historial de Git, diferencias visuales lado a lado y restaurar con deshacer.
- **Colaboración**: fusión a tres bandas al guardar si otra persona guardó antes, presencia en la barra de estado y comentarios de revisión con globos sobre los widgets.
- **Componentes**: guardar la selección como componente `.olvglc`, biblioteca, catálogo local o por URL con SHA-256 y cuatro componentes de ejemplo.
- **Licencias**: ediciones Community/Pro/Enterprise con licencias Ed25519, `tools/license_tool.py` para emitirlas y licencias de terceros. Nada se bloquea en la beta.

## 0.9.0b1 — Beta pública (Fase 9)

**Pruebas masivas**
- `tools/fuzz.py`: miles de sesiones de edición al azar (todos los widgets y acciones, deshacer/rehacer, estilos, páginas…) comprobando que el YAML generado se analiza, que importarlo y regenerarlo da el mismo texto, que el JSON conserva el proyecto, que el C compila con LVGL 9.5 y 9.6 y que deshacer todo vuelve al principio. También YAML dañados a propósito: el importador o los acepta o da un error con su línea, nunca se cae.
- Resultado antes de publicar: 600 sesiones de 80 operaciones, 4 000 YAML dañados y 230 compilaciones de C (LVGL 9.5 y 9.6) sin fallos tras las correcciones de abajo.

**Correcciones**
- Un mismo evento repetido en un widget (dos `on_click`) se unía mal: ahora se fusionan sus acciones (ESPHome no admite claves repetidas) y el código C no define dos veces la misma función.
- Direcciones de mosaicos, listas desplegables y pestañas escritas a mano («LEFT | right», valores no válidos) ya no generan C que no compila: se filtran y se avisa.
- Un `src:` de imagen que no es un texto (p. ej. un mapa) ya no impide generar el YAML.
- `pages:` vacío en un YAML importado ya no cambia el orden de las secciones al regenerar.
- Claves repetidas en el YAML (dos `widgets:` en el mismo widget, dos `then:`…) se avisan con su línea, como hace ESPHome, en lugar de mezclarse en silencio.
- Un botón con `text:` y además un label hijo llamado `<botón>_label` generaba dos widgets con el mismo id.
- Validación nueva: mínimo ≥ máximo en deslizadores, arcos y barras; eventos repetidos; acciones que muestran/ocultan o actualizan widgets que no existen.

**Rendimiento**
- La vista de código sólo sustituye el trozo del YAML que cambia (antes reescribía y volvía a colorear el fichero entero en cada cambio; con un panel de 7 000 líneas se notaba).

**Beta**
- Errores inesperados: no cierran la aplicación; se autoguarda el proyecto, se guarda un informe en la carpeta de registros y se avisa con la opción de copiarlo.
- Ayuda › Informe de diagnóstico (versiones, plugins, proyecto y registro, sin claves ni contenido), Abrir carpeta de registros, Guía de usuario (F1) y Novedades.
- Registro en `%APPDATA%\OpenLVGLStudio\logs\olvgl.log`.
- `tools/build_release.py` crea el paquete de la beta (`dist/OpenLVGLStudio-<versión>.zip` + SHA-256) con la extensión de VS Code; nunca incluye ficheros personales y se niega a empaquetar si encuentra algo parecido a una clave.
- `pyproject.toml`: `pip install .` instala las órdenes `olvgl` y `open-lvgl-studio`.
- `install_vscode.bat` encuentra la extensión de cualquier versión.

## 0.8.0 — IA generativa (Fase 8)
Generar y refactorizar páginas con IA (local, Claude o compatible con OpenAI), extraer estilos e ids descriptivos. Ver `docs/11_ia.md`.

## 0.7.0 — SDK de plugins (Fase 7)
Widgets, exportadores, reglas y órdenes de plugins. Ver `docs/10_plugins.md`.

## 0.6.0 — Simulador profesional (Fase 6)
Gestos, varios dispositivos y rotación, perfil de RAM/flash, grabar sesiones. Ver `docs/09_simulador.md`.

## 0.5.0 — VS Code (Fase 5)
Extensión con Live Sync, vista previa y diagnósticos. Ver `docs/08_vscode.md`.

## 0.4.x — Soporte completo de LVGL (Fase 4)
Todos los widgets, estilos por parte y estado, temas, eventos avanzados, código C para LVGL 9; iconos, idiomas y menús por grupos.

## 0.3.0 — Sincronización bidireccional (Fase 3)
## 0.2.0 — Importación de YAML (Fase 2)
## 0.1.0 — MVP (Fase 1)
