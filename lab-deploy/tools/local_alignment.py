"""L507 CPU backend: real systemd scope + original blockalign numerical engine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

os.environ.update(OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='8',MKL_NUM_THREADS='8',MPLBACKEND='Agg',
                  MPLCONFIGDIR='/data/barranco/runtime/cache/matplotlib',XDG_CACHE_HOME='/data/barranco/runtime/cache',
                  TMPDIR='/data/barranco/runtime/test-tmp')
RUNTIME=Path('/data/barranco/runtime/alignment313')
REPO=Path('/data/repos/Alineacion-point-cloud')
sys.path.insert(0,str(REPO/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))


def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['audit','campaign','export'])
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--manifests',type=Path,nargs='*')
    p.add_argument('--map');p.add_argument('--product',default='combined_ply');p.add_argument('--sparse',action='store_true')
    p.add_argument('--color',choices=['original','by_block'],default='original')
    args=p.parse_args();workspace=args.workspace.resolve();workspace.mkdir(parents=True,exist_ok=True)
    import pycolmap
    if pycolmap.__version__!='3.13.0':raise RuntimeError('PyCOLMAP version mismatch')
    import subprocess
    env=dict(os.environ,PATH=str(RUNTIME/'bin')+os.pathsep+os.environ['PATH'])
    os.environ['PATH']=env['PATH']
    if 'COLMAP 3.13.0' not in subprocess.check_output(['colmap','-h'],text=True):raise RuntimeError('Native version mismatch')
    runtime_files=[RUNTIME/'bin/colmap',*sorted((RUNTIME/'conda-meta').glob('*.json')),
                   *sorted(Path(pycolmap.__file__).parent.rglob('*.so'))]
    runtime_identity={str(p.relative_to(RUNTIME)):hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime_files}
    from blockalign.storage import write,lock
    from blockalign.contracts import digest
    from blockalign import Workspace
    from blockalign.artifacts import require_job
    run_id='local-'+str(int(time.time()))+'-'+str(os.getpid())
    directory=workspace/'runs'/run_id;directory.mkdir(parents=True)
    context=directory/'local-context.json';write(context,{'backend':'local','pid':os.getpid(),'cpus':8,'memory_gib':40})
    os.environ['BLOCKALIGN_LOCAL_CONTEXT']=str(context);os.environ['BLOCKALIGN_CPUS']='8'
    require_job()
    group=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split(':',2)[2].lstrip('/')
    scope=group.name
    if not scope.startswith('barranco-alignment-') or not scope.endswith('.scope'):
        raise RuntimeError('Use an explicitly named barranco-alignment-* systemd user scope')
    from reconstruction_worker import telemetry,Guard
    guard=Guard();root=Path('/data/barranco');stop=threading.Event()
    def monitor():
        failures=0
        while not stop.wait(5):
            try:
                values=telemetry(root);guard.evaluate(values,time.monotonic());failures=0
                write(directory/'telemetry.json',values)
            except Exception as exc:
                failures+=1
                write(directory/'monitor-error.json',{'error':str(exc),'failures':failures})
                if 'SAFETY STOP' in str(exc) or failures>=3:
                    # Stop precisely this real scope, including native matching
                    # children; never signal the login session's process group.
                    subprocess.run(['systemctl','--user','kill','--kill-whom=all','--signal=KILL',scope],timeout=15)
                    os._exit(75)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    with lock(workspace/'locks'/'local-execution.lock'):
        w=Workspace.open(workspace)
        scratch=Path(tempfile.mkdtemp(prefix=run_id+'-',dir=str(workspace)))
        try:
            if args.operation in ['audit','campaign']:
                if not args.manifests:raise ValueError('Manifests required')
                refs=[w.register_block(m) for m in args.manifests]
                if args.operation=='audit':
                    from blockalign.audit import audit_block
                    result={ref:audit_block(workspace,ref,w.block(ref),scratch)[0] for ref in refs}
                else:
                    hints=json.loads((REPO/'examples/barranco-map-neighbors.json').read_text())
                    if isinstance(hints,dict):hints=hints.get('pairs',hints.get('neighbors',[]))
                    reference=next((r for r in refs if r.startswith('009@')),refs[0])
                    plan=w.plan_campaign(refs,reference=reference,map_hints=hints)
                    hashes={str(f.relative_to(REPO)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (REPO/'src').rglob('*.py')}
                    request={'run_id':run_id,'plan':plan,'runtime':runtime_identity,
                             'pair_engine':digest({'code':hashes,'runtime':runtime_identity,'native':'3.13.0','pycolmap':pycolmap.__version__})}
                    write(directory/'request.json',request)
                    from blockalign.campaign import run
                    result=run(workspace,request,scratch)
            else:
                if not args.map:raise ValueError('Map required')
                mapping=json.loads((workspace/'maps'/args.map/'map.json').read_text())
                choices={r:'sparse' if args.sparse else 'dense' for r in mapping['placements']}
                expected=0
                for ref in mapping['placements']:
                    m=mapping['manifests'][ref]
                    if args.sparse:
                        import struct
                        with (Path(m['sparse']['model_uri'])/'points3D.bin').open('rb') as f:expected+=struct.unpack('<Q',f.read(8))[0]*29
                    else:
                        expected+=sum(Path(a['uri']).stat().st_size*1.1 for a in m['assets'] if a['asset_id']=='dense')
                if shutil.disk_usage('/data').free<expected+50*1024**3:
                    raise RuntimeError('Insufficient export storage plus 50 GiB reserve; sources retained')
                plan=w.plan_export(args.map,product=args.product,block_assets=choices,color_mode=args.color)
                from blockalign.exports import export
                result=export(workspace,{'run_id':run_id,'plan':plan},scratch)
            write(directory/'result.json',result)
            print(json.dumps({'run_id':run_id,'result':result},indent=2),flush=True)
        except BaseException as exc:
            write(directory/'failure.json',{'error':str(exc)})
            raise
        finally:
            stop.set()
            # Preserve scratch diagnostics on failure; success has published data.
            if (directory/'result.json').exists():shutil.rmtree(scratch)


if __name__=='__main__':main()
