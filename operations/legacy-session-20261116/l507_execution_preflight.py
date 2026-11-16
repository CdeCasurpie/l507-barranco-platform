import pathlib
exec(pathlib.Path('/tmp/opencode/l507_storage.py').read_text().split('\njobs=')[0])
BASE=pathlib.Path('/home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115')
assignments=json.loads((BASE/'assignments.json').read_text())['assignments']
CODE=CODE.split("docker=[]")[0]+r'''
import shutil
a=next(x for x in ASSIGNMENTS if x['node_tag']==tag)
root=pathlib.Path(a['work_root'])
result['download']=json.loads((root/'status.json').read_text())
result['active']=json.loads(pathlib.Path('/var/lib/lab-deploy/active.json').read_text())
result['disk']=run('df','-h','/data','/')
result['gpu']=run('nvidia-smi','--query-gpu=temperature.gpu,memory.used,utilization.gpu','--format=csv,noheader')
result['compute']=run('nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader')
result['mem_available_gib']=int(next(l.split()[1] for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))/1024**2
result['docker']=subprocess.run(['systemctl','is-active','docker','containerd'],capture_output=True,text=True).stdout
result['after']=mounts
print('RESULT='+json.dumps(result))
'''
CODE=CODE.replace('ASSIGNMENTS',repr(assignments))
for a in assignments:print(work(a['node_tag'],a['ip'].split('.')[-1],a['mac']),flush=True)
