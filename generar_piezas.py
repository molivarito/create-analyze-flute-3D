import sys
import os
import json
import numpy as np
import trimesh
import pyvista as pv

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QMessageBox, QTabWidget)
from PyQt5.QtCore import Qt
from pyvistaqt import QtInteractor
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# --- Funciones de Geometría ---

def interpolate_radius(y_pos, profile_points):
    """Calcula el radio en una posición Y específica."""
    p1, p2 = None, None
    for i in range(len(profile_points) - 1):
        if profile_points[i]['position'] <= y_pos <= profile_points[i+1]['position']:
            p1, p2 = profile_points[i], profile_points[i+1]
            break
    if not p1: return profile_points[-1]['diameter'] / 2.0
    y1, r1 = p1['position'], p1['diameter'] / 2.0
    y2, r2 = p2['position'], p2['diameter'] / 2.0
    if (y2 - y1) == 0: return r1
    return r1 + (r2 - r1) * ((y_pos - y1) / (y2 - y1))

def create_revolved_solid(profile_points, resolution=100):
    """Crea un sólido 3D revolucionando un perfil (radio, pos) alrededor del eje Y."""
    fixed_points = []
    for i, point in enumerate(profile_points):
        if i > 0 and point['position'] == profile_points[i-1]['position']:
            point['position'] += 0.001
        fixed_points.append(point)
    profile_2d = [(p['diameter'] / 2, p['position']) for p in fixed_points]
    mesh = trimesh.creation.revolve(linestring=profile_2d, resolution=resolution)
    return mesh

def trimesh_to_pyvista(trimesh_mesh):
    """Convierte una malla de Trimesh a una malla de PyVista."""
    faces = np.c_[np.full(len(trimesh_mesh.faces), 3), trimesh_mesh.faces]
    return pv.PolyData(trimesh_mesh.vertices, faces)

# --- Clase Principal de la GUI ---

class PartViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visualizador y Exportador de Piezas de Flauta")
        self.setGeometry(100, 100, 1400, 900)

        self.internal_data, self.external_data = None, None
        self.external_mesh_tm, self.internal_mesh_tm = None, None
        self.cutter_meshes_tm = []
        self.default_dir = os.path.abspath('../data_json/Grenser-Montero/')
        
        main_widget = QWidget(); self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        controls_widget = QWidget(); controls_layout = QVBoxLayout(controls_widget)
        controls_widget.setMaximumWidth(350)

        self.internal_label = QLabel("Perfil Interno: No cargado")
        self.load_internal_btn = QPushButton("Cargar Perfil Interno (.json)")
        self.external_label = QLabel("Perfil Externo: No cargado")
        self.load_external_btn = QPushButton("Cargar Perfil Externo (.json)")
        self.generate_btn = QPushButton("1. Visualizar Perfiles y Piezas")
        self.export_btn = QPushButton("2. Exportar Piezas Individuales...")
        
        controls_layout.addWidget(self.load_internal_btn)
        controls_layout.addWidget(self.internal_label); controls_layout.addSpacing(20)
        controls_layout.addWidget(self.load_external_btn)
        controls_layout.addWidget(self.external_label); controls_layout.addStretch()
        controls_layout.addWidget(self.generate_btn); controls_layout.addWidget(self.export_btn)

        self.tabs = QTabWidget()
        self.plot_2d_widget = QWidget(); plot_2d_layout = QVBoxLayout(self.plot_2d_widget)
        self.mpl_figure = Figure(); self.mpl_canvas = FigureCanvas(self.mpl_figure)
        plot_2d_layout.addWidget(self.mpl_canvas)
        self.tabs.addTab(self.plot_2d_widget, "Vista 2D (Perfiles)")

        self.plot_3d_widget = QWidget(); plot_3d_layout = QVBoxLayout(self.plot_3d_widget)
        self.plotter_3d = QtInteractor(self.plot_3d_widget)
        plot_3d_layout.addWidget(self.plotter_3d.interactor)
        self.tabs.addTab(self.plot_3d_widget, "Vista 3D (Piezas Separadas)")

        main_layout.addWidget(controls_widget); main_layout.addWidget(self.tabs)
        
        self.load_internal_btn.clicked.connect(lambda: self.load_file('internal'))
        self.load_external_btn.clicked.connect(lambda: self.load_file('external'))
        self.generate_btn.clicked.connect(self.generate_and_visualize)
        self.export_btn.clicked.connect(self.export_stls)
        
    def load_file(self, file_type):
        title = f"Seleccionar Perfil {'Interno' if file_type == 'internal' else 'Externo'}"
        path, _ = QFileDialog.getOpenFileName(self, title, self.default_dir, "JSON Files (*.json)")
        if path:
            if file_type == 'internal': self.internal_path = path; self.internal_label.setText(f"Interno: ...{os.path.basename(path)}")
            else: self.external_path = path; self.external_label.setText(f"Externo: ...{os.path.basename(path)}")

    def generate_and_visualize(self):
        if not hasattr(self, 'internal_path') or not self.internal_path or not hasattr(self, 'external_path') or not self.external_path:
            QMessageBox.warning(self, "Archivos Faltantes", "Por favor, carga ambos perfiles."); return
        try:
            with open(self.internal_path, 'r') as f: self.internal_data = json.load(f)
            with open(self.external_path, 'r') as f: self.external_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error de Lectura", f"Error: {e}"); return
            
        print("Generando modelos base...")
        self.external_mesh_tm = create_revolved_solid(self.external_data['measurements'])
        self.internal_mesh_tm = create_revolved_solid(self.internal_data['measurements'])
        
        print("Generando cortadores para los agujeros...")
        self.cutter_meshes_tm = []
        for i in range(self.internal_data.get("Number of holes", 0)):
            y_pos = self.internal_data["Holes position"][i]
            d_outer_hole = self.internal_data["Holes diameter"][i]
            d_inner_hole = d_outer_hole + 1.0

            r_body_ext = interpolate_radius(y_pos, self.external_data['measurements'])
            r_body_int = interpolate_radius(y_pos, self.internal_data['measurements'])
            
            cutter_height = r_body_ext - r_body_int + 6
            template_cutter_profile = [
                (0, -cutter_height/2), (d_outer_hole/2, -cutter_height/2),
                (d_inner_hole/2, cutter_height/2), (0, cutter_height/2)
            ]
            template_cutter = trimesh.creation.revolve(linestring=template_cutter_profile, axis=[0,0,1])

            x_target_pos = (r_body_ext + r_body_int) / 2
            
            rotation = trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 1, 0])
            translation = trimesh.transformations.translation_matrix([x_target_pos, y_pos, 0])
            
            transform = translation @ rotation
            
            cutter = template_cutter.copy()
            cutter.apply_transform(transform)
            self.cutter_meshes_tm.append(cutter)
            
            # --- NUEVO: Imprimir datos de depuración para el primer agujero ---
            if i == 0:
                print("\n--- DATOS DE DEPURACIÓN (Primer Agujero) ---")
                print(f"Posición del agujero (Y): {y_pos:.2f}")
                print(f"Radio Exterior del Cuerpo en Y: {r_body_ext:.2f}")
                print(f"Radio Interno del Cuerpo en Y: {r_body_int:.2f}")
                print(f"Posición X objetivo del cortador: {x_target_pos:.2f}")
                print(f"Límites del cortador ANTES de transformar: {np.round(template_cutter.bounds, 2)}")
                print(f"Límites del cortador DESPUÉS de transformar: {np.round(cutter.bounds, 2)}")
                print("------------------------------------------\n")

        self.plot_2d(); self.plot_3d()
        print("Visualización actualizada con todas las piezas.")

    def plot_2d(self):
        self.mpl_figure.clear(); ax = self.mpl_figure.add_subplot(111)
        ax.plot([p['position'] for p in self.internal_data['measurements']], [p['diameter']/2 for p in self.internal_data['measurements']], 'r--', label='Interno')
        ax.plot([p['position'] for p in self.internal_data['measurements']], [-p['diameter']/2 for p in self.internal_data['measurements']], 'r--')
        ax.plot([p['position'] for p in self.external_data['measurements']], [p['diameter']/2 for p in self.external_data['measurements']], 'b-', label='Externo')
        ax.plot([p['position'] for p in self.external_data['measurements']], [-p['diameter']/2 for p in self.external_data['measurements']], 'b-')
        ax.set_aspect('equal'); ax.set_xlabel("Posición (mm)"); ax.set_ylabel("Radio (mm)"); ax.set_title("Perfiles"); ax.legend(); ax.grid(True); self.mpl_canvas.draw()

    def plot_3d(self):
        self.plotter_3d.clear()
        self.plotter_3d.add_mesh(trimesh_to_pyvista(self.external_mesh_tm), style='surface', color='silver', opacity=0.3)
        self.plotter_3d.add_mesh(trimesh_to_pyvista(self.internal_mesh_tm), color='maroon', opacity=0.5)
        for cutter in self.cutter_meshes_tm:
            self.plotter_3d.add_mesh(trimesh_to_pyvista(cutter), color='gold')
        self.plotter_3d.reset_camera()

    def export_stls(self):
        if not self.external_mesh_tm: QMessageBox.warning(self, "Modelos no generados", "Primero debes generar los modelos."); return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Piezas STL", self.default_dir, "STL (*.stl)")
        if not path: return
        base, _ = os.path.splitext(path)
        try:
            self.external_mesh_tm.export(base + "_EXTERNAL.stl")
            self.internal_mesh_tm.export(base + "_INTERNAL.stl")
            for i, cutter in enumerate(self.cutter_meshes_tm):
                cutter.export(base + f"_CUTTER_{i+1}.stl")
            QMessageBox.information(self, "Exportación Exitosa", f"Archivos guardados correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"Error: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PartViewerApp()
    window.show()
    sys.exit(app.exec_())