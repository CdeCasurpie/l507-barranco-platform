#!/usr/bin/env python3
"""Root-owned, demand-mounted data bridge; shares the deployment lease."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys


def run(args, check=True):
    return subprocess.run(args, capture_output=True, text=True, check=check, timeout=120)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2 or sys.argv[1] not in ['open','close','status']:
        raise RuntimeError('Usage: sudo lab-volume open|close|status')
    path=Path('/etc/lab-deploy/node.json')
    if path.stat().st_uid or path.stat().st_mode & 0o022:
        raise RuntimeError('Insecure node configuration')
    cfg=json.loads(path.read_text())
    links=json.loads(run(['ip','-j','link']).stdout)
    if cfg['mac'] not in [p.get('address') for p in links]:
        raise RuntimeError('Hardware MAC mismatch')
    import pwd
    if not (Path(pwd.getpwnam(cfg['user']).pw_dir)/(cfg['tag']+'.txt')).is_file():
        raise RuntimeError('Node tag mismatch')
    lock=Path('/var/lib/lab-deploy/deployment.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def mounted():
        if not os.path.ismount('/data'):
            return False
        item=json.loads(run(['findmnt','-J','--mountpoint','/data']).stdout)['filesystems'][0]
        if os.path.realpath(item['source'])!=os.path.realpath('/dev/disk/by-uuid/'+cfg['uuid']):
            raise RuntimeError('Wrong filesystem mounted')
        if (Path(cfg['data_root'])/'NODE_TAG.txt').read_text().strip()!=cfg['tag']:
            raise RuntimeError('Wrong volume tag')
        return True
    if sys.argv[1]=='open':
        if not mounted():
            if any(Path('/data').iterdir()):
                raise RuntimeError('Unmounted /data is not empty')
            run(['mount','-t','ext4','-o','nodev,nosuid','/dev/disk/by-uuid/'+cfg['uuid'],'/data'])
            if not mounted():
                raise RuntimeError('Mount verification failed')
        run(['systemctl','start','containerd.service','docker.service'])
        if run(['docker','info','--format','{{.DockerRootDir}}']).stdout.strip()!=cfg['data_root']+'/runtime/docker':
            raise RuntimeError('Wrong Docker storage root')
    elif sys.argv[1]=='close' and mounted():
        if run(['pgrep','-af',r'^docker (build|buildx)'],False).returncode==0:
            raise RuntimeError('Build is active')
        if run(['systemctl','is-active','--quiet','docker.service'],False).returncode==0 and run(['docker','ps','-q']).stdout.strip():
            raise RuntimeError('Containers are active')
        run(['systemctl','stop','docker.socket','docker.service','containerd.service'])
        run(['umount','/data'])
    print(json.dumps({'tag':cfg['tag'],'mounted':mounted()}))


if __name__=='__main__':
    main()
