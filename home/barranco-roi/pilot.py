"""Measured surface pilot, strictly using the user's saved 025 polygon."""
import os
os.environ.update(OPENBLAS_NUM_THREADS='2', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
import argparse
import json
from pathlib import Path
import sys
import time
import hashlib
import shutil
import subprocess
import threading
import numpy as np
from scipy.spatial import cKDTree, Delaunay
import shapely
from shapely.geometry import LineString, Point, Polygon
from roi.core import ply_header, world_xyz, polygon, inside, atomic_json, output_header

ROOT=Path(__file__).resolve().parent
SELECTION='s-1794364122096131540'
BASE=Path('/data/barranco/roi/025')/SELECTION
OUT=BASE/'pilot-v1'
SOURCE=BASE/'j-1794364335553248746-4dc292/dense_roi_local.ply'
VOXEL=.05
allowed=set(os.sched_getaffinity(0));efficient={8,9,10,11}
if efficient<=allowed:os.sched_setaffinity(0,efficient)


def log(*args):print(time.strftime('%H:%M:%S'),*args,flush=True)


def guard(extra=0):
    if shutil.disk_usage('/data').free < 50*1024**3+extra:
        raise RuntimeError('Insufficient storage above the 50 GiB reserve')
    temps=[]
    for hw in Path('/sys/class/hwmon').glob('hwmon*'):
        n=hw/'name'
        if n.exists() and n.read_text().strip() in ['coretemp','k10temp']:
            temps.extend(int(p.read_text())/1000 for p in hw.glob('temp*_input'))
    if temps and max(temps)>=90:raise RuntimeError('CPU reached 90 C: pause and review pilot')


def save_cloud(path,xyz,rgb,normals):
    props=[('x','float'),('y','float'),('z','float'),('red','uchar'),('green','uchar'),('blue','uchar'),('nx','float'),('ny','float'),('nz','float')]
    dt=np.dtype([(n,'u1' if t=='uchar' else '<f4') for n,t in props])
    d=np.empty(len(xyz),dt)
    for i,n in enumerate(['x','y','z']):d[n]=xyz[:,i]
    for i,n in enumerate(['red','green','blue']):d[n]=rgb[:,i]
    for i,n in enumerate(['nx','ny','nz']):d[n]=normals[:,i]
    with path.open('xb') as f:f.write(output_header(len(d),props));f.write(d.tobytes())


def save_mesh(path,vertices,faces,colors):
    props=[('x','float'),('y','float'),('z','float'),('red','uchar'),('green','uchar'),('blue','uchar')]
    vd=np.empty(len(vertices),dtype=[(n,'u1' if t=='uchar' else '<f4') for n,t in props])
    for i,n in enumerate(['x','y','z']):vd[n]=vertices[:,i]
    for i,n in enumerate(['red','green','blue']):vd[n]=colors[:,i]
    fd=np.empty(len(faces),dtype=[('n','u1'),('indices','<i4',(3,))]);fd['n']=3;fd['indices']=faces
    guard(vd.nbytes+fd.nbytes+16*1024**2)
    text='ply\nformat binary_little_endian 1.0\ncomment map_world metric; open surfaces, no hole filling\n'
    text+=f'element vertex {len(vertices)}\n'+''.join(f'property {t} {n}\n' for n,t in props)
    text+=f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n'
    with path.open('xb') as f:f.write(text.encode());f.write(vd.tobytes());f.write(fd.tobytes())


def selection():
    return json.loads((ROOT/'state/selections'/f'{SELECTION}.json').read_text())


def prepare(voxel=VOXEL,replace=False):
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'common.npz').exists() and not replace:raise RuntimeError('Common sample already published')
    if replace:
        previous=json.loads((OUT/'prepare.json').read_text())
        if previous['selection_id']!=SELECTION or previous['source']!=str(SOURCE):raise RuntimeError('Refusing to replace unrelated derived data')
    started=time.monotonic();s=selection();T=np.array(s['source']['world_from_block'])
    p=polygon(s['vertices']);meta=ply_header(SOURCE)
    raw=np.fromfile(SOURCE,dtype=meta['dtype'],offset=meta['offset'])
    if len(raw)!=meta['count']:raise RuntimeError('Truncated crop')
    xyz=world_xyz(raw,T)
    if not inside(p,xyz).all():raise RuntimeError('Crop contains points outside user polygon')
    lo=xyz.min(axis=0);q=np.floor((xyz-lo)/voxel).astype(np.int64)
    dims=q.max(axis=0)+1
    keys=(q[:,0]*dims[1]+q[:,1])*dims[2]+q[:,2];del q
    _,indices=np.unique(keys,return_index=True);indices.sort();del keys
    xyz=xyz[indices]
    rgb=np.column_stack([raw[n][indices] for n in ['red','green','blue']])
    normals=np.column_stack([raw[n][indices] for n in ['nx','ny','nz']]).astype(np.float64)
    R=T[:3,:3]/np.cbrt(np.linalg.det(T[:3,:3]));normals=normals@R.T
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-20)
    guard(len(xyz)*70+100*1024**2)
    def dest(name):return OUT/('.'+name+'.new' if replace else name)
    with dest('common.npz').open('xb') as f:
        np.savez(f,xyz=xyz.astype('f4'),rgb=rgb,normals=normals.astype('f4'))
    indices.astype('<u4').tofile(dest('common_roi_indices.bin'))
    save_cloud(dest('common_world.ply'),xyz,rgb,normals)
    tree=cKDTree(xyz)
    rng=np.random.default_rng(25);sample=xyz[rng.choice(len(xyz),min(20000,len(xyz)),replace=False)]
    distance,_=tree.query(sample,k=2,workers=2)
    result={'selection_id':SELECTION,'selection_area_m2':p.area,'source':str(SOURCE),
        'full_crop_points':meta['count'],'common_points':len(xyz),'voxel_m':voxel,
        'sampling':f'first original record per occupied {voxel} m world voxel, preserving record order',
        'spacing_m_quantiles':np.quantile(distance[:,1],[.1,.5,.9]).tolist(),
        'coordinate_frame':'map_world','duration_s':time.monotonic()-started,
        'roi_indices_sha256':hashlib.sha256(dest('common_roi_indices.bin').read_bytes()).hexdigest(),
        'world_from_block':T.tolist()}
    if replace:
        atomic_json(OUT/f'prepare-{previous["voxel_m"]}-history.json',previous)
        for name in ['common.npz','common_roi_indices.bin','common_world.ply']:dest(name).replace(OUT/name)
    atomic_json(OUT/'prepare.json',result);log(result)


