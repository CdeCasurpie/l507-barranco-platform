"""Join verified, already world-aligned PLY meshes without welding or transforms."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
from roi.core import atomic_json, sha_file

ROOT = Path(__file__).resolve().parent
BASE = ROOT/'exports/mesh-campaign-20261112'
VERTEX = np.dtype([('x','<f4'),('y','<f4'),('z','<f4'),('red','u1'),('green','u1'),('blue','u1')])
FACE = np.dtype([('n','u1'),('indices','<u4',(3,))])


def header(path):
    elements = {}
    current = None
    with path.open('rb') as f:
        if f.readline().strip() != b'ply':
            raise ValueError('Not a PLY: '+str(path))
        while True:
            raw = f.readline()
            if not raw:
                raise ValueError('Truncated header')
            row = raw.decode('ascii').split()
            if not row:
                continue
            if row[0] == 'end_header':
                break
            if row[0] == 'format' and row[1:] != ['binary_little_endian','1.0']:
                raise ValueError('Expected binary little-endian')
            if row[0] == 'element':
                current = row[1]
                elements[current] = dict(count=int(row[2]), properties=[])
            elif row[0] == 'property':
                elements[current]['properties'].append(row[1:])
        offset = f.tell()
    if list(elements) != ['vertex','face']:
        raise ValueError('Unexpected mesh elements')
    aliases = {'float32':'float','uint8':'uchar','uint32':'int','int32':'int','uint':'int'}
    properties = [[aliases.get(v,v) for v in row] for row in elements['vertex']['properties']]
    if properties != [['float','x'],['float','y'],['float','z'],['uchar','red'],['uchar','green'],['uchar','blue']]:
        raise ValueError('Unexpected XYZ/RGB schema')
    properties = [[aliases.get(v,v) for v in row] for row in elements['face']['properties']]
    if properties != [['list','uchar','int','vertex_indices']]:
        raise ValueError('Unexpected triangle schema')
    nv, nf = elements['vertex']['count'], elements['face']['count']
    if path.stat().st_size != offset+nv*15+nf*13:
        raise ValueError('Mesh size does not match header')
    return dict(vertices=nv,faces=nf,offset=offset)


def combine():
    manifest = json.loads((BASE/'manifest.json').read_text())
    assert manifest['collected'] == 15 and not manifest['failed']
    records = []
    for block, item in sorted(manifest['blocks'].items()):
        path = BASE/block/('manzana_'+block+'_world.ply')
        meta = header(path)
        assert meta['vertices'] == item['vertices'] and meta['faces'] == item['faces']
        assert sha_file(path) == item['sha256'], 'Source checksum mismatch '+block
        records.append(dict(block=block,path=path,source=item,**meta))
    nv = sum(r['vertices'] for r in records)
    nf = sum(r['faces'] for r in records)
    assert nv < 2**31
    output = BASE/'barranco_15_manzanas_world.ply'
    if output.exists() or output.with_suffix('.ply.part').exists():
        raise ValueError('Combined destination already exists')
    assert shutil.disk_usage(BASE).free > nv*15+nf*13+10*1024**3
    temporary = output.with_suffix('.ply.part')
    text = ('ply\nformat binary_little_endian 1.0\n'
            'comment 15 user-selected manzanas joined in map_world; original RGB\n'
            'comment no additional transforms, welding, smoothing or hole filling\n'
            f'element vertex {nv}\nproperty float x\nproperty float y\nproperty float z\n'
            'property uchar red\nproperty uchar green\nproperty uchar blue\n'
            f'element face {nf}\nproperty list uchar int vertex_indices\nend_header\n')
    bounds = np.array([[np.inf]*3,[-np.inf]*3])
    ranges = []
    with temporary.open('xb') as out:
        out.write(text.encode())
        for r in records:
            with r['path'].open('rb') as src:
                src.seek(r['offset'])
                for start in range(0,r['vertices'],500000):
                    count = min(500000,r['vertices']-start)
                    raw = src.read(count*15)
                    vertices = np.frombuffer(raw,VERTEX)
                    xyz = np.column_stack([vertices[n] for n in ['x','y','z']])
                    assert len(vertices)==count and np.isfinite(xyz).all()
                    bounds[0] = np.minimum(bounds[0],xyz.min(axis=0))
                    bounds[1] = np.maximum(bounds[1],xyz.max(axis=0))
                    out.write(raw)
        vertex_base = face_base = 0
        for r in records:
            with r['path'].open('rb') as src:
                src.seek(r['offset']+r['vertices']*15)
                for start in range(0,r['faces'],500000):
                    count = min(500000,r['faces']-start)
                    faces = np.frombuffer(src.read(count*13),FACE).copy()
                    assert len(faces)==count and (faces['n']==3).all()
                    assert (faces['indices']<r['vertices']).all()
                    faces['indices'] += vertex_base
                    assert (faces['indices']<nv).all()
                    out.write(faces.tobytes())
            ranges.append(dict(block=r['block'],first_vertex=vertex_base,vertices=r['vertices'],
                               first_face=face_base,faces=r['faces'],source_sha256=r['source']['sha256']))
            vertex_base += r['vertices']
            face_base += r['faces']
            print('JOINED',r['block'],r['vertices'],'vertices',r['faces'],'faces',flush=True)
        out.flush()
        os.fsync(out.fileno())
    check = header(temporary)
    assert check['vertices']==nv and check['faces']==nf
    # Read back the published candidate, checking every global triangle index.
    with temporary.open('rb') as f:
        f.seek(check['offset']+nv*15)
        for start in range(0,nf,500000):
            faces = np.frombuffer(f.read(min(500000,nf-start)*13),FACE)
            assert (faces['n']==3).all() and (faces['indices']<nv).all()
        assert not f.read(1)
    checksum = sha_file(temporary)
    temporary.rename(output)
    report = dict(mesh=str(output),vertices=nv,faces=nf,bytes=output.stat().st_size,sha256=checksum,
                  coordinate_frame='map_world',bounds=bounds.tolist(),blocks=ranges,
                  operation='Concatenate aligned XYZ/RGB and offset triangle indices; no vertex welding or extra transforms')
    atomic_json(output.with_suffix('.json'),report)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return output


def open_viewer(path, desktop_pid):
    env = {k:v for k,v in os.environ.items() if k in ['HOME','USER','LOGNAME','PATH','LANG','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS']}
    proc = Path('/proc')/str(desktop_pid)
    if proc.stat().st_uid != os.getuid() or (proc/'comm').read_text().strip() != 'meshlab':
        raise ValueError('Expected an existing MeshLab process owned by this user')
    keys = {b'DISPLAY',b'XAUTHORITY',b'WAYLAND_DISPLAY',b'XDG_RUNTIME_DIR',b'DBUS_SESSION_BUS_ADDRESS',b'QT_QPA_PLATFORM'}
    for field in (proc/'environ').read_bytes().split(b'\0'):
        key, sep, value = field.partition(b'=')
        if sep and key in keys:
            env[key.decode()] = value.decode()
    command = ['systemd-run','--user','--unit=barranco-combined-view','-p','MemoryMax=40G','-p','MemorySwapMax=0','-p','Nice=10']
    for key in ['DISPLAY','XAUTHORITY','WAYLAND_DISPLAY','QT_QPA_PLATFORM']:
        if key in env:
            command += ['--setenv='+key+'='+env[key]]
    command += ['meshlab',str(path)]
    subprocess.run(command,env=env,check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--desktop-pid',type=int)
    args = parser.parse_args()
    output = combine()
    if args.desktop_pid:
        open_viewer(output,args.desktop_pid)
