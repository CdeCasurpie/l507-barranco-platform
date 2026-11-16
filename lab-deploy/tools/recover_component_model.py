"""Validated derived SfM from two overlapping mapper components, originals kept."""
import os
os.environ.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import numpy as np
import pycolmap as pc

sys.path.insert(0,'/data/repos/Alineacion-point-cloud/src')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blockalign.storage import write
from blockalign.artifacts import require_job
from alignexp.audit import observation_preservation,reciprocal_tracks,reprojection_stats,input_image_multiplicity
from alignexp.fusion import verify_image_union
from reconstruction_worker import telemetry,Guard

root=Path('/data/barranco/recovery007');context=root/'local-context.json'
write(context,{'backend':'local','pid':os.getpid()});os.environ['BLOCKALIGN_LOCAL_CONTEXT']=str(context);require_job()
group=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split(':',2)[2].lstrip('/')
if not group.name.startswith('barranco-alignment-'):raise RuntimeError('Explicit bounded scope required')
stop=threading.Event();guard=Guard()
def monitor():
    misses=0
    while not stop.wait(5):
        try:
            t=telemetry(root);guard.evaluate(t,time.monotonic());write(root/'telemetry.json',t);misses=0
        except Exception as exc:
            misses+=1;write(root/'monitor-error.json',{'error':str(exc)})
            if 'SAFETY STOP' in str(exc) or misses>=3:
                subprocess.run(['systemctl','--user','kill','--kill-whom=all','--signal=KILL',group.name],timeout=15);os._exit(75)
threading.Thread(target=monitor,daemon=True).start()
native='/data/barranco/runtime/alignment313/bin/colmap'
a=root/'components/1';b=root/'components/0';merged=root/'merged';optimized=root/'optimized'
if merged.exists() or optimized.exists():raise RuntimeError('Use fresh recovery directories; retain prior evidence')
merged.mkdir();optimized.mkdir()
def command(args,name):
    with (root/name).open('w') as log:
        p=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError('Recovery command failed: '+name)
try:
    original_a=pc.Reconstruction(str(a));original_b=pc.Reconstruction(str(b))
    shared=set(original_a.reg_image_ids())&set(original_b.reg_image_ids())
    if len(shared)<6:raise RuntimeError('Insufficient shared registered views')
    command([native,'model_merger','--input_path1',str(a),'--input_path2',str(b),'--output_path',str(merged),'--max_reproj_error','8'],'merger.log')
    candidate=pc.Reconstruction(str(merged));verify_image_union(candidate,original_a.reg_image_ids(),original_b.reg_image_ids())
    before=reprojection_stats(candidate)
    command([native,'bundle_adjuster','--input_path',str(merged),'--output_path',str(optimized),
             '--BundleAdjustment.max_num_iterations','100','--BundleAdjustment.use_gpu','0'],'bundle.log')
    final=pc.Reconstruction(str(optimized));verify_image_union(final,original_a.reg_image_ids(),original_b.reg_image_ids())
    observations={'1':observation_preservation(a,optimized),'0':observation_preservation(b,optimized)}
    tracks=reciprocal_tracks(final);stats=reprojection_stats(final,update_errors=True)
    baseline=input_image_multiplicity(a)+input_image_multiplicity(b)
    if tracks['exact_duplicate_elements'] or tracks['duplicate_image_observations']>baseline:
        raise RuntimeError('Derived model has conflicting track multiplicity')
    if any(v['loss_fraction']>.05 for v in observations.values()):raise RuntimeError('Excessive observation loss')
    if stats['mean_error_px']>2 or stats['p90_error_px']>4:raise RuntimeError('Derived reprojection quality insufficient')
    final.write(str(optimized))
    result={'passed':True,'shared_images':len(shared),'registered_union':final.num_reg_images(),'cameras':len(final.cameras),
            'before':before,'after':stats,'observations':observations,'tracks':tracks,
            'source_components':[str(a),str(b)],'derived_model':str(optimized),
            'operation':'validated merger + explicit global BA; new dense must be generated; original models/dense kept'}
    write(root/'result.json',result);print(json.dumps(result,indent=2),flush=True)
finally:stop.set()
