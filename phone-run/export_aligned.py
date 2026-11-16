"""Exporta la sparse COLMAP (RGB real) de manzanas ya alineadas al marco map_world
(world_from_sparse = world_from_asset @ inv(sparse_from_asset)) y verifica contra
sparse_global_por_manzana.ply (mismo block_id). Python puro (sin numpy)."""
import json, struct, sys
from pathlib import Path
E = Path('/data/barranco/exports/barranco-full-v1'); A = Path('/data/barranco/alignment-inputs/barranco-full-v1')
OUT = Path.home() / 'phone-run/aligned'; OUT.mkdir(exist_ok=True)
blocks = sys.argv[1:]; ids = {int(b) for b in blocks}
atlas = {a['block_id']: a for a in json.load(open(E / 'transforms_atlas.json'))['atlas']}

def stats(pts):
    n = len(pts); c = [sum(p[i] for p in pts) / n for i in range(3)]
    return n, c, [min(p[i] for p in pts) for i in range(3)] + [max(p[i] for p in pts) for i in range(3)]

# global sparse: x,y,z f4, rgb u1, block_id u2 = 17 bytes
gpts = {b: [] for b in ids}
with open(E / 'sparse_global_por_manzana.ply', 'rb') as f:
    while f.readline() != b'end_header\n': pass
    data = f.read()
for x, y, z, r, g, b, bid in struct.iter_unpack('<3f3BH', data):
    if bid in ids: gpts[bid].append((x, y, z))
del data

for blk in blocks:
    bid = int(blk); M = atlas[bid]['world_from_asset']
    # experimento usado por el atlas (p.ej. 007 tiene combined_v1 y recovered_v2)
    bjp = next(p for p in (A / blk).glob('*/block.json')
               if any(x['uri'] == atlas[bid]['source_uri'] for x in json.load(open(p))['assets']))
    bj = json.load(open(bjp))
    s2a = next(x for x in bj['assets'] if x['asset_id'] == 'dense')['sparse_from_asset']
    assert all(abs(s2a[i][j] - (i == j)) < 1e-12 for i in range(4) for j in range(4)), f'{blk}: sparse_from_asset no es identidad'
    out = []; pts = []
    with open(bjp.parent / 'model' / 'points3D.bin', 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            _, x, y, z, r, g, b, _, t = struct.unpack('<Q3d3BdQ', f.read(51)); f.seek(8 * t, 1)
            w = tuple(M[i][0] * x + M[i][1] * y + M[i][2] * z + M[i][3] for i in range(3))
            pts.append(w); out.append(struct.pack('<3f3B', *w, r, g, b))
    n1, c1, b1 = stats(pts); n2, c2, b2 = stats(gpts[bid])
    dc = sum((c1[i] - c2[i]) ** 2 for i in range(3)) ** .5; db = max(abs(b1[i] - b2[i]) for i in range(6))
    print(f"{blk} [{bjp.parent.name}]: puntos={n1} en_global={n2} dif_centroide={dc:.3f} m dif_bbox={db:.3f} m", flush=True)
    with open(OUT / f'manzana-{blk}_alineada.ply', 'wb') as f:
        f.write(f"ply\nformat binary_little_endian 1.0\ncomment Barranco {blk}: sparse COLMAP con RGB real, marco map_world (EPSG:32718 local; sumar world_origin de map.json para UTM)\nelement vertex {n1}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n".encode())
        f.write(b''.join(out))
