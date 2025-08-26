# Análisis y Visualización 3D de Flautas Traveseras

Este proyecto contiene un conjunto de herramientas desarrolladas en Python para generar, ensamblar y visualizar modelos 3D de flautas traveseras históricas a partir de datos de medición almacenados en formato `.json`.

El flujo de trabajo principal consiste en tomar perfiles de diámetro interno y externo de cada pieza de la flauta (cabeza, cuerpo izquierdo, cuerpo derecho, pie), y utilizar librerías de modelado 3D como **CadQuery** y **Trimesh** para reconstruir los sólidos.

## Características Principales

- **Corrección Automática de Nombres:** Escanea directorios y corrige nombres de archivos `.json` comunes.
- **Modelado 3D Paramétrico:** Genera sólidos 3D por revolución a partir de perfiles 2D.
- **Ensamblaje Virtual:** Une las diferentes partes de la flauta (cabeza, cuerpos, pie) en un modelo completo.
- **Visualización Interactiva:** Utiliza `PyQt5` y `PyVista` para crear interfaces gráficas que permiten explorar los modelos 3D y sus perfiles 2D.
- **Exportación a STL:** Permite guardar las piezas generadas en formato `.stl` para su uso en otros programas de CAD o para impresión 3D.

---

## Descripción de los Scripts

El repositorio contiene varias aplicaciones y scripts, cada uno con un propósito específico.

### 1. `navegador_flautas.py` (Aplicación Principal)

Esta es la herramienta más completa y recomendada para el uso general.

**Propósito:**
- Escanear un directorio que contiene subdirectorios, donde cada subdirectorio representa una flauta completa.
- Cargar todas las piezas (`headjoint`, `left`, `right`, `foot`) de cada flauta.
- Ensamblar virtualmente la flauta completa, posicionando cada pieza correctamente.
- Visualizar tanto piezas individuales como la flauta completa en un visor 3D interactivo.
- Ajustar la calidad de la malla 3D en tiempo real.

**Uso:**
1. Ejecutar el script: `python navegador_flautas.py`.
2. Pulsar **"1. Seleccionar Directorio de Flautas"** y elegir la carpeta que contiene los subdirectorios de cada flauta.
3. Pulsar **"2. Escanear y Cargar Flautas"**. El programa procesará todos los archivos.
4. Navegar por el árbol de la izquierda para seleccionar una flauta completa o una pieza individual y verla en el visor 3D.

---

### 2. `visualizador_flauta_3D.py`

**Propósito:**
- Herramienta de propósito específico para generar y visualizar **una única pieza** de flauta (ej. la cabeza o el pie).
- Utiliza **CadQuery** para el modelado 3D, realizando operaciones booleanas para crear el cuerpo hueco y los agujeros.
- Permite ajustar parámetros como el ángulo de conicidad de los agujeros.
- Ofrece una vista 2D de los perfiles y una vista 3D del resultado final.
- Permite exportar la pieza final ensamblada a un archivo `.stl`.

**Uso:**
1. Ejecutar el script: `python visualizador_flauta_3D.py`.
2. Cargar el perfil interno y externo de la pieza deseada.
3. Ajustar los parámetros (calidad, ángulo).
4. Pulsar **"Generar y Ensamblar Pieza"**.
5. Se mostrará el resultado y se preguntará si se desea guardar el archivo STL.

---

### 3. `generar_piezas.py`

**Propósito:**
- Similar al `visualizador_flauta_3D.py`, pero utiliza **Trimesh** en lugar de CadQuery.
- Su principal diferencia es que visualiza los **componentes por separado**: el sólido externo (semitransparente), el sólido interno y los "cortadores" (los cilindros que se usarán para perforar los agujeros).
- Es una herramienta útil para depurar la geometría y la posición de los agujeros antes de realizar las operaciones booleanas.
- Permite exportar cada componente (`_EXTERNAL`, `_INTERNAL`, `_CUTTER_...`) a archivos `.stl` individuales.

**Uso:**
1. Ejecutar el script: `python generar_piezas.py`.
2. Cargar los perfiles interno y externo.
3. Pulsar **"1. Visualizar Perfiles y Piezas"**.
4. Pulsar **"2. Exportar Piezas Individuales..."** para guardar los componentes.

---

### 4. `lee_json.py`

**Propósito:**
- Script sin interfaz gráfica (se ejecuta desde la línea de comandos).
- Su función es tomar un perfil interno y uno externo, procesarlos con **Trimesh** y exportar directamente un único archivo `.stl` del resultado final.
- Contiene lógica para corregir "escalones" verticales en los perfiles, un problema común que puede hacer fallar las operaciones de revolución.

**Uso:**
- Modificar las variables al final del archivo (`base_path`, `internal_file`, etc.) para apuntar a los archivos deseados.
- Ejecutar desde la terminal: `python lee_json.py`.
- El archivo `.stl` se generará en el directorio del script.

---

## Requisitos (Dependencias)

Para ejecutar estos scripts, necesitas instalar las siguientes librerías de Python:

```bash
pip install numpy
pip install pyqt5
pip install pyvista
pip install pyvistaqt
pip install cadquery
pip install trimesh
pip install matplotlib
```

## Estructura de Datos (`.json`)

El sistema espera archivos `.json` con una estructura específica:

- **`measurements`**: Una lista de diccionarios, cada uno con:
  - `position`: La coordenada a lo largo del eje de la flauta (en mm).
  - `diameter`: El diámetro de la flauta en esa posición (en mm).
- **`Holes position`** (solo en perfiles internos): Una lista con las posiciones de los centros de los agujeros.
- **`Holes diameter`** (solo en perfiles internos): Una lista con los diámetros de los agujeros.
- **`Total length`**, **`Mortise length`** (opcional, para ensamblaje): Metadatos sobre la longitud de la pieza y sus zonas de encaje (mortaja).

Los nombres de archivo deben seguir la convención: `[nombre_pieza].json` para el perfil interno y `[nombre_pieza]_external.json` para el externo. El `navegador_flautas.py` puede corregir pequeños errores en estos nombres.