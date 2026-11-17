"""Explicit, bounded derived-sparse jobs. No dense, matching or source writes."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from graph_edit import fingerprint


def atomic(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2));temp.replace(path)


def metrics(r,samples):
    import numpy as np
    errors=[];positive=0
    for image_id,observations in samples.items():
        im=r.images[image_id];camera=r.cameras[im.camera_id]
        xyz=np.array([r.points3D[pid].xyz for pid,xy in observations])
        xy=np.array([xy for pid,xy in observations])
        transformed=(im.cam_from_world.rotation.matrix()@xyz.T).T+im.cam_from_world.translation
        good=transformed[:,2]>1e-9;positive+=int(good.sum())
        projected=camera.img_from_cam(transformed[:,:2]/transformed[:,2:])
        residual=np.linalg.norm(projected-xy,axis=1)
        residual[~good]=np.inf;errors.extend(residual.tolist())
    finite=np.array([e for e in errors if np.isfinite(e)])
    return dict(observations=len(errors),positive_depth_fraction=positive/max(1,len(errors)),
                finite_projection_fraction=len(finite)/max(1,len(errors)),
                median_px=float(np.median(finite)) if len(finite) else None,
                p95_px=float(np.percentile(finite,95)) if len(finite) else None)


def compute(job):
    import numpy as np
    import pycolmap
    assert pycolmap.__version__=='3.11.1'
    spec=json.loads((job/'request.json').read_text())
    draft=spec['draft'];model=Path(draft['source_model'])
    assert fingerprint(model)==draft['source_hashes'],'Source changed'
    r=pycolmap.Reconstruction(str(model))
    baseline_counts=[len(r.reg_image_ids()),len(r.points3D)]
    total=sum(len(r.images[i].points2D) for i in r.reg_image_ids())
    step=max(1,total//50000);counter=0;samples={}
    for im in r.images.values():
        for point in im.points2D:
            if not point.has_point3D():continue
            if counter%step==0:
                samples.setdefault(im.image_id,[]).append((point.point3D_id,point.xy.copy()))
            counter+=1
    deleted=draft.get('deleted',[])
    samples={i:v for i,v in samples.items() if i not in deleted}
    # Remove only derived observations; COLMAP updates tracks/orphan points.
    for image_id in deleted:
        r.deregister_image(image_id)
    # Exclude points removed when their supporting views were deregistered.
    samples={i:[(pid,xy) for pid,xy in observations if pid in r.points3D]
             for i,observations in samples.items()}
    samples={i:v for i,v in samples.items() if v}
    baseline_counts=[len(r.reg_image_ids()),len(r.points3D)]
    before=metrics(r,samples)
    ids=spec['camera_ids'];delta=dict(zip(ids,np.array(spec['displacements'])))
    rotations=dict(zip(ids,np.array(spec.get('rotations',[np.eye(3).tolist() for _ in ids]))))
    old_centers={i:np.array(r.images[i].projection_center()) for i in r.reg_image_ids()}
    assert set(ids)-set(deleted)==set(r.reg_image_ids())
    for point in r.points3D.values():
        cameras={el.image_id for el in point.track.elements}
        if cameras:
            xyz=np.array(point.xyz)
            point.xyz=np.mean([rotations[i]@(xyz-old_centers[i])+old_centers[i]+delta[i] for i in cameras],axis=0)
    for image_id,im in r.images.items():
        if image_id in deleted:continue
        matrix=im.cam_from_world.rotation.matrix()@rotations[image_id].T
        center=old_centers[image_id]+delta[image_id]
        im.cam_from_world=pycolmap.Rigid3d(pycolmap.Rotation3d(matrix),-matrix@center)
    deformed=metrics(r,samples)
    # Use low-level triangulator: high-level triangulate_points also invokes BA.
    import sqlite3
    database=Path(spec.get('database_path',model.parents[1]/'database.db'))
    if not database.is_file():
        raise RuntimeError('Falta la BD de matches de esta revisión; no se ejecutará BA como sustituto')
    frozen={i:r.images[i].cam_from_world.matrix().copy() for i in r.reg_image_ids()}
    graph=pycolmap.CorrespondenceGraph()
    for i in r.reg_image_ids():graph.add_image(i,len(r.images[i].points2D))
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        for i in r.reg_image_ids():
            name=db.execute('SELECT name FROM images WHERE image_id=?',(i,)).fetchone()
            assert name and name[0]==r.images[i].name,'BD/model mismatch'
        for pair,rows,cols,blob in db.execute('SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0'):
            a,b=divmod(pair,2147483647)
            if a not in frozen or b not in frozen:continue
            assert cols==2 and len(blob)==rows*8
            graph.add_correspondences(a,b,np.frombuffer(blob,dtype='<u4').reshape(-1,2).copy())
    graph.finalize()
    colors={}
    for point in r.points3D.values():
        for element in point.track.elements:
            colors[(element.image_id,element.point2D_idx)]=np.array(point.color,dtype=float)
    for pid in list(r.points3D):r.delete_point3D(pid)
    tri=pycolmap.IncrementalTriangulator(graph,r)
    options=pycolmap.IncrementalTriangulatorOptions()
    # Finalize removes images without surviving correspondences. Keep their
    # edited poses registered, but there are no observations to triangulate.
    unmatched_images=[i for i in sorted(r.reg_image_ids()) if not graph.exists_image(i)]
    for i in sorted(r.reg_image_ids()):
        if graph.exists_image(i):tri.triangulate_image(options,i)
    tri.complete_all_tracks(options)
    tri.merge_all_tracks(options)
    tri.retriangulate(options)
    for point in r.points3D.values():
        rgb=[colors[(e.image_id,e.point2D_idx)] for e in point.track.elements if (e.image_id,e.point2D_idx) in colors]
        point.color=np.array(np.mean(rgb,axis=0) if rgb else [160,160,160],dtype=np.uint8)
    for i,pose in frozen.items():np.testing.assert_allclose(r.images[i].cam_from_world.matrix(),pose,atol=1e-12,rtol=0)
    # Associations were rebuilt: evaluate surviving observations, not old point IDs.
    samples={}
    for im in r.images.values():
        if im.image_id in deleted:continue
        observations=[(p.point3D_id,p.xy.copy()) for p in im.points2D if p.has_point3D()]
        if observations:samples[im.image_id]=observations[::max(1,len(observations)//30)]
    if not samples:raise RuntimeError('No points survived triangulation with edited fixed poses')
    solver_usable=True
    r.update_point_3d_errors()
    after=metrics(r,samples)
    pin_errors={str(p['id']):float(np.linalg.norm(r.images[p['id']].projection_center()-p['target']))
                for p in draft['pins']}
    quality=(after['p95_px'] is not None and before['p95_px'] is not None and
             after['p95_px']<=max(4.,before['p95_px']*1.25) and
             after['positive_depth_fraction']>=before['positive_depth_fraction']-.005 and
             after['finite_projection_fraction']>=before['finite_projection_fraction']-.005 and
             solver_usable and
              max(pin_errors.values(),default=0.)<1e-6)
    assert len(r.reg_image_ids())==baseline_counts[0]
    output=job/'candidate';output.mkdir()
    r.write(str(output))
    assert fingerprint(model)==draft['source_hashes'],'Source changed during job'
    report=dict(before=before,deformed=deformed,after=after,pin_errors=pin_errors,
                cameras=len(r.reg_image_ids()),points=len(r.points3D),quality_screen_passed=quality,
                status='candidate_review_required' if quality else 'candidate_rejected',
                geometry_approved=False,dense_authorized=False,
                source_unchanged=True,output_model=str(output),
                excluded_camera_ids=deleted,unmatched_camera_ids=unmatched_images,
                tracks_recomputed=True,matching_executed=False,ba_executed=False,
                evaluation_scope='Sample of fitting observations, NOT independent held-out validation',
                note='Low-level triangulation from existing verified matches. Every camera pose fixed; no BA. Manual poses are not scientific approval.',
                solver_report='Triangulation only; no optimization of poses or intrinsics')
    atomic(job/'report.json',report)


def supervise(job):
    state=dict(state='running',started_at=time.time(),geometry_approved=False,dense_authorized=False)
    atomic(job/'status.json',state)
    child=None
    try:
        with (job/'worker.log').open('ab') as log:
            child=subprocess.Popen([sys.executable,'-B',__file__,str(job),'--compute'],
                                   stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            def cancel(*_):
                raise RuntimeError('Cancelled by operator')
            signal.signal(signal.SIGTERM,cancel)
            signal.signal(signal.SIGINT,cancel)
            hot={}
            while child.poll() is None:
                temperatures=[]
                for hw in Path('/sys/class/hwmon').glob('hwmon*'):
                    name=hw/'name'
                    if name.exists() and name.read_text().strip() in ('coretemp','k10temp'):
                        temperatures += [int(p.read_text())/1000 for p in hw.glob('temp*_input')]
                if not temperatures:raise RuntimeError('CPU telemetry unavailable')
                cpu=max(temperatures)
                ssds=[]
                for hw in Path('/sys/class/hwmon').glob('hwmon*'):
                    name=hw/'name'
                    if name.exists() and name.read_text().strip()=='nvme':
                        for p in hw.glob('temp*_input'):
                            label=p.with_name(p.name.replace('_input','_label'))
                            if label.exists() and label.read_text().strip()=='Composite':
                                ssds.append(int(p.read_text())/1000)
                if not ssds:raise RuntimeError('SSD telemetry unavailable')
                gpu=float(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu',
                    '--format=csv,noheader,nounits'],text=True,timeout=5).splitlines()[0])
                memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
                ram=int(memory['MemAvailable'].split()[0])/1024**2
                for name,value,warn,stop in [('cpu',cpu,90,95),('ssd',max(ssds),70,80),('gpu',gpu,80,85)]:
                    if value>=stop:raise RuntimeError('Safety stop: '+name+' immediate')
                    if value>=warn:hot.setdefault(name,time.monotonic())
                    else:hot.pop(name,None)
                if ram<8:hot.setdefault('ram',time.monotonic())
                else:hot.pop('ram',None)
                if any(time.monotonic()-t>=30 for t in hot.values()):
                    raise RuntimeError('Safety stop: sustained thermal/RAM boundary')
                disk=os.statvfs(job)
                if disk.f_bavail*disk.f_frsize<50*2**30:raise RuntimeError('Safety stop: /data reserve')
                disk=os.statvfs('/')
                if disk.f_bavail*disk.f_frsize<3*2**30:raise RuntimeError('Safety stop: / reserve')
                state.update(cpu_c=cpu,gpu_c=gpu,ssd_c=max(ssds),updated_at=time.time())
                atomic(job/'status.json',state)
                time.sleep(2)
            if child.returncode:raise RuntimeError('Adjustment failed; inspect worker.log')
        report=json.loads((job/'report.json').read_text())
        state.update(state=report['status'],finished_at=time.time(),report=report)
    except BaseException as error:
        if child is not None and child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL)
        state.update(state='failed',error=str(error),finished_at=time.time())
    atomic(job/'status.json',state)


if __name__=='__main__':
    job=Path(sys.argv[1]).resolve()
    assert job.is_relative_to('/data/barranco/manual-graph-editor/jobs')
    if '--compute' in sys.argv:compute(job)
    else:supervise(job)
