import json
from pathlib import Path
import subprocess
root=Path('/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-006-14nov')
assert NODE_TAG=='L507_006'
s=json.loads((root/'reconstruction-full-status.json').read_text())
def cmd(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=20)
    return {'rc':p.returncode,'out':p.stdout[-7000:],'err':p.stderr[-500:]}
r={'tag':NODE_TAG,'state':s.get('state'),'stage':s.get('stage'),'pid':s.get('pid')}
r['gpu']=cmd(['nvidia-smi','--query-gpu=temperature.gpu,utilization.gpu,power.draw,power.limit','--format=csv,noheader,nounits'])
r['gpu_apps']=cmd(['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv,noheader'])
container=s.get('container')
assert container and container.startswith('barranco-')
r['container_processes']=cmd(['docker','top',container,'-eo','pid,ppid,comm,pcpu,pmem,etime'])
r['container_stats']=cmd(['docker','stats','--no-stream','--format','{{.CPUPerc}} {{.MemUsage}}',container])
r['container_limits']=cmd(['docker','inspect','--format','{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}}',container])
config=json.loads((root/'config-full.json').read_text())
r['colmap_config']=config.get('colmap')
paths=[root/'logs/reconstruction/full/sfm.log',
       root/'outputs/cuadra-006'/s['experiment']/'logs/sfm.log']
r['log_tails']=[]
for p in paths:
    if p.is_file():
        with p.open('rb') as f:
            f.seek(max(0,p.stat().st_size-4500))
            text=f.read().decode(errors='replace')
        r['log_tails'].append({'path':str(p),'mtime':p.stat().st_mtime,'tail':text})
print('ADMIN_REPLY='+json.dumps(r))
