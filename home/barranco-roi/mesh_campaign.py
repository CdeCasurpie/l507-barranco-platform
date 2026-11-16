"""Authorized per-block mesh campaign; uses the existing private SSH adapter."""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, '/home/exitoso/lab-deploy/tools')
from drive_download_campaign import remote
sys.path.insert(0, '/home/exitoso/lab-deploy')
from labdeploy.store import atomic_json
from labdeploy.ssh import credentials
import pexpect
from roi.mvs_interface import camera_table, camera_mapping

SITE = json.loads(Path('/home/exitoso/lab-deploy/config/site.json').read_text())
# Observed by make check, 2026-11-12; every SSH operation verifies tag and MAC.
IPS = dict(zip(['001','002','003','004','005','006','007','008','009','010','011','012','015','023','024'],
               ['56','54','55','44','58','64','71','77','78','66','65','53','61','72','68']))
DIRECTORY = ROOT / 'state' / 'mesh-campaign-20261112'
EXPORTS = ROOT / 'exports' / 'mesh-campaign-20261112'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024**2), b''):
            h.update(block)
    return h.hexdigest()


def transfer(source, target):
    password, _ = credentials(SITE)
    ssh = 'ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts -o LogLevel=ERROR -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1'
    bandwidth = '8000' if ':' in source else '4000'
    child = pexpect.spawn('rsync', ['-a','--partial','--bwlimit='+bandwidth,'-e',ssh,source,target], encoding='utf-8', timeout=900, echo=False)
    while True:
        event = child.expect(['[Pp]assword:',pexpect.EOF,pexpect.TIMEOUT])
        if event == 0:
            child.sendline(password)
        elif event == 1:
            break
        else:
            child.close(force=True)
            raise RuntimeError('Transfer timeout; own partial is retained')
    child.close()
    if child.exitstatus != 0:
        raise RuntimeError('Transfer failed: '+str(child.exitstatus))


def prepare():
    inventory = json.loads((DIRECTORY/'inventory.json').read_text())['blocks']
    blocks = api('/api/blocks')
    assert len(blocks) == 15 and all(b['selection_current'] for b in blocks)
    snapshots = DIRECTORY/'selections'
    snapshots.mkdir(exist_ok=True)
    manifest = dict(campaign='mesh-campaign-20261112', created_at=time.time(), assignments={})
    for b in blocks:
        block = b['block']
        observed = inventory[block]
        if 'error' in observed or not observed['source_exists'] or not observed['mounted']:
            raise RuntimeError('Source unavailable on '+block)
        config = api('/api/roi.json?block='+block)
        path = snapshots/('roi_'+block+'.json')
        if path.exists() and json.loads(path.read_text()) != config:
            raise RuntimeError('Frozen selection changed: '+block)
        atomic_json(path, config)
        source = Path('/data/barranco/results/barranco-full-v1')/block
        runs = [p.parent for p in source.glob('*/collection-receipt.json') if json.loads(p.read_text())['source'] == config['native_source_root']]
        if len(runs) != 1:
            raise RuntimeError('Cannot locate exact source '+block)
        run = runs[0]
        audit = []
        if block != '025':
            global_table = camera_table(run/'mvs/scene.mvs')
            meta = json.loads((run/'mvs/dense-batches.json').read_text())
            for item in meta['ranges']:
                chunk = run/'mvs/chunks'/Path(item['source']).parent.name
                dense = camera_table(chunk/'scene_dense.mvs')
                mapping, delta = camera_mapping(global_table, dense)
                unchanged, _ = camera_mapping(dense, camera_table(chunk/'scene.mvs'))
                if unchanged != list(range(len(mapping))):
                    raise RuntimeError('Densification changed camera order '+block)
                audit.append(dict(batch=chunk.name, cameras=len(mapping), max_pose_delta=delta))
        atomic_json(DIRECTORY/('camera-preflight-'+block+'.json'),audit)
        busy = block in ['001','018']
        assignment = dict(roi=config, node_tag=observed['tag'], mac=SITE['nodes'][observed['tag']],
                          ip=observed['ip'], mountpoint=observed['mount'], source_root=observed['source_root'],
                          work_root=observed['mount']+'/photogrammetry/roi-campaigns/mesh-20261112/'+block,
                          threads=2 if busy else 6, memory_gib=24 if busy else 40, existing_gpu_job=busy,
                          status='reuse_pilot' if block=='025' else 'prepared')
        manifest['assignments'][block] = assignment
        print('PREPARED',block,observed['tag'],'batches',len(audit),'threads',assignment['threads'],flush=True)
    atomic_json(DIRECTORY/'manifest.json',manifest)
    archive = DIRECTORY/'runtime.tar.gz'
    previous_bundle = json.loads((DIRECTORY/'runtime.json').read_text()) if (DIRECTORY/'runtime.json').exists() else {}
    if not archive.exists() or previous_bundle.get('native_tool_sha256') != sha(ROOT/'runtime/tools/mesh_roi'):
        temporary = archive.with_suffix('.gz.new')
        with tarfile.open(temporary,'w:gz',compresslevel=3) as tar:
            tar.add(ROOT/'runtime/tools/mesh_roi',arcname='runtime/mesh_roi')
            tar.add(ROOT/'runtime/openmvs/bin/ReconstructMesh',arcname='runtime/openmvs/bin/ReconstructMesh')
            tar.add(ROOT/'runtime/openmvs/lib',arcname='runtime/openmvs/lib')
        temporary.replace(archive)
    atomic_json(DIRECTORY/'runtime.json',dict(sha256=sha(archive),bytes=archive.stat().st_size,
                worker_sha256=sha(ROOT/'mesh_worker.py'), camera_parser_sha256=sha(ROOT/'roi/mvs_interface.py'),
                native_tool_sha256=sha(ROOT/'runtime/tools/mesh_roi')))
    print('READY runtime archive',archive.stat().st_size,flush=True)


