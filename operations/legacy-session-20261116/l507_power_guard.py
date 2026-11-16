import pathlib,base64
exec(pathlib.Path('/tmp/opencode/l507_storage.py').read_text().split('\njobs=')[0])
BASE=pathlib.Path('/tmp/opencode/l507-review-power')
BASE.mkdir(exist_ok=True)
(BASE/'known_hosts').write_text(pathlib.Path('/tmp/opencode/l507-storage/known_hosts').read_text())
assignments=json.loads(pathlib.Path('/home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115/assignments.json').read_text())['assignments']
guard=r'''
import json,pathlib,subprocess,time,sys
p=pathlib.Path(sys.argv[1]);record=json.loads(p.read_text());root=pathlib.Path(record['root'])
start=time.monotonic();seen=False
while time.monotonic()-start<7*24*3600:
 try:
  s=json.loads((root/'reconstruction-full-status.json').read_text())
  seen=seen or s.get('pid')!=record['previous_worker_pid']
  if seen and s.get('state') in ('failed','awaiting_review','completed'):
   value=float(subprocess.check_output(['nvidia-smi','-i',record['uuid'],'--query-gpu=power.limit','--format=csv,noheader,nounits'],text=True).strip())
   if value==record['applied_w']:
    subprocess.run(['nvidia-smi','-i',record['uuid'],'-pl',str(record['previous_w'])],check=True)
    record['restoration']='restored'
   else:record['restoration']='operator_changed_limit'
   record['finished_at']=time.time();p.write_text(json.dumps(record,indent=2));break
 except (FileNotFoundError,json.JSONDecodeError):pass
 time.sleep(10)
'''
for a in assignments:
 CODE=r'''
import json,pathlib,subprocess,os,base64,time
a=ASSIGNMENT
assert (pathlib.Path('/home/utec_alumno')/(a['node_tag']+'.txt')).is_file()
assert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
uuid,limit,minimum=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,power.limit,power.min_limit','--format=csv,noheader,nounits'],text=True).strip().split(',')
uuid=uuid.strip();limit=float(limit);assert float(minimum)<=100<=limit
root=pathlib.Path(a['work_root']);old=json.loads((root/'reconstruction-full-status.json').read_text());assert old['state']=='failed'
record={'root':str(root),'uuid':uuid,'previous_w':limit,'applied_w':100,'previous_worker_pid':old['pid'],'started_at':time.time()}
receipt=pathlib.Path('/var/lib/lab-deploy')/('review-power-'+a['node_tag']+'-'+str(time.time_ns())+'.json')
receipt.write_text(json.dumps(record,indent=2))
script=receipt.with_suffix('.py');script.write_bytes(base64.b64decode(GUARD))
subprocess.run(['nvidia-smi','-i',uuid,'-pl','100'],check=True,capture_output=True)
with receipt.with_suffix('.log').open('a') as log:
 p=subprocess.Popen(['python3','-B','-u',str(script),str(receipt)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('RESULT='+json.dumps({'after':['power=100W'],'receipt':str(receipt),'guard_pid':p.pid,'previous_w':limit}))
'''.replace('ASSIGNMENT',repr(a)).replace('GUARD',repr(base64.b64encode(guard.encode()).decode()))
 print(work(a['node_tag'],a['ip'].split('.')[-1],a['mac']),flush=True)
