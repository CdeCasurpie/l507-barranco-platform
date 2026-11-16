exec(open('/tmp/opencode/collect_cut020_review.py').read().split('code="import pathlib,json')[0])
import concurrent.futures
sys.path.insert(0,'/home/exitoso/lab-deploy/tools')
import barranco_status as monitor
campaign=Path('/home/exitoso/lab-deploy/.state/campaigns/barranco-running-20261116')
rows=monitor.assignments(campaign,site)
stamp=time.strftime('%Y%m%d-%H%M%S',time.gmtime())
receipt_dir=Path('/data/barranco/review/catalog-20261116-134343')
receipt_dir.mkdir(exist_ok=True)
manifest_source=Path('/tmp/opencode/barranco_sparse_manifest.py').read_text().replace("assert a['block_id'] in ('019','020','021')","").replace("assert s['stage']=='sparse_review' and 'sfm' in s['completed_stages']","assert 'sfm' in s['completed_stages']")
def collect(row):
 status=monitor.inspect(row,site,password)
 label=row['block_id']
 key=label.replace(' ','-').replace('/','-')
 dest=receipt_dir/key
 if (dest/'collection.json').exists():
  old=json.loads((dest/'collection.json').read_text())
  return {'label':label,'state':'awaiting_review','dataset':str(dest),'components':old['components']}
 if status.get('state')!='awaiting_review':
  return {'label':label,'state':status.get('state'),'stage':status.get('stage'),'dataset':None}
 original=dict(row)
 row=dict(row,block_id='026' if label=='026 parque' else ('006' if label.startswith('006') else label.split()[0]))
 localopts=list(opts)
 localopts[localopts.index('UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts')]='UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts /home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115/known_hosts'
 localopts[localopts.index('HostKeyAlias=192.0.2.58')]='HostKeyAlias='+row['ip']
 if row['node_tag']=='L507_005':localopts[localopts.index('HostKeyAlias='+row['ip'])]='HostKeyAlias=192.0.2.58'
 if row['node_tag']=='L507_022':localopts[localopts.index('HostKeyAlias='+row['ip'])]='HostKeyAlias=192.0.2.67'
 code="import pathlib,json\na="+repr(row)+"\nassert (pathlib.Path.home()/(a['node_tag']+'.txt')).is_file()\nassert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]\nBINDINGS={'assignments':[a]}\nNODE_TAG=a['node_tag']\n"+manifest_source
 m=run('ssh',localopts+[site['ssh_user']+'@'+row['ip'],shlex.join(['python3','-B','-c',code])],'ADMIN_REPLY=')
 key=label.replace(' ','-').replace('/','-')
 dest=receipt_dir/key;dest.mkdir(exist_ok=True)
 (receipt_dir/(key+'-manifest.json')).write_text(json.dumps(m,indent=2))
 fl=receipt_dir/(key+'-files.txt');fl.write_text('\n'.join(m['files'])+'\n')
 run('rsync',['-a','--partial','--files-from='+str(fl),'-e',shlex.join(['ssh']+localopts),site['ssh_user']+'@'+row['ip']+':'+m['root']+'/',str(dest)+'/'])
 for name,e in m['files'].items():
  p=dest/name;h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(4194304),b''):h.update(b)
  assert p.stat().st_size==e['bytes'] and h.hexdigest()==e['sha256']
 (dest/'collection.json').write_text(json.dumps(dict(m,sha256_verified=True,geometry_approved=False,dense_collected=False),indent=2))
 return {'label':label,'state':status['state'],'dataset':str(dest),'components':m['components']}
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 futures={pool.submit(collect,r):r for r in rows}
 for f in concurrent.futures.as_completed(futures):
  row=futures[f]
  try:result=f.result()
  except Exception as e:result={'label':row['block_id'],'state':'collection_failed','error':str(e),'dataset':None}
  results.append(result);print(json.dumps(result),flush=True)
for label,path in [
 ('006 vertical original','/data/barranco/review/barranco-inputs-20261115/006-single14nov-sequential'),
 ('006 reconectada — NO aprobada','/data/barranco/review/barranco-inputs-20261115/006-bridges-corrected')]:
 results.append({'label':label,'state':'local_preserved','dataset':path})
results.sort(key=lambda r:r['label'])
(receipt_dir/'catalog.json').write_text(json.dumps({'observed_at':time.time(),'datasets':results},indent=2))
print('CATALOG='+str(receipt_dir/'catalog.json'))
