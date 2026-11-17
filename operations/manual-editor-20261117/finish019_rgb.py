"""Color existing QEM derivatives from retained RGB references; no geometry edits."""
import gc
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/exitoso/home/barranco-roi')
import simplify_meshes as sm
import numpy as np
from roi.core import sha_file
root=Path(sys.argv[1]);output=root/'simplified70_rgb';output.mkdir()
def plain_header(path):
    result={}
    with path.open('rb') as f:
        while True:
            line=f.readline();assert line
            if line.startswith(b'element '):
                _,name,n=line.split();result[name.decode()]=int(n)
            if line.strip()==b'end_header':break
        result['offset']=f.tell()
    return result
def text(nv,nf):
    return ('ply\nformat binary_little_endian 1.0\n'
        'comment 019 native frame; QEM70 derivative; RGB from original dense reference\n'
        'comment overlapping parts concatenated; no surface fusion or texture atlas\n'
        f'element vertex {nv}\nproperty float x\nproperty float y\nproperty float z\n'
        'property uchar red\nproperty uchar green\nproperty uchar blue\n'
        f'element face {nf}\nproperty list uchar int vertex_indices\nend_header\n').encode()
def save(path,xyz,faces,rgb):
    assert np.isfinite(xyz).all() and (faces>=0).all() and (faces<len(xyz)).all()
    with path.open('xb') as f:
        f.write(text(len(xyz),len(faces)))
        for first in range(0,len(xyz),200000):
            last=min(first+200000,len(xyz));v=np.empty(last-first,sm.VERTEX)
            for i,n in enumerate(['x','y','z']):v[n]=xyz[first:last,i]
            for i,n in enumerate(['red','green','blue']):v[n]=rgb[first:last,i]
            v.tofile(f)
        for first in range(0,len(faces),200000):
            rows=np.empty(min(200000,len(faces)-first),sm.FACE);rows['n']=3
            rows['indices']=faces[first:first+len(rows)];rows.tofile(f)
records=[]
for source in sorted((root/'simplified70').glob('[0-9][0-9][0-9].ply')):
    reference=root/'colored-reference'/source.name
    xyz,_,rgb=sm.load_mesh(reference)
    meta=plain_header(source)
    with source.open('rb') as f:
        f.seek(meta['offset'])
        vertices=np.fromfile(f,dtype='<f4',count=meta['vertex']*3).reshape(-1,3)
        rows=np.fromfile(f,dtype=sm.FACE,count=meta['face'])
    assert (rows['n']==3).all()
    _,indices=sm.cKDTree(xyz).query(vertices,k=1,workers=4)
    faces=rows['indices'];colors=rgb[indices]
    path=output/source.name
    save(path,vertices,faces,colors)
    check_xyz,check_faces,_=sm.load_mesh(path)
    np.testing.assert_array_equal(check_xyz.astype('<f4'),vertices)
    np.testing.assert_array_equal(check_faces,faces)
    record=dict(path=str(path),chunk=source.stem,**sm.header(path),sha256=sha_file(path))
    records.append(record)
    # A separate, explicitly lower-resolution proxy keeps interactive renders light.
    ms=sm.pm.MeshSet()
    ms.add_mesh(sm.pm.Mesh(vertex_matrix=vertices,face_matrix=faces),'render proxy')
    target=max(100,int(meta['face']*2_000_000/14_761_295))
    if len(faces)>target:
        ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,preserveboundary=True,
            preservenormal=True,preservetopology=True,autoclean=True)
    candidate=ms.current_mesh();pv=candidate.vertex_matrix();pf=candidate.face_matrix()
    _,pi=sm.cKDTree(vertices).query(pv,k=1,workers=4)
    proxy=output/'render_parts';proxy.mkdir(exist_ok=True)
    save(proxy/source.name,pv,pf,colors[pi])
    print('SIMPLIFIED019_RGB',source.stem,'XYZ and faces unchanged',flush=True)
    del xyz,rgb,vertices,rows,faces,colors,check_xyz,check_faces,indices,ms,candidate,pv,pf,pi
    gc.collect()
assert len(records)==26
nv=sum(r['vertices'] for r in records);nf=sum(r['faces'] for r in records)
assert nv<2**31
destination=output/'manzana019_unida_simplificada70_rgb.ply'
with destination.open('xb') as out:
    out.write(text(nv,nf))
    for row in records:
        with Path(row['path']).open('rb') as f:
            f.seek(row['offset']);left=row['vertices']*15
            while left:
                raw=f.read(min(left,8*1024**2));assert raw
                out.write(raw);left-=len(raw)
    base=0
    for row in records:
        with Path(row['path']).open('rb') as f:
            f.seek(row['offset']+row['vertices']*15)
            for first in range(0,row['faces'],200000):
                count=min(200000,row['faces']-first)
                faces=np.frombuffer(f.read(count*13),sm.FACE).copy()
                assert (faces['indices']<row['vertices']).all()
                faces['indices']+=base;out.write(faces.tobytes())
        base+=row['vertices']
(output/'report.json').write_text(json.dumps(dict(mesh=str(destination),vertices=nv,faces=nf,
    sha256=sha_file(destination),qem_geometry_unchanged=True,originals_preserved=True,
    target_removed_fraction=.7,vertex_rgb=True,no_texture_atlas=True,globally_fused=False,
    color_method='nearest colored reference-mesh vertex, as in previous simplification delivery',
    chunks=records),indent=2))
print('SIMPLIFIED019_RGB_JOINED',destination,flush=True)
