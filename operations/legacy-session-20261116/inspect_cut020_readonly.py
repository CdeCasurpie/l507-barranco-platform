exec(open('/tmp/opencode/collect_cut020_review.py').read().split('code="import pathlib,json')[0])
code=r'''
import json,pathlib,sqlite3
a=ASSIGNMENT
assert (pathlib.Path.home()/(a['node_tag']+'.txt')).is_file()
assert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
result={}
for label,root in [('ensayo',pathlib.Path(a['work_root'])),('original',pathlib.Path('/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-020'))]:
 s=json.loads((root/'reconstruction-full-status.json').read_text())
 out=root/'outputs/cuadra-020'/s['experiment']
 col=out/'colmap'
 info={'state':s['state'],'files':[str(p.relative_to(col)) for p in col.iterdir() if p.is_file()]}
 for p in col.glob('*json'):
  if p.stat().st_size<20000:info[p.name]=json.loads(p.read_text())
 dbs=list(col.glob('*.db'))
 if dbs:
  db=sqlite3.connect(dbs[0].as_uri()+'?mode=ro',uri=True)
  names=dict(db.execute('select image_id,name from images'))
  times={i:((int(pathlib.Path(n).stem.rsplit('_',1)[1])-1)/2 if label=='original' else int(pathlib.Path(n).stem.split('_')[1])/1e6) for i,n in names.items()}
  edges=[]
  for pair,n in db.execute('select pair_id,rows from two_view_geometries where rows>0'):
   i,j=divmod(pair,2147483647)
   edges.append((times[i],times[j],n,i,j))
  loops=[e for e in edges if min(e[:2])<120 and max(e[:2])>=365]
  info['verified_start_end_pairs']=len(loops)
  info['strongest_start_end']=sorted(loops,key=lambda e:e[2],reverse=True)[:15]
  info['cut_pairs']=[e for e in edges if abs(e[0]-e[1])<=.51 and (200<=e[0]<=203 or 273<=e[0]<=275)]
  db.close()
 log=root/'logs/reconstruction/full/sfm.log'
 if log.exists():info['log_tail']=log.read_text()[-3000:]
 result[label]=info
print('INSPECT='+json.dumps(result))
'''.replace('ASSIGNMENT',repr(a))
r=run('ssh',opts+[site['ssh_user']+'@'+a['ip'],shlex.join(['python3','-B','-c',code])],'INSPECT=')
print(json.dumps(r,indent=2))
