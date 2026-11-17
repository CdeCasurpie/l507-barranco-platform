"""Exact concatenation into one file, plus explicitly reduced render proxy."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/exitoso/home/barranco-roi')
import simplify_meshes as sm
import numpy as np
from roi.core import sha_file
root=Path(sys.argv[1]);normalized=root/'normalized';normalized.mkdir()
proxy=root/'render_parts';proxy.mkdir()
records=[]
def save(path,xyz,faces):
    with path.open('xb') as f:
        f.write(('ply\nformat binary_little_endian 1.0\ncomment native 019 coordinates; concatenation, not surface fusion\n'
         f'element vertex {len(xyz)}\nproperty float x\nproperty float y\nproperty float z\n'
         f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n').encode())
        np.asarray(xyz,dtype='<f4').tofile(f)
        rows=np.empty(len(faces),sm.FACE);rows['n']=3;rows['indices']=faces;rows.tofile(f)
def header(path):
    result={}
    with path.open('rb') as f:
        while True:
            line=f.readline()
            if line.startswith(b'element '):
                _,name,n=line.split();result[name.decode()]=int(n)
            if line.strip()==b'end_header':break
        result['offset']=f.tell()
    return result
for source in sorted((root/'raw/chunks').glob('*/scene_mesh.ply')):
    ms=sm.pm.MeshSet();ms.load_new_mesh(str(source));mesh=ms.current_mesh()
    xyz=mesh.vertex_matrix();faces=mesh.face_matrix()
    assert np.isfinite(xyz).all() and (faces>=0).all() and (faces<len(xyz)).all()
    p=normalized/(source.parent.name+'.ply');save(p,xyz,faces)
    records.append(dict(path=str(p),**header(p),source=str(source)))
    print('NORMALIZED',source.parent.name,len(xyz),len(faces),flush=True)
assert len(records)==26
nv=sum(r['vertex'] for r in records);nf=sum(r['face'] for r in records)
assert nv<2**31
combined=root/'manzana019_unida.ply'
with combined.open('xb') as out:
    out.write(('ply\nformat binary_little_endian 1.0\ncomment all 26 chunks concatenated; overlaps retained; no transforms\n'
     f'element vertex {nv}\nproperty float x\nproperty float y\nproperty float z\n'
     f'element face {nf}\nproperty list uchar int vertex_indices\nend_header\n').encode())
    for r in records:
        with Path(r['path']).open('rb') as f:
            f.seek(r['offset']);remaining=r['vertex']*12
            while remaining:
                data=f.read(min(8*1024**2,remaining));assert data
                out.write(data);remaining-=len(data)
    offset=0
    for r in records:
        with Path(r['path']).open('rb') as f:
            f.seek(r['offset']+r['vertex']*12)
            for first in range(0,r['face'],250000):
                count=min(250000,r['face']-first)
                faces=np.frombuffer(f.read(count*13),sm.FACE).copy()
                assert len(faces)==count and (faces['n']==3).all() and (faces['indices']<r['vertex']).all()
                faces['indices']+=offset;out.write(faces.tobytes())
        offset+=r['vertex']
# The original joined file is full-resolution. Only the render proxy is reduced.
budget=2_000_000
for r in records:
    ms=sm.pm.MeshSet();ms.load_new_mesh(r['path'])
    target=max(100,int(budget*r['face']/max(1,nf)))
    if r['face']>target:
        ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,preserveboundary=True,
            preservenormal=True,preservetopology=True,optimalplacement=True,autoclean=True)
    mesh=ms.current_mesh();p=proxy/Path(r['path']).name
    save(p,mesh.vertex_matrix(),mesh.face_matrix())
(root/'union-report.json').write_text(json.dumps(dict(mesh=str(combined),vertices=nv,faces=nf,
    sha256=sha_file(combined),parts=26,operation='concatenation only; no transforms or welding',
    render_proxy_target_faces=budget,render_proxy_decimated=True,originals_preserved=True),indent=2))
print('JOIN_READY',combined,nv,nf,flush=True)
