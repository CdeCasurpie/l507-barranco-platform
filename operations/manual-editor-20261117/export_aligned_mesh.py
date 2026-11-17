"""RGB-preserving lightweight derivative, one joined mesh in user's saved frame."""
import gc,json,sys,time
from pathlib import Path
sys.path.insert(0,'/home/exitoso/home/barranco-roi')
import simplify_meshes as sm
import numpy as np
from roi.core import sha_file

root=Path(sys.argv[1]);cfg=json.loads((root/'export-plan.json').read_text())
out=root/'lightweight';out.mkdir()
matrix=np.array(cfg['matrix'],dtype='f8')
rows=cfg['meshes'];budget=1877662
counts=[sm.header(root/'raw'/r['filename'])['faces'] for r in rows]
total=sum(counts);records=[]
def text(nv,nf):
    return ('ply\nformat binary_little_endian 1.0\n'
        'comment user manual world placement; RGB from dense points; overlapping chunks not welded\n'
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
            count=min(200000,len(faces)-first);r=np.empty(count,sm.FACE)
            r['n']=3;r['indices']=faces[first:first+count];r.tofile(f)
for item,count in zip(rows,counts):
    p=root/'raw'/item['filename'];assert sha_file(p)==item['sha256']
    xyz,faces,rgb=sm.load_mesh(p)
    target=min(count,max(100,round(budget*count/max(1,total))))
    ms=sm.pm.MeshSet();ms.add_mesh(sm.pm.Mesh(vertex_matrix=xyz,face_matrix=faces),'lightweight QEM')
    if count>target:
        ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,qualitythr=.3,
            preserveboundary=True,boundaryweight=10.,preservenormal=True,preservetopology=True,
            optimalplacement=True,planarquadric=True,planarweight=.1,autoclean=True)
    m=ms.current_mesh();vx=m.vertex_matrix();fc=m.face_matrix()
    _,indices=sm.cKDTree(xyz).query(vx,k=1,workers=4);colors=rgb[indices]
    world=vx@matrix[:3,:3].T+matrix[:3,3]
    dest=out/item['filename'];save(dest,world,fc,colors)
    records.append(dict(path=str(dest),**sm.header(dest)))
    print(cfg['block'],'LIGHT_RGB_WORLD',item['filename'],count,'->',len(fc),flush=True)
    del xyz,faces,rgb,ms,m,vx,fc,indices,colors,world;gc.collect()
nv=sum(r['vertices'] for r in records);nf=sum(r['faces'] for r in records);assert nv<2**31
dest=root/('manzana_'+cfg['block']+'_world_light_rgb.ply')
with dest.open('xb') as f:
    f.write(text(nv,nf))
    for r in records:
        with Path(r['path']).open('rb') as source:
            source.seek(r['offset']);left=r['vertices']*15
            while left:
                data=source.read(min(left,8*1024**2));assert data
                f.write(data);left-=len(data)
    base=0
    for r in records:
        with Path(r['path']).open('rb') as source:
            source.seek(r['offset']+r['vertices']*15)
            for first in range(0,r['faces'],200000):
                n=min(200000,r['faces']-first);faces=np.frombuffer(source.read(n*13),sm.FACE).copy()
                assert (faces['n']==3).all() and (faces['indices']<r['vertices']).all()
                faces['indices']+=base;f.write(faces.tobytes())
        base+=r['vertices']
(root/'delivery.json').write_text(json.dumps(dict(block=cfg['block'],mesh=str(dest),vertices=nv,faces=nf,
    bytes=dest.stat().st_size,sha256=sha_file(dest),target_faces=budget,
    matrix=cfg['matrix'],placement_session=cfg['session_id'],coordinate_frame='map_world local origin',
    geometry_deformed=False,vertices_welded=False,globally_fused=False,rgb=True,
    originals_preserved=True,parts=len(records),relative_face_reduction=1-nf/max(1,total)),indent=2))
print('DELIVERY_READY',dest,flush=True)
