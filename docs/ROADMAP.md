# Roadmap

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Benchmark, casos de uso, diseño técnico, UML, definición del AST | ✅ Entregada |
| 1 | MVP: canvas, Label/Button/Image, guardado JSON, generador ESPHome, simulación básica | ✅ Entregada (autoprueba 17/17 en Windows) |
| 2 | Parser YAML → AST → modelo; reconstrucción visual; sistema de propiedades | ✅ Entregada (autoprueba 25/25; ver `05_importacion.md`) |
| 3 | Diff/Merge, sincronización en tiempo real, historial integrado con el código | ✅ Entregada (autoprueba 29/29; ver `06_sincronizacion.md`) |
| 4 | Todos los widgets LVGL, temas, estilos y eventos avanzados, generador C LVGL | ✅ Entregada (autoprueba 39/39; ver `07_fase4.md`) |
| 5 | Extensión VS Code (Open Visual Designer, Live Sync, Preview) | ✅ Entregada (autoprueba 42/42; ver `08_vscode.md`) |
| 6 | Simulador profesional: táctil, swipe, rotación, multipantalla, perfilado | ✅ Entregada (autoprueba 46/46; ver `09_simulador.md`) |
| 7 | SDK de plugins: widgets y exportadores externos | ✅ Entregada (autoprueba 49/49; ver `10_plugins.md`) |
| 8 | IA generativa: diseño por prompt, refactorización | ✅ Entregada (autoprueba 53/53; ver `11_ia.md`) |
| 9 | Beta pública: testing masivo, corrección de errores, optimización | ✅ Entregada (autoprueba 57/57; ver `12_beta.md`) |
| 10 | Enterprise: colaboración, versiones visuales, marketplace, licencias | ✅ Entregada (autoprueba 63/63; ver `13_enterprise.md`) |

## Qué incluye la Fase 1

- Canvas con zoom (Ctrl+rueda), desplazamiento (botón central o Espacio+arrastrar), rejilla y ajuste a rejilla.
- Paleta con Label, Button e Image: arrastrar al canvas o doble clic.
- Mover, redimensionar con tiradores, selección múltiple con recuadro, Ctrl+clic, flechas (Mayús = 10 px).
- Alinear y traer al frente / enviar atrás.
- Copiar, pegar, duplicar y eliminar.
- Varias páginas (pantallas) con su color de fondo.
- Panel de propiedades por tipo de widget y editor de eventos (cambiar de página, acción de Home Assistant, log, YAML libre).
- Árbol del proyecto.
- YAML ESPHome en vivo y exportación a carpeta (`ui_lvgl.yaml`, `main.yaml` plantilla, `images/`).
- Simulador básico: pulsar botones, botones conmutables, navegación entre páginas, registro de acciones.
- Deshacer/rehacer ilimitado, autoguardado cada minuto con recuperación, recientes en SQLite.
