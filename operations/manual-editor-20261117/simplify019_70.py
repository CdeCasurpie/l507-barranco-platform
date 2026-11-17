"""70% face reduction per chunk, then join unchanged native-coordinate parts."""
import gc
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,'/home/exitoso/home/barranco-roi')
import simplify_meshes as sm
import numpy as np
from roi.core import sha_file
root=Path(sys.argv[1]);output=root/'simplified70';output.mkdir()
def header(path):
    meta={}
    with path.open('rb') as f:
        while True:
            line=f.readline()
            assert line,'Truncated PLY'
            if line.startswith(b'element '):
                _,key,n=line.split();meta[key.decode()]=int(n)
            if line.strip()==b'end_header':break
        meta['offset']=f.tell()
    return meta
def text(nv,nf):
    return ('ply\nformat binary_little_endian 1.0\n'
        'comment 019 native coordinates; QEM target 70 percent face reduction; no vertex RGB\n'
        'comment concatenation of overlapping chunks; no surface fusion or hole filling\n'
        f'element vertex {nv}\nproperty float x\nproperty float y\nproperty float z\n'
        f'element face {nf}\nproperty list uchar int vertex_indices\nend_header\n').encode()
records=[];started=time.time()
for source in sorted((root/'normalized').glob('*.ply')):
    ms=sm.pm.MeshSet();ms.load_new_mesh(str(source));original=ms.current_mesh().face_number()
    target=int(original*.30)
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,qualitythr=.3,
        preserveboundary=True,boundaryweight=10.,preservenormal=True,preservetopology=True,
        optimalplacement=True,planarquadric=True,planarweight=.1,autoclean=True,selected=False)
    mesh=ms.current_mesh();xyz=mesh.vertex_matrix();faces=mesh.face_matrix()
    assert np.isfinite(xyz).all() and (faces>=0).all() and (faces<len(xyz)).all()
    path=output/source.name
    with path.open('xb') as f:
        f.write(text(len(xyz),len(faces)));np.asarray(xyz,dtype='<f4').tofile(f)
        for first in range(0,len(faces),250000):
            count=min(250000,len(faces)-first);rows=np.empty(count,sm.FACE)
            rows['n']=3;rows['indices']=faces[first:first+count];rows.tofile(f)
    record=dict(path=str(path),chunk=source.stem,original_faces=original,**header(path),sha256=sha_file(path))
    records.append(record)
    (output/'progress.json').write_text(json.dumps(dict(completed=len(records),total=26,last=record),indent=2))
    print('SIMPLIFIED019',source.stem,original,'->',len(faces),flush=True)
    del xyz,faces,mesh,ms;gc.collect()
assert len(records)==26
nv=sum(r['vertex'] for r in records);nf=sum(r['face'] for r in records)
assert nv<2**31
destination=output/'manzana019_unida_simplificada70.ply'
with destination.open('xb') as out:
    out.write(text(nv,nf))
    for row in records:
        with Path(row['path']).open('rb') as f:
            f.seek(row['offset']);left=row['vertex']*12
            while left:
                raw=f.read(min(left,8*1024**2));assert raw
                out.write(raw);left-=len(raw)
    base=0
    for row in records:
        with Path(row['path']).open('rb') as f:
            f.seek(row['offset']+row['vertex']*12)
            for first in range(0,row['face'],250000):
                count=min(250000,row['face']-first)
                faces=np.frombuffer(f.read(count*13),sm.FACE).copy()
                assert len(faces)==count and (faces['n']==3).all() and (faces['indices']<row['vertex']).all()
                faces['indices']+=base;out.write(faces.tobytes())
        base+=row['vertex']
original=sum(r['original_faces'] for r in records)
(output/'report.json').write_text(json.dumps(dict(mesh=str(destination),vertices=nv,faces=nf,
    original_faces=original,target_removed_fraction=.7,actual_removed_fraction=1-nf/original,
    sha256=sha_file(destination),seconds=time.time()-started,parts=records,
    coordinate_frame='019 native unchanged',vertex_rgb=False,originals_preserved=True,
    method='QEM per chunk, boundaries normals topology protected; no global plane regularization',
    globally_fused=False),indent=2))
print('SIMPLIFICATION_READY',destination,original,'->',nf,flush=True)
