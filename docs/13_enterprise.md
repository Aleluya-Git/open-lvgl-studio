# Fase 10 — Enterprise

Colaboración, control de versiones visual, marketplace de componentes y licencias comerciales. Todo funciona **sin servidor**: con ficheros junto al proyecto, que viajan con él a una carpeta compartida (red, OneDrive, Dropbox, Syncthing…) o a un repositorio Git.

## 1. Rendimiento: mover con las flechas

Antes, cada pulsación de flecha reconstruía el árbol del proyecto entero, recreaba las fuentes y repintaba todos los widgets de la página (~90 ms con tu panel). Ahora el ViewModel informa de qué ha cambiado (`last_change`: geometría, widgets concretos o estructura) y:

- el árbol no se reconstruye si sólo cambia la posición o el tamaño;
- el lienzo sólo repinta los widgets cuya caja o propiedades cambian y conserva las fuentes y colores mientras no cambien los recursos del proyecto.

La autoprueba lo mide (`capturas/rendimiento_f10.txt`) y comprueba que el árbol no se reconstruye.

## 2. Control de versiones visual — Equipo › Versiones (Ctrl+Alt+V)

- **Guardar versión…**: instantánea con nombre en `<proyecto>.versiones/` (junto al `.olvgl` o al YAML vinculado), con autor y fecha.
- **Historial de Git**: si el fichero está en un repositorio, aparecen sus commits (sólo se leen con `git log`/`git show`; nunca se modifica el repositorio).
- **Diferencias visuales**: la versión elegida y el proyecto actual lado a lado, con cada widget marcado en verde (añadido), rojo (eliminado) o ámbar (cambiado), y la lista de cambios (geometría, propiedades, eventos, contenedor, orden; páginas, estilos, fuentes, imágenes, pantalla).
- **Restaurar esta versión**: sustituye el proyecto como un cambio que se puede deshacer.

Código: `olvgl/domain/visual_diff.py`, `olvgl/infrastructure/versions.py`, `olvgl/presentation/versions_ui.py`.

## 3. Colaboración multiusuario

- **Fusión al guardar**: si otra persona guardó el mismo `.olvgl` desde que lo abriste, al guardar se hace una fusión a tres bandas (lo común, lo tuyo, lo suyo) widget a widget y propiedad a propiedad. Si los dos cambiasteis lo mismo, se queda lo tuyo y se te enseña la lista de conflictos. La fusión se deshace con Ctrl+Z. (`olvgl/domain/project_merge.py`)
- **Presencia**: la barra de estado muestra 👥 quién más tiene abierto el proyecto (latido cada minuto en `<proyecto>.presencia/`), y avisa si alguien ha guardado.
- **Comentarios de revisión** (Equipo › Comentarios, Ctrl+Alt+C): sobre el widget seleccionado o la página, con respuestas y «resuelto». Se ven como globos amarillos sobre los widgets y se guardan en `<proyecto>.comentarios.json`, fusionándose con los de los demás.
- Con YAML vinculado, la sincronización de la Fase 3 ya fusiona los cambios hechos a mano o por otros en el YAML.

## 4. Marketplace de componentes — Equipo › Componentes (Ctrl+Alt+K)

- **Guardar selección como componente…**: los widgets seleccionados (con sus hijos, estilos, fuentes e imágenes) en un paquete `.olvglc` con nombre, autor, descripción, etiquetas y licencia.
- **Biblioteca**: componentes instalados, con vista previa; **Insertar en la página** (dentro del contenedor seleccionado si lo hay) con ids únicos y referencias de eventos renombradas; exportar e instalar desde fichero.
- **Catálogo**: un `index.json` local o en una URL. Cada componente se descarga y se comprueba con su SHA-256 antes de instalarse. Viene un catálogo de ejemplo (`marketplace/`: tarjeta de luz, termostato, barra de navegación, medidor de energía).
- **Publicar un catálogo propio**: pon tus `.olvglc` en una carpeta, genera su índice con `olvgl.infrastructure.components.build_index(carpeta)` (o adapta `tools/build_components.py`) y súbela a cualquier web; en el catálogo pega la URL de su `index.json`.

## 5. Licencias comerciales — Ayuda › Licencia

- Licencias firmadas con **Ed25519** (implementación propia en Python puro, comprobada con el vector del RFC 8032): la aplicación sólo lleva claves públicas (`olvgl/resources/license_public_keys.txt`); no se pueden falsificar sin la clave privada.
- Ediciones (licencia doble GPL-3.0-or-later o comercial, ver `LICENSING.md`):
  - **Community**: todo el diseñador, simulador, exportar ESPHome y C, plugins, versiones, colaboración y componentes;
  - **Pro**: además **importar y sincronizar YAML** (menú, abrir un `.yaml`, revincular un proyecto) y la **extensión de VS Code** (la orden `serve` y las órdenes de la línea de comandos que leen YAML responden «requiere Pro»);
  - **Enterprise**: además las **herramientas de IA** (menú IA y la orden `generate`).
  Se configura en `olvgl/application/licensing.py` (`FEATURES`). `OLVGL_LICENSE_ENFORCE=0` desactiva las comprobaciones (desarrollo y pruebas); `OLVGL_LICENSE=ruta` usa una licencia compartida de la empresa.
- La clave pública del autor ya está registrada en `olvgl/resources/license_public_keys.txt`.
- `tools/license_tool.py`:
  - `keygen [--register]` crea tu clave privada en `~/.olvgl/licencias/` (nunca en el proyecto) y registra la pública;
  - `sign --licensee "Empresa" --edition pro --seats 5 --days 365 --out cliente.olvgl-lic` emite una licencia;
  - `verify fichero` la comprueba.
- El usuario la carga en **Ayuda › Licencia › Cargar licencia…**; se guarda en su carpeta de datos.
- Pestaña **Licencias de terceros** (`olvgl/resources/THIRD_PARTY.md`): Qt/PySide6 (LGPLv3), PyYAML (MIT), Montserrat (OFL)… Tenlo en cuenta al distribuir una edición comercial.

Licencia de la aplicación: doble, GPL-3.0-or-later o comercial (`LICENSE`, `COMMERCIAL-LICENSE.md`, `LICENSING.md`).

## Pruebas

- `tests/test_versions.py`, `tests/test_collab.py`, `tests/test_components.py`, `tests/test_licensing.py`: diferencias, instantáneas, historial de Git, fusión a tres bandas (también con proyectos aleatorios), presencia, comentarios de dos personas, paquetes y catálogo con SHA-256, Ed25519 y licencias manipuladas o caducadas.
- Autoprueba F10: rendimiento al mover, versiones con capturas, dos personas en la misma carpeta, componentes del catálogo, licencias.