def deploy(a):
    code = f'''
import json,os
from pathlib import Path
a={a!r}
assert (Path.home()/(a['node_tag']+'.txt')).is_file(), 'Tag mismatch'
assert a['mac'] in [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')], 'MAC mismatch'
assert os.path.ismount(a['mountpoint']), 'Unmounted source'
root=Path(a['work_root']);root.mkdir(parents=True,exist_ok=True)
p=root/'assignment.json'
if p.exists() and json.loads(p.read_text())!=a:raise RuntimeError('Conflicting assignment')
p.write_text(json.dumps(a,indent=2))
print('DOWNLOAD_REPLY='+json.dumps({{'ready':True}}))
'''
    remote(SITE,a['ip'],code)
    prefix=SITE['ssh_user']+'@'+a['ip']+':'
    parent=str(Path(a['work_root']).parent)
    transfer(str(DIRECTORY/'runtime.tar.gz'),prefix+parent+'/runtime.tar.gz')
    transfer(str(ROOT/'mesh_worker.py'),prefix+a['work_root']+'/mesh_worker.py')
    transfer(str(ROOT/'roi/mvs_interface.py'),prefix+a['work_root']+'/mvs_interface.py')
    bundle=json.loads((DIRECTORY/'runtime.json').read_text())
    code=f'''
import json,os,subprocess,tarfile,hashlib
from pathlib import Path
a={a!r};root=Path(a['work_root']);parent=root.parent
h=hashlib.sha256((parent/'runtime.tar.gz').read_bytes()).hexdigest()
assert h=={bundle['sha256']!r}, 'Runtime transfer checksum mismatch'
if not (parent/'runtime').exists():
 with tarfile.open(parent/'runtime.tar.gz') as t:t.extractall(parent,filter='data')
for path,expected in [(root/'mesh_worker.py',{bundle['worker_sha256']!r}),(root/'mvs_interface.py',{bundle['camera_parser_sha256']!r}),(parent/'runtime/mesh_roi',{bundle['native_tool_sha256']!r})]:
 assert hashlib.sha256(path.read_bytes()).hexdigest()==expected, 'Worker transfer checksum mismatch'
env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(os.getuid())+'/bus')
unit='barranco-mesh-'+a['roi']['block']+'-20261112'
check=subprocess.run(['systemctl','--user','is-active',unit],env=env,capture_output=True,text=True)
if check.returncode!=0:
 subprocess.run(['systemctl','--user','reset-failed',unit],env=env,capture_output=True)
 cmd=['systemd-run','--user','--unit='+unit,'--working-directory='+str(root),'-p','MemoryMax='+str(a['memory_gib'])+'G','-p','MemorySwapMax=0','-p','CPUQuota='+str(a['threads']*100)+'%','-p','Nice=10','-p','IOWeight=20','python3','-B','-u',str(root/'mesh_worker.py'),str(root)]
 p=subprocess.run(cmd,env=env,capture_output=True,text=True)
 if p.returncode:raise RuntimeError(p.stderr)
print('DOWNLOAD_REPLY='+json.dumps({{'unit':unit,'state':'launched','block':a['roi']['block']}}))
'''
    return remote(SITE,a['ip'],code,timeout=180)


