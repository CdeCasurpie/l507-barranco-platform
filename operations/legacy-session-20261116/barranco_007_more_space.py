import json
import os
from pathlib import Path
import shutil
import subprocess

assert NODE_TAG=='L507_007'
before=shutil.disk_usage('/').free
result={'tag':NODE_TAG,'removed_installers':[],'old_snap_revisions':[]}
for home in Path('/home').iterdir():
    folder=home/'Descargas'
    if not folder.is_dir() or folder.is_symlink():
        continue
    for p in folder.glob('google-chrome-stable_current_amd64*.deb'):
        if p.is_symlink() or not p.is_file():
            continue
        check=subprocess.run(['dpkg-deb','-f',str(p),'Package'],capture_output=True,text=True,timeout=15)
        if check.returncode==0 and check.stdout.strip()=='google-chrome-stable':
            result['removed_installers'].append({'path':str(p),'bytes':p.stat().st_size})
            p.unlink()
process_text=''
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try: process_text+=p.read_bytes().decode(errors='replace')+'\n'
    except OSError: pass
env=dict(os.environ,LC_ALL='C')
listing=subprocess.run(['snap','list','--all'],capture_output=True,text=True,env=env,timeout=30)
result['listing']={'rc':listing.returncode,'out':listing.stdout,'err':listing.stderr}
for name,revision in [('code','278'),('firefox','8568'),('snapd-desktop-integration','387')]:
    lines=[l.split() for l in listing.stdout.splitlines()[1:]]
    if not any(len(l)>5 and l[0]==name and l[2]==revision and
               ('disabled' in l[-1] or 'desactivado' in l[-1]) for l in lines):
        continue
    if '/snap/'+name+'/'+revision in process_text:
        result['old_snap_revisions'].append({'name':name,'revision':revision,'skipped':'in use'})
        continue
    p=subprocess.run(['snap','remove',name,'--revision='+revision],capture_output=True,text=True,timeout=90)
    result['old_snap_revisions'].append({'name':name,'revision':revision,'rc':p.returncode,
                                        'out':p.stdout[-500:],'err':p.stderr[-500:]})
result['freed_gib']=round((shutil.disk_usage('/').free-before)/2**30,3)
result['root_free_gib']=round(shutil.disk_usage('/').free/2**30,2)
print('ADMIN_REPLY='+json.dumps(result))
