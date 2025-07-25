import json
import os
import numpy as np
import trimesh

def create_revolved_solid_trimesh(profile_points, resolution=100):
    """
    Crea un sólido 3D por revolución usando Trimesh.
    """
    profile_2d = [(p['diameter'] / 2, p['position']) for p in profile_points]
    
    mesh = trimesh.creation.revolve(
        linestring=profile_2d,
        resolution=resolution
    )
    return mesh

def fix_profile_steps(measurements):
    """
    Busca escalones verticales en el perfil y los convierte en diagonales
    muy pronunciadas añadiendo un pequeño offset.
    """
    new_measurements = []
    for i, point in enumerate(measurements):
        if i > 0 and point['position'] == measurements[i-1]['position']:
            # Se encontró un escalón vertical. Añadir un offset minúsculo.
            point['position'] += 0.001
        new_measurements.append(point)
    return new_measurements


def assemble_final_model(internal_data, external_data, output_filename):
    """
    Crea y ensambla las piezas en el modelo 3D final.
    """
    print("\n--- Ensamblaje Final (con Corrección de Escalones) ---")

    # --- NUEVO: Corregir los perfiles antes de usarlos ---
    print("1. Corrigiendo perfiles para eliminar escalones verticales...")
    external_data['measurements'] = fix_profile_steps(external_data['measurements'])
    internal_data['measurements'] = fix_profile_steps(internal_data['measurements'])
    
    print("2. Creando sólidos de revolución...")
    external_solid_tm = create_revolved_solid_trimesh(external_data['measurements'])
    internal_solid_tm = create_revolved_solid_trimesh(internal_data['measurements'])
    
    print("3. Vaciando el cuerpo de la flauta...")
    try:
        # Se añade un último intento de procesado por si acaso
        if not external_solid_tm.is_watertight: external_solid_tm = external_solid_tm.process()
        if not internal_solid_tm.is_watertight: internal_solid_tm = internal_solid_tm.process()
        
        hollow_body_tm = external_solid_tm.difference(internal_solid_tm)
    except Exception as e:
         print(f"ERROR: La resta final falló incluso después de la corrección: {e}")
         return

    print("4. Creando y perforando el agujero de embocadura...")
    hole_pos_z = internal_data['Holes position'][0]
    hole_radius = internal_data['Holes diameter'][0] / 2
    
    transform_matrix = trimesh.transformations.translation_matrix([0, 0, hole_pos_z])
    transform_matrix = np.dot(transform_matrix, trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    
    embouchure_cutter_tm = trimesh.creation.cylinder(
        radius=hole_radius, height=80, transform=transform_matrix
    )
    
    final_model_tm = hollow_body_tm.difference(embouchure_cutter_tm)

    print(f"5. Exportando el modelo final a '{output_filename}'...")
    final_model_tm.export(output_filename)
    print(f"¡Proceso completado! El archivo '{output_filename}' ha sido guardado.")

# --- Ejecución Principal ---
if __name__ == '__main__':
    base_path = '../data_json/Grenser-Montero/'
    internal_file = 'headjoint.json'
    external_file = 'headjoint_external_SIMPLE.json'
    output_stl_file = 'headjoint_FINAL.stl'

    internal_path = os.path.join(base_path, internal_file)
    external_path = os.path.join(base_path, external_file)

    try:
        with open(internal_path, 'r') as f:
            internal_data = json.load(f)
        with open(external_path, 'r') as f:
            external_data = json.load(f)
    except FileNotFoundError:
        # Si el archivo simplificado no existe, se usa el de la conversación anterior
        print("Usando el perfil simplificado definido internamente.")
        external_data = {
            "measurements": [
              { "position": 0.0, "diameter": 23.0 }, { "position": 7.0, "diameter": 23.0 },
              { "position": 7.0, "diameter": 29.5 }, { "position": 182.6, "diameter": 29.5 },
              { "position": 185.0, "diameter": 32.4 }, { "position": 218.8, "diameter": 29.4 }
            ]
        }
        with open(internal_path, 'r') as f:
            internal_data = json.load(f)

    assemble_final_model(internal_data, external_data, output_stl_file)