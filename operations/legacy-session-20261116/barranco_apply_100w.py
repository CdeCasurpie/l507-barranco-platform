import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert NODE_TAG in {'L507_002','L507_004','L507_005','L507_007','L507_008',
                    'L507_009','L507_010','L507_011','L507_015','L507_021','L507_022'}
a=next(a for a in BINDINGS['assignments'] if a['node_tag']==NODE_TAG)
root=Path(a['work_root'])
assert json.loads((root/'assignment.json').read_text())==a
assert os.path.ismount('/data')
def capture(args):
    return subprocess.check_output(args,text=True,timeout=30).strip()
rows=capture(['nvidia-smi','--query-gpu=index,power.limit,power.min_limit,power.max_limit,temperature.gpu,fan.speed',
              '--format=csv,noheader,nounits']).splitlines()
assert len(rows)==1,'Expected exactly one GPU'
fields=[v.strip() for v in rows[0].split(',')]
index,old,minimum,maximum,temp,fan=fields
assert index=='0' and float(minimum)<=100<=float(maximum)
token=hashlib.sha256((str(root)+'full').encode()).hexdigest()[:12]
owned=capture(['docker','ps','-q','--filter','label=photogrammetry.run='+token]).splitlines()
owned_pids=set()
for container in owned:
    labels=json.loads(capture(['docker','inspect','--format','{{json .Config.Labels}}',container]))
    assert labels.get('photogrammetry.run')==token
    table=capture(['docker','top',container,'-eo','pid'])
    owned_pids.update(int(v.strip()) for v in table.splitlines()[1:] if v.strip().isdigit())
compute=capture(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'])
gpu_pids={int(v.strip()) for v in compute.splitlines() if v.strip().isdigit()}
assert gpu_pids<=owned_pids,'Other GPU workload present; no power change applied'
result=subprocess.run(['nvidia-smi','-i','0','-pl','100'],capture_output=True,text=True,timeout=30)
assert result.returncode==0,result.stderr
after=capture(['nvidia-smi','--query-gpu=power.limit,temperature.gpu,fan.speed','--format=csv,noheader,nounits'])
assert float(after.split(',')[0])==100
record={'tag':NODE_TAG,'block':a['block_id'],'root':str(root),'before_limit_w':float(old),
        'requested_limit_w':100,'after':after,'before_gpu_c':float(temp),'fan_before':fan,
        'thermal_guard_modified':False,'authorized_by_user':True,'at':time.time()}
path=root/('power-policy-100w-'+str(time.time_ns())+'.json')
path.write_text(json.dumps(record,indent=2)+'\n')
print('ADMIN_REPLY='+json.dumps(record))
