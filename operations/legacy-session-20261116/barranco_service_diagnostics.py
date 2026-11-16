import json
import subprocess
def cmd(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=30)
    return {'rc':p.returncode,'out':p.stdout[-4500:],'err':p.stderr[-300:]}
result={'tag':NODE_TAG}
if NODE_TAG=='L507_008':
    result['reload']=cmd(['systemctl','daemon-reload'])
    result['need_reload']=cmd(['systemctl','show','docker.service','containerd.service','-p','NeedDaemonReload'])
if NODE_TAG=='L507_004':
    result['display_errors']=cmd(['journalctl','-b','--no-pager','-n','12','-u','gdm.service','-u','gpu-manager.service','-u','plymouth-quit.service','-o','cat'])
if NODE_TAG=='L507_015':
    result['firmware_errors']=cmd(['journalctl','-b','--no-pager','-n','12','-u','fwupd.service','-o','cat'])
print('ADMIN_REPLY='+json.dumps(result))