def filter_faces(vertices,faces,p,max_edge=.45):
    kept=[];rejected_length=rejected_roi=0
    interior=p.buffer(-max_edge)
    for start in range(0,len(faces),100000):
        f=faces[start:start+100000];tri=vertices[f]
        edge=np.maximum.reduce([np.linalg.norm(tri[:,0]-tri[:,1],axis=1),np.linalg.norm(tri[:,1]-tri[:,2],axis=1),np.linalg.norm(tri[:,2]-tri[:,0],axis=1)])
        ok=edge<=max_edge;rejected_length+=int((~ok).sum())
        cen=tri.mean(axis=1)
        safe=shapely.contains_xy(interior,cen[:,0],cen[:,1])
        for j in np.flatnonzero(ok & ~safe):
            xy=tri[j,:,:2]
            shape=Polygon(xy)
            if shape.area<1e-12:shape=LineString(xy)
            if not p.covers(shape):ok[j]=False;rejected_roi+=1
        kept.append(f[ok]);guard()
    return np.concatenate(kept),{'input_faces':len(faces),'rejected_long_edges':rejected_length,
                                'rejected_outside_roi':rejected_roi,'max_edge_m':max_edge}


def compact(vertices,faces,colors):
    ids,inverse=np.unique(faces,return_inverse=True)
    return vertices[ids],inverse.reshape(-1,3).astype('i4'),colors[ids]


