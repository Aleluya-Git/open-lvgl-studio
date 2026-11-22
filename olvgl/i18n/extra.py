"""Textos traducibles que no pasan por una llamada literal a tr():
constantes de módulo y nombres de las operaciones de deshacer/rehacer."""
EXTRA = (
    # filtros de los diálogos de ficheros
    "Proyecto Open LVGL Studio (*{ext})", "YAML de ESPHome (*.yaml *.yml)",
    "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.svg)",
    # editor de estilo por parte y estado
    "Fondo", "Opacidad del fondo", "Color del borde", "Grosor del borde", "Radio", "Color del texto",
    "Color de la sombra", "Sombra", "Relleno", "Opacidad",
    # deshacer / rehacer
    "Alinear", "Cambiar geometría", "Distribuir", "Editar estilo", "Editar eventos", "Editar propiedades",
    "Editar tema", "Mover", "Nuevo estilo", "Renombrar", "Eliminar estilo", "Eliminar imagen", "Renombrar estilo",
    "Añadir imagen", "Añadir pantalla", "Cambiar orden", "Cargar desde el YAML", "Duplicar",
    "Editar pantalla", "Editar propiedades de la página", "Eliminar capa superior", "Eliminar pantalla",
    "Eliminar", "Mover pantalla", "Pegar", "Nuevo proyecto",
    # contenedores de pestañas / mosaicos
    "Añadir pestaña", "Añadir mosaico",
    # origen de los plugins
    "Integrado", "Usuario", "Variable",
    # IA (Fase 8): proveedores y ejemplos
    "Generador local (sin IA, plantillas)", "Claude (Anthropic)", "Compatible con OpenAI (OpenAI, LM Studio, Ollama…)",
    "Página de luces con 6 luces y el termostato, tema oscuro",
    "Control de 3 persianas con deslizadores y color verde",
    "Música del salón y escenas, con barra de navegación",
    "Energía: consumo y producción solar, con la hora",
    "Ajustes de la pantalla: modo noche, sonidos y brillo",
    "Tema oscuro y textos más grandes", "Tema claro y botones azules", "Redondear las esquinas",
    "Extraer estilos compartidos", "Poner ids descriptivos",
    # Fase 10: licencias (mensajes y nombres de funciones) y deshacer de la fusión
    "Sin licencia: edición Community", "Licencia válida", "Firma ilegible",
    "La firma no corresponde a ninguna clave de esta aplicación (licencia manipulada o de otro vendedor)",
    "Control de versiones visual", "Publicar componentes", "IA con Claude u OpenAI",
    "Comentarios y presencia en carpetas compartidas", "Fusión automática al guardar",
    "Fusionar cambios de otra persona",
    # pantallas propias (mensajes de validación)
    "Ponle un nombre a la pantalla", "Ya hay una pantalla de serie con ese nombre",
    # ediciones (nombres de funciones con licencia)
    "Importar y sincronizar YAML de ESPHome", "Extensión de VS Code (vista previa, Live Sync, diagnósticos)",
    "Herramientas de IA (generar, refactorizar, estilos e ids)",
    "No se pueden guardar pantallas sin los ajustes de la aplicación",
    # tamaño de los iconos de las barras
    "Pequeños", "Medianos", "Grandes", "Muy grandes",
    # editor de estilo completo e indicador de aguja
    'Degradado', 'Dirección del degradado', 'Color final del degradado', 'Empieza en (0-255)',
    'Termina en (0-255)', 'Borde', 'Opacidad del borde', 'Lados del borde', 'Borde por encima de los hijos',
    'Contorno', 'Color del contorno', 'Grosor del contorno', 'Separación del contorno',
    'Opacidad del contorno', 'Desplazamiento X', 'Desplazamiento Y', 'Extensión', 'Opacidad de la sombra',
    'Texto', 'Opacidad del texto', 'Fuente', 'Alineación del texto', 'Espacio entre letras',
    'Espacio entre líneas', 'Decoración', 'Arriba', 'Abajo', 'Izquierda', 'Derecha', 'Entre filas',
    'Entre columnas', 'Arco', 'Color del arco', 'Grosor del arco', 'Opacidad del arco',
    'Extremos redondeados', 'Línea', 'Color de la línea', 'Grosor de la línea', 'Opacidad de la línea',
    'Trazo (discontinua)', 'Hueco (discontinua)', 'Imagen', 'Teñir con color', 'Intensidad del tinte',
    'Teñir la imagen de fondo', 'Intensidad del tinte de fondo', 'Tamaño y posición', 'Ancho mínimo',
    'Ancho máximo', 'Alto mínimo', 'Alto máximo', 'Desplazar X', 'Desplazar Y', 'Giro (décimas de grado)',
    'Recortar esquinas', 'Valor mínimo', 'Valor máximo', 'Ángulo total (°)',
    'Ángulo de inicio (°, 0 = las 3)', 'Marcas por encima de los indicadores', 'Número de marcas', 'Grosor',
    'Largo (px o %)', 'Color', 'Separación del borde', 'Cada cuántas marcas', 'Separación de los números',
    'Id (para cambiarla con lvgl.indicator.update)', 'Valor',
    'Largo respecto al radio (px, negativo = más corta)', 'Id (para cambiarlo con lvgl.indicator.update)',
    'Desde el valor', 'Hasta el valor', 'Radio respecto a la escala (px)', 'Eje X en la imagen',
    'Eje Y en la imagen', 'Color inicial', 'Color final', 'Grosor de las marcas',
    'Degradado sólo en este rango', 'Aguja', 'Aguja de imagen', 'Color de marcas',
    # deshacer: arrastrar en el árbol
    'Mover en el árbol',
    # orientación de la pantalla
    'Horizontal', 'Vertical', 'Horizontal invertida', 'Vertical invertida', 'Orientación de la pantalla',
    # fuentes
    'Añadir fuente de la biblioteca',
    'Añadir fuente desde GitHub o una URL',
    'Añadir fuente desde un fichero',
    'Añadir fuente de Google Fonts',
    'Editar fuente',
    '＋ Montserrat, Roboto o iconos…',
    '＋ Desde GitHub o una URL…',
    '＋ Desde un fichero…',
    '＋ Google Fonts…',
    'La dirección debe empezar por https://',
    'El enlace no apunta a un fichero de fuente (.ttf, .otf, .woff, .woff2, .bdf o .pcf)',
    'El fichero no es una fuente (.ttf, .otf, .woff, .woff2, .bdf o .pcf)',
    'Escribe el nombre de la familia tal como aparece en fonts.google.com (p. ej. «Open Sans»)',
    'El enlace es una página web, no el fichero: en GitHub usa el enlace «Raw» o «Download raw file»',
    'Lo descargado no es una fuente TTF/OTF/WOFF',
    'Añadir fuente',
    'Eliminar fuente',
)
