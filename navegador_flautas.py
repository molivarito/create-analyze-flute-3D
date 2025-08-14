import sys
import os
import json
import numpy as np
import cadquery as cq
import pyvista as pv
import difflib
from collections import defaultdict

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QMessageBox, QTreeWidget, QTreeWidgetItem, QFormLayout, QSpinBox,
                             QGroupBox, QHeaderView)
from PyQt5.QtCore import Qt
from pyvistaqt import QtInteractor

# --- Lógica de Corrección de Archivos ---

class FileCorrector:
    """
    Escanea un directorio base, encuentra subdirectorios de flautas y corrige
    los nombres de los archivos .json basados en una lista de nombres correctos.
    """
    CORRECT_NAMES = [
        "headjoint.json", "headjoint_external.json",
        "left.json", "left_external.json",
        "right.json", "right_external.json",
        "foot.json", "foot_external.json"
    ]

    def __init__(self, base_path):
        self.base_path = base_path
        self.corrections_log = []

    def find_closest_match(self, typo):
        """Encuentra la coincidencia más cercana en la lista de nombres correctos."""
        matches = difflib.get_close_matches(typo, self.CORRECT_NAMES, n=1, cutoff=0.8)
        return matches[0] if matches else None

    def scan_and_correct(self):
        """
        Recorre los subdirectorios y renombra los archivos .json con errores de tipeo.
        Devuelve una lista de los directorios de flautas encontrados.
        """
        print("--- Iniciando escaneo y corrección de nombres de archivo ---")
        flute_dirs = [d.path for d in os.scandir(self.base_path) if d.is_dir()]
        
        for flute_dir in flute_dirs:
            print(f"Escaneando: {os.path.basename(flute_dir)}")
            for filename in os.listdir(flute_dir):
                if filename.endswith(".json"):
                    if filename not in self.CORRECT_NAMES:
                        correct_name = self.find_closest_match(filename)
                        if correct_name:
                            old_path = os.path.join(flute_dir, filename)
                            new_path = os.path.join(flute_dir, correct_name)
                            os.rename(old_path, new_path)
                            log_msg = f"Corregido: '{filename}' -> '{correct_name}' en {os.path.basename(flute_dir)}"
                            print(log_msg)
                            self.corrections_log.append(log_msg)
        print("--- Escaneo finalizado ---")
        return flute_dirs

# --- Lógica de Ensamblaje 3D (Reutilizada y encapsulada) ---

def interpolate_radius(y_pos, profile_points):
    """Calcula el radio en una posición Y específica."""
    p1, p2 = None, None
    for i in range(len(profile_points) - 1):
        if profile_points[i]['position'] <= y_pos <= profile_points[i+1]['position']:
            p1, p2 = profile_points[i], profile_points[i+1]; break
    if not p1: return profile_points[-1]['diameter'] / 2.0
    y1, r1 = p1['position'], p1['diameter'] / 2.0; y2, r2 = p2['position'], p2['diameter'] / 2.0
    if abs(y2 - y1) < 1e-9: return r1
    return r1 + (r2 - r1) * ((y_pos - y1) / (y2 - y1))