def ball():
    sys.path.insert(0,str(ROOT/'runtime/meshdeps'));import pymeshlab as pm
    started=time.monotonic();guard()
    data=np.load(OUT/'common.npz');xyz=data['xyz'];rgb=data['rgb'];normals=data['normals']
    log('BPA input',len(xyz))
    mesh=pm.Mesh(vertex_matrix=xyz.astype('f8'),v_normals_matrix=normals.astype('f8'),
                 v_color_matrix=np.column_stack([rgb/255,np.ones(len(rgb))]))
    ms=pm.MeshSet();ms.add_mesh(mesh,'025 user ROI common 10cm')
    for radius in [.14]:
        guard();log('Ball radius',radius)
        ms.generate_surface_reconstruction_ball_pivoting(ballradius=pm.PureValue(radius),clustering=20.,creasethr=90.,deletefaces=False)
    m=ms.current_mesh();v=m.vertex_matrix();f=m.face_matrix();colors=np.clip(m.vertex_color_matrix()[:,:3]*255,0,255).astype('u1')
    f,checks=filter_faces(v,f,polygon(selection()['vertices']))
    v,f,colors=compact(v,f,colors)
    save_mesh(OUT/'ball_pivoting_world.ply',v,f,colors)
    result={'method':'ball_pivoting','input_points':len(xyz),'vertices':len(v),'faces':len(f),
            'radii_m':[.14],'clustering_percent_of_radius':20,'close_holes':False,'smoothing':False,
            'duration_s':time.monotonic()-started,**checks}
    atomic_json(OUT/'ball_pivoting.json',result);log(result)


def ball_tiled():
    """Same input points, local BPA with internal halos and shared original vertex IDs."""
    sys.path.insert(0,str(ROOT/'runtime/meshdeps'));import pymeshlab as pm
    started=time.monotonic();data=np.load(OUT/'common.npz')
    xyz=data['xyz'].astype('f8');rgb=data['rgb'];normals=data['normals'].astype('f8')
    tile_size=20.;halo=.5;origin=xyz[:,:2].min(axis=0)
    cells=np.floor((xyz[:,:2]-origin)/tile_size).astype('i4');tiles=np.unique(cells,axis=0)
    allfaces=[];calls=[]
    for k,(tx,ty) in enumerate(tiles):
        guard();lo=origin+np.array([tx,ty])*tile_size;hi=lo+tile_size
        ids=np.flatnonzero((xyz[:,0]>=lo[0]-halo)&(xyz[:,0]<=hi[0]+halo)&(xyz[:,1]>=lo[1]-halo)&(xyz[:,1]<=hi[1]+halo))
        if len(ids)<3:continue
        start=time.monotonic();ms=pm.MeshSet()
        ms.add_mesh(pm.Mesh(vertex_matrix=xyz[ids],v_normals_matrix=normals[ids],v_color_matrix=np.column_stack([rgb[ids]/255,np.ones(len(ids))])))
        ms.generate_surface_reconstruction_ball_pivoting(ballradius=pm.PureValue(.14),clustering=20.,creasethr=90.,deletefaces=False)
        m=ms.current_mesh();v=m.vertex_matrix();f=m.face_matrix()
        if len(v)!=len(ids) or not np.array_equal(v,xyz[ids]):raise RuntimeError('BPA changed vertex indexing; explicit mapping required')
        f=ids[f]
        cen=xyz[f].mean(axis=1);owner=np.floor((cen[:,:2]-origin)/tile_size).astype('i4')
        f=f[(owner[:,0]==tx)&(owner[:,1]==ty)]
        allfaces.append(f.astype('i4'));calls.append({'tile':[int(tx),int(ty)],'input_points_with_halo':len(ids),'owned_faces':len(f),'seconds':time.monotonic()-start})
        del ms,m,v
        log('BPA tile',k+1,'/',len(tiles),'points',len(ids),'faces',len(f),'seconds',calls[-1]['seconds'])
    faces=np.concatenate(allfaces)
    canonical=np.sort(faces,axis=1).astype('<i4');keys=canonical.view('V12').ravel()
    _,unique=np.unique(keys,return_index=True);faces=faces[unique];del canonical,keys
    faces,checks=filter_faces(xyz,faces,polygon(selection()['vertices']))
    vertices,faces,colors=compact(xyz,faces,rgb)
    save_mesh(OUT/'ball_pivoting_tiled_world.ply',vertices,faces,colors)
    result={'method':'Ball Pivoting in spatial tiles with shared original point IDs',
        'input_points':len(xyz),'vertices':len(vertices),'faces':len(faces),'radius_m':.14,
        'clustering_percent_of_radius':20,'tile_size_m':tile_size,'internal_halo_m':halo,
        'tiles':calls,'close_holes':False,'smoothing':False,'duration_s':time.monotonic()-started,
        'note':'Bounded local BPA candidate, not claimed bit-identical to one global BPA run. Halo points are all inside the user polygon.',**checks}
    atomic_json(OUT/'ball_pivoting_tiled.json',result);log({k:v for k,v in result.items() if k!='tiles'})


