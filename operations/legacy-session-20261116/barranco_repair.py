import json
from pathlib import Path
import subprocess
def run(args, timeout=90):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return {'rc':p.returncode,'out':p.stdout[-6500:],'err':p.stderr[-1000:]}
    except subprocess.TimeoutExpired:
        return {'error':'timeout; inspect before retry'}
r={'tag':NODE_TAG}
if NODE_TAG=='L507_007':
    r['snap_revisions']=run(['snap','list','--all'])
    r['sessions']=run(['loginctl','list-sessions','--no-legend'])
    r['active_processes']=run(['ps','-eo','pid,user,comm,pcpu','--sort=-pcpu'])
    r['active_processes']['out']='\n'.join(r['active_processes']['out'].splitlines()[:12])
if NODE_TAG=='L507_015':
    simulation=run(['apt-get','-s','install','--only-upgrade','fwupd','libfwupd2'])
    r['simulation']=simulation
    assert simulation['rc']==0
    installs=[l.split()[1] for l in simulation['out'].splitlines() if l.startswith('Inst ')]
    assert set(installs)<= {'fwupd','libfwupd2','libfwupd3'}
    assert not any(l.startswith('Remv ') for l in simulation['out'].splitlines())
    r['repair']=run(['apt-get','-y','--no-install-recommends','install','--only-upgrade','fwupd','libfwupd2'],180)
    if r['repair'].get('rc')==0:
        r['start']=run(['systemctl','start','fwupd.service'])
        r['version']=run(['fwupdmgr','--version'])
        r['service']=run(['systemctl','show','fwupd.service','-p','ActiveState','-p','SubState','-p','Result'])
        r['dpkg_audit']=run(['dpkg','--audit'])
print('ADMIN_REPLY='+json.dumps(r))