def inspect_job(a):
    return remote(SITE,a['ip'],f'''
import json,os,subprocess
from pathlib import Path
root=Path({a['work_root']!r});p=root/'status.json'
s=json.loads(p.read_text()) if p.exists() else {{'stage':'not_started'}}
s['worker_alive']=bool(s.get('pid') and Path('/proc/'+str(s['pid'])+'/cmdline').exists() and str(root).encode() in Path('/proc/'+str(s['pid'])+'/cmdline').read_bytes())
env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(os.getuid())+'/bus')
unit='barranco-mesh-'+{a['roi']['block']!r}+'-20261112'
properties=subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','-p','Result','-p','MemoryCurrent','-p','MemoryPeak'],env=env,capture_output=True,text=True).stdout
s['service']=dict(line.split('=',1) for line in properties.splitlines() if '=' in line)
mem={{k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}}
s['system_ram_available_gib']=round(mem['MemAvailable']/1024**3,2)
cg=Path('/sys/fs/cgroup/user.slice/user-'+str(os.getuid())+'.slice/user@'+str(os.getuid())+'.service/app.slice/'+unit+'.service')
if (cg/'memory.stat').exists():
 s['cgroup_memory']=dict(line.split() for line in (cg/'memory.stat').read_text().splitlines())
 s['cgroup_events']=(cg/'memory.events').read_text()
if not s['worker_alive'] and s.get('stage') not in ['not_started','failed','completed']:
 s.update(stage='failed',error='Worker exited without completion: '+str(s['service']))
if s.get('stage')=='failed':
 logs=sorted(root.glob('*.log'),key=lambda p:p.stat().st_mtime)
 s['last_log']=logs[-1].read_text()[-5000:] if logs else ''
print('DOWNLOAD_REPLY='+json.dumps(s))
''')


def repair_tool(a):
    """Update only our derived filter executable; running reconstruction continues."""
    if inspect_job(a).get('stage') == 'completed':
        return dict(state='already_completed')
    destination = str(Path(a['work_root']).parent/'runtime/mesh_roi')
    transfer(str(ROOT/'runtime/tools/mesh_roi'),SITE['ssh_user']+'@'+a['ip']+':'+destination)
    expected = sha(ROOT/'runtime/tools/mesh_roi')
    code=f'''
import json,os,subprocess,hashlib
from pathlib import Path
a={a!r};root=Path(a['work_root'])
assert hashlib.sha256(Path({destination!r}).read_bytes()).hexdigest()=={expected!r}
env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(os.getuid())+'/bus')
unit='barranco-mesh-'+a['roi']['block']+'-20261112'
active=subprocess.run(['systemctl','--user','is-active',unit],env=env,capture_output=True,text=True).returncode==0
if not active:
 subprocess.run(['systemctl','--user','reset-failed',unit],env=env,capture_output=True)
 cmd=['systemd-run','--user','--unit='+unit,'--working-directory='+str(root),'-p','MemoryMax='+str(a['memory_gib'])+'G','-p','MemorySwapMax=0','-p','CPUQuota='+str(a['threads']*100)+'%','-p','Nice=10','-p','IOWeight=20','python3','-B','-u',str(root/'mesh_worker.py'),str(root)]
 p=subprocess.run(cmd,env=env,capture_output=True,text=True)
 if p.returncode:raise RuntimeError(p.stderr)
print('DOWNLOAD_REPLY='+json.dumps({{'filter_sha256':{expected!r},'restarted_own_failed_worker':not active}}))
'''
    return remote(SITE,a['ip'],code)


def repair():
    manifest=json.loads((DIRECTORY/'manifest.json').read_text())
    values={}
    with ThreadPoolExecutor(max_workers=14) as pool:
        futures={pool.submit(repair_tool,a):b for b,a in manifest['assignments'].items() if b!='025'}
        for future in as_completed(futures):
            block=futures[future]
            try:
                values[block]=future.result()
            except Exception as exc:
                values[block]=dict(error=str(exc))
            print(block,values[block],flush=True)
    atomic_json(DIRECTORY/'filter-update.json',dict(updated_at=time.time(),blocks=values))


def launch():
    manifest=json.loads((DIRECTORY/'manifest.json').read_text())
    launched={}
    with ThreadPoolExecutor(max_workers=14) as pool:
        futures={pool.submit(deploy,a):block for block,a in manifest['assignments'].items() if block!='025'}
        for future in as_completed(futures):
            block=futures[future]
            try:
                launched[block]=future.result()
            except Exception as exc:
                launched[block]=dict(state='launch_failed',error=str(exc))
            atomic_json(DIRECTORY/'launch.json',launched)
            print(block,launched[block],flush=True)


