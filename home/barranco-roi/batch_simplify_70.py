"""Approved 70% reduction for 15 blocks; preserve each block as an independent mesh."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'exports/mesh-campaign-20261112'
OUT=BASE/'simplified_70pct_blocks'
PYTHON='/data/barranco/runtime/alignment313/bin/python'


def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.json.new')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temp.replace(path)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for raw in iter(lambda:f.read(8*1024**2),b''):h.update(raw)
    return h.hexdigest()


def worker(block):
    from simplify_meshes import load_mesh, save_mesh, clean_components, surface_distances
    from preview_simplification import generate_preview
    source=BASE/block/('manzana_'+block+'_world.ply')
    original=json.loads((BASE/'manifest.json').read_text())['blocks'][block]
    destination=OUT/'meshes'/('manzana_'+block+'_simplified_70pct.ply')
    work=OUT/'work'/block
    work.mkdir(parents=True,exist_ok=True)
    destination.parent.mkdir(parents=True,exist_ok=True)
    report_path=OUT/'reports'/(block+'.json')
    status=dict(block=block,pid=os.getpid(),started_at=time.time(),source=str(source))
    began=time.monotonic()
    def progress(stage,**kwargs):
        status.update(stage=stage,updated_at=time.time(),elapsed_seconds=time.monotonic()-began,**kwargs)
        atomic(work/'status.json',status)
        print(block,stage,kwargs,flush=True)
    try:
        if report_path.exists():
            report=json.loads(report_path.read_text())
            assert report['original_sha256']==original['sha256'] and sha(destination)==report['sha256']
            progress('completed',cached=True)
            return
        progress('verify_source')
        assert sha(source)==original['sha256']
        if block=='025':
            preview=BASE/'simplified/previews/025_70pct_no_distance_limit'
            old=json.loads((preview/'report.json').read_text())
            approved=preview/'manzana_025_70pct_preview.ply'
            assert sha(approved)==old['sha256']
            if not destination.exists():os.link(approved,destination)
            assert sha(destination)==old['sha256']
            report=dict(old,reused_approved_025=True,mesh=str(destination),original_sha256=original['sha256'],
                        original=dict(vertices=original['vertices'],faces=original['faces'],bytes=original['bytes']),
                        execution_seconds=time.monotonic()-began)
            atomic(report_path,report)
            progress('completed',faces=report['faces'],bytes=report['bytes'],reused=True)
            return
        reference=work/'reference_retained.ply'
        cleanup_path=work/'cleanup.json'
        if not reference.exists():
            progress('tiny_component_cleanup')
            xyz,faces,rgb=load_mesh(source)
            xyz,faces,rgb,cleanup=clean_components(xyz,faces,rgb)
            save_mesh(reference,xyz,faces,rgb)
            atomic(cleanup_path,cleanup)
            del xyz,faces,rgb
        cleanup=json.loads(cleanup_path.read_text())
        generation_path=work/'generation.json'
        if destination.exists():
            generation=json.loads(generation_path.read_text())
            assert sha(destination)==generation['sha256']
        else:
            progress('generating')
            generation=generate_preview(work,work,destination,70,block=block,progress=progress)
        progress('measuring_surface_without_distance_gate')
        measured=time.monotonic()
        xyz,faces,_=load_mesh(reference)
        vx,fc,_=load_mesh(destination)
        distances=surface_distances(xyz,faces,vx,fc,all_vertices=True)
        report=dict(block=block,mesh=str(destination),sha256=generation['sha256'],vertices=generation['vertices'],
                    faces=generation['faces'],bytes=destination.stat().st_size,
                    original=dict(vertices=original['vertices'],faces=original['faces'],bytes=original['bytes']),
                    original_sha256=original['sha256'],roi_selection_id=json.loads((BASE/block/('roi_'+block+'.json')).read_text())['selection_id'],
                    face_reduction_percent=100*(1-generation['faces']/original['faces']),
                    distance_gate_enabled=False,coordinate_frame='map_world',already_world_aligned=True,
                    method='Same approved 025 preview: local PCA normals, connected RANSAC planes, QEM removing 70 percent of faces',
                    cleanup=cleanup,distances=distances,timings_s=generation['timings_s'],
                    measurement_seconds=time.monotonic()-measured,execution_seconds=time.monotonic()-began,
                    gpu_used=False,close_holes=False)
        atomic(report_path,report)
        progress('completed',faces=report['faces'],bytes=report['bytes'])
    except BaseException as exc:
        progress('failed',error=str(exc))
        raise


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((BASE/'manifest.json').read_text())
    assert manifest['collected']==15 and not manifest['failed']
    config=dict(reduction_percent=70,distance_gate_enabled=False,source_campaign=str(BASE),
                separate_meshes=True,max_parallel=2,approved_block='025')
    config_path=OUT/'batch_config.json'
    if config_path.exists():assert json.loads(config_path.read_text())==config
    atomic(config_path,config)
    started=time.time()
    values={}
    def one(block):
        logpath=OUT/'work'/block/'worker.log'
        logpath.parent.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4')
        with logpath.open('a') as log:
            process=subprocess.run([PYTHON,'-B','-u',str(Path(__file__).resolve()),'worker','--block',block],
                                   cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        if process.returncode:
            raise RuntimeError('Worker failed: '+str(logpath))
        return json.loads((OUT/'reports'/(block+'.json')).read_text())
    blocks=sorted(manifest['blocks'],key=lambda b:manifest['blocks'][b]['faces'],reverse=True)
    # Preserve the exact approved sample immediately; other blocks run at most two together.
    values['025']=one('025')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(one,b):b for b in blocks if b!='025'}
        for future in as_completed(futures):
            block=futures[future]
            try:values[block]=future.result()
            except Exception as exc:values[block]=dict(error=str(exc))
            atomic(OUT/'status.json',dict(started_at=started,updated_at=time.time(),blocks=values,
                                         completed=sum('error' not in v for v in values.values())))
            print('FINISHED',block,'faces',values[block].get('faces'),'bytes',values[block].get('bytes'),values[block].get('error',''),flush=True)
    failed={b:v for b,v in values.items() if 'error' in v}
    if failed:raise RuntimeError('Some blocks failed: '+json.dumps(failed))
    atomic(OUT/'manifest.json',dict(blocks=values,completed=15,geometry_bytes=sum(v['bytes'] for v in values.values()),
        vertices=sum(v['vertices'] for v in values.values()),faces=sum(v['faces'] for v in values.values()),
        elapsed_seconds=time.time()-started,reduction_percent=70,distance_gate_enabled=False,
        coordinate_frame='map_world',independent_objects_required=True))
    subprocess.run([PYTHON,'-B','-u',str(ROOT/'package_simplified_blocks.py')],cwd=ROOT,check=True)
    subprocess.run(['blender','--background','--factory-startup','--threads','4','--python-exit-code','1','--python',str(ROOT/'blender_blocks.py'),
                    '--',str(OUT),'build'],cwd=ROOT,check=True)
    subprocess.run(['blender','--background',str(OUT/'barranco_15_manzanas_70pct.blend'),'--threads','4','--python-exit-code','1','--python',
                    str(ROOT/'blender_blocks.py'),'--',str(OUT),'audit'],cwd=ROOT,check=True)
    subprocess.run([PYTHON,'-B','-u',str(ROOT/'package_simplified_blocks.py'),'--finalize'],cwd=ROOT,check=True)
    print('ALL DONE',OUT,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['run','worker'])
    p.add_argument('--block')
    a=p.parse_args()
    if a.action=='worker':worker(a.block)
    else:run()
