import json
from networkx.readwrite import json_graph
import networkx as nx
from collections import defaultdict
from pathlib import Path

new_data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
G = json_graph.node_link_graph(new_data, edges='links')

print("\n[4] Top 15 god nodes por degree total:")
top = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:15]
for n in top:
    nd = G.nodes[n]
    label = nd.get('label', n)[:50]
    src = nd.get('source_file', '')[:45]
    deg = G.degree(n)
    print(f"  [{deg:3d}] {label} | {src}")

print()

# 5. Endpoints sin fuente
ep_nodes = [(n, G.nodes[n]) for n in G.nodes() if n.startswith('ep_') or n.startswith('endpoint_')]
ep_no_route = [(n, d) for n, d in ep_nodes if not d.get('source_file','')]
print(f"[5] Endpoints sin archivo fuente: {len(ep_no_route)} de {len(ep_nodes)} endpoints")
for n, d in ep_no_route[:15]:
    print(f"  {n}: '{d.get('label','')}'")

print()

# 6. Rutas llamadas desde templates vs rutas definidas en routes.py
# Buscar endpoints que templates referencian pero que NO coinciden con rutas reales
called_endpoints = set()
for u, v, d in G.edges(data=True):
    u_file = G.nodes[u].get('source_file','') or ''
    if ('templates' in u_file or u_file.endswith('.html')) and d.get('relation') == 'calls':
        called_endpoints.add(v)

# Rutas definidas en routes.py
defined_routes = set(n for n in G.nodes()
                     if 'routes.py' in (G.nodes[n].get('source_file','') or ''))

# Endpoints llamados desde templates que no tienen correspondencia en routes
phantom_endpoints = called_endpoints - defined_routes
print(f"[6] Endpoints phantom (llamados desde templates pero sin ruta real): {len(phantom_endpoints)}")
for ep in sorted(list(phantom_endpoints))[:20]:
    nd = G.nodes[ep]
    print(f"  {nd.get('label', ep)} | src: {nd.get('source_file','(ninguno)')}")

print()

# 7. Detectar duplicados reales — mismo label en fuente diferente (no primitivos)
label_map = defaultdict(list)
PRIMITIVES = {'str', 'int', 'float', 'bool', 'dict', 'list', 'tuple', 'exception', 'bytes',
              'none', 'datetime', '__repr__()', '__init__()', '__str__()'}
for n, d in G.nodes(data=True):
    label = d.get('label', '').strip().lower()
    src = d.get('source_file','') or ''
    if label and label not in PRIMITIVES and len(label) > 3:
        label_map[label].append((n, src))

real_dups = {k: v for k, v in label_map.items() if len(v) > 1}
print(f"[7] Duplicados reales (misma entidad en multiples fuentes): {len(real_dups)}")
for label, entries in list(real_dups.items())[:15]:
    sources = [e[1] for e in entries]
    print(f"  '{label}':")
    for nid, src in entries:
        print(f"    - {nid} ({src})")