def status():
    manifest=json.loads((DIRECTORY/'manifest.json').read_text())
    values={}
    with ThreadPoolExecutor(max_workers=14) as pool:
        futures={pool.submit(inspect_job,a):block for block,a in manifest['assignments'].items() if block!='025'}
        for future in as_completed(futures):
            block=futures[future]
            try:
                values[block]=future.result()
            except Exception as exc:
                values[block]=dict(stage='connection_error',error=str(exc))
            value=values[block]
            print(block,value.get('stage'),'alive',value.get('worker_alive'),'seconds',value.get('stage_seconds'),'points',value.get('sample',{}).get('selected_points'),value.get('error',''),flush=True)
    atomic_json(DIRECTORY/'status.json',dict(observed_at=time.time(),blocks=values))
    return values


def reuse_pilot(manifest):
    roi = manifest['assignments']['025']['roi']
    pilot = Path('/data/barranco/roi/025')/roi['selection_id']/'pilot-v1'
    prep = json.loads((pilot/'prepare.json').read_text())
    original = json.loads((ROOT/'state/selections'/(roi['selection_id']+'.json')).read_text())
    if prep['voxel_m'] != .1 or prep['world_from_block'] != roi['world_from_block'] or original['vertices'] != roi['vertices']:
        raise RuntimeError('025 pilot is incompatible with frozen selection')
    checks = json.loads((pilot/'checksums.json').read_text())['delaunay_world.ply']
    source = pilot/'delaunay_world.ply'
    if sha(source) != checks['sha256']:
        raise RuntimeError('025 pilot checksum mismatch')
    destination = EXPORTS/'025'
    destination.mkdir(parents=True,exist_ok=True)
    mesh = destination/'manzana_025_world.ply'
    if not mesh.exists():
        shutil.copy2(source,mesh)
    if sha(mesh) != checks['sha256']:
        raise RuntimeError('025 collected checksum mismatch')
    result = json.loads((pilot/'delaunay.json').read_text())
    result.update(block='025',selection_id=roi['selection_id'],reused_pilot=True,sha256=checks['sha256'],bytes=mesh.stat().st_size,mesh=str(mesh),world_from_block=roi['world_from_block'])
    atomic_json(destination/'result.json',result)
    atomic_json(destination/'roi_025.json',roi)
    return result


def collect(a, value):
    block = a['roi']['block']
    result = value['result']
    destination = EXPORTS/block
    destination.mkdir(parents=True,exist_ok=True)
    mesh = destination/('manzana_'+block+'_world.ply')
    if mesh.exists():
        if sha(mesh) != result['sha256']:
            raise RuntimeError('Existing local mesh checksum differs '+block)
    else:
        if shutil.disk_usage(destination).free < result['bytes']+10*1024**3:
            raise RuntimeError('Collection would breach 10 GiB free on home')
        prefix = SITE['ssh_user']+'@'+a['ip']+':'
        partial = destination/(mesh.name+'.partial')
        transfer(prefix+result['mesh'],str(partial))
        if sha(partial) != result['sha256']:
            raise RuntimeError('Transferred mesh checksum mismatch '+block)
        partial.replace(mesh)
    for name in ['result.json','camera-audit.json','sampling.json','delaunay-command.json']:
        transfer(SITE['ssh_user']+'@'+a['ip']+':'+a['work_root']+'/'+name,str(destination/name))
    atomic_json(destination/('roi_'+block+'.json'),a['roi'])
    return dict(result,local_mesh=str(mesh),collected_at=time.time())


def watch():
    manifest = json.loads((DIRECTORY/'manifest.json').read_text())
    EXPORTS.mkdir(parents=True,exist_ok=True)
    report_path = DIRECTORY/'collection.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else dict(blocks={})
    report['blocks']['025'] = reuse_pilot(manifest)
    atomic_json(report_path,report)
    started = time.monotonic()
    while time.monotonic()-started < 8*3600:
        values = status()
        for block,value in sorted(values.items()):
            if value.get('stage') == 'completed' and block not in report['blocks']:
                try:
                    report['blocks'][block] = collect(manifest['assignments'][block],value)
                    atomic_json(report_path,report)
                    print('COLLECTED',block,report['blocks'][block]['bytes'],flush=True)
                except Exception as exc:
                    print('COLLECTION ERROR',block,str(exc),flush=True)
        report.update(updated_at=time.time(),collected=len(report['blocks']),geometry_bytes=sum(b['bytes'] for b in report['blocks'].values()),
                      failed={b:v.get('error') for b,v in values.items() if v.get('stage')=='failed'})
        atomic_json(report_path,report)
        atomic_json(EXPORTS/'manifest.json',dict(campaign=manifest['campaign'],selections={b:a['roi']['selection_id'] for b,a in manifest['assignments'].items()},**report))
        if len(report['blocks'])==15:
            print('ALL 15 MESHES COLLECTED',report['geometry_bytes'],flush=True)
            return
        if all(v.get('stage') in ['completed','failed'] for v in values.values()) and all(b in report['blocks'] for b,v in values.items() if v.get('stage')=='completed'):
            print('FINISHED WITH FAILURES',report['failed'],flush=True)
            return
        time.sleep(30)
    raise RuntimeError('Watch exceeded eight hours; daughter jobs retain independent status')