class FluteAssembler:
    """
    Toma datos de perfiles interno y externo y ensambla una pieza de flauta 3D.
    """
    def __init__(self, internal_data, external_data, cone_angle_deg=5.0):
        self.internal_data = internal_data
        self.external_data = external_data
        self.cone_angle_deg = cone_angle_deg

    def _create_cq_solid_from_profile(self, profile_points):
        path_pts = [(p['diameter'] / 2, p['position']) for p in profile_points]
        if not path_pts: return None
        if path_pts[0][0] > 1e-6: path_pts.insert(0, (0, path_pts[0][1]))
        if path_pts[-1][0] > 1e-6: path_pts.append((0, path_pts[-1][1]))
        return cq.Workplane("XZ").polyline(path_pts).close().revolve()

    def assemble(self):
        """Realiza el ensamblaje completo y devuelve el sólido de CadQuery."""
        external_solid = self._create_cq_solid_from_profile(self.external_data['measurements'])
        internal_solid = self._create_cq_solid_from_profile(self.internal_data['measurements'])
        if not external_solid or not internal_solid: return None

        cutters = []
        cone_angle_rad = np.deg2rad(self.cone_angle_deg)
        for i in range(self.internal_data.get("Number of holes", 0)):
            z_pos = self.internal_data["Holes position"][i]
            d_outer_hole = self.internal_data["Holes diameter"][i]
            
            r_body_ext = interpolate_radius(z_pos, self.external_data['measurements'])
            r_body_int = interpolate_radius(z_pos, self.internal_data['measurements'])
            wall_thickness = r_body_ext - r_body_int
            cutter_height = wall_thickness + 4.0 # Margen extra
            
            r_outer_hole = d_outer_hole / 2.0
            change_in_radius = wall_thickness * np.tan(cone_angle_rad)
            r_inner_hole = r_outer_hole + change_in_radius
            
            template_solid = cq.Solid.makeCone(r_outer_hole, r_inner_hole, cutter_height)
            template_wp = cq.Workplane(template_solid).translate((0,0,-cutter_height/2))
            
            x_target = (r_body_ext + r_body_int) / 2
            cutter = template_wp.rotate((0,0,0), (0,1,0), -90).translate((x_target, 0, z_pos))
            cutters.append(cutter)
            
        result = external_solid.cut(internal_solid)
        for cutter in cutters:
            result = result.cut(cutter)
        return result

def cq_to_pyvista(cq_solid, quality=100):
    """Convierte un objeto de CadQuery a PyVista para visualización."""
    if cq_solid is None: return pv.PolyData()
    
    tolerance = 0.5 / quality # Mayor calidad = menor tolerancia (malla más fina)

    shape = cq_solid.val()
    if not isinstance(shape, cq.Shape): shape = shape.toOCC()
    vertices_vector, faces = shape.tessellate(tolerance=tolerance)
    vertices_np = np.array([v.toTuple() for v in vertices_vector])
    if len(faces) == 0: return pv.PolyData()
    faces_pv = np.c_[np.full(len(faces), 3), faces].astype(np.int_)
    return pv.PolyData(vertices_np, faces_pv)

# --- Clase Principal de la GUI ---

class FluteBrowserApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Navegador de Flautas 3D")
        self.setGeometry(100, 100, 1600, 1000)

        self.base_path = None
        self.flutes_data = {} # Estructura: { "flute_name": { "part_name": cq_solid, ... } }

        main_widget = QWidget(); self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # --- Panel de Control (Izquierda) ---
        controls_widget = QWidget(); controls_layout = QVBoxLayout(controls_widget)
        controls_widget.setMaximumWidth(400)

        self.select_dir_btn = QPushButton("1. Seleccionar Directorio de Flautas")
        self.dir_label = QLabel("Directorio no seleccionado.")
        self.load_btn = QPushButton("2. Escanear y Cargar Flautas")

        view_options_group = QGroupBox("Opciones de Visualización")
        view_options_layout = QFormLayout(view_options_group)
        self.quality_input = QSpinBox()
        self.quality_input.setRange(50, 800)
        self.quality_input.setValue(200)
        self.quality_input.setSingleStep(25)
        self.quality_input.setToolTip("Aumenta la resolución del modelo 3D.\nUn valor más alto puede tardar más en cargar.")
        view_options_layout.addRow("Calidad de Malla:", self.quality_input)
        
        tree_group = QGroupBox("Flautas Cargadas")
        tree_layout = QVBoxLayout(tree_group)
        self.flute_tree = QTreeWidget()
        self.flute_tree.setHeaderLabel("Flautas y Piezas")
        tree_layout.addWidget(self.flute_tree)

        controls_layout.addWidget(self.select_dir_btn)
        controls_layout.addWidget(self.dir_label)
        controls_layout.addWidget(self.load_btn)
        controls_layout.addWidget(view_options_group)
        controls_layout.addWidget(tree_group)

        # --- Visor 3D (Derecha) ---
        plot_3d_widget = QWidget()
        plot_3d_layout = QVBoxLayout(plot_3d_widget)
        self.plotter_3d = QtInteractor(plot_3d_widget)
        plot_3d_layout.addWidget(self.plotter_3d.interactor)

        main_layout.addWidget(controls_widget)
        main_layout.addWidget(plot_3d_widget, 1)

        # --- Conexiones ---
        self.select_dir_btn.clicked.connect(self.select_directory)
        self.load_btn.clicked.connect(self.scan_and_load_flutes)
        self.flute_tree.itemClicked.connect(self.on_item_selected)
        self.quality_input.valueChanged.connect(self.refresh_current_model)

    def select_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar Directorio Raíz de Flautas")
        if path:
            self.base_path = path
            self.dir_label.setText(f"...{os.path.basename(path)}")

    def scan_and_load_flutes(self):
        if not self.base_path:
            QMessageBox.warning(self, "Directorio no seleccionado", "Por favor, selecciona primero el directorio que contiene tus flautas."); return

        corrector = FileCorrector(self.base_path)
        flute_dirs = corrector.scan_and_correct()
        if corrector.corrections_log:
            QMessageBox.information(self, "Correcciones Realizadas", "\n".join(corrector.corrections_log))

        self.flutes_data.clear()
        self.flute_tree.clear()
        QApplication.setOverrideCursor(Qt.WaitCursor)

        for flute_dir in flute_dirs:
            flute_name = os.path.basename(flute_dir)
            
            # Agrupar archivos por pieza (headjoint, left, etc.)
            part_files = defaultdict(dict)
            for filename in os.listdir(flute_dir):
                if filename.endswith(".json"):
                    part_name = filename.replace(".json", "").replace("_external", "")
                    if "external" in filename:
                        part_files[part_name]['external'] = os.path.join(flute_dir, filename)
                    else:
                        part_files[part_name]['internal'] = os.path.join(flute_dir, filename)
            
            if not part_files: continue

            self.flutes_data[flute_name] = {}
            flute_item = QTreeWidgetItem(self.flute_tree, [flute_name])

            for part_name, files in sorted(part_files.items()):
                if 'internal' in files and 'external' in files:
                    print(f"Procesando: {flute_name} -> {part_name}")
                    try:
                        with open(files['internal'], 'r') as f: internal_data = json.load(f)
                        with open(files['external'], 'r') as f: external_data = json.load(f)
                        
                        assembler = FluteAssembler(internal_data, external_data)
                        final_solid = assembler.assemble()

                        if final_solid:
                            self.flutes_data[flute_name][part_name] = final_solid
                            part_item = QTreeWidgetItem(flute_item, [part_name])
                            part_item.setData(0, Qt.UserRole, (flute_name, part_name))
                    except Exception as e:
                        print(f"ERROR al procesar {flute_name}/{part_name}: {e}")
        
        self.flute_tree.expandAll()
        self.flute_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Proceso Completado", f"Se han cargado {len(self.flutes_data)} flautas.")

    def refresh_current_model(self):
        """Refresca el modelo actual en el visor, típicamente al cambiar un parámetro."""
        current_item = self.flute_tree.currentItem()
        if current_item:
            self.display_selected_model(current_item, 0, reset_camera=False)

    def on_item_selected(self, item, column):
        """Maneja el evento de clic en un item del árbol."""
        self.display_selected_model(item, column, reset_camera=True)

    def display_selected_model(self, item, column, reset_camera=True):
        item_data = item.data(0, Qt.UserRole)
        if not item_data: return # Es un item de nivel superior (nombre de flauta)

        flute_name, part_name = item_data
        cq_solid = self.flutes_data.get(flute_name, {}).get(part_name)

        if cq_solid:
            print(f"Mostrando: {flute_name} - {part_name} (Calidad: {self.quality_input.value()})")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.plotter_3d.clear()
            pv_mesh = cq_to_pyvista(cq_solid, self.quality_input.value())
            self.plotter_3d.add_mesh(pv_mesh, color='tan', show_edges=True)
            if reset_camera:
                self.plotter_3d.reset_camera()
            QApplication.restoreOverrideCursor()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FluteBrowserApp()
    window.show()
    sys.exit(app.exec_())