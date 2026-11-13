# Fase 9 — Beta pública

Objetivo: que cualquiera pueda instalarla y usarla con su panel, y que lo que falle se pueda reproducir y corregir.

## 1. Pruebas masivas

| Prueba | Qué comprueba | Cómo |
|---|---|---|
| Sesiones de edición al azar | Cada pocos pasos: ids únicos, el YAML se analiza, importar→generar da el mismo texto, el JSON conserva el proyecto, el C se genera (y compila), la disposición se calcula. Al final, deshacer todo = proyecto inicial y rehacer = final. | `python tools/fuzz.py --sessions 500 --steps 80` |
| YAML dañado | Líneas borradas, duplicadas, mal sangradas, valores raros, ficheros cortados: el importador acepta o da un error con línea; nunca otra excepción. Lo importado se regenera de forma estable. | `python tools/fuzz.py --sessions 0 --yaml 2000` |
| Compilación del C | `ui.c` compila con `-Wall -Werror` contra LVGL 9.5 y 9.6. | `OLVGL_LVGL_INC=…/lvgl:…/conf python tools/fuzz.py --c` |
| Pruebas unitarias | 173 pruebas, incluidas 25 sesiones al azar y 250 YAML dañados (`tests/test_fuzz.py`). | `python -m pytest` |
| Autoprueba de la interfaz | 57 comprobaciones en Windows con capturas; incluye una tanda de pruebas masivas y medidas de rendimiento. | `autoprueba.bat` |

Un fallo de `fuzz.py` se guarda en `fuzz_fallos/<semilla>.json` con las operaciones que lo producen; la misma semilla lo repite siempre.

## 2. Correcciones

Ver `CHANGELOG.md` (0.9.0b1).

## 3. Optimización

Medido con tu panel real (605 widgets, 8 páginas, ~7 000 líneas) en la autoprueba (`capturas/rendimiento.txt`): importar, cambiar de página, mover un widget, actualizar la vista de código y generar el YAML. La vista de código ahora sólo sustituye el trozo que cambia.

## 4. Informar de un problema

1. **Ayuda › Informe de diagnóstico… › Copiar** (o Guardar).
2. Describe qué hacías y qué esperabas; si puedes, adjunta el YAML o el `.olvgl` (o un trozo que lo reproduzca).
3. Si la aplicación avisó de un *error inesperado*, adjunta también el `error_*.txt` de **Ayuda › Abrir carpeta de registros**.

El informe no incluye claves de API, contraseñas ni el contenido de tus ficheros; las rutas de tu carpeta personal aparecen como `~`.

## 5. Publicar la beta

```
python tools/build_release.py           →  dist/OpenLVGLStudio-0.9.0b1.zip  (+ .sha256)
```

El paquete lleva la aplicación, los plugins de ejemplo, la documentación, ejemplos, pruebas y la extensión de VS Code ya empaquetada. Excluye `.venv`, cachés, capturas, autoguardados y los ficheros privados de `PRIVATE` (p. ej. `examples/panel-domotica_final.yaml`). Quien lo reciba: descomprimir → `install.bat` → `run.bat` (y `autoprueba.bat` para comprobar su equipo).

## 6. Limitaciones conocidas de la beta

- Plataforma probada: Windows 11 con Python 3.11–3.15. Linux y macOS deberían funcionar (todo es Python + Qt) pero no se prueban.
- El simulador ejecuta las acciones de LVGL; las lambdas y las acciones de Home Assistant sólo se registran.
- Fuentes propias (`font:` con ficheros TTF o de Google Fonts) se dibujan con la más parecida instalada; Montserrat se ve exacta.
- `online_image` y las imágenes que no están en disco se dibujan como un marco.
- No hay importación de código C de LVGL (sólo exportación).
- El generador de IA local entiende peticiones típicas de domótica; para instrucciones libres hace falta un proveedor (Claude, OpenAI, Ollama, LM Studio).
- Sin instalador firmado: se instala con `install.bat` sobre Python.
