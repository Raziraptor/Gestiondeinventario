import json
from networkx.readwrite import json_graph
from pathlib import Path

new_data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
G = json_graph.node_link_graph(new_data, edges='links')

print("=== AUDITORIA DE DIRECCIONES INCORRECTAS ===\n")

problems = []

for u, v, d in G.edges(data=True):
    u_label = G.nodes[u].get('label', u)
    v_label = G.nodes[v].get('label', v)
    u_file  = G.nodes[u].get('source_file', '') or ''
    v_file  = G.nodes[v].get('source_file', '') or ''
    relation = d.get('relation', '')

    # Patron 1: arista "calls" donde source es ruta y target es plantilla
    u_is_route    = 'routes.py' in u_file or 'routes_' in u
    v_is_template = 'templates' in v_file or v_file.endswith('.html')
    if relation == 'calls' and u_is_route and v_is_template:
        problems.append({
            'tipo': 'INVERTIDA: ruta->plantilla',
            'source': u_label, 'source_file': u_file,
            'target': v_label, 'target_file': v_file,
            'fix': f'Invertir: la plantilla usa url_for hacia la ruta, no la ruta llama a la plantilla'
        })

    # Patron 2: modelo llama a ruta
    u_is_model    = 'models' in u_file and u_file.endswith('.py')
    v_is_route_f  = 'routes.py' in v_file
    if relation == 'calls' and u_is_model and v_is_route_f:
        problems.append({
            'tipo': 'INVERTIDA: modelo->ruta',
            'source': u_label, 'source_file': u_file,
            'target': v_label, 'target_file': v_file,
            'fix': 'Invertir: las rutas llaman a modelos, no al reves'
        })

    # Patron 3: helper importa blueprint
    u_is_helper   = 'helpers.py' in u_file
    v_is_bp_init  = '__init__.py' in v_file and 'blueprints' in v_file
    if relation == 'calls' and u_is_helper and v_is_bp_init:
        problems.append({
            'tipo': 'INVERTIDA: helper->blueprint',
            'source': u_label, 'source_file': u_file,
            'target': v_label, 'target_file': v_file,
            'fix': 'Los helpers no deben depender de blueprints (dependency inversion)'
        })

    # Patron 4: servicio llama a ruta (arquitectura rota)
    u_is_service  = 'services' in u_file and u_file.endswith('.py')
    if relation == 'calls' and u_is_service and v_is_route_f:
        problems.append({
            'tipo': 'INVERTIDA: servicio->ruta',
            'source': u_label, 'source_file': u_file,
            'target': v_label, 'target_file': v_file,
            'fix': 'Los servicios no deben llamar a rutas HTTP'
        })

print(f"Total problemas de direccion encontrados: {len(problems)}\n")
for i, p in enumerate(problems[:25]):
    print(f"[{i+1}] {p['tipo']}")
    print(f"  Source: {p['source']}")
    print(f"  Source file: {p['source_file']}")
    print(f"  Target: {p['target']}")
    print(f"  Target file: {p['target_file']}")
    print(f"  Fix: {p['fix']}")
    print()
