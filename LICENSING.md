# Licencia de Open LVGL Studio

Open LVGL Studio se ofrece con **licencia doble**. Elige la que te convenga:

1. **GNU General Public License v3.0 o posterior** (`GPL-3.0-or-later`, texto completo en [`LICENSE`](LICENSE)).
   Puedes usarlo, estudiarlo, modificarlo y redistribuirlo gratis. Si distribuyes la aplicación o una versión
   modificada, tienes que hacerlo también bajo la GPL y con su código fuente.
2. **Licencia comercial** ([`COMMERCIAL-LICENSE.md`](COMMERCIAL-LICENSE.md)).
   Para empresas que no quieren o no pueden cumplir la GPL (integrarlo en un producto cerrado, redistribuirlo sin
   publicar sus cambios) o que necesitan las ediciones **Pro** o **Enterprise** con soporte.

## Ediciones

| Edición | Incluye |
|---|---|
| **Community** (GPL, gratis) | Diseñador completo: lienzo, todos los widgets de LVGL, estilos y temas, eventos, simulador, exportar ESPHome y código C, plugins, versiones, colaboración en carpeta compartida y componentes |
| **Pro** | Community + **importar y sincronizar YAML de ESPHome** + **extensión de VS Code** (vista previa, Live Sync, diagnósticos, exportar C desde el editor) |
| **Enterprise** | Pro + **herramientas de IA** (generar páginas, refactorizar, extraer estilos, ids descriptivos) |

> **Sistema de licencias desactivado.** Ahora mismo todas las funciones (incluidas las de Pro y Enterprise) están disponibles sin licencia. El código de licencias se conserva: se reactiva con `ENFORCE_DEFAULT = "1"` en `olvgl/application/licensing.py` o arrancando con `OLVGL_LICENSE_ENFORCE=1`.

La edición la da un fichero de licencia firmado (Ayuda › Licencia). Las funciones de cada edición están en
`olvgl/application/licensing.py` (`FEATURES`).

> Como el código se publica bajo GPL, cualquiera puede compilar una versión sin comprobaciones. La licencia
> comercial no es una protección técnica sino un permiso legal (usar el software fuera de los términos de la GPL)
> más lo que el vendedor ofrezca (soporte, actualizaciones, facturas).

## Lo generado es tuyo

El YAML de ESPHome, el código C y los proyectos que crees con la aplicación son tuyos y no quedan sujetos a la
GPL ni a la licencia comercial.

## Componentes de terceros

Ver [`olvgl/resources/THIRD_PARTY.md`](olvgl/resources/THIRD_PARTY.md) (Qt/PySide6 LGPL v3, PyYAML MIT,
Montserrat OFL…). Todos son compatibles con la GPL v3 y con una distribución comercial que los respete.

## Contribuciones

Para poder ofrecer la licencia doble, el autor necesita poder relicenciar cada contribución. Quien envíe cambios
debe aceptar un acuerdo de contribución (CLA) que lo permita; sin él, sólo se pueden aceptar contribuciones
pequeñas que el autor reescriba.