def api(path):
    with urlopen('http://127.0.0.1:8765' + path, timeout=120) as response:
        return json.load(response)


def inspect(block):
    tag = block['node']
    ip = '10.100.41.' + IPS[tag[-3:]]
    config = api('/api/roi.json?block=' + block['block'])
    code = f'''
import json,os,subprocess,shutil,time
from pathlib import Path
tag={tag!r}
assert (Path.home()/(tag+'.txt')).is_file(), 'Wrong tag'
assert {SITE['nodes'][tag]!r} in [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')], 'Wrong MAC'
def cmd(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=25);return p.stdout.strip() if p.returncode==0 else p.stderr.strip()
mem={{k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}}
mount='/mnt/datos' if tag=='L507_001' else '/data'
source=Path({config['native_source_root']!r})
if tag=='L507_001':source=Path(str(source).replace('/data/','/mnt/datos/',1))
result={{'tag':tag,'ip':{ip!r},'cpus':os.cpu_count(),'load':os.getloadavg(),'ram_available_gib':round(mem['MemAvailable']/1024**3,2),
 'ram_total_gib':round(mem['MemTotal']/1024**3,2),'mount':mount,'mounted':os.path.ismount(mount),'free_gib':round(shutil.disk_usage(mount).free/1024**3,2),
 'gpu':cmd(['nvidia-smi','--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits']),
 'gpu_processes':cmd(['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv,noheader,nounits']),
 'processes':cmd(['ps','-eo','user,pid,pcpu,pmem,comm','--sort=-pcpu']),
 'source_root':str(source),'source_exists':source.is_dir(),
 'docker':cmd(['docker','ps','--format','{{{{.ID}}}} {{{{.Names}}}} {{{{.Status}}}}']),
 'tools':{{name:shutil.which(name) for name in ['g++','python3','ReconstructMesh','InterfaceCOLMAP']}}}}
result['processes']='\\n'.join(result['processes'].splitlines()[:18])
result['files']=[str(p.relative_to(source)) for p in (source/'mvs').glob('*')]
result['chunk_files']=[str(p.relative_to(source)) for p in (source/'mvs/chunks/000').glob('*')]
result['chunk_metadata']={{str(p.relative_to(source)):json.loads(p.read_text()) for p in (source/'mvs/chunks/000').glob('*.json') if p.stat().st_size<50000}}
result['python_modules']=cmd(['python3','-c','import numpy,scipy,shapely; print(numpy.__version__, scipy.__version__, shapely.__version__)'])
print('DOWNLOAD_REPLY='+json.dumps(result))
'''
    return dict(block=block['block'], config=config, **remote(SITE, ip, code, timeout=100))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inspect','prepare','launch','status','watch','repair-filter'])
    args = parser.parse_args()
    if args.action == 'prepare':
        return prepare()
    if args.action == 'launch':
        return launch()
    if args.action == 'status':
        return status()
    if args.action == 'watch':
        return watch()
    if args.action == 'repair-filter':
        return repair()
    blocks = api('/api/blocks')
    assert len(blocks) == 15 and all(b['selection_current'] for b in blocks)
    directory = DIRECTORY
    directory.mkdir(exist_ok=True)
    results = {}
    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = {pool.submit(inspect, b): b for b in blocks}
        for future in as_completed(futures):
            b = futures[future]
            try:
                value = future.result()
                results[b['block']] = value
                print(b['block'], value['tag'], 'RAM', value['ram_available_gib'], 'load', value['load'], 'GPU', value['gpu'], 'source', value['source_exists'], flush=True)
            except Exception as exc:
                results[b['block']] = {'error':str(exc)}
                print(b['block'], 'ERROR', exc, flush=True)
            atomic_json(directory / 'inventory.json', {'observed_at': time.time(), 'blocks':results})


if __name__ == '__main__':
    main()
