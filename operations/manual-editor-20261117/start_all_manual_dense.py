"""Launch independent remote workers; never duplicate the existing 022 pilot."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
import time

labels=['006-horiz-s-m','010','011','014','015','016-023','019','020','021','026-parque','027']
root=Path('/tmp/opencode')/('dense-launch-batch-'+str(int(time.time())))
root.mkdir()
(root/'plan.json').write_text(json.dumps(dict(labels=labels,existing_022='/tmp/opencode/pilot022-dense-launch.json',
    no_retriangulation=['026-parque','027'],ba=False,mesh='OpenMVS ReconstructMesh Delaunay per chunk'),indent=2))
print('LAUNCH_BATCH',root,flush=True)
def launch(label):
    with (root/(label+'.log')).open('wb') as log:
        p=subprocess.run(['python3','-B','/tmp/opencode/start_pilot022_dense.py',label],
                         stdout=log,stderr=subprocess.STDOUT,timeout=600)
    result=dict(label=label,returncode=p.returncode,log=str(root/(label+'.log')))
    (root/(label+'.json')).write_text(json.dumps(result))
    return result
with ThreadPoolExecutor(max_workers=4) as pool:
    futures={pool.submit(launch,label):label for label in labels}
    for future in as_completed(futures):
        try:print(json.dumps(future.result()),flush=True)
        except Exception as error:print(json.dumps(dict(label=futures[future],error=str(error))),flush=True)
print('LAUNCH_ATTEMPTS_COMPLETE',root,flush=True)
