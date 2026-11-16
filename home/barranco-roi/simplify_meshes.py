"""Measured, reversible per-block simplification with a real surface-distance pilot."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '4')
os.environ.setdefault('OMP_NUM_THREADS', '4')
import argparse
from contextlib import contextmanager
import gc
import json
from pathlib import Path
import shutil
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np
import scipy.sparse as sparse
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'runtime/meshdeps'))
import pymeshlab as pm
from combine_meshes import BASE, VERTEX, FACE, header
from roi.core import atomic_json, sha_file


def load_mesh(path):
    meta = header(path)
    with path.open('rb') as f:
        f.seek(meta['offset'])
        v = np.fromfile(f, VERTEX, meta['vertices'])
        faces = np.fromfile(f, FACE, meta['faces'])
    assert (faces['n'] == 3).all() and (faces['indices'] < len(v)).all()
    xyz = np.column_stack([v[n] for n in ['x','y','z']]).astype('f8')
    rgb = np.column_stack([v[n] for n in ['red','green','blue']])
    assert np.isfinite(xyz).all()
    return xyz, faces['indices'].astype('i4'), rgb


def compact(xyz, faces, rgb):
    used, inverse = np.unique(faces, return_inverse=True)
    return xyz[used], inverse.reshape(-1,3).astype('i4'), rgb[used]


def save_mesh(path, xyz, faces, rgb):
    if path.exists() or path.with_suffix('.ply.part').exists():
        raise RuntimeError('Destination exists: '+str(path))
    assert np.isfinite(xyz).all() and (faces >= 0).all() and (faces < len(xyz)).all()
    text = ('ply\nformat binary_little_endian 1.0\ncomment map_world metric; simplified derivative; no hole filling\n'
            f'element vertex {len(xyz)}\nproperty float x\nproperty float y\nproperty float z\n'
            'property uchar red\nproperty uchar green\nproperty uchar blue\n'
            f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
    temporary = path.with_suffix('.ply.part')
    with temporary.open('xb') as out:
        out.write(text.encode())
        for start in range(0,len(xyz),250000):
            stop = min(len(xyz), start+250000)
            rows = np.empty(stop-start, VERTEX)
            for i,n in enumerate(['x','y','z']): rows[n] = xyz[start:stop,i]
            for i,n in enumerate(['red','green','blue']): rows[n] = rgb[start:stop,i]
            out.write(rows.tobytes())
        for start in range(0,len(faces),250000):
            rows = np.empty(min(250000,len(faces)-start), FACE)
            rows['n'] = 3
            rows['indices'] = faces[start:start+250000]
            out.write(rows.tobytes())
        out.flush()
        os.fsync(out.fileno())
    temporary.rename(path)
    return dict(vertices=len(xyz),faces=len(faces),bytes=path.stat().st_size,sha256=sha_file(path))


def face_geometry(xyz, faces):
    normals = np.cross(xyz[faces[:,1]]-xyz[faces[:,0]], xyz[faces[:,2]]-xyz[faces[:,0]])
    length = np.linalg.norm(normals,axis=1)
    normals /= np.maximum(length[:,None],1e-30)
    return normals, length*.5


def edge_table(faces):
    edges = np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]).astype('u8')
    edges.sort(axis=1)
    codes = (edges[:,0] << np.uint64(32)) | edges[:,1]
    del edges
    order = np.argsort(codes, kind='stable')
    sorted_codes = codes[order]
    starts = np.r_[0,np.flatnonzero(sorted_codes[1:] != sorted_codes[:-1])+1]
    counts = np.diff(np.r_[starts,len(order)])
    unique = sorted_codes[starts]
    return unique, starts, counts, order


def clean_components(xyz, faces, rgb, diameter=.20, area_limit=.02):
    codes, _, _, _ = edge_table(faces)
    a, b = (codes >> np.uint64(32)).astype('i4'), (codes & np.uint64(0xffffffff)).astype('i4')
    graph = sparse.csr_matrix((np.ones(len(a),dtype='u1'),(a,b)),shape=(len(xyz),len(xyz)))
    count, labels = connected_components(graph,directed=False)
    _, areas = face_geometry(xyz,faces)
    face_labels = labels[faces[:,0]]
    component_area = np.bincount(face_labels,weights=areas,minlength=count)
    lo = np.full((count,3),np.inf)
    hi = np.full((count,3),-np.inf)
    for k in range(3):
        np.minimum.at(lo[:,k],labels,xyz[:,k])
        np.maximum.at(hi[:,k],labels,xyz[:,k])
    diag = np.linalg.norm(hi-lo,axis=1)
    remove = (diag < diameter) & (component_area < area_limit)
    keep = ~remove[face_labels]
    report = dict(total_components=int(count),removed_components=int(remove.sum()),removed_faces=int((~keep).sum()),
                  removed_area_m2=float(component_area[remove].sum()),diameter_limit_m=diameter,area_limit_m2=area_limit)
    if not keep.all():
        xyz, faces, rgb = compact(xyz,faces[keep],rgb)
    return xyz,faces,rgb,report


def local_surface_normals(xyz, neighbors=24):
    """PCA over local neighborhoods, avoiding noisy individual triangle normals."""
    tree=cKDTree(xyz)
    normals=np.empty_like(xyz)
    for start in range(0,len(xyz),50000):
        stop=min(start+50000,len(xyz))
        _,ids=tree.query(xyz[start:stop],k=min(neighbors,len(xyz)),workers=4)
        points=xyz[ids]
        points-=points.mean(axis=1,keepdims=True)
        covariance=np.einsum('nki,nkj->nij',points,points)
        _,vectors=np.linalg.eigh(covariance)
        normals[start:stop]=vectors[:,:,0]
    return normals


def topology(xyz, faces, sharp_degrees=30):
    _, areas = face_geometry(xyz,faces)
    vertex_normals=local_surface_normals(xyz)
    normals=np.empty((len(faces),3),'f8')
    for start in range(0,len(faces),200000):
        stop=min(start+200000,len(faces))
        n=vertex_normals[faces[start:stop]]
        # PCA signs are arbitrary; align within each triangle before averaging.
        signs=np.where(np.einsum('nki,ni->nk',n,n[:,0])>=0,1.,-1.)
        mean=(n*signs[:,:,None]).sum(axis=1)
        normals[start:stop]=mean/np.maximum(np.linalg.norm(mean,axis=1,keepdims=True),1e-30)
    codes, starts, counts, order = edge_table(faces)
    pairs = counts==2
    left = (order[starts[pairs]] % len(faces)).astype('i4')
    right = (order[starts[pairs]+1] % len(faces)).astype('i4')
    sharp = np.abs(np.einsum('ij,ij->i',normals[left],normals[right])) < np.cos(np.deg2rad(sharp_degrees))
    protected_codes = np.r_[codes[~pairs],codes[pairs][sharp]]
    protected = np.zeros(len(xyz),bool)
    protected[(protected_codes >> np.uint64(32)).astype('i4')] = True
    protected[(protected_codes & np.uint64(0xffffffff)).astype('i4')] = True
    # Preserve an extra face ring around open/nonmanifold boundaries and creases.
    ring = protected[faces].any(axis=1)
    protected[faces[ring].ravel()] = True
    return normals,areas,left,right,protected


def detect_planes(xyz, faces, normals, areas, tolerance=.05, max_planes=32, seed=25):
    rng = np.random.default_rng(seed)
    ids = rng.choice(len(faces),min(80000,len(faces)),replace=False)
    centers = xyz[faces[ids]].mean(axis=1)
    ns = normals[ids]
    remaining = np.ones(len(ids),bool)
    models = []
    cosine = np.cos(np.deg2rad(12))
    min_count = max(60,int(len(ids)*.001))
    for _ in range(max_planes):
        eligible = np.flatnonzero(remaining)
        if len(eligible) < min_count:
            break
        best = None
        for index in rng.choice(eligible,min(64,len(eligible)),replace=False):
            n = ns[index]
            if np.linalg.norm(n)<.9:
                continue
            d = -float(centers[index]@n)
            good = remaining & (np.abs(centers@n+d)<=tolerance) & (np.abs(ns@n)>=cosine)
            support = int(good.sum())
            if best is None or support>best[0]:
                best = support,n,d,good
        if best is None or best[0]<min_count:
            break
        _,n,d,good = best
        pts = centers[good]
        center = pts.mean(axis=0)
        _,vectors = np.linalg.eigh((pts-center).T@(pts-center))
        fit = vectors[:,0]
        if abs(fit@n)>=cosine:
            n,d = fit,-float(center@fit)
        good = remaining & (np.abs(centers@n+d)<=tolerance) & (np.abs(ns@n)>=cosine)
        if good.sum()<min_count:
            remaining[best[3]] = False
            continue
        models.append(dict(normal=n.tolist(),d=d,sampled_faces=int(good.sum())))
        remaining[good] = False
    labels = np.full(len(faces),-1,'i4')
    best = np.full(len(faces),np.inf)
    for k,model in enumerate(models):
        n,d = np.array(model['normal']),model['d']
        for start in range(0,len(faces),200000):
            stop = min(start+200000,len(faces))
            dist = np.abs(xyz[faces[start:stop]]@n+d).max(axis=1)
            ok = (dist<=tolerance) & (np.abs(normals[start:stop]@n)>=cosine) & (dist<best[start:stop])
            labels[start:stop][ok] = k
            best[start:stop][ok] = dist[ok]
    return models,labels


def regularize_planes(xyz, faces, normals, areas, left, right, protected, tolerance=.05):
    models, labels = detect_planes(xyz,faces,normals,areas,tolerance=tolerance)
    same = (labels[left]>=0) & (labels[left]==labels[right])
    graph = sparse.csr_matrix((np.ones(int(same.sum()),'u1'),(left[same],right[same])),shape=(len(faces),len(faces)))
    count, components = connected_components(graph,directed=False)
    support = np.bincount(components,weights=areas,minlength=count)
    number = np.bincount(components,minlength=count)
    valid = (support>=2.) & (number>=100)
    accepted = (labels>=0) & valid[components]
    regions = np.where(accepted,components,-1).astype('i4')
    vmin = np.full(len(xyz),np.iinfo('i4').max,'i4')
    vmax = np.full(len(xyz),-1,'i4')
    for k in range(3):
        np.minimum.at(vmin,faces[:,k],regions)
        np.maximum.at(vmax,faces[:,k],regions)
    eligible = (vmin==vmax) & (vmin>=0) & ~protected
    region_model = np.full(count,-1,'i4')
    np.maximum.at(region_model,components[accepted],labels[accepted])
    output = xyz.copy()
    max_move = 0.
    for k,model in enumerate(models):
        ids = np.flatnonzero(eligible & (region_model[np.maximum(vmax,0)]==k))
        n = np.array(model['normal'])
        signed = xyz[ids]@n+model['d']
        move = np.clip(.65*signed,-tolerance,tolerance)
        output[ids] -= move[:,None]*n
        if len(move): max_move=max(max_move,float(np.abs(move).max()))
    assert np.array_equal(output[protected],xyz[protected])
    return output,eligible,dict(models=models,connected_regions=int(np.unique(regions[accepted]).size),
                               eligible_vertices=int(eligible.sum()),protected_vertices=int(protected.sum()),
                               planar_faces=int(accepted.sum()),max_displacement_m=max_move,
                               detection_tolerance_m=tolerance,normal_angle_deg=12,min_region_area_m2=2.,blend=.65)


def clip_roi(xyz, faces, roi_vertices):
    # Allow only 50 micrometers for the float32 PLY publication roundoff.
    roi = Polygon(roi_vertices).buffer(.00005)
    shapely.prepare(roi)
    keep = np.ones(len(faces),bool)
    for start in range(0,len(faces),50000):
        xy = xyz[faces[start:start+50000],:2]
        shapes = shapely.polygons(xy)
        valid = shapely.covers(roi,shapes)
        a,b=xy[:,1]-xy[:,0],xy[:,2]-xy[:,0]
        degenerate = np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])<1e-12
        if degenerate.any():
            valid[degenerate] = shapely.covers(roi,shapely.linestrings(xy[degenerate]))
        keep[start:start+len(xy)] = valid
    return faces[keep],int((~keep).sum())


def surface_distances(reference_xyz, reference_faces, candidate_xyz, candidate_faces, samples=100000, all_vertices=False):
    ms = pm.MeshSet()
    ms.add_mesh(pm.Mesh(vertex_matrix=reference_xyz,face_matrix=reference_faces),'retained reference')
    ms.add_mesh(pm.Mesh(vertex_matrix=candidate_xyz,face_matrix=candidate_faces),'candidate')
    report = {}
    for name,source,target in [('reference_to_candidate',0,1),('candidate_to_reference',1,0)]:
        passes=[('surface',False,True,samples)]
        if all_vertices:
            passes.insert(0,('vertices',True,False,ms.mesh(source).vertex_number()))
        chunks=[]
        summaries={}
        vertex_count=0
        outliers=[]
        for pass_name,vertices,on_surface,number in passes:
            before = ms.mesh_number()
            result = ms.get_hausdorff_distance(sampledmesh=source,targetmesh=target,savesample=True,
                         samplevert=vertices,sampleedge=on_surface,sampleface=on_surface,samplenum=number,maxdist=pm.PureValue(10.))
            ids=[]
            index=0
            while len(ids)<ms.mesh_number():
                if ms.mesh_id_exists(index): ids.append(index)
                index+=1
            generated = [i for i in ids if i not in [0,1]]
            if not generated or ms.mesh_number()<=before:
                raise RuntimeError('Surface filter did not return its distance samples')
            # The saved closest target points duplicate each distance. Use only
            # the source sample points, and explicitly request N vertices in a
            # separate pass: samplevert=True alone does NOT mean all vertices.
            sample_ids=[i for i in generated if 'sample point' in ms.mesh(i).label().lower()]
            if len(sample_ids)!=1:
                raise RuntimeError('Cannot identify the independent surface samples')
            sample_mesh=ms.mesh(sample_ids[0])
            values=np.asarray(sample_mesh.vertex_scalar_array()).copy()
            assert len(values)==int(result['n_samples'])
            if vertices:
                assert len(values)==ms.mesh(source).vertex_number(), 'Not all vertices were sampled'
                vertex_count=len(values)
            bad=np.flatnonzero(values>.07)
            if len(bad):outliers.extend(sample_mesh.vertex_matrix()[bad[:100]].tolist())
            chunks.append(values)
            summaries[pass_name]={k:float(v) for k,v in result.items() if isinstance(v,(int,float))}
            del sample_mesh
            for index in generated:
                ms.set_current_mesh(index)
                ms.delete_current_mesh()
        distances=np.concatenate(chunks)
        assert len(distances)>0 and np.isfinite(distances).all() and (distances>=0).all()
        report[name] = dict(samples=len(distances),all_vertex_samples=vertex_count,mean_m=float(distances.mean()),rms_m=float(np.sqrt(np.mean(distances**2))),
                            p95_m=float(np.quantile(distances,.95)),p99_m=float(np.quantile(distances,.99)),
                            sampled_max_m=float(distances.max()),above_5cm=int((distances>.05).sum()),above_7cm=int((distances>.07).sum()),
                            filter_summary=summaries,outlier_points_above_7cm=outliers)
    del ms
    gc.collect()
    report['method'] = 'Bidirectional point-to-triangle surface distances; '+('all vertices plus sampled faces and edges' if all_vertices else 'sampled faces and edges')+'; not vertex-to-vertex and not an exhaustive Hausdorff bound.'
    return report


class Pilot:
    def __init__(self,args):
        self.args = args
        self.output = BASE/'simplified'/args.run_id
        if self.output.exists():
            raise RuntimeError('Run already exists; choose a new --run-id')
        self.output.mkdir(parents=True)
        self.started = time.monotonic()
        self.state = dict(block=args.block,pid=os.getpid(),started_at=time.time(),timings_s={},stage='created')

    @contextmanager
    def timed(self,name):
        self.state.update(stage=name,updated_at=time.time())
        atomic_json(self.output/'status.json',self.state)
        print(time.strftime('%H:%M:%S'),name,'START',flush=True)
        start=time.monotonic()
        try:
            yield
        finally:
            elapsed=time.monotonic()-start
            self.state['timings_s'][name]=elapsed
            self.state['updated_at']=time.time()
            atomic_json(self.output/'status.json',self.state)
            print(time.strftime('%H:%M:%S'),name,f'{elapsed:.2f}s',flush=True)

    def run(self):
        args=self.args
        source=BASE/args.block/('manzana_'+args.block+'_world.ply')
        manifest=json.loads((BASE/'manifest.json').read_text())['blocks'][args.block]
        roi=json.loads((BASE/args.block/('roi_'+args.block+'.json')).read_text())
        if shutil.disk_usage(self.output).free<12*1024**3:
            raise RuntimeError('Need at least 12 GiB free on home for this pilot')
        with self.timed('load_and_verify'):
            assert sha_file(source)==manifest['sha256']
            xyz,faces,rgb=load_mesh(source)
        original=dict(vertices=len(xyz),faces=len(faces),bytes=source.stat().st_size,sha256=manifest['sha256'])
        with self.timed('tiny_component_cleanup'):
            xyz,faces,rgb,cleanup=clean_components(xyz,faces,rgb)
            save_mesh(self.output/'reference_retained.ply',xyz,faces,rgb)
        with self.timed('boundaries_and_creases'):
            normals,areas,left,right,protected=topology(xyz,faces)
        with self.timed('ransac_and_connected_planar_regularization'):
            planar,interior,planes=regularize_planes(xyz,faces,normals,areas,left,right,protected,tolerance=args.tolerance)
            atomic_json(self.output/'planes.json',planes)
        del normals,areas,left,right
        with self.timed('color_reference_index'):
            tree=cKDTree(xyz)
        variants={}
        for name,positions in [('qem',xyz),('planar_qem',planar)]:
            attempts=[]
            for ratio in [.5,.75,.9]:
                label=name+'_'+str(int(ratio*100))
                with self.timed(label+'_decimation'):
                    weights=np.ones(len(xyz))
                    weights[protected]=1000.
                    if name=='planar_qem': weights[interior]=.25
                    ms=pm.MeshSet()
                    ms.add_mesh(pm.Mesh(vertex_matrix=positions,face_matrix=faces,v_scalar_array=weights),name)
                    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=int(len(faces)*ratio),qualitythr=.3,
                         preserveboundary=True,boundaryweight=10.,preservenormal=True,preservetopology=True,
                         optimalplacement=True,planarquadric=True,planarweight=.1,qualityweight=True,autoclean=True,selected=False)
                    mesh=ms.current_mesh()
                    vx=mesh.vertex_matrix()
                    fc=mesh.face_matrix()
                    del mesh,ms,weights
                    gc.collect()
                with self.timed(label+'_roi_and_color'):
                    fc,rejected=clip_roi(vx,fc,roi['vertices'])
                    _,index=tree.query(vx,k=1,workers=4)
                    colors=rgb[index]
                    vx,fc,colors=compact(vx,fc,colors)
                    # Validate exactly the float32 coordinates that will be saved.
                    vx=vx.astype('f4').astype('f8')
                with self.timed(label+'_surface_validation'):
                    distances=surface_distances(xyz,faces,vx,fc,samples=args.samples)
                passed=all(distances[d]['p99_m']<=args.tolerance and distances[d]['sampled_max_m']<=args.outer_tolerance
                           for d in ['reference_to_candidate','candidate_to_reference'])
                with self.timed(label+'_save'):
                    path=self.output/('manzana_'+args.block+'_'+label+'.ply')
                    stats=save_mesh(path,vx,fc,colors)
                result=dict(path=str(path),target_face_ratio=ratio,actual_face_ratio=len(fc)/len(faces),
                            roi_rejected_faces=rejected,distances=distances,accepted=passed,**stats)
                attempts.append(result)
                atomic_json(self.output/(label+'.json'),result)
                print('RESULT',label,'accepted',passed,'faces',len(fc),'max_m',
                      max(distances[d]['sampled_max_m'] for d in ['reference_to_candidate','candidate_to_reference']),flush=True)
                del vx,fc,colors,index
                gc.collect()
                if passed:
                    canonical=self.output/('manzana_'+args.block+'_'+name+'.ply')
                    os.link(path,canonical)
                    result['canonical_path']=str(canonical)
                    break
            variants[name]=dict(attempts=attempts,selected=next((a for a in attempts if a['accepted']),None))
            atomic_json(self.output/'variants.json',variants)
        report=dict(block=args.block,source=str(source),original=original,cleanup=cleanup,planes=planes,variants=variants,
                    tolerance_p99_m=args.tolerance,tolerance_sampled_max_m=args.outer_tolerance,close_holes=False,
                    gpu_used=False,threads=4,roi_selection_id=roi['selection_id'],coordinate_frame='map_world',
                    timings_s=self.state['timings_s'],total_seconds=time.monotonic()-self.started,
                    validation_reference='Original mesh after explicitly reported tiny-component removal.',
                    color_transfer='Nearest original retained vertex RGB; geometry error measured independently against triangle surfaces.')
        atomic_json(self.output/'comparison.json',report)
        write_report(self.output,report)
        self.state.update(stage='completed',total_seconds=report['total_seconds'])
        atomic_json(self.output/'status.json',self.state)
        print('COMPLETED',self.output,'seconds',report['total_seconds'],flush=True)


def write_report(directory,r):
    lines=['# Piloto de simplificación — manzana '+r['block'],'',
           f"Original: {r['original']['vertices']:,} vértices; {r['original']['faces']:,} caras.",
           f"Tiempo total: {r['total_seconds']:.2f} s.",
           f"Componentes diminutos retirados: {r['cleanup']['removed_components']}; caras: {r['cleanup']['removed_faces']}.",
           f"Planos detectados: {len(r['planes']['models'])}; regiones conectadas: {r['planes']['connected_regions']}.",'',
           '| Variante | Caras | Tamaño MiB | P99 máximo entre sentidos (cm) | Máximo muestreado (cm) | Aceptada |',
           '|---|---:|---:|---:|---:|---|']
    for name,variant in r['variants'].items():
        for a in variant['attempts']:
            ds=[a['distances'][d] for d in ['reference_to_candidate','candidate_to_reference']]
            lines.append(f"| {name} {a['target_face_ratio']:.0%} | {a['faces']:,} | {a['bytes']/1024**2:.2f} | {max(d['p99_m'] for d in ds)*100:.3f} | {max(d['sampled_max_m'] for d in ds)*100:.3f} | {a['accepted']} |")
    sampling='Se evaluaron todos los vértices y muestras de caras/aristas contra las superficies triangulares, en ambos sentidos.' if r.get('full_vertex_validation') else 'Las distancias son de muestras de caras/aristas a superficies triangulares, en ambos sentidos.'
    lines+=['',sampling,
            'El máximo muestreado no garantiza el máximo sobre toda la superficie.',
            'Las caras fuera del ROI se filtran; no se rellenan huecos. RGB transferido de la referencia.',
            'Procesamiento CPU mediante NumPy/SciPy/PyMeshLab; no se presenta como aceleración GPU.','',
            '## Tiempos por etapa','']
    lines += [f'- {k}: {v:.2f} s' for k,v in r['timings_s'].items()]
    (directory/'REPORTE.md').write_text('\n'.join(lines)+'\n')


def verify_existing(args):
    directory=BASE/'simplified'/args.run_id
    report=json.loads((directory/'comparison.json').read_text())
    start=time.monotonic()
    xyz,faces,_=load_mesh(directory/'reference_retained.ply')
    verification=dict(all_vertices=True,independent_sample_points=True,variants={})
    for name,variant in report['variants'].items():
        selected=variant['selected']
        if not selected:
            continue
        path=Path(selected['canonical_path'])
        assert sha_file(path)==selected['sha256']
        print('VERIFY',name,'all vertices and surface samples',flush=True)
        began=time.monotonic()
        vx,fc,_=load_mesh(path)
        distances=surface_distances(xyz,faces,vx,fc,samples=args.samples,all_vertices=True)
        passed=all(distances[d]['p99_m']<=args.tolerance and distances[d]['sampled_max_m']<=args.outer_tolerance
                   for d in ['reference_to_candidate','candidate_to_reference'])
        verification['variants'][name]=dict(path=str(path),accepted=passed,distances=distances,seconds=time.monotonic()-began)
        atomic_json(directory/'verification.json',verification)
        print('VERIFIED',name,'accepted',passed,'seconds',verification['variants'][name]['seconds'],
              'max',max(distances[d]['sampled_max_m'] for d in ['reference_to_candidate','candidate_to_reference']),flush=True)
        del vx,fc
        gc.collect()
    verification['total_seconds']=time.monotonic()-start
    atomic_json(directory/'verification.json',verification)
    text=['','## Verificación reforzada posterior','',
          'Incluye todos los vértices de ambas mallas y muestras adicionales de caras/aristas.',
          'Cada punto se cuenta una sola vez; no se duplican los puntos más cercanos guardados por MeshLab.',
          'Esta verificación posterior tiene prioridad sobre la aceptación preliminar.','']
    for name,value in verification['variants'].items():
        ds=[value['distances'][d] for d in ['reference_to_candidate','candidate_to_reference']]
        text.append(f"- {name}: aceptada={value['accepted']}; P99={max(d['p99_m'] for d in ds)*100:.3f} cm; máximo observado={max(d['sampled_max_m'] for d in ds)*100:.3f} cm; tiempo={value['seconds']:.2f} s.")
    text.append(f"- Tiempo total de verificación reforzada: {verification['total_seconds']:.2f} s.")
    with (directory/'REPORTE.md').open('a') as f:
        f.write('\n'.join(text)+'\n')


def publish_verified(args):
    directory=BASE/'simplified'/args.run_id
    report=json.loads((directory/'comparison.json').read_text())
    verification=json.loads((directory/'verification.json').read_text())
    reference=header(directory/'reference_retained.ply')
    accepted=[]
    for name,value in verification['variants'].items():
        if not value['accepted']:
            continue
        selected=report['variants'][name]['selected']
        assert value['distances']['reference_to_candidate']['all_vertex_samples']==reference['vertices']
        assert value['distances']['candidate_to_reference']['all_vertex_samples']==selected['vertices']
        accepted.append((selected['faces'],name,selected,value))
    if not accepted:
        raise RuntimeError('No candidate passed the complete-vertex validation; nothing published')
    _,name,selected,validation=min(accepted)
    source=Path(selected['canonical_path'])
    assert sha_file(source)==selected['sha256']
    target=BASE/'simplified'/report['block']
    target.mkdir(exist_ok=True)
    path=target/('manzana_'+report['block']+'_simplified.ply')
    if path.exists():
        assert sha_file(path)==selected['sha256'], 'Published result already differs'
    else:
        os.link(source,path)
    result=dict(block=report['block'],variant=name,mesh=str(path),source=report['source'],original=report['original'],
                result=selected,verification=validation,cleanup=report['cleanup'],planes=report['planes'],
                face_reduction_percent=100*(1-selected['faces']/report['original']['faces']),
                vertex_reduction_percent=100*(1-selected['vertices']/report['original']['vertices']),
                pilot_seconds=report['total_seconds'],full_validation_seconds=verification['total_seconds'],
                coordinate_frame='map_world',already_world_aligned=True,apply_additional_transform=False,
                roi_selection_id=report['roi_selection_id'],close_holes=False,gpu_used=False)
    atomic_json(target/'report.json',result)
    roi=json.loads((BASE/report['block']/('roi_'+report['block']+'.json')).read_text())
    atomic_json(target/('roi_'+report['block']+'.json'),roi)
    atomic_json(directory/'recommendation.json',dict(variant=name,path=str(path),fully_verified=True))
    ds=[validation['distances'][d] for d in ['reference_to_candidate','candidate_to_reference']]
    lines=['# Simplificación verificada — manzana '+report['block'],'',
        'Método: normales locales PCA, RANSAC conectado, regularización parcial de planos y QEM con protección por error medido.','',
        '| Métrica | Original | Simplificada |','|---|---:|---:|',
        f"| Vértices | {report['original']['vertices']:,} | {selected['vertices']:,} |",
        f"| Triángulos | {report['original']['faces']:,} | {selected['faces']:,} |",
        f"| Tamaño MB | {report['original']['bytes']/1e6:.2f} | {selected['bytes']/1e6:.2f} |",'',
        f"Reducción de caras: {result['face_reduction_percent']:.2f} %. Reducción de vértices: {result['vertex_reduction_percent']:.2f} %.",
        f"P99 máximo entre sentidos: {max(d['p99_m'] for d in ds)*100:.3f} cm. Máximo observado: {max(d['sampled_max_m'] for d in ds)*100:.3f} cm.",
        'Se comprobaron TODOS los vértices de ambas mallas y muestras adicionales de caras y aristas.',
        'El máximo observado no es una demostración del máximo continuo dentro de cada triángulo.',
        f"Planos: {len(report['planes']['models'])}; regiones conectadas: {report['planes']['connected_regions']}.",
        f"Componentes diminutos retirados: {report['cleanup']['removed_components']}; caras retiradas en esa limpieza: {report['cleanup']['removed_faces']}.",'',
        '## Tiempos de ejecución',
        f"- Piloto final/refinamiento, incluidas sus validaciones: {report['total_seconds']:.2f} s.",
        f"- Validaciones completas dentro del piloto: {verification['total_seconds']:.2f} s (incluidas en el tiempo anterior).",
        f"- Verificación completa de la versión aceptada: {validation['seconds']:.2f} s.",'',
        'La comparación diagnóstica anterior y sus tiempos están en '+str(Path(report.get('previous_run',str(directory)))/'REPORTE.md')+'.',
        'RGB conservado mediante transferencia desde los vértices originales. Sin cierre de huecos.',
        'Coordenadas ya alineadas en map_world: no aplicar otra transformación. Procesamiento CPU.','',
        'Archivo: `'+str(path)+'`','SHA256: `'+selected['sha256']+'`']
    (target/'REPORTE.md').write_text('\n'.join(lines)+'\n')
    project=ET.Element('MeshLabProject')
    group=ET.SubElement(project,'MeshGroup')
    for label,mesh_path,visible in [('Original '+report['block'],Path(report['source']),'0'),('Simplificada verificada '+report['block'],path,'1')]:
        layer=ET.SubElement(group,'MLMesh',label=label,filename=os.path.relpath(mesh_path,target),visible=visible)
        ET.SubElement(layer,'MLMatrix44').text='\n1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1\n'
    ET.SubElement(project,'RasterGroup')
    ET.ElementTree(project).write(target/('comparacion_'+report['block']+'.mlp'),encoding='utf-8',xml_declaration=True)
    index_path=BASE/'simplified/report.json'
    index=json.loads(index_path.read_text()) if index_path.exists() else dict(blocks={})
    index['blocks'][report['block']]=dict(mesh=str(path),sha256=selected['sha256'],faces=selected['faces'],
        vertices=selected['vertices'],fully_verified=True,report=str(target/'report.json'))
    index['updated_at']=time.time()
    index['pending_blocks']=sorted(set(json.loads((BASE/'manifest.json').read_text())['blocks'])-set(index['blocks']))
    atomic_json(index_path,index)
    print('PUBLISHED',path,'faces',selected['faces'],'vertices',selected['vertices'],'bytes',selected['bytes'],flush=True)


def refine_existing(args):
    previous=BASE/'simplified'/args.run_id
    original_report=json.loads((previous/'comparison.json').read_text())
    previous_verification=json.loads((previous/'verification.json').read_text())
    points=[]
    for direction in ['reference_to_candidate','candidate_to_reference']:
        points.extend(previous_verification['variants']['planar_qem']['distances'][direction]['outlier_points_above_7cm'])
    if not points:
        raise RuntimeError('No measured planar outliers require feedback protection')
    args.run_id += '_guarded'
    pilot=Pilot(args)
    try:
        with pilot.timed('load_reference'):
            xyz,faces,rgb=load_mesh(previous/'reference_retained.ply')
            os.link(previous/'reference_retained.ply',pilot.output/'reference_retained.ply')
            roi=json.loads((BASE/args.block/('roi_'+args.block+'.json')).read_text())
        with pilot.timed('local_normals_and_topology'):
            normals,areas,left,right,protected=topology(xyz,faces)
        with pilot.timed('connected_planar_regularization'):
            planar,interior,planes=regularize_planes(xyz,faces,normals,areas,left,right,protected,tolerance=args.tolerance)
            atomic_json(pilot.output/'planes.json',planes)
        del normals,areas,left,right
        tree=cKDTree(xyz)
        frozen=np.zeros(len(xyz),bool)
        attempts=[]
        final_verification=None
        selected=None
        for iteration in range(1,5):
            label='planar_guarded_'+str(iteration)
            with pilot.timed(label+'_protect_measured_outliers'):
                for ids in tree.query_ball_point(np.array(points),r=.7+.3*(iteration-1),workers=4):
                    frozen[ids]=True
                for _ in range(2):
                    frozen[faces[frozen[faces].any(axis=1)].ravel()]=True
                exclude=frozen[faces].any(axis=1)
                positions=planar.copy()
                positions[frozen]=xyz[frozen]
            with pilot.timed(label+'_decimation'):
                weights=np.ones(len(xyz))
                weights[protected]=1000.
                weights[interior]=.25
                weights[frozen]=1e8
                ms=pm.MeshSet()
                ms.add_mesh(pm.Mesh(vertex_matrix=positions,face_matrix=faces,v_scalar_array=weights,
                                    f_scalar_array=(~exclude).astype('f8')),'guarded planar QEM')
                ms.compute_selection_by_scalar_per_face(minq=.5,maxq=1.,inclusive=True)
                assert np.array_equal(ms.current_mesh().face_selection_array(),~exclude)
                ms.meshing_decimation_quadric_edge_collapse(targetfacenum=int(len(faces)*.9),qualitythr=.3,
                    preserveboundary=True,boundaryweight=10.,preservenormal=True,preservetopology=True,
                    optimalplacement=True,planarquadric=True,planarweight=.1,qualityweight=True,autoclean=True,selected=True)
                mesh=ms.current_mesh()
                vx,fc=mesh.vertex_matrix(),mesh.face_matrix()
                del mesh,ms,weights,positions
                gc.collect()
            with pilot.timed(label+'_roi_and_color'):
                frozen_distance,_=cKDTree(vx).query(xyz[frozen],k=1,workers=4)
                if len(frozen_distance) and frozen_distance.max()>.00005:
                    raise RuntimeError('Selected-only QEM changed a feedback-frozen vertex')
                fc,rejected=clip_roi(vx,fc,roi['vertices'])
                _,index=tree.query(vx,k=1,workers=4)
                colors=rgb[index]
                vx,fc,colors=compact(vx,fc,colors)
                vx=vx.astype('f4').astype('f8')
            with pilot.timed(label+'_full_surface_validation'):
                distances=surface_distances(xyz,faces,vx,fc,samples=args.samples,all_vertices=True)
            passed=all(distances[d]['p99_m']<=args.tolerance and distances[d]['sampled_max_m']<=args.outer_tolerance
                       for d in ['reference_to_candidate','candidate_to_reference'])
            with pilot.timed(label+'_save'):
                path=pilot.output/('manzana_'+args.block+'_'+label+'.ply')
                stats=save_mesh(path,vx,fc,colors)
            result=dict(path=str(path),target_face_ratio=.9,actual_face_ratio=len(fc)/len(faces),
                        roi_rejected_faces=rejected,distances=distances,accepted=passed,
                        frozen_vertices=int(frozen.sum()),frozen_faces=int(exclude.sum()),iteration=iteration,**stats)
            attempts.append(result)
            atomic_json(pilot.output/(label+'.json'),result)
            print('GUARDED RESULT',iteration,'accepted',passed,'frozen vertices',result['frozen_vertices'],
                  'max_m',max(distances[d]['sampled_max_m'] for d in ['reference_to_candidate','candidate_to_reference']),flush=True)
            if passed:
                canonical=pilot.output/('manzana_'+args.block+'_planar_qem.ply')
                os.link(path,canonical)
                result['canonical_path']=str(canonical)
                selected=result
                final_verification=dict(path=str(canonical),accepted=True,distances=distances,
                    seconds=pilot.state['timings_s'][label+'_full_surface_validation'])
                break
            points=[]
            for direction in ['reference_to_candidate','candidate_to_reference']:
                points.extend(distances[direction]['outlier_points_above_7cm'])
            del vx,fc,colors,index
            gc.collect()
        report=dict(original_report,variants={'planar_qem':dict(attempts=attempts,selected=selected)},planes=planes,
                    timings_s=pilot.state['timings_s'],total_seconds=time.monotonic()-pilot.started,
                    previous_run=str(previous),feedback='Freeze measured >7 cm outlier neighborhoods plus two face rings; decimate only the selected remainder.',
                    full_vertex_validation=True)
        atomic_json(pilot.output/'comparison.json',report)
        write_report(pilot.output,report)
        if not selected:
            raise RuntimeError('Four feedback passes could not meet the 7 cm limit; candidates remain unpublished')
        atomic_json(pilot.output/'verification.json',dict(all_vertices=True,independent_sample_points=True,
            variants={'planar_qem':final_verification},total_seconds=sum(v for k,v in pilot.state['timings_s'].items() if k.endswith('_full_surface_validation'))))
        pilot.state.update(stage='completed',total_seconds=report['total_seconds'])
        atomic_json(pilot.output/'status.json',pilot.state)
        publish_verified(args)
        print('GUARDED COMPLETED',pilot.output,'seconds',report['total_seconds'],flush=True)
    except BaseException as exc:
        pilot.state.update(stage='failed',error=str(exc),elapsed_seconds=time.monotonic()-pilot.started)
        atomic_json(pilot.output/'status.json',pilot.state)
        raise


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--block',default='025')
    p.add_argument('--tolerance',type=float,default=.05)
    p.add_argument('--outer-tolerance',type=float,default=.07)
    p.add_argument('--samples',type=int,default=100000)
    p.add_argument('--run-id',default='pilot_025_5cm_v1')
    p.add_argument('--verify-run',action='store_true')
    p.add_argument('--publish-run',action='store_true')
    p.add_argument('--refine-run',action='store_true')
    args=p.parse_args()
    if not 0<args.tolerance<=args.outer_tolerance<=.07 or args.samples<10000:
        p.error('Require 0 < tolerance <= outer tolerance <= 0.07 m and >=10000 samples')
    if args.verify_run:
        return verify_existing(args)
    if args.publish_run:
        return publish_verified(args)
    if args.refine_run:
        return refine_existing(args)
    pilot=Pilot(args)
    try:
        pilot.run()
    except BaseException as exc:
        pilot.state.update(stage='failed',error=str(exc),elapsed_seconds=time.monotonic()-pilot.started)
        atomic_json(pilot.output/'status.json',pilot.state)
        raise


if __name__=='__main__':
    main()
