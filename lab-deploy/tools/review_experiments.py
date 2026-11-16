"""Inspect approved review-only jobs and collect sparse results, never dense."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time

import pexpect

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from labdeploy.ssh import credentials

STATE = PROJECT / '.state/campaigns/barranco-inputs-20261115'


def remote(assignment, code, timeout=120):
    site = json.loads((PROJECT / 'config/site.json').read_text())
    password, _ = credentials(site)
    child = pexpect.spawn('ssh', [
        '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'UserKnownHostsFile=' + str(STATE / 'known_hosts'),
        site['ssh_user'] + '@' + assignment['ip'],
        shlex.join(['python3', '-B', '-c', code])],
        encoding='utf-8', echo=False, timeout=timeout)
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
            raise RuntimeError('Remote inspection timed out')
    child.close()
    output = ''.join(chunks)
    if 'REVIEW_REPLY=' not in output:
        raise RuntimeError(output[-1800:])
    return json.loads(output.rsplit('REVIEW_REPLY=', 1)[1].splitlines()[0])


def inspect(a):
    launch_path = STATE / 'reconstruction-launch.json'
    launches = json.loads(launch_path.read_text()) if launch_path.exists() else {}
    expected_pid = launches.get(a['node_tag'], {}).get('pid')
    code = '''
import pathlib,json
a=ASSIGNMENT;root=pathlib.Path(a['work_root'])
assert (pathlib.Path.home()/(a['node_tag']+'.txt')).is_file()
assert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
p=root/'reconstruction-full-status.json'
s=json.loads(p.read_text()) if p.exists() else {'state':'not_started'}
expected=EXPECTED_PID
pending=pathlib.Path('/proc/'+str(expected)+'/cmdline')
if expected and s.get('pid')!=expected and pending.exists() and str(root).encode() in pending.read_bytes():
 s={'state':'starting','pid':expected,'stage':'verifying_inputs'}
proc=pathlib.Path('/proc/'+str(s.get('pid'))+'/cmdline')
s['worker_alive']=proc.exists() and str(root).encode() in proc.read_bytes()
if not s['worker_alive'] and s.get('state') not in ('failed','awaiting_review','completed','not_started'):
 s['observed_error']='Worker missing; no automatic retry'
 s['state']='failed'
if s.get('state')=='failed':
 log=root/'review-worker.log'
 s['log_tail']=log.read_text()[-4000:] if log.exists() else ''
print('REVIEW_REPLY='+json.dumps(s))
'''.replace('ASSIGNMENT', repr(a)).replace('EXPECTED_PID',repr(expected_pid))
    return remote(a, code)


def collect_sparse(a, status):
    code = '''
import pathlib,json,hashlib
a=ASSIGNMENT;root=pathlib.Path(a['work_root'])
s=json.loads((root/'reconstruction-full-status.json').read_text())
assert s.get('sparse_ready') or s.get('state')=='awaiting_review' or 'sfm' in s.get('completed_stages',[])
out=root/'outputs'/('cuadra-'+a['block_id'])/s['experiment']
selected=(out/'colmap/best_model.txt').read_text().strip()
assert '/' not in selected and selected not in ('','.','..')
files={}
paths=[out/'colmap/best_model.txt',out/'colmap/sparse.ply']
paths+=list((out/'colmap/sparse').rglob('*.bin'))
paths+=list((out/'metrics').glob('*.json'))
paths+=list((out/'metrics').glob('*.csv'))
for name in ['config_resolved.yaml','image_info.json','run_manifest.json']:
 paths.append(out/name)
for p in paths:
 if not p.is_file():continue
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 files[str(p.relative_to(out))]={'bytes':p.stat().st_size,'sha256':h.hexdigest()}
assert any(name.startswith('colmap/sparse/'+selected+'/') for name in files)
print('REVIEW_REPLY='+json.dumps({'root':str(out),'selected':selected,'files':files,'state':s['state']}))
'''.replace('ASSIGNMENT', repr(a))
    snapshot = remote(a, code)
    destination = Path('/data/barranco/review/barranco-inputs-20261115') / (
        a['block_id'] + '-' + a['variant'])
    destination.mkdir(parents=True, exist_ok=True)
    filelist = STATE / (a['node_tag'] + '-sparse-files.txt')
    filelist.write_text('\n'.join(snapshot['files']) + '\n')
    password, _ = credentials(json.loads((PROJECT / 'config/site.json').read_text()))
    ssh = shlex.join(['ssh', '-o', 'StrictHostKeyChecking=yes',
                      '-o', 'UserKnownHostsFile=' + str(STATE / 'known_hosts')])
    child = pexpect.spawn('rsync', [
        '-a', '--partial', '--files-from=' + str(filelist), '-e', ssh,
        'utec_alumno@' + a['ip'] + ':' + snapshot['root'] + '/',
        str(destination) + '/'], encoding='utf-8', echo=False, timeout=600)
    while True:
        event = child.expect(['[Pp]assword:', pexpect.EOF, pexpect.TIMEOUT])
        if event == 0:
            child.sendline(password)
        elif event == 1:
            break
        else:
            child.close(force=True)
            raise RuntimeError('Sparse collection timed out')
    child.close()
    if child.exitstatus:
        raise RuntimeError('Sparse collection failed')
    for name, expected in snapshot['files'].items():
        p = destination / name
        h = hashlib.sha256()
        with p.open('rb') as stream:
            for chunk in iter(lambda: stream.read(4194304), b''):
                h.update(chunk)
        if p.stat().st_size != expected['bytes'] or h.hexdigest() != expected['sha256']:
            raise RuntimeError('Collected sparse checksum mismatch: ' + name)
    snapshot.update(destination=str(destination), node=a['node_tag'],
                    block=a['block_id'], variant=a['variant'], collected_at=time.time(),
                    dense_collected=False, manually_accepted=False)
    (destination / 'collection.json').write_text(json.dumps(snapshot, indent=2))
    return snapshot


def main(watch=False):
    assignments = json.loads((STATE / 'assignments.json').read_text())['assignments']
    collected = {}
    started = time.monotonic()
    while True:
        values = {}
        for a in assignments:
            tag = a['node_tag']
            try:
                s = inspect(a)
                sparse_available = s.get('sparse_ready') or 'sfm' in s.get('completed_stages', [])
                if sparse_available and (tag not in collected or s.get('state') == 'awaiting_review'):
                    collected[tag] = collect_sparse(a, s)
                values[tag] = s
                print(tag, s.get('state'), s.get('stage'), s.get('registered_images'),
                      s.get('error', ''), flush=True)
            except Exception as exc:
                values[tag] = {'state': 'inspection_error', 'error': str(exc)}
                print(tag, 'inspection_error', str(exc), flush=True)
        report = {'observed_at': time.time(), 'nodes': values, 'collections': collected}
        temp = STATE / 'review-status.json.new'
        temp.write_text(json.dumps(report, indent=2))
        temp.replace(STATE / 'review-status.json')
        terminal = all(v.get('state') in ('failed', 'awaiting_review') for v in values.values())
        if terminal or not watch:
            return
        if time.monotonic() - started > 7 * 24 * 3600:
            raise RuntimeError('Monitoring limit reached; daughter jobs not cancelled')
        time.sleep(60)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--state', type=Path)
    args = parser.parse_args()
    if args.state is not None:
        STATE = args.state.resolve()
    main(args.watch)