def ball_3d():
    sys.path.insert(0,str(ROOT/'runtime/meshdeps'));import pymeshlab as pm
    started=time.monotonic();data=np.load(OUT/'common.npz')
    xyz=data['xyz'].astype('f8');rgb=data['rgb'];normals=data['normals'].astype('f8')
    size=5.;halo=.5;origin=xyz.min(axis=0)
    cell=np.floor((xyz-origin)/size).astype('i4');dims=cell.max(axis=0)+1
    keys=(cell[:,0].astype('i8')*dims[1]+cell[:,1])*dims[2]+cell[:,2]
    codes=np.unique(keys);del keys,cell
    queue=[]
    for key in codes:
        tz=key%dims[2];rest=key//dims[2];ty=rest%dims[1];tx=rest//dims[1]
        queue.append((origin+np.array([tx,ty,tz])*size,size))
    tree=cKDTree(xyz);allfaces=[];calls=[];cursor=0
    while cursor<len(queue):
        lo,side=queue[cursor];cursor+=1;guard();hi=lo+side
        ids=np.asarray(tree.query_ball_point(lo+side/2,r=side/2+halo,p=np.inf),dtype='i4')
        if len(ids)<3:continue
        if len(ids)>20000 and side>1.25:
            for x in [0,1]:
                for y in [0,1]:
                    for z in [0,1]:queue.append((lo+np.array([x,y,z])*side/2,side/2))
            continue
        ids.sort();start=time.monotonic();ms=pm.MeshSet()
        ms.add_mesh(pm.Mesh(vertex_matrix=xyz[ids],v_normals_matrix=normals[ids],v_color_matrix=np.column_stack([rgb[ids]/255,np.ones(len(ids))])))
        ms.generate_surface_reconstruction_ball_pivoting(ballradius=pm.PureValue(.14),clustering=20.,creasethr=90.,deletefaces=False)
        m=ms.current_mesh();v=m.vertex_matrix();f=m.face_matrix()
        if len(v)!=len(ids) or not np.array_equal(v,xyz[ids]):raise RuntimeError('BPA vertex correspondence changed')
        f=ids[f];cen=xyz[f].mean(axis=1)
        owned=np.all((cen>=lo)&(cen<hi),axis=1);f=f[owned]
        allfaces.append(f.astype('i4'));calls.append({'origin':lo.tolist(),'core_size_m':side,'input_points':len(ids),'faces':len(f),'seconds':time.monotonic()-start})
        del ms,m,v
        if len(calls)%50==0:log('BPA 3D completed tiles',len(calls),'queue',cursor,'/',len(queue),'faces',sum(c['faces'] for c in calls))
    faces=np.concatenate(allfaces);canonical=np.sort(faces,axis=1).astype('<i4')
    _,unique=np.unique(canonical.view('V12').ravel(),return_index=True);faces=faces[unique];del canonical
    faces,checks=filter_faces(xyz,faces,polygon(selection()['vertices']))
    vertices,faces,colors=compact(xyz,faces,rgb)
    save_mesh(OUT/'ball_pivoting_world.ply',vertices,faces,colors)
    result={'method':'Ball Pivoting on bounded 3D tiles, common point IDs merged',
        'input_points':len(xyz),'vertices':len(vertices),'faces':len(faces),'radius_m':.14,
        'clustering_percent_of_radius':20,'initial_tile_size_m':size,'minimum_tile_size_m':1.25,'internal_halo_m':halo,
        'local_point_cap':20000,'tiles':calls,'close_holes':False,'smoothing':False,'duration_s':time.monotonic()-started,
        'note':'Local bounded BPA variant; not a completed single global BPA run. No points outside user polygon used. Seams may remain open.',**checks}
    atomic_json(OUT/'ball_pivoting.json',result);log({k:v for k,v in result.items() if k!='tiles'})


