# Fase 0 · 01 — Benchmark: LVGL Pro y SquareLine Studio

Fecha del análisis: noviembre de 2026.

## 1. Panorama

| | **LVGL Pro (Editor)** | **SquareLine Studio / Vision** | **Open LVGL Studio (objetivo)** |
|---|---|---|---|
| Fabricante | Equipo de LVGL | SquareLine Kft. | Open source |
| Formato fuente | XML declarativo de LVGL + C | Proyecto propietario `.spj` → C/MicroPython | JSON abierto (`.olvgl`) ↔ ESPHome YAML / C |
| Salida | C para LVGL | C (y MicroPython) | **ESPHome YAML** (Fase 1), C LVGL (Fase 4) |
| ESPHome | No | Studio: descartado; Vision: anunciado | **Nativo, primera clase** |
| Ingeniería inversa de código | No (el XML es la fuente) | No | **Sí** (Fase 2: YAML, lambdas, C++) |
| Sincronización código ↔ diseño | Parcial (XML) | No (exporta en una dirección) | **Bidireccional** (Fase 3) |
| Licencia gratuita | Community: no comercial, sin CLI | Vision Free: 5 pantallas / 50 widgets, no comercial | Libre, sin límites |
| Licencia comercial | Product: 20.000 USD por producto (5 años) | Vision Business: 79–280 USD/puesto/mes | Doble licencia (Fase 10) |
| Plataformas | Win / Linux / macOS (x64, arm64) | Win / Linux / macOS | Win / Linux / macOS (Qt6) |

## 2. LVGL Pro

**Qué ofrece**

- Editor de escritorio, CLI (solo en planes de pago) y visor en navegador.
- Interfaz definida en **XML** declarativo: componentes, estilos y pantallas como ficheros de texto versionables.
- *Figma Flow*: importar diseños desde Figma.
- Variantes de producto y compartición online de proyectos.

**Modelo de negocio**: plan Community gratuito sólo para uso personal/evaluación; planes comerciales por producto (Product: 20.000 USD con licencia mínima de 5 años) más soporte de pago.

**Lecciones para Open LVGL Studio**

- Un formato fuente **textual y diffable** es clave para Git → nuestro `.olvgl` es JSON ordenado y estable.
- La separación componente/estilo/pantalla del XML es buena referencia para nuestro modelo de estilos (Fase 4).
- Su ausencia de ESPHome es nuestro hueco principal de mercado.

## 3. SquareLine Studio / SquareLine Vision

**Qué ofrece**

- Editor WYSIWYG maduro: arrastrar y soltar, pantallas, animaciones, temas, eventos con acciones predefinidas.
- Exportación a C para LVGL (plantillas por placa) y simulador integrado.
- Vision (sucesor): versión web + escritorio con colaboración y límites por pantallas/widgets según plan.

**ESPHome**: en septiembre de 2026 el soporte del foro confirmó que **SquareLine Studio no tendrá soporte ESPHome**; se trasladará a SquareLine Vision, sin fecha.

**Puntos débiles detectados**

1. Exportación en una sola dirección: editar el C generado rompe la relación con el diseño.
2. Límites de pantallas/widgets en planes baratos.
3. Formato de proyecto cerrado.
4. Sin ingeniería inversa de código existente.

## 4. ESPHome + LVGL (plataforma destino)

- ESPHome integra LVGL como componente `lvgl:` configurado en YAML (páginas, widgets, estilos, eventos y acciones), con lambdas C++ para lógica.
- En 2026 ESPHome ha migrado de LVGL 8 a **LVGL 9.x** (9.5 y luego 9.6, PR esphome#20257 en el hito 2026.11.0). La migración no rompe el YAML existente, pero cambia detalles visuales por defecto (p. ej. opacidad de arcos, sombra de 1 px en botones). El generador debe ser **consciente de la versión**: Fase 1 apunta a LVGL 9 con YAML compatible hacia atrás.
- Hoy los usuarios escriben el YAML a mano: no hay editor visual que lea y escriba ESPHome directamente. **Ese es el núcleo de valor de Open LVGL Studio.**

## 5. Matriz de funcionalidades priorizada

| Funcionalidad | LVGL Pro | SquareLine | Prioridad | Fase |
|---|:-:|:-:|:-:|:-:|
| Canvas WYSIWYG con zoom/pan | ✔ | ✔ | Alta | 1 |
| Label / Button / Image | ✔ | ✔ | Alta | 1 |
| Exportar ESPHome YAML | ✘ | ✘ | **Crítica** | 1 |
| Simulador | ✔ | ✔ | Alta | 1 (básico) / 6 |
| Importar YAML ESPHome | ✘ | ✘ | **Crítica** | 2 |
| Sincronización bidireccional | ~ | ✘ | **Crítica** | 3 |
| Todos los widgets LVGL | ✔ | ✔ | Alta | 4 |
| Estilos y temas | ✔ | ✔ | Alta | 4 |
| Extensión VS Code | ✘ | ✘ | Media | 5 |
| Plugins | ~ | ✘ | Media | 7 |
| IA generativa | ~ | ~ | Media | 8 |
| Colaboración | ✔ | ✔ (Vision) | Baja | 10 |

## Referencias

- Precios y planes LVGL Pro: https://lvgl.io/pro/pricing
- Licencias SquareLine Vision: https://docs.vision.squareline.io/docs/licenses_limitations
- Hilo SquareLine + ESPHome: https://forum.squareline.io/t/squareline-esphome/5301
- Migración de ESPHome a LVGL 9.5: https://github.com/esphome/esphome/pull/12312
- Migración de ESPHome a LVGL 9.6: https://github.com/esphome/esphome/pull/20257
