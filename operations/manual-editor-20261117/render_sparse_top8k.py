"""Actual full sparse RGB, orthographic XY projection, black background."""
import hashlib,json,math,sys,time,uuid
from pathlib import Path
from urllib.request import urlopen
import numpy as np
from PIL import Image
sys.path.insert(0,'/home/exitoso/home/barranco-roi')
from roi.catalog import read_sparse_points
root=Path('/data/barranco/review')/('sparse-render8k-'+uuid.uuid4().hex)
root.mkdir()
with urlopen('http://127.0.0.1:8765/api/alignment/catalog',timeout=60) as r:catalog=json.load(r)
with urlopen('http://127.0.0.1:8765/api/overview',timeout=60) as r:overview=json.load(r)
anchors={a['id']:a for a in catalog['anchors']}
rows=[anchors[b['block']] for b in overview['blocks']]
assert len(rows)==26
width,height=7680,4320
bounds=np.array(overview['bounds'],dtype='f8');center=(bounds[0,:2]+bounds[1,:2])/2
extent=bounds[1,:2]-bounds[0,:2]
units_per_pixel=max(extent[0]/width,extent[1]/height)*1.06
lo=center-np.array([width,height])*units_per_pixel/2
rgb=np.zeros((height*width,3),dtype='u1')
depth=np.full(height*width,-np.inf,dtype='f4')
sources=[];started=time.time();total=inside=0
for row in rows:
    xyz,colors=read_sparse_points(row['model'])
    matrix=np.array(row['matrix'],dtype='f8')
    model_count=len(xyz);visible=0
    for first in range(0,len(xyz),500000):
        world=xyz[first:first+500000]@matrix[:3,:3].T+matrix[:3,3]
        finite=np.isfinite(world).all(axis=1)
        xy=np.floor((world[:,:2]-lo)/units_per_pixel).astype('i8')
        ix=xy[:,0];iy=height-1-xy[:,1]
        good=finite&(ix>=0)&(ix<width)&(iy>=0)&(iy<height)
        indices=np.flatnonzero(good);visible+=len(indices)
        if not len(indices):continue
        pixel=iy[indices]*width+ix[indices];z=world[indices,2]
        # Keep the topmost observed point per output pixel, not an invented surface.
        order=np.lexsort((z,pixel));sorted_pixel=pixel[order]
        last=np.r_[sorted_pixel[1:]!=sorted_pixel[:-1],True];chosen=order[last]
        ids=pixel[chosen];zs=z[chosen]
        higher=zs>depth[ids]
        ids=ids[higher];zs=zs[higher]
        rgb[ids]=colors[first+indices[chosen[higher]]]
        depth[ids]=zs
    total+=model_count;inside+=visible
    sources.append(dict(id=row['id'],block=row.get('block'),model=row['model'],matrix=row['matrix'],
        hashes=row.get('hashes'),points=model_count,points_in_frame=visible))
    print('SPARSE_RENDER',row.get('block',row['id']),model_count,'points',flush=True)
image=Image.fromarray(rgb.reshape(height,width,3))
path=root/'barranco_sparse_superior_8K_RGB.png';image.save(path,compress_level=6)
preview=image.resize((1920,1080),Image.Resampling.LANCZOS);preview.save(root/'preview_1920.png')
report=dict(image=str(path),width=width,height=height,projection='orthographic XY, looking down -Z, north +Y up',
    background='black',original_rgb=True,full_sparse=True,source_points=total,points_in_frame=inside,
    rendered_pixels=int(np.isfinite(depth).sum()),point_size_pixels=1,grid=False,labels=False,ui=False,
    world_origin=catalog['world_origin'],sources=sources,frame_xy_min=lo.tolist(),
    units_per_pixel=units_per_pixel,frame_note='Same world orientation; fit overview robust bounds plus 6% margin, not exact screenshot camera',
    elapsed_seconds=time.time()-started)
(root/'report.json').write_text(json.dumps(report,indent=2))
Path('/tmp/opencode/sparse8k-delivery.json').write_text(json.dumps(dict(directory=str(root)),indent=2))
web=Path('/tmp/opencode/render019-web/sparse8k');web.mkdir(exist_ok=True)
for name,target in [('barranco_sparse_8K.png',path),('preview.png',root/'preview_1920.png')]:
    link=web/name
    if link.is_symlink():link.unlink()
    elif link.exists():raise RuntimeError('Refuse replacing a non-symlink')
    link.symlink_to(target)
(web/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Barranco · sparse 8K</title>
<style>body{margin:20px;background:#000;color:#eee;font:16px system-ui}a{color:#8bd5ff}img{width:100%;height:auto}</style>
<h1>Barranco · nube sparse · superior ortográfica</h1>
<p>7680 × 4320 · RGB original · fondo negro · sin cuadrícula ni etiquetas · colocaciones manuales guardadas.</p>
<a href="barranco_sparse_8K.png" download>Descargar PNG 8K original</a><p><a href="barranco_sparse_8K.png">Abrir imagen a resolución completa</a></p>
<img src="preview.png" alt="Vista superior de las nubes sparse de Barranco">''')
print('SPARSE8K_READY',path,'POINTS',total,'SECONDS',report['elapsed_seconds'],flush=True)
