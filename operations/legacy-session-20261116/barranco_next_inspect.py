import json
from pathlib import Path
import subprocess
def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=60)
    return {'rc':p.returncode,'out':p.stdout[-7000:],'err':p.stderr[-500:]}
r={'tag':NODE_TAG}
if NODE_TAG=='L507_007':
    r['environments']=run(['du','-x','-B1','--max-depth=1','/home/utec/exit/envs'])
    r['downloads']=[]
    for home in Path('/home').iterdir():
        folder=home/'Descargas'
        if folder.is_dir():
            for p in folder.iterdir():
                r['downloads'].append({'path':str(p),'bytes':p.lstat().st_size,'directory':p.is_dir()})
    r['cache']=run(['du','-x','-B1','--max-depth=2','/home/mariel/.cache','/home/utec/.cache','/var/cache'])
if NODE_TAG=='L507_015':
    r['versions']=run(['dpkg-query','-W','-f','${Package} ${Version} ${Status}\n','fwupd','libfwupd2'])
    r['policy']=run(['apt-cache','policy','fwupd','libfwupd2'])
    r['simulation']=run(['apt-get','-s','install','--only-upgrade','fwupd','libfwupd2'])
print('ADMIN_REPLY='+json.dumps(r))
