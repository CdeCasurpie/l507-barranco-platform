import base64
import json
import os
from pathlib import Path
import shlex
import sys

import pexpect

from .store import ROOT


class RemoteError(RuntimeError):
    pass


def credentials(site):
    path=str(Path(site['lab_tools']).expanduser())
    if path not in sys.path:sys.path.insert(0,path)
    try:
        import lab_config
        default_ssh,default_sudo=lab_config.DEFAULT_SSH_PASSWORD,lab_config.DEFAULT_SUDO_PASSWORD
    except ImportError:
        default_ssh=default_sudo=''
    password=os.environ.get('LAB_SSH_PASSWORD',default_ssh)
    sudo=os.environ.get('LAB_SUDO_PASSWORD',default_sudo)
    if not password:
        raise RemoteError('Configure the existing lab_config adapter or LAB_SSH_PASSWORD in the coordinator environment')
    return password,sudo


class SSH:
    def __init__(self,site,store):
        self.site,self.store=site,store

    def call(self,ip,action,payload,sudo=False,timeout=120):
        password,sudo_password=credentials(self.site)
        if sudo and not sudo_password:
            raise RemoteError('LAB_SUDO_PASSWORD/provider is required for deployment')
        code=(ROOT/'labdeploy/agent.py').read_text()
        encoded=base64.b64encode(json.dumps(payload).encode()).decode()
        args=['python3','-u','-c',code,action,encoded]
        if sudo:
            args=['sudo','-S','-p','LABCTL_SUDO:','--',*args]
        command=shlex.join(args)
        opts=['-o','ConnectTimeout=8','-o','StrictHostKeyChecking=accept-new',
              '-o','UserKnownHostsFile='+str(self.store.root/'known_hosts'),'-o','LogLevel=ERROR',
              '-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no','-o','NumberOfPasswordPrompts=1']
        child_env={k:v for k,v in os.environ.items() if k not in ['LAB_SSH_PASSWORD','LAB_SUDO_PASSWORD','HF_TOKEN','GH_TOKEN','GITHUB_TOKEN']}
        c=pexpect.spawn('ssh',[*opts,self.site['ssh_user']+'@'+ip,command],encoding='utf-8',timeout=timeout,echo=False,env=child_env)
        chunks=[]
        while True:
            event=c.expect(['[Pp]assword:','LABCTL_SUDO:','LABCTL_SOURCE_SECRET:',pexpect.EOF,pexpect.TIMEOUT])
            chunks.append(c.before.replace('\r',''))
            if event==0:c.sendline(password)
            elif event==1:c.sendline(sudo_password)
            elif event==2:c.sendline(password)
            elif event==3:
                c.close()
                break
            else:
                c.close(force=True)
                raise RemoteError('SSH timeout; a started remote deployment continues independently')
        output=''.join(chunks)
        marker='LABCTL_RESULT='
        index=output.rfind(marker)
        if index<0:
            raise RemoteError(f'No structured reply from {ip}: '+output[-1000:])
        reply=json.loads(output[index+len(marker):].splitlines()[0])
        if not reply['ok']:
            raise RemoteError(reply.get('kind','Error')+': '+reply['error'])
        return reply['result']
