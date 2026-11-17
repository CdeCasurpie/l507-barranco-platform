"""Transfer existing dense RGB to mesh vertices without changing XYZ or faces."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from scipy.spatial import cKDTree

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
    return h.hexdigest()
def header(path):
    dtype=[];nv=nf=0;current=None
    aliases={'float32':'<f4','float':'<f4','uint8':'u1','uchar':'u1','float64':'<f8','double':'<f8'}
    with path.open('rb') as f:
        assert f.readline().strip()==b'ply'
        while True:
            row=f.readline().decode().split()
            assert row
            if row[0]=='format':assert row[1]=='binary_little_endian'
            if row[0]=='element':
                current=row[1]
                if current=='vertex':nv=int(row[2])
                elif current=='face':nf=int(row[2])
            elif row[0]=='property' and current=='vertex':
                assert row[1]!='list';dtype.append((row[2],aliases[row[1]]))
            elif row[0]=='end_header':break
        return dict(vertices=nv,faces=nf,dtype=np.dtype(dtype),offset=f.tell())

root=Path(sys.argv[1]);destination=root/'colored-chunks';destination.mkdir()
manifest=json.loads((root/'mesh-chunks.json').read_text());assert manifest['complete']
records=[]
for name in manifest['meshes']:
    mesh=Path(name);chunk=mesh.parent
    cloud=chunk/'scene_dense_scalar.ply'
    receipt=json.loads((chunk/'batch-receipt.json').read_text())
    assert sha(cloud)==receipt['cloud']['sha256']
    cm=header(cloud);mm=header(mesh)
    assert all(n in cm['dtype'].names for n in ['x','y','z','red','green','blue'])
    assert mm['dtype'].names==('x','y','z') and mm['dtype'].itemsize==12
    cv=np.memmap(cloud,dtype=cm['dtype'],mode='r',offset=cm['offset'],shape=(cm['vertices'],))
    mv=np.memmap(mesh,dtype=mm['dtype'],mode='r',offset=mm['offset'],shape=(mm['vertices'],))
    xyz=np.column_stack([cv[n] for n in ['x','y','z']])
    tree=cKDTree(xyz);output=destination/(chunk.name+'.ply')
    out_dtype=np.dtype([('x','<f4'),('y','<f4'),('z','<f4'),('red','u1'),('green','u1'),('blue','u1')])
    distance_samples=[];coordinates=hashlib.sha256()
    with output.open('xb') as out:
        out.write(('ply\nformat binary_little_endian 1.0\ncomment dense nearest-point RGB; XYZ and faces unchanged\n'
            f'element vertex {mm["vertices"]}\nproperty float x\nproperty float y\nproperty float z\n'
            'property uchar red\nproperty uchar green\nproperty uchar blue\n'
            f'element face {mm["faces"]}\nproperty list uchar int vertex_indices\nend_header\n').encode())
        for first in range(0,mm['vertices'],200000):
            part=mv[first:first+200000];points=np.column_stack([part[n] for n in ['x','y','z']])
            distances,indices=tree.query(points,k=1,workers=4)
            rows=np.empty(len(part),out_dtype)
            for n in ['x','y','z']:rows[n]=part[n]
            for n in ['red','green','blue']:rows[n]=cv[n][indices]
            coordinates.update(points.astype('<f4').tobytes())
            distance_samples.extend(distances[::max(1,len(distances)//2000)].tolist())
            out.write(rows.tobytes())
        with mesh.open('rb') as source:
            source.seek(mm['offset']+mm['vertices']*12)
            shutil.copyfileobj(source,out,8*1024**2)
    # Verify geometry after writing: compare every coordinate and face byte.
    check=header(output)
    colored=np.memmap(output,dtype=check['dtype'],mode='r',offset=check['offset'],shape=(check['vertices'],))
    verified=hashlib.sha256()
    for first in range(0,check['vertices'],200000):
        part=colored[first:first+200000]
        verified.update(np.column_stack([part[n] for n in ['x','y','z']]).astype('<f4').tobytes())
    assert verified.hexdigest()==coordinates.hexdigest()
    with mesh.open('rb') as a,output.open('rb') as b:
        a.seek(mm['offset']+mm['vertices']*12);b.seek(check['offset']+check['vertices']*15)
        while True:
            left=a.read(8*1024**2);right=b.read(8*1024**2)
            assert left==right
            if not left:break
    records.append(dict(chunk=chunk.name,path=str(output),sha256=sha(output),
        vertices=mm['vertices'],faces=mm['faces'],xyz_unchanged=True,faces_unchanged=True,
        dense_sha256=receipt['cloud']['sha256'],
        nearest_distance_p95_native_units=float(np.percentile(distance_samples,95))))
    (destination/'progress.json').write_text(json.dumps(dict(completed=len(records),total=26),indent=2))
    print('COLORED019',chunk.name,'XYZ/faces verified unchanged',flush=True)
    del cv,mv,colored,xyz,tree
(destination/'manifest.json').write_text(json.dumps(dict(complete=True,meshes=records,
    method='Nearest dense-point RGB transfer; same type of post-mesh color transfer as previous campaign',
    no_texture_atlas=True,geometry_unchanged=True),indent=2))
