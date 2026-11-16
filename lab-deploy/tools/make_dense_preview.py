"""Non-destructive bounded-memory preview and full-file checksum in one pass."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading
import time

os.environ.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
import numpy as np

sys.path.insert(0,'/data/repos/Alineacion-point-cloud/src')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blockalign.plyio import header,chunks,write_header
from blockalign.storage import write
from blockalign.artifacts import require_job
from reconstruction_worker import telemetry,Guard


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-points',type=int,default=5000000);a=p.parse_args()
    if a.max_points<1:raise ValueError('Positive preview budget required')
    if a.output.exists():raise RuntimeError('Preview already exists; preserve the published file')
    allowed=set(os.sched_getaffinity(0));chosen={8,9,10,11}
    os.sched_setaffinity(0,chosen if chosen<=allowed else set(sorted(allowed)[:4]))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    context=a.output.with_suffix('.context.json');write(context,{'backend':'local','pid':os.getpid()});os.environ['BLOCKALIGN_LOCAL_CONTEXT']=str(context);require_job()
    group=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split(':',2)[2].lstrip('/')
    if not group.name.startswith('barranco-alignment-'):raise RuntimeError('Named bounded scope required')
    meta=header(a.input);stride=max(1,math.ceil(meta['count']/a.max_points));count=(meta['count']+stride-1)//stride
    if shutil.disk_usage('/data').free<count*100+50*1024**3:raise RuntimeError('Insufficient preview reserve')
    guard=Guard();stop=threading.Event()
    def monitor():
        failures=0
        while not stop.wait(5):
            try:
                values=telemetry(a.output.parent);warnings=guard.evaluate(values,time.monotonic());failures=0
                write(a.output.with_suffix('.telemetry.json'),{'values':values,'warnings':warnings})
            except Exception as exc:
                failures+=1
                write(a.output.with_suffix('.monitor-error.json'),{'error':str(exc),'failures':failures,'at':time.time()})
                if 'SAFETY STOP' in str(exc) or failures>=3:
                    subprocess.run(['systemctl','--user','kill','--kill-whom=all','--signal=KILL',group.name],timeout=15);os._exit(75)
    import subprocess
    threading.Thread(target=monitor,daemon=True).start()
    before=a.input.stat();sha=hashlib.sha256();offset=0;written=0
    with a.input.open('rb') as source:sha.update(source.read(meta['offset']))
    temporary=a.output.with_suffix('.ply.part')
    try:
        with temporary.open('wb') as dest:
            write_header(dest,count,meta['properties'])
            for data in chunks(a.input,meta):
                sha.update(data.tobytes())
                first=(-offset)%stride;selected=data[first::stride];dest.write(selected.tobytes())
                written+=len(selected);offset+=len(data)
        after=a.input.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Full export changed during read')
        if written!=count:raise RuntimeError('Preview count mismatch')
        temporary.replace(a.output)
        receipt={'source':str(a.input),'source_vertices':meta['count'],'source_bytes':before.st_size,'source_sha256':sha.hexdigest(),
                 'preview':str(a.output),'preview_vertices':written,'stride':stride,
                 'operation':'display-only sampling; full-resolution source preserved byte-for-byte','at':time.time()}
        write(a.output.with_suffix('.json'),receipt);print(json.dumps(receipt,indent=2))
    finally:stop.set()


if __name__=='__main__':main()
