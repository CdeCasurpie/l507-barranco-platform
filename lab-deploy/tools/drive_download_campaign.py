"""Coordinate direct-to-daughter downloads; no reconstruction is launched."""
import base64
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import shlex
import sys
import threading
import time

import pexpect

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from labdeploy.ssh import credentials
from labdeploy.store import atomic_json


def remote(site, ip, code, timeout=90):
    password, _ = credentials(site)
    child = pexpect.spawn('ssh', [
        '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'UserKnownHostsFile=' + str(PROJECT / '.state/known_hosts'),
        '-o', 'LogLevel=ERROR', '-o', 'PreferredAuthentications=password',
        '-o', 'PubkeyAuthentication=no', '-o', 'NumberOfPasswordPrompts=1',
        site['ssh_user'] + '@' + ip, shlex.join(['python3', '-B', '-c', code])],
        encoding='utf-8', timeout=timeout, echo=False)
    chunks = []
    while True:
        event = child.expect(['[Pp]assword:', pexpect.EOF, pexpect.TIMEOUT])
        chunks.append(child.before)
        if event == 0:
            child.sendline(password)
        elif event == 1:
            break
        else:
            child.close(force=True)
            raise RuntimeError('SSH timed out; remote worker may still be active')
    child.close()
    output = ''.join(chunks)
    if 'DOWNLOAD_REPLY=' not in output:
        raise RuntimeError(output[-1500:])
    return json.loads(output.rsplit('DOWNLOAD_REPLY=', 1)[-1].splitlines()[0])


def bootstrap(site, assignment, worker, start=True):
    payload = base64.b64encode(json.dumps(assignment).encode()).decode()
    source = base64.b64encode(worker.encode()).decode()
    code = f'''
import base64,json,os,subprocess,sys
from pathlib import Path
a=json.loads(base64.b64decode({payload!r}))
if not os.path.ismount('/data'): raise RuntimeError('/data is not mounted')
if not (Path.home()/(a['node_tag']+'.txt')).is_file(): raise RuntimeError('Tag mismatch')
macs=[p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')]
if a['mac'].lower() not in macs: raise RuntimeError('MAC mismatch')
root=Path(a['work_root']);root.mkdir(parents=True,exist_ok=True)
path=root/'assignment.json'
if path.exists() and json.loads(path.read_text())!=a: raise RuntimeError('Assignment already exists with different content')
if not path.exists(): path.write_text(json.dumps(a,indent=2)+'\\n')
if not {start!r}:
 print('DOWNLOAD_REPLY='+json.dumps({{'state':'assigned','block_id':a['block_id'],'node_tag':a['node_tag']}}));sys.exit(0)
status=root/'status.json'
if status.exists():
 s=json.loads(status.read_text())
 if s.get('state')=='downloaded':
  print('DOWNLOAD_REPLY='+json.dumps(s));sys.exit(0)
 pid=s.get('pid')
 if pid and Path('/proc/'+str(pid)+'/cmdline').exists() and str(root).encode() in Path('/proc/'+str(pid)+'/cmdline').read_bytes():
  print('DOWNLOAD_REPLY='+json.dumps(s));sys.exit(0)
script=root/'download_worker.py';script.write_bytes(base64.b64decode({source!r}))
with (root/'download.log').open('a') as log:
 p=subprocess.Popen(['python3','-B','-u',str(script),str(root)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('DOWNLOAD_REPLY='+json.dumps({{'state':'starting','pid':p.pid}}))
'''
    return remote(site, assignment['ip'], code)


def inspect(site, assignment):
    return remote(site, assignment['ip'], f'''
import json,os
from pathlib import Path
root=Path({assignment['work_root']!r})
p=root/'status.json'
s=json.loads(p.read_text()) if p.exists() else {{'state':'not_started'}}
pid=s.get('pid')
s['worker_alive']=bool(pid and Path('/proc/'+str(pid)+'/cmdline').exists() and str(root).encode() in Path('/proc/'+str(pid)+'/cmdline').read_bytes())
print('DOWNLOAD_REPLY='+json.dumps(s))
''')


def main(root, status_only=False, prepare_only=False):
    site = json.loads((PROJECT / 'config/site.json').read_text())
    campaign = json.loads((root / 'assignments.json').read_text())
    worker = (PROJECT / 'tools/drive_download_worker.py').read_text()
    summary = {'campaign_id': campaign['campaign_id'], 'state': 'running', 'nodes': {}}
    mutex = threading.Lock()

    def record(assignment, value):
        with mutex:
            summary['nodes'][assignment['node_tag']] = value
            summary['updated_at'] = time.time()
            atomic_json(root / 'status.json', summary)

    def work(assignment):
        tag = assignment['node_tag']
        try:
            if prepare_only:
                return tag, bootstrap(site, assignment, worker, start=False)
            if status_only:
                return tag, inspect(site, assignment)
            value = bootstrap(site, assignment, worker)
            record(assignment, value)
            errors = 0
            while value.get('state') not in ('downloaded', 'failed'):
                time.sleep(30)
                try:
                    value = inspect(site, assignment)
                    errors = 0
                    if not value.get('worker_alive') and value.get('state') not in ('downloaded', 'failed'):
                        value = bootstrap(site, assignment, worker)
                except Exception as exc:
                    errors += 1
                    print('POLL', tag, str(exc), flush=True)
                    if errors >= 20:
                        raise
                    continue
                record(assignment, value)
            print('FINISHED', tag, value['state'], flush=True)
            return tag, value
        except Exception as exc:
            value = {'state': 'coordinator_error', 'error': str(exc)}
            if not status_only and not prepare_only:
                record(assignment, value)
            print('ERROR', tag, str(exc), flush=True)
            return tag, value

    if not status_only and not prepare_only:
        summary['nodes'] = {a['node_tag']: {'state': 'queued', 'block_id': a['block_id']} for a in campaign['assignments']}
        atomic_json(root / 'status.json', summary)
    with ThreadPoolExecutor(max_workers=8 if status_only or prepare_only else campaign['max_parallel']) as pool:
        for tag, value in pool.map(work, campaign['assignments']):
            summary['nodes'][tag] = value
    expected = 'assigned' if prepare_only else 'downloaded'
    summary['state'] = expected if all(v.get('state') == expected for v in summary['nodes'].values()) else 'partial'
    if status_only or prepare_only:
        print(json.dumps(summary, indent=2))
    else:
        atomic_json(root / 'status.json', summary)


if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve()
    if '--prepare' in sys.argv:
        main(root, prepare_only=True)
    elif '--status' in sys.argv:
        main(root, status_only=True)
    else:
        with (root / 'coordinator.lock').open('a') as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main(root)
