"""Additional RGB derivative with official median face budget; not metric density."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/exitoso/home/barranco-roi')
import simplify_meshes as sm
import numpy as np
from roi.core import sha_file
root=Path(sys.argv[1]);out=root/'official_budget_rgb';out.mkdir()
source=root/'simplified70_rgb'
report=json.loads((source/'report.json').read_text())
budget=1877662
def text(nv,nf):
    return ('ply\nformat binary_little_endian 1.0\ncomment 019 RGB; official median face budget, not metric density\n'
        f'element vertex {nv}\nproperty float x\nproperty float y\nproperty float z\n'
        'property uchar red\nproperty uchar green\nproperty uchar blue\n'
        f'element face {nf}\nproperty list uchar int vertex_indices\nend_header\n').encode()
records=[]
for row in report['chunks']:
    p=Path(row['path']);xyz,faces,rgb=sm.load_mesh(p)
    target=max(100,round(budget*len(faces)/report['faces']))
    ms=sm.pm.MeshSet();ms.add_mesh(sm.pm.Mesh(vertex_matrix=xyz,face_matrix=faces),'019 lightweight')
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,qualitythr=.3,
        preserveboundary=True,boundaryweight=10.,preservenormal=True,preservetopology=True,
        optimalplacement=True,planarquadric=True,planarweight=.1,autoclean=True)
    m=ms.current_mesh();vx=m.vertex_matrix();fc=m.face_matrix()
    _,idx=sm.cKDTree(xyz).query(vx,k=1,workers=4);colors=rgb[idx]
    dest=out/p.name
    with dest.open('xb') as f:
        f.write(text(len(vx),len(fc)))
        v=np.empty(len(vx),sm.VERTEX)
        for i,n in enumerate(['x','y','z']):v[n]=vx[:,i]
        for i,n in enumerate(['red','green','blue']):v[n]=colors[:,i]
        v.tofile(f)
        rows=np.empty(len(fc),sm.FACE);rows['n']=3;rows['indices']=fc;rows.tofile(f)
    records.append(dict(path=str(dest),**sm.header(dest)))
    print('LIGHT019',p.stem,len(faces),'->',len(fc),flush=True)
nv=sum(r['vertices'] for r in records);nf=sum(r['faces'] for r in records)
dest=out/'manzana019_presupuesto_oficial_rgb.ply'
with dest.open('xb') as f:
    f.write(text(nv,nf))
    for r in records:
        with Path(r['path']).open('rb') as s:
            s.seek(r['offset']);left=r['vertices']*15
            while left:
                raw=s.read(min(left,8*1024**2));assert raw;f.write(raw);left-=len(raw)
    base=0
    for r in records:
        with Path(r['path']).open('rb') as s:
            s.seek(r['offset']+r['vertices']*15)
            for first in range(0,r['faces'],200000):
                count=min(200000,r['faces']-first)
                rows=np.frombuffer(s.read(count*13),sm.FACE).copy()
                assert (rows['indices']<r['vertices']).all()
                rows['indices']+=base;f.write(rows.tobytes())
        base+=r['vertices']
(out/'report.json').write_text(json.dumps(dict(mesh=str(dest),sha256=sha_file(dest),
    vertices=nv,faces=nf,bytes=dest.stat().st_size,target_faces=budget,
    metric_density_matched=False,reason='Match median face budget of official meshes, scale not yet certified',
    coordinate_frame='019 native unchanged',rgb=True,originals_preserved=True,
    globally_fused=False),indent=2))
print('LIGHTWEIGHT_READY',dest,nv,nf,flush=True)
