import json
from networkx.readwrite import json_graph
import networkx as nx
from collections import defaultdict
from pathlib import Path

new_data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
G = json_graph.node_link_graph(new_data, edges='links')

print("=== AUDITORIA PROFUNDA DEL GRAFO ===\n")

# 1. Nodos huerfanos (sin aristas)
orphans = [n for n in G.nodes() if G.degree(n) == 0]
print(f"[1] Nodos huerfanos (degree=0): {len(orphans)}")
for o in orphans[:8]:
    print(f"  - {G.nodes[o].get('label', o)} ({G.nodes[o].get('source_file','')})")

print()

# 2. Nodos duplicados (mismo label, distinto ID)
label_map = defaultdict(list)
for n, d in G.nodes(data=True):
    label = d.get('label', '').strip().lower()
    if label:
        label_map[label].append(n)
dups = {k: v for k, v in label_map.items() if len(v) > 1}
print(f"[2] Nodos con label duplicado: {len(dups)}")
for label, ids in list(dups.items())[:10]:
    files = [G.nodes[i].get('source_file','?') for i in ids]
    print(f"  '{label}' -> {ids}")
    print(f"    archivos: {files}")

print()

# 3. Aristas rotas: source o target no existen como nodo
broken = []
for u, v in G.edges():
    if u not in G.nodes or v not in G.nodes:
        broken.append((u, v))
print(f"[3] Aristas rotas (nodo inexistente): {len(broken)}")
for b in broken[:5]:
    print(f"  {b[0]} -> {b[1]}")

print()

# 4. God nodes con ratio in/out sospechoso
# En arquitectura correcta: templates tienen muchos OUTBOUND (calls endpoints)
# Las rutas tienen muchos INBOUND (llamadas desde templates + servicios)
print("[4] Top 15 god nodes y su ratio in/out:")
degrees = [(G.in_degree(n), G.out_degree(n), n) for n in G.nodes() if isinstance(G, nx.DiGraph) or True]
top = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:15]
for n in top:
    nd = G.nodes[n]
    label = nd.get('label', n)[:45]
    src = nd.get('source_file', '')[:40]
    deg = G.degree(n)
    print(f"  [{deg:3d}] {label} | {src}")

print()

# 5. Endpoints referenciados en templates que NO existen como rutas en routes.py
# Buscar nodos con prefijo 'ep_' o 'endpoint_' que no tienen source en routes.py
ep_nodes = [(n, G.nodes[n]) for n in G.nodes() if n.startswith('ep_') or n.startswith('endpoint_')]
ep_no_route = [(n, d) for n, d in ep_nodes if not d.get('source_file','')]
print(f"[5] Endpoints sin archivo fuente ({len(ep_no_route)} de {len(ep_nodes)} eps):")
for n, d in ep_no_route[:15]:
    print(f"  {n}: '{d.get('label','')}'")

print()

# 6. Verificar simetria: si A llama a B, B deberia ser llamado (tener in_degree > 0)
# Buscar endpoints que solo tienen aristas salientes pero son destinos de calls
called_targets = set()
for u, v, d in G.edges(data=True):
    if d.get('relation') == 'calls':
        called_targets.add(v)

# Los targets de calls que a su vez llaman cosas - OK
# Los nodos que NUNCA son llamados pero son endpoints - sospechoso
route_nodes = [(n, G.nodes[n]) for n in G.nodes()
               if 'routes.py' in (G.nodes[n].get('source_file','') or '')]
uncalled_routes = [(n, d) for n, d in route_nodes
                   if n not in called_targets and G.degree(n) > 0]
print(f"[6] Rutas nunca llamadas desde templates/servicios: {len(uncalled_routes)}")
for n, d in uncalled_routes[:10]:
    print(f"  {d.get('label', n)} | deg={G.degree(n)}")
