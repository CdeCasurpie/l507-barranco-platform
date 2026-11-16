"""Prepare, start and inspect bounded native-resolution reconstruction jobs."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from drive_download_campaign import remote
sys.path.insert(0,str(PROJECT))
from labdeploy.store import atomic_json

CENTRAL=Path('/data/barranco/campaigns/barranco-full-v1')


def prepare(site,a,update=False,cpus=6,cpuset=None):
    if not 1<=cpus<=8:raise ValueError('CPU quota must be 1..8')
    if a.get('recovery_of'):
        raise ValueError('A validated recovery has its own seed/configuration; do not replace it with the generic preparation template')
    release=json.loads((PROJECT/'releases/l507-segmentation-v1.json').read_text())
    payload={'assignment':a,'release':release,
             'worker':(PROJECT/'tools/reconstruction_worker.py').read_text(),
             'post':(PROJECT/'tools/campaign_post.py').read_text(),
             'batches':(PROJECT/'tools/dense_batches.py').read_text()}
    b64=base64.b64encode(json.dumps(payload).encode()).decode()
    code=f'''
import base64,copy,json,os,hashlib,shutil
from pathlib import Path
p=json.loads(base64.b64decode({b64!r}));a=p['assignment'];release=p['release'];root=Path(a['work_root'])
if not os.path.ismount('/data') or root.stat().st_dev!=Path('/data').stat().st_dev:raise RuntimeError('Wrong data mount')
if not (Path.home()/(a['node_tag']+'.txt')).is_file():raise RuntimeError('Node tag mismatch')
if a['mac'] not in [x.read_text().strip().lower() for x in Path('/sys/class/net').glob('*/address')]:raise RuntimeError('Node MAC mismatch')
if json.loads((root/'assignment.json').read_text())!=a:raise RuntimeError('Download assignment differs')
if json.loads((root/'status.json').read_text())['state']!='downloaded':raise RuntimeError('Downloads incomplete')
meta=json.loads(Path('/var/lib/lab-deploy/active.json').read_text());data=Path(meta['data_root'])
template=json.loads((data/'outputs/cuadra-025/seg025_0_10s_combined_v1/run_manifest.json').read_text())['config']
allow_update={update!r}
if allow_update:
 for launch in root.glob('reconstruction-*-launch.json'):
  record=json.loads(launch.read_text());proc=Path('/proc/'+str(record.get('pid'))+'/cmdline')
  if proc.exists() and str(root).encode() in proc.read_bytes():raise RuntimeError('Cannot update a live execution bundle')
history=None
if (root/'reconstruction.json').exists():
 history=root/'preparation-history'/hashlib.sha256((root/'reconstruction.json').read_bytes()).hexdigest()[:16]
images={{role:{{'tag':im['tag'],'id':im['id']}} for role,im in zip(['reconstruction','segmentation'],release['images'])}}
spec={{'schema':1,'campaign_id':a['campaign_id'],'node_tag':a['node_tag'],'block_id':a['block_id'],
       'code_root':meta['code_root'],'certified_data_root':meta['data_root'],'pipeline_commit':release['git']['commit'],
       'images':images,'worker_sha256':hashlib.sha256(p['worker'].encode()).hexdigest(),
       'post_sha256':hashlib.sha256(p['post'].encode()).hexdigest(),
       'dense_batches_sha256':hashlib.sha256(p['batches'].encode()).hexdigest(),
       'dense_policy':{{'native_until_images':96,'max_batch_images':64,'core_images':40,'assembly':'same-frame concatenation; overlap redundancy retained'}},
       'resource_limits':{{'cpus':{cpus},'cpuset_cpus':{cpuset!r},'memory_gib':40,'additional_swap':0,'root_stop_gib':3,'data_stop_gib':50}}}}
def immutable(path,text):
 if path.exists() and path.read_text()!=text:
  if not allow_update:raise RuntimeError('Existing preparation differs: '+str(path))
  if path.name.startswith('config-'):raise RuntimeError('Changing a materialized configuration requires a new experiment revision')
  history.mkdir(parents=True,exist_ok=True);shutil.copy2(path,history/path.name)
  path.write_text(text);return
 if not path.exists():path.write_text(text)
for folder in ['scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction','outputs']:(root/folder).mkdir(parents=True,exist_ok=True)
immutable(root/'NODE_TAG.txt',a['node_tag']+'\\n')
immutable(root/'reconstruction.json',json.dumps(spec,indent=2)+'\\n')
immutable(root/'reconstruction_worker.py',p['worker'])
immutable(root/'campaign_post.py',p['post'])
immutable(root/'dense_batches.py',p['batches'])
for profile,name,end in [('full','barranco_4k_2fps_combined_v1',None),('diagnostic','barranco_4k_diagnostic_v1','00:00:10')]:
 cfg=copy.deepcopy(template);cfg['experiment']={{'name':name,'notes':'Native 3840x2160, full clips at 2fps; bounded supervised campaign'}}
 cfg['paths']={{'raw_root':str(root/'datasets/raw'),'output_root':str(root/'outputs')}}
 cfg['frames'].update(fps=2,start=None,end=end,resize=None,extra_args=['-threads','8'])
 cfg['telemetry']['enabled']=True;cfg['georef']['enabled']=False
 cfg['colmap']['camera_model']='SIMPLE_RADIAL'
 cfg['colmap']['feature_extractor']['max_image_size']=4096
 cfg['colmap']['undistort']['max_image_size']=-1
 cfg['colmap']['matcher']['methods']=['exhaustive']
 cfg['masking'].update(dilate_px=9,apply_to_dense=True)
 cfg['masking']['backends']['segformer'].update(model_id='/models/segformer',inference_size=2048,dilate_px=9)
 cfg['masking']['backends']['sam3'].update(checkpoint='/models/sam3/sam3.pt',tiles=[2,2],tile_overlap=.15,tile_prompts=['power line','utility pole'],dilate_px=9)
 cfg['openmvs']['densify'].update(resolution_level=0,number_views=4)
 cfg['openmvs']['densify']['extra_args'].update({{'max-threads':8,'max-resolution':100000,'min-resolution':640,'crop-to-roi':0,'estimate-roi':0,'tower-mode':0}})
 for stage in ['mesh','refine','clean','texture']:cfg['openmvs'][stage]['enabled']=False
 cfg['runtime'].update(verify_cache=True,multi_image=True,model_manifests={{'segformer':'/models/segformer/weights-manifest.json','sam3':'/models/sam3/weights-manifest.json'}})
 immutable(root/('config-'+profile+'.json'),json.dumps(cfg,indent=2)+'\\n')
print('DOWNLOAD_REPLY='+json.dumps({{'node':a['node_tag'],'block':a['block_id'],'state':'prepared','root':str(root),'spec':spec}}))
'''
    return remote(site,a['ip'],code,timeout=90)


def start(site,a,profile,preflight=False,retry=False):
    return remote(site,a['ip'],f'''
import fcntl,json,os,subprocess,shutil,time
from pathlib import Path
root=Path({a['work_root']!r});profile={profile!r};preflight={preflight!r}
if not os.path.ismount('/data'):raise RuntimeError('Data not mounted')
with (root/'reconstruction-launch.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 label='preflight' if preflight else profile
 status=root/('reconstruction-'+label+'-status.json');launch=root/('reconstruction-'+label+'-launch.json')
 if launch.exists():
  old=json.loads(launch.read_text());pid=old['pid'];proc=Path('/proc/'+str(pid)+'/cmdline')
  if proc.exists() and str(root).encode() in proc.read_bytes():
   print('DOWNLOAD_REPLY='+json.dumps({{'state':'already_running','pid':pid}}));raise SystemExit(0)
 if status.exists():
  state=json.loads(status.read_text())
  if state['state'] in ['completed','partial','prepared']:
   print('DOWNLOAD_REPLY='+json.dumps(state));raise SystemExit(0)
  if not {retry!r}:raise RuntimeError('Previous interrupted/failed job requires explicit --retry')
  history=root/'attempt-history'/(label+'-'+str(int(state.get('started_at',time.time())*1000)))
  history.mkdir(parents=True,exist_ok=True);shutil.copy2(status,history/status.name)
  if launch.exists():shutil.copy2(launch,history/launch.name)
 args=['python3','-B','-u',str(root/'reconstruction_worker.py'),str(root),'--profile',profile]
 if preflight:args.append('--preflight')
 with (root/('logs/reconstruction/'+label+'-worker.log')).open('a') as log:
  p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 record={{'pid':p.pid,'profile':label,'state':'starting','block_id':{a['block_id']!r},'node_tag':{a['node_tag']!r}}}
 launch.write_text(json.dumps(record))
 print('DOWNLOAD_REPLY='+json.dumps(record))
''')


def status(site,a,profile,preflight=False):
    label='preflight' if preflight else profile
    return remote(site,a['ip'],f'''
import json,time
from pathlib import Path
root=Path({a['work_root']!r});path=root/('reconstruction-'+{label!r}+'-status.json')
s=json.loads(path.read_text()) if path.exists() else {{'state':'not_started'}}
s.update(node_tag={a['node_tag']!r},block_id={a['block_id']!r})
pid=s.get('pid');proc=Path('/proc/'+str(pid)+'/cmdline')
s['worker_alive']=bool(pid and proc.exists() and str(root).encode() in proc.read_bytes())
if s.get('updated_at'):s['heartbeat_age_seconds']=round(time.time()-s['updated_at'],1)
print('DOWNLOAD_REPLY='+json.dumps(s))
''')


def cancel(site,a,profile):
    return remote(site,a['ip'],f'''
import json,os,signal
from pathlib import Path
root=Path({a['work_root']!r})
if not (Path.home()/({a['node_tag']!r}+'.txt')).is_file():raise RuntimeError('Tag mismatch')
if {a['mac']!r} not in [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')]:raise RuntimeError('MAC mismatch')
p=root/('reconstruction-'+{profile!r}+'-status.json')
s=json.loads(p.read_text()) if p.exists() else {{'state':'not_started'}}
if s['state'] in ['failed','completed','partial','not_started']:
 print('DOWNLOAD_REPLY='+json.dumps({{'state':'already_terminal','previous':s['state']}}));raise SystemExit(0)
pid=s.get('pid');proc=Path('/proc/'+str(pid)+'/cmdline')
if not proc.exists() or str(root).encode() not in proc.read_bytes() or b'reconstruction_worker.py' not in proc.read_bytes():
 raise RuntimeError('Worker is not live; reconcile its explicitly named container instead of signaling another process')
os.kill(pid,signal.SIGTERM)
print('DOWNLOAD_REPLY='+json.dumps({{'state':'cancellation_requested','pid':pid}}))
''')


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','start','status','cancel'])
    p.add_argument('--blocks',default='all');p.add_argument('--profile',choices=['diagnostic','full'],default='full')
    p.add_argument('--preflight',action='store_true');p.add_argument('--retry',action='store_true');p.add_argument('--update',action='store_true')
    p.add_argument('--cpus',type=int,default=6)
    p.add_argument('--cpuset')
    args=p.parse_args();site=json.loads((PROJECT/'config/site.json').read_text())
    assignments=json.loads((CENTRAL/'assignments.json').read_text())['assignments']
    overrides=json.loads((CENTRAL/'execution-overrides.json').read_text()) if (CENTRAL/'execution-overrides.json').exists() else {}
    assignments=[overrides.get(a['block_id'],a) for a in assignments]
    blocks=args.blocks.split(',')
    selected=[a for a in assignments if a['block_id']!='TODO' and (args.blocks=='all' or a['block_id'] in blocks)]
    if not selected:raise ValueError('No blocks selected')
    results={}
    def work(a):
        try:
            if args.action=='prepare':r=prepare(site,a,args.update,args.cpus,args.cpuset)
            elif args.action=='start':r=start(site,a,args.profile,args.preflight,args.retry)
            elif args.action=='cancel':r=cancel(site,a,args.profile)
            else:r=status(site,a,args.profile,args.preflight)
        except Exception as exc:r={'state':'error','error':str(exc),'block_id':a['block_id'],'node_tag':a['node_tag']}
        return a['block_id'],r
    with ThreadPoolExecutor(max_workers=5) as pool:
        for block,r in pool.map(work,selected):results[block]=r
    label='preflight' if args.preflight else args.profile
    atomic_json(CENTRAL/('reconstruction-'+args.action+'-'+label+'.json'),{'at':time.time(),'blocks':results})
    if args.action=='status':
        for block,r in sorted(results.items()):
            print(block,r['node_tag'],r['state'],r.get('stage',''),r.get('error',''),json.dumps(r.get('telemetry',{})))
    else:print(json.dumps(results,indent=2))
    if any(r.get('state')=='error' for r in results.values()):raise SystemExit(1)


if __name__=='__main__':main()
