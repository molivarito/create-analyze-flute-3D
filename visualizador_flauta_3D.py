import sys
import os
import json
import numpy as np
import cadquery as cq
import pyvista as pv

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QMessageBox, QTabWidget, QSpinBox, QFormLayout,
                             QGroupBox, QDoubleSpinBox) #<-- LÍNEA CORREGIDA
from PyQt5.QtCore import Qt
from pyvistaqt import QtInteractor
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.patches as patches

# --- Funciones de Geometría ---

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

def create_cq_solid_from_profile(profile_points):
    """Crea un sólido de CadQuery a partir de un perfil de revolución."""
    path_pts = [(p['diameter'] / 2, p['position']) for p in profile_points]
    if not path_pts: return None
    
    if path_pts[0][0] > 1e-6: path_pts.insert(0, (0, path_pts[0][1]))
    if path_pts[-1][0] > 1e-6: path_pts.append((0, path_pts[-1][1]))
    
    try:
        solid = cq.Workplane("XZ").polyline(path_pts).close().revolve()
        return solid
    except Exception as e:
        print(f"ERROR en CadQuery al crear sólido: {e}"); return None

def cq_to_pyvista(cq_solid, quality=100):
    """Convierte un objeto de CadQuery a PyVista para visualización."""
    if cq_solid is None: return pv.PolyData()
    tolerance = 0.5 / quality
    shape = cq_solid.val()
    if not isinstance(shape, cq.Shape): shape = shape.toOCC()
    vertices_vector, faces = shape.tessellate(tolerance=tolerance)
    vertices_np = np.array([v.toTuple() for v in vertices_vector])
    if len(faces) == 0: return pv.PolyData()
    faces_pv = np.c_[np.full(len(faces), 3), faces].astype(np.int_)
    return pv.PolyData(vertices_np, faces_pv)

# --- Clase Principal de la GUI ---

class FluteAssemblerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ensamblador de Flauta con CadQuery")
        self.setGeometry(100, 100, 1400, 900)

        self.internal_data, self.external_data = None, None
        self.final_cq_solid = None
        self.default_dir = os.path.abspath('../data_json/Grenser-Montero/')
        
        main_widget = QWidget(); self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        controls_widget = QWidget(); controls_layout = QVBoxLayout(controls_widget)
        controls_widget.setMaximumWidth(350)
        
        load_group = QGroupBox("Carga de Perfiles")
        load_layout = QVBoxLayout(load_group)
        self.internal_label = QLabel("Interno: No cargado")
        self.load_internal_btn = QPushButton("Cargar Perfil Interno (.json)")
        self.external_label = QLabel("Externo: No cargado")
        self.load_external_btn = QPushButton("Cargar Perfil Externo (.json)")
        load_layout.addWidget(self.load_internal_btn); load_layout.addWidget(self.internal_label)
        load_layout.addWidget(self.load_external_btn); load_layout.addWidget(self.external_label)
        
        params_group = QGroupBox("Parámetros de Generación")
        params_layout = QFormLayout(params_group)
        self.quality_input = QSpinBox(self)
        self.quality_input.setRange(50, 500); self.quality_input.setValue(300)
        params_layout.addRow("Calidad de Malla:", self.quality_input)
        self.angle_input = QDoubleSpinBox(self)
        self.angle_input.setRange(-20.0, 20.0); self.angle_input.setValue(5.0); self.angle_input.setSuffix(" °")
        params_layout.addRow("Ángulo Conicidad (°):", self.angle_input)

        self.assemble_btn = QPushButton("Generar y Ensamblar Pieza")
        
        controls_layout.addWidget(load_group); controls_layout.addWidget(params_group)
        controls_layout.addStretch(); controls_layout.addWidget(self.assemble_btn)

        self.tabs = QTabWidget()
        self.plot_2d_widget = QWidget(); plot_2d_layout = QVBoxLayout(self.plot_2d_widget)
        self.mpl_figure = Figure(); self.mpl_canvas = FigureCanvas(self.mpl_figure)
        plot_2d_layout.addWidget(self.mpl_canvas)
        self.tabs.addTab(self.plot_2d_widget, "Vista 2D de Perfiles")
        
        self.plot_3d_final_widget = QWidget(); plot_3d_final_layout = QVBoxLayout(self.plot_3d_final_widget)
        self.plotter_3d_final = QtInteractor(self.plot_3d_final_widget)
        plot_3d_final_layout.addWidget(self.plotter_3d_final.interactor)
        self.tabs.addTab(self.plot_3d_final_widget, "Vista 3D Final")

        main_layout.addWidget(controls_widget); main_layout.addWidget(self.tabs, 1)
        
        self.load_internal_btn.clicked.connect(lambda: self.load_file('internal'))
        self.load_external_btn.clicked.connect(lambda: self.load_file('external'))
        self.assemble_btn.clicked.connect(self.assemble_model)

    def load_file(self, file_type):
        title = f"Seleccionar Perfil {'Interno' if file_type == 'internal' else 'Externo'}"
        path, _ = QFileDialog.getOpenFileName(self, title, self.default_dir, "JSON Files (*.json)")
        if path:
            if file_type == 'internal': self.internal_path = path; self.internal_label.setText(f"Interno: ...{os.path.basename(path)}")
            else: self.external_path = path; self.external_label.setText(f"Externo: ...{os.path.basename(path)}")

    def assemble_model(self):
        if not hasattr(self, 'internal_path') or not self.internal_path or not hasattr(self, 'external_path') or not self.external_path:
            QMessageBox.warning(self, "Archivos Faltantes", "Por favor, carga ambos perfiles."); return
        try:
            with open(self.internal_path, 'r') as f: self.internal_data = json.load(f)
            with open(self.external_path, 'r') as f: self.external_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error de Lectura", f"Error: {e}"); return
        
        print("--- Iniciando Proceso con CadQuery ---")
        self.plot_2d(); QApplication.processEvents()

        external_solid = create_cq_solid_from_profile(self.external_data['measurements'])
        internal_solid = create_cq_solid_from_profile(self.internal_data['measurements'])
        if not external_solid or not internal_solid: QMessageBox.critical(self, "Error", "Fallo al crear sólidos base."); return
            
        print("Creando cortadores de agujeros...")
        cutters = []
        cone_angle_rad = np.deg2rad(self.angle_input.value())

        for i in range(self.internal_data.get("Number of holes", 0)):
            z_pos = self.internal_data["Holes position"][i]
            d_outer_hole = self.internal_data["Holes diameter"][i]
            
            r_body_ext = interpolate_radius(z_pos, self.external_data['measurements'])
            r_body_int = interpolate_radius(z_pos, self.internal_data['measurements'])
            wall_thickness = r_body_ext - r_body_int
            cutter_height = wall_thickness + 2.0
            
            r_outer_hole = d_outer_hole / 2.0
            change_in_radius = wall_thickness * np.tan(cone_angle_rad)
            r_inner_hole = r_outer_hole + change_in_radius
            
            template_solid = cq.Solid.makeCone(r_outer_hole, r_inner_hole, cutter_height)
            template_wp = cq.Workplane(template_solid).translate((0,0,-cutter_height/2))
            
            x_target = (r_body_ext + r_body_int) / 2
            
            cutter = (template_wp
                      .rotate((0,0,0), (0,1,0), -90)
                      .translate((x_target, 0, z_pos))
                     )
            cutters.append(cutter)
            
        print("Realizando operaciones booleanas...")
        try:
            result = external_solid.cut(internal_solid)
            for cutter in cutters:
                result = result.cut(cutter)
            self.final_cq_solid = result
        except Exception as e:
            QMessageBox.critical(self, "Error de Ensamblaje", f"La operación booleana falló.\nError: {e}"); return
            
        print("Ensamblaje completado. Mostrando resultado...")
        self.plot_3d()
        self.tabs.setCurrentWidget(self.plot_3d_final_widget)
        
        reply = QMessageBox.question(self, 'Guardar Modelo Final', '¡Ensamblaje completado! ¿Deseas guardar el STL?', QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes: self.export_final_stl()
            
    def export_final_stl(self):
        if not self.final_cq_solid: return
        part_name = self.internal_data.get("Part", "flauta_parte")
        default_filename = os.path.join(self.default_dir, f"{part_name}_FINAL.stl")
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Pieza Final", default_filename, "STL (*.stl)")
        if path:
            cq.exporters.export(self.final_cq_solid, path, tolerance=(0.5 / self.quality_input.value()))
            print(f"Modelo final guardado en {path}")
            
    def plot_2d(self):
        self.mpl_figure.clear(); ax = self.mpl_figure.add_subplot(111)
        ax.plot([p['position'] for p in self.internal_data['measurements']], [p['diameter']/2 for p in self.internal_data['measurements']], 'r--', label='Interno')
        ax.plot([p['position'] for p in self.internal_data['measurements']], [-p['diameter']/2 for p in self.internal_data['measurements']], 'r--')
        ax.plot([p['position'] for p in self.external_data['measurements']], [p['diameter']/2 for p in self.external_data['measurements']], 'b-', label='Externo')
        ax.plot([p['position'] for p in self.external_data['measurements']], [-p['diameter']/2 for p in self.external_data['measurements']], 'b-')
        
        cone_angle_rad = np.deg2rad(self.angle_input.value())
        for i in range(self.internal_data.get("Number of holes", 0)):
            z_pos = self.internal_data["Holes position"][i]
            d_outer_hole = self.internal_data["Holes diameter"][i]
            
            r_ext = interpolate_radius(z_pos, self.external_data['measurements'])
            r_int = interpolate_radius(z_pos, self.internal_data['measurements'])
            wall_thickness = r_ext - r_int
            
            r_outer_hole = d_outer_hole / 2.0
            r_inner_hole = r_outer_hole + wall_thickness * np.tan(cone_angle_rad)
            
            top_points = [[z_pos-r_outer_hole, r_ext], [z_pos+r_outer_hole, r_ext], [z_pos+r_inner_hole, r_int], [z_pos-r_inner_hole, r_int]]
            ax.add_patch(patches.Polygon(top_points, closed=True, facecolor='gold', alpha=0.6))
            
        ax.set_aspect('equal'); ax.set_xlabel("Posición (mm)"); ax.set_ylabel("Radio (mm)"); ax.set_title("Perfiles"); ax.legend(); ax.grid(True); self.mpl_canvas.draw()
    
    def plot_3d(self):
        self.plotter_3d_final.clear()
        if self.final_cq_solid:
            pv_mesh = cq_to_pyvista(self.final_cq_solid, self.quality_input.value())
            self.plotter_3d_final.add_mesh(pv_mesh, color='tan', show_edges=True)
        self.plotter_3d_final.reset_camera()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FluteAssemblerApp()
    window.show()
    sys.exit(app.exec_())