import json
import os
from pathlib import Path
import shutil
import subprocess
import time

def run(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {'rc': p.returncode, 'stdout': p.stdout[-2500:], 'stderr': p.stderr[-1500:]}
    except subprocess.TimeoutExpired:
        return {'error': 'timeout; inspect own test container before retry'}

root_free = shutil.disk_usage('/').free/2**30
data_free = shutil.disk_usage('/data').free/2**30
result = {'tag': NODE_TAG, 'root_free_gib':round(root_free,2),
          'data_free_gib':round(data_free,2)}
assert os.path.ismount('/data')
configuration = json.loads(Path('/etc/docker/daemon.json').read_text())
assert configuration['data-root'].startswith('/data/')
result['gpu_jobs'] = run(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'])
result['temperatures'] = run(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'])
if root_free < 3.75 or data_free < 100:
    result['blocked'] = 'existing worker disk preflight reserve not met'
else:
    result['start_runtime'] = run(['systemctl','start','containerd.service','docker.service'], 90)
    result['docker_info'] = run(['docker','info','--format','{{.DockerRootDir}}'])
    images = {
        'reconstruction': ('photogrammetry:l507-v1-pycolmap',
            'sha256:1a3c25a01680253192d7b95bb57abb3c2a680a1db8d9888c6fe533fcf08e98e0'),
        'segmentation': ('photogrammetry-seg:l507-v1',
            'sha256:9679fd9e51dac6b80cd7fdd75d43b3976c783c81393c25f407e24e14bd127042'),
    }
    result['images'] = {}
    can_test = (result['gpu_jobs'].get('rc') == 0 and not result['gpu_jobs']['stdout'].strip()
                and result['temperatures'].get('rc') == 0
                and float(result['temperatures']['stdout'].strip()) < 65)
    for role, (tag, expected) in images.items():
        identity = run(['docker','image','inspect','--format','{{.Id}}',tag])
        result['images'][role] = {'identity':identity, 'expected':expected,
                                 'matches':identity.get('stdout','').strip()==expected}
        if not result['images'][role]['matches'] or not can_test:
            continue
        test = ("import pycolmap,subprocess; print('pycolmap',pycolmap.__version__); "
                "subprocess.run(['colmap','-h'],check=True,stdout=subprocess.DEVNULL)"
                if role=='reconstruction' else
                "import torch; print('torch',torch.__version__); "
                "assert torch.cuda.is_available(); x=torch.ones(1,device='cuda'); "
                "print('cuda_scalar',x.item())")
        name = 'barranco-preflight-'+role+'-'+str(time.time_ns())
        result['images'][role]['test_container'] = name
        result['images'][role]['smoke_test'] = run([
            'docker','run','--pull=never','--rm','--name',name,
            '--network','none','--gpus','all','--read-only',
            '--tmpfs','/tmp:rw,size=128m','--memory','2g','--memory-swap','2g',
            '--cpus','1','--env','HF_HUB_OFFLINE=1','--env','PYTHONDONTWRITEBYTECODE=1',
            '--entrypoint','python3',tag,'-B','-c',test],120)
    release=Path('/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1')
    result['release_code']= (release/'code').is_dir()
    result['release_data']= (release/'data').is_dir()
    result['failed_units']=run(['systemctl','--failed','--no-pager','--plain'])
    result['containers']=run(['docker','ps','--format','{{.Names}} {{.Status}}'])
print('ADMIN_REPLY='+json.dumps(result))