def planes():
    started=time.monotonic();guard();data=np.load(OUT/'common.npz')
    xyz=data['xyz'].astype('f8');rgb=data['rgb'];normals=data['normals'].astype('f8')
    rng=np.random.default_rng(25);labels=np.full(len(xyz),-1,np.int32);models=[]
    pool=rng.choice(len(xyz),min(70000,len(xyz)),replace=False)
    for iteration in range(80):
        eligible=pool[labels[pool]<0]
        if len(eligible)<180:break
        sub=xyz[eligible];sn=normals[eligible]
        candidates=rng.choice(eligible,min(40,len(eligible)),replace=False)
        best=None;best_count=0
        for index in candidates:
            n=normals[index];d=-xyz[index]@n
            good=(np.abs(sub@n+d)<=.08)&(np.abs(sn@n)>=np.cos(np.deg2rad(20)))
            count=int(good.sum())
            if count>best_count:best_count=count;best=(n,d,eligible[good])
        if best_count<120:break
        n,d,inliers=best;fit=xyz[inliers];center=fit.mean(axis=0)
        _,vectors=np.linalg.eigh((fit-center).T@(fit-center));n=vectors[:,0];d=-center@n
        mask=(labels<0)&(np.abs(xyz@n+d)<=.08)&(np.abs(normals@n)>=np.cos(np.deg2rad(20)))
        ids=np.flatnonzero(mask)
        if len(ids)<500:break
        labels[ids]=len(models)
        models.append({'normal':n.tolist(),'d':float(d),'points':len(ids),
                       'median_residual_m':float(np.median(np.abs(xyz[ids]@n+d)))})
        if iteration%5==0:log('RANSAC planes',len(models),'assigned',int((labels>=0).sum()));guard()
    out_vertices=[];out_faces=[];out_colors=[];offset=0;raw_faces=0
    for i,model in enumerate(models):
        guard();ids=np.flatnonzero(labels==i);pts=xyz[ids];n=np.array(model['normal']);d=model['d']
        basis=np.eye(3)[np.argmin(np.abs(n))];u=np.cross(n,basis);u/=np.linalg.norm(u);v=np.cross(n,u)
        uv=np.column_stack([pts@u,pts@v]);_,unique=np.unique(np.round(uv,5),axis=0,return_index=True)
        uv=uv[unique];pts=pts[unique];ids=ids[unique]
        if len(pts)<3:continue
        tri=Delaunay(uv).simplices
        # Support checks at centroids and edge midpoints prevent long bridges.
        edge=np.maximum.reduce([np.linalg.norm(uv[tri[:,0]]-uv[tri[:,1]],axis=1),np.linalg.norm(uv[tri[:,1]]-uv[tri[:,2]],axis=1),np.linalg.norm(uv[tri[:,2]]-uv[tri[:,0]],axis=1)])
        tri=tri[edge<=.35]
        tree=cKDTree(uv);support=np.ones(len(tri),bool)
        for a,b,c in [(1/3,1/3,1/3),(.5,.5,0),(.5,0,.5),(0,.5,.5)]:
            q=a*uv[tri[:,0]]+b*uv[tri[:,1]]+c*uv[tri[:,2]]
            distances,_=tree.query(q,k=1,workers=2);support&=distances<=.10
        tri=tri[support];raw_faces+=len(tri)
        projected=pts-(pts@n+d)[:,None]*n
        tri,_=filter_faces(projected,tri,polygon(selection()['vertices']),max_edge=.35)
        if not len(tri):continue
        pv,pf,pc=compact(projected,tri,rgb[ids]);out_vertices.append(pv);out_faces.append(pf+offset);out_colors.append(pc);offset+=len(pv)
    if not out_faces:raise RuntimeError('No supported planar faces')
    vertices=np.concatenate(out_vertices);faces=np.concatenate(out_faces);colors=np.concatenate(out_colors)
    save_mesh(OUT/'ransac_planar_world.ply',vertices,faces,colors)
    np.save(OUT/'plane_labels.npy',labels)
    result={'method':'RANSAC planes + local 2D Delaunay + support rejection','input_points':len(xyz),
        'planes':models,'assigned_points':int((labels>=0).sum()),'unassigned_points':int((labels<0).sum()),
        'vertices':len(vertices),'faces':len(faces),'distance_threshold_m':.08,'normal_threshold_degrees':20,
        'max_edge_m':.35,'support_distance_m':.10,'close_holes':False,
        'note':'Plane-only candidate: nonplanar vegetation/residual points are not reconstructed; no watertight completion.',
        'duration_s':time.monotonic()-started}
    atomic_json(OUT/'ransac_planar.json',result);log({k:v for k,v in result.items() if k!='planes'})


