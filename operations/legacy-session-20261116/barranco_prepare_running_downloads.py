import codecs
import concurrent.futures
import json
from pathlib import Path
import re
import time
import urllib.request

ROOT_ID='PRIVATE_DRIVE_ID'
CAMPAIGN='barranco-running-20261116'
STATE=Path('/home/exitoso/lab-deploy/.state/campaigns')/CAMPAIGN
mapping={'010':'007','011':'015','014':'021','015':'009','019':'004',
         '020':'005','021':'002','022':'011','023+016':'022','027':'008'}
ips={'002':'54','004':'44','005':'103','007':'71','008':'77','009':'78',
     '011':'65','015':'61','021':'80','022':'101'}
site=json.loads(Path('/home/exitoso/lab-deploy/config/site.json').read_text())
def listing(ident):
    url='https://drive.google.com/drive/folders/'+ident+'?hl=en'
    with urllib.request.urlopen(url,timeout=40) as response:
        html=response.read().decode()
    encoded=re.search(r"window\['_DRIVE_ivd'\] = '((?:\\.|[^'])*)'",html)[1]
    encoded=re.sub(r'\\x([0-9a-fA-F]{2})',lambda m:chr(int(m[1],16)),encoded)
    return json.loads(encoded.replace("\\'","'").replace(r'\/','/'))[0]
folders=[x for x in listing(ROOT_ID) if x[2].endswith('_running')]
assert {f[2][:-8] for f in folders}==set(mapping)
def inspect(folder):
    label=folder[2][:-8]
    block='016-023' if label=='023+016' else label
    number=mapping[label];tag='L507_'+number
    files=[]
    for item in listing(folder[0]):
        name=item[2];suffix=Path(name).suffix.lower()
        if suffix not in ('.mp4','.srt','.png'):
            continue
        assert isinstance(item[13],(int,str)) and int(item[13])>0
        sub='reference' if suffix=='.png' else 'datasets/raw/cuadra-'+block+('/drone' if name.startswith('DJI_') else '/phone')
        files.append({'id':item[0],'name':name,'bytes':int(item[13]),
                      'drive_modified_at_ms':item[10],'relative_path':sub+'/'+name})
    videos=[f for f in files if f['name'].lower().endswith('.mp4')]
    assert len(videos)==(8 if block=='016-023' else 1)
    # Terrestrial baseline first; each node downloads its own originals directly.
    files.sort(key=lambda f:(f['name'].startswith('DJI_'),f['name']))
    return {'schema':1,'campaign_id':CAMPAIGN,'block_id':block,'node_tag':tag,
            'mac':site['nodes'][tag],'ip':'10.100.41.'+ips[number],
            'work_root':'/data/photogrammetry/campaigns/'+CAMPAIGN+'/cuadra-'+block,
            'operation':'download_only','drive_folder_id':folder[0],
            'source_folder':folder[2],'files':files}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    assignments=list(pool.map(inspect,folders))
bundle={'schema':1,'campaign_id':CAMPAIGN,'operation':'download_only',
        'max_parallel':10,'created_at':time.time(),'assignments':assignments,
        'reconstruction_runtime':'pycolmap 3.11.1',
        'master_python':'/data/barranco/runtime/alignment311/bin/python',
        'reconstruction_authorized':False}
STATE.mkdir(parents=True,exist_ok=True)
path=STATE/'assignments.json'
if path.exists():
    old=json.loads(path.read_text())
    assert old['assignments']==assignments,'Do not overwrite differing assignments'
else:
    path.write_text(json.dumps(bundle,indent=2)+'\n')
for a in assignments:
    print(a['block_id'],a['node_tag'],len(a['files']),
          round(sum(f['bytes'] for f in a['files'])/2**30,3),'GiB')
print('STATE',STATE)
