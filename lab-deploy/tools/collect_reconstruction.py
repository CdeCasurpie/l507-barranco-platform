"""Collect a finished full run, byte-verified and atomically published."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

import pexpect

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from drive_download_campaign import remote
sys.path.insert(0,str(PROJECT))
from labdeploy.ssh import credentials
from labdeploy.store import atomic_json

CENTRAL=Path('/data/barranco/campaigns/barranco-full-v1')


def snapshot(site,a,profile):
    return remote(site,a['ip'],f'''
import hashlib,json,os,shutil,time
from pathlib import Path
root=Path({a['work_root']!r});status=json.loads((root/('reconstruction-'+{profile!r}+'-status.json')).read_text())
if status['state'] not in ['completed','partial']:raise RuntimeError('Only validated finished runs can be collected')
proc=Path('/proc/'+str(status['pid'])+'/cmdline')
if proc.exists() and str(root).encode() in proc.read_bytes():raise RuntimeError('Worker is still exiting; retry collection shortly')
out=root/'outputs'/('cuadra-'+{a['block_id']!r})/status['experiment']
manifest=out/'snapshot.json'
if manifest.exists():
 value=json.loads(manifest.read_text())
else:
 for db in [out/'colmap/database.db',out/'colmap/database.snapshot.db']:
  wal=Path(str(db)+'-wal')
  if wal.exists() and wal.stat().st_size:raise RuntimeError('Nonempty source WAL')
 provenance=out/'provenance';provenance.mkdir(exist_ok=True)
 for name in ['assignment.json','reconstruction.json','config-'+{profile!r}+'.json','reconstruction-'+{profile!r}+'-status.json']:
  shutil.copy2(root/name,provenance/name)
 value={{'schema':1,'block_id':{a['block_id']!r},'node_tag':{a['node_tag']!r},'experiment':status['experiment'],'files':{{}},'symlinks':{{}}}}
 for path in sorted(out.rglob('*')):
  name=str(path.relative_to(out))
  if path.is_symlink():
   target=os.readlink(path)
   if Path(target).is_absolute() or not path.resolve().is_relative_to(out.resolve()):raise RuntimeError('Nonportable link: '+name)
   value['symlinks'][name]=target
  elif path.is_file():
   if path.name.endswith(('-shm','-wal')):continue
   before=path.stat();h=hashlib.sha256()
   with path.open('rb') as f:
    for chunk in iter(lambda:f.read(4*1024**2),b''):h.update(chunk)
   after=path.stat()
   if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Source changed during snapshot')
   value['files'][name]={{'bytes':after.st_size,'sha256':h.hexdigest()}}
 value['total_bytes']=sum(v['bytes'] for v in value['files'].values())
 manifest.write_text(json.dumps(value,indent=2)+'\\n')
print('DOWNLOAD_REPLY='+json.dumps({{'root':str(out),'snapshot':value}}))
''',timeout=600)


def collect(site,a,profile,include_intermediates=False):
    with (CENTRAL/'collection.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _collect(site,a,profile,include_intermediates)


def _collect(site,a,profile,include_intermediates=False):
    if not os.path.ismount('/data'):raise RuntimeError('Master data volume is not mounted')
    description=snapshot(site,a,profile);manifest=dict(description['snapshot'])
    omitted={};native_omitted={};batch_omitted={}
    if not include_intermediates:
        omitted={name:v for name,v in manifest['files'].items()
                 if Path(name).name.endswith('.dmap') or '.dmap.' in Path(name).name}
        # Keep one lossless XYZ/RGB/normal dense product centrally, not two copies
        # of the same points. Native visibility lists remain on the daughter.
        if 'mvs/scene_dense_scalar.ply' in manifest['files'] and 'mvs/scene_dense.ply' in manifest['files']:
            native_omitted={'mvs/scene_dense.ply':manifest['files']['mvs/scene_dense.ply']}
        batch_omitted={name:v for name,v in manifest['files'].items() if name.startswith('mvs/chunks/') and Path(name).name in ['scene_dense.ply','scene_dense_scalar.ply']}
        manifest['files']={name:v for name,v in manifest['files'].items() if name not in omitted and name not in native_omitted and name not in batch_omitted}
        manifest['total_bytes']=sum(v['bytes'] for v in manifest['files'].values())
    parent=Path('/data/barranco/results/barranco-full-v1')/a['block_id'];parent.mkdir(parents=True,exist_ok=True)
    final=parent/manifest['experiment'];pending=parent/('.'+manifest['experiment']+'.incoming')
    if final.exists():
        if not (final/'collection-receipt.json').exists():raise RuntimeError('Existing destination lacks a receipt')
        return final
    if shutil.disk_usage('/data').free<manifest['total_bytes']*1.1+50*1024**3:
        raise RuntimeError('Insufficient master storage plus 50 GiB reserve; retain source on daughter')
    pending.mkdir(exist_ok=True)
    password,_=credentials(site)
    ssh='ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o UserKnownHostsFile='+str(PROJECT/'.state/known_hosts')+' -o LogLevel=ERROR -o PreferredAuthentications=password -o PubkeyAuthentication=no'
    source=site['ssh_user']+'@'+a['ip']+':'+description['root']+'/'
    excludes=[] if include_intermediates else ['--exclude=*.dmap','--exclude=*.dmap.*']
    if native_omitted:excludes.append('--exclude=/mvs/scene_dense.ply')
    if batch_omitted:excludes.append('--exclude=/mvs/chunks/**/scene_dense*.ply')
    child=pexpect.spawn('rsync',['-a','--partial','--exclude=*-wal','--exclude=*-shm',*excludes,'--info=stats2','-e',ssh,source,str(pending)+'/'],encoding='utf-8',timeout=10,echo=False)
    try:
        while True:
            event=child.expect(['[Pp]assword:',pexpect.EOF,pexpect.TIMEOUT])
            if event==0:child.sendline(password)
            elif event==1:
                print(child.before,flush=True);break
            if shutil.disk_usage('/data').free<50*1024**3:raise RuntimeError('Master reserve reached during transfer')
        child.close()
        if child.exitstatus:raise RuntimeError('Rsync failed: '+str(child.exitstatus))
    except BaseException:
        child.close(force=True);raise
    for name,expected in manifest['files'].items():
        path=pending/name
        if not path.resolve().is_relative_to(pending.resolve()) or not path.is_file() or path.stat().st_size!=expected['bytes']:
            raise RuntimeError('Collected file mismatch: '+name)
        h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(4*1024**2),b''):h.update(chunk)
        if h.hexdigest()!=expected['sha256']:raise RuntimeError('Collected hash mismatch: '+name)
    for name,target in manifest['symlinks'].items():
        if os.readlink(pending/name)!=target:raise RuntimeError('Collected link mismatch')
    receipt={'at':time.time(),'node_tag':a['node_tag'],'block_id':a['block_id'],'bytes':manifest['total_bytes'],
             'files':len(manifest['files']),'source':description['root'],'all_sha256_verified':True,
             'collection_mode':'all_intermediates' if include_intermediates else 'products',
             'depth_maps_retained_on_daughter':{'files':len(omitted),'bytes':sum(v['bytes'] for v in omitted.values())},
             'native_dense_retained_on_daughter':native_omitted}
    receipt['batch_clouds_retained_on_daughter']={'files':len(batch_omitted),'bytes':sum(v['bytes'] for v in batch_omitted.values())}
    atomic_json(pending/'collection-manifest.json',dict(manifest,omitted_depth_maps=omitted,omitted_native_dense=native_omitted,omitted_batch_clouds=batch_omitted))
    atomic_json(pending/'collection-receipt.json',receipt)
    pending.rename(final)
    atomic_json(CENTRAL/('collection-'+a['block_id']+'-'+profile+'.json'),dict(receipt,destination=str(final)))
    print(json.dumps(receipt),flush=True)
    return final


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--block',required=True);p.add_argument('--profile',choices=['diagnostic','full'],default='full');p.add_argument('--include-intermediates',action='store_true');args=p.parse_args()
    site=json.loads((PROJECT/'config/site.json').read_text())
    a=next(a for a in json.loads((CENTRAL/'assignments.json').read_text())['assignments'] if a['block_id']==args.block)
    if (CENTRAL/'execution-overrides.json').exists():a=json.loads((CENTRAL/'execution-overrides.json').read_text()).get(args.block,a)
    print('COLLECTED',collect(site,a,args.profile,args.include_intermediates))