def delaunay():
    started=time.monotonic();guard()
    runtime=ROOT/'runtime/openmvs';work=ROOT/'runtime/native-025'/SELECTION/'mesh-work'
    work.mkdir(exist_ok=True)
    source=Path('/data/barranco/results/barranco-full-v1/025/barranco_4k_2fps_combined_v1')
    scene=work/'scene_dense.mvs'
    if not scene.exists():shutil.copy2(source/'mvs/scene_dense.mvs',scene)
    images=work/'images'
    if not images.exists():images.symlink_to(source/'colmap/undistorted/images',target_is_directory=True)
    native=work.parent/'native_common.ply'
    env=dict(os.environ,LD_LIBRARY_PATH=str(runtime/'lib'))
    cmd=[str(runtime/'bin/ReconstructMesh'),'-w',str(work),'-i',str(scene),'-p',str(native),
         '-o',str(work/'mesh_local.ply'),'--cuda-device','-2','--max-threads','2',
         '--min-point-distance','0','--constant-weight','0','--decimate','1',
         '--remove-spurious','0','--remove-spikes','0','--close-holes','0','--smooth','0',
         '--crop-to-roi','0','--archive-type','1']
    atomic_json(OUT/'delaunay-command.json',{'argv':cmd,'pointcloud':'native lists preserved, matched common 10cm sample'})
    with (OUT/'delaunay-native.log').open('x') as log_file:
        process=subprocess.Popen(cmd,cwd=work,env=env,stdout=log_file,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                time.sleep(3);guard()
                if shutil.disk_usage(work).free<4*1024**3:raise RuntimeError('Native scratch reached 4 GiB reserve on root')
                if time.monotonic()-started>3600:raise RuntimeError('Delaunay one-hour pilot budget exceeded')
            if process.returncode:raise RuntimeError('ReconstructMesh failed; inspect delaunay-native.log')
        except BaseException:
            if process.poll() is None:process.terminate();process.wait(timeout=20)
            raise
    sys.path.insert(0,str(ROOT/'runtime/meshdeps'));import pymeshlab as pm
    ms=pm.MeshSet();ms.load_new_mesh(str(work/'mesh_local.ply'))
    m=ms.current_mesh();local=m.vertex_matrix();faces=m.face_matrix()
    T=np.array(selection()['source']['world_from_block']);vertices=local@T[:3,:3].T+T[:3,3]
    common=np.load(OUT/'common.npz');tree=cKDTree(common['xyz'])
    distance,index=tree.query(vertices,k=1,workers=2);colors=common['rgb'][index]
    faces,checks=filter_faces(vertices,faces,polygon(selection()['vertices']))
    vertices,faces,colors=compact(vertices,faces,colors)
    save_mesh(OUT/'delaunay_world.ply',vertices,faces,colors)
    result={'method':'OpenMVS 2.3 Delaunay + visibility graph-cut','input_points':len(common['xyz']),
        'vertices':len(vertices),'faces':len(faces),'min_point_distance_pixels':0,'constant_weight':False,
        'close_holes':False,'smoothing':False,'decimation':1,'vertex_support_distance_p95_m':float(np.quantile(distance,.95)),
        'duration_s':time.monotonic()-started,**checks}
    atomic_json(OUT/'delaunay.json',result);log(result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','ball','ball-tiled','ball-3d','planes','delaunay']);p.add_argument('--voxel',type=float,default=VOXEL);p.add_argument('--replace-common',action='store_true');a=p.parse_args()
    if a.stage=='prepare':prepare(a.voxel,a.replace_common)
    else:{'ball':ball,'ball-tiled':ball_tiled,'ball-3d':ball_3d,'planes':planes,'delaunay':delaunay}[a.stage]()
