"""Launch the three approved phone experiments; never mesh or align them."""
import base64
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
STATE = PROJECT / '.state/campaigns/barranco-inputs-20261115'
sys.path.insert(0, str(PROJECT / 'tools'))
from drive_download_campaign import remote


def launch(retry=False, assignments_path=None, sequential=False):
    global STATE
    facts_state = PROJECT / '.state/campaigns/barranco-inputs-20261115'
    if assignments_path is not None:
        STATE = Path(assignments_path).resolve().parent
    site = json.loads((PROJECT / 'config/site.json').read_text())
    # Verified host keys from the download campaign, including DHCP changes.
    import drive_download_campaign as transport
    import pexpect
    import shlex
    from labdeploy.ssh import credentials

    def call(ip, code):
        password, _ = credentials(site)
        child = pexpect.spawn('ssh', [
            '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(STATE / 'known_hosts'),
            site['ssh_user'] + '@' + ip,
            shlex.join(['python3', '-B', '-c', code])],
            encoding='utf-8', echo=False, timeout=180)
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
                raise RuntimeError('Launch acknowledgement uncertain; reconcile before retry')
        child.close()
        output = ''.join(chunks)
        marker = 'DOWNLOAD_REPLY='
        if marker not in output:
            raise RuntimeError(output[-2000:])
        return json.loads(output.rsplit(marker, 1)[1].splitlines()[0])

    files = {
        'phone_worker.py': Path('/home/exitoso/phone-run/phone_worker.py').read_text(),
        'reconstruction_worker.py': (PROJECT / 'tools/reconstruction_worker.py').read_text(),
        'dense_batches.py': (PROJECT / 'tools/dense_batches.py').read_text(),
        'campaign_post.py': (PROJECT / 'tools/campaign_post.py').read_text(),
    }
    files['review_worker.py'] = '''
import json,sys,hashlib
from pathlib import Path
from phone_worker import PhoneWorker
class ReviewWorker(PhoneWorker):
    def preflight(self):
        root=self.root
        for item in self.assignment['files']:
            p=root/item['relative_path']
            receipt=json.loads(p.with_name(p.name+'.fetch.json').read_text())
            if p.stat().st_size!=item['bytes'] or receipt['drive_file_id']!=item['id']:
                raise RuntimeError('Input receipt mismatch')
            h=hashlib.sha256()
            with p.open('rb') as f:
                for b in iter(lambda:f.read(4194304),b''):h.update(b)
            if h.hexdigest()!=receipt['sha256']:raise RuntimeError('Input checksum mismatch')
        super().preflight()
    def run(self):
        super().run()
        self.save(state='awaiting_review',stage='dense_complete',
                  review_required=True,alignment_authorized=False,mesh_authorized=False)
if __name__=='__main__':
    import fcntl,signal
    root=Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=ReviewWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
        signal.signal(signal.SIGINT,lambda *_:setattr(worker,'cancelled',True))
        try:worker.run()
        except BaseException as e:
            worker.save(state='failed',error=str(e))
            raise
'''
    assignments = json.loads((STATE / 'assignments.json').read_text())['assignments']
    results = {}
    for assignment in assignments:
        facts = json.loads((facts_state / (assignment['node_tag'] + '.json')).read_text())
        assert facts['download']['state'] == 'downloaded'
        cfg = json.loads(Path('/home/exitoso/phone-run/m3/006/config-full.json').read_text())
        root = assignment['work_root']
        exp = 'phone_native_2fps_' + assignment['variant'] + '_review_v1'
        cfg['experiment'] = {'name': exp, 'notes': 'Approved: stop after dense; manual review before alignment or mesh'}
        cfg['paths'] = {'raw_root': root + '/datasets/raw', 'output_root': root + '/outputs'}
        cfg['frames'].update(fps=2, resize=None, start=None, end=None)
        cfg['telemetry'] = {'enabled': False}
        # Separate camera estimation per image, avoiding falsely shared intrinsics.
        cfg['colmap']['single_camera_per_source'] = False
        if sequential:
            assert len(assignment['files']) == 1, 'Sequential profile requires a single reviewed clip'
            cfg['colmap']['single_camera_per_source'] = True
            cfg['colmap']['matcher'].update(methods=['sequential'], sequential_overlap=10,
                                            loop_detection=False, vocab_tree_path=None)
        for key in ('mesh', 'refine', 'clean', 'texture'):
            cfg['openmvs'][key]['enabled'] = False
        spec = json.loads(Path('/home/exitoso/phone-run/m3/006/reconstruction.json').read_text())
        spec.update(campaign_id=assignment['campaign_id'], node_tag=assignment['node_tag'],
                    block_id=assignment['block_id'], full_experiment=exp,
                    code_root=facts['active']['code_root'],
                    certified_data_root=facts['active']['data_root'])
        for name, key in [('reconstruction_worker.py', 'worker_sha256'),
                          ('dense_batches.py', 'dense_batches_sha256'),
                          ('campaign_post.py', 'post_sha256')]:
            spec[key] = hashlib.sha256(files[name].encode()).hexdigest()
        payload = {'assignment': assignment, 'config': cfg, 'spec': spec, 'files': files}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        code = '''
import base64,json,os,pathlib,subprocess,time,shutil
p=json.loads(base64.b64decode(ENCODED));a=p['assignment'];root=pathlib.Path(a['work_root'])
assert os.path.ismount('/data')
assert (pathlib.Path.home()/(a['node_tag']+'.txt')).is_file()
assert a['mac'] in [q.read_text().strip() for q in pathlib.Path('/sys/class/net').glob('*/address')]
assert json.loads((root/'assignment.json').read_text())==a
assert json.loads((root/'status.json').read_text())['state']=='downloaded'
status=root/'reconstruction-full-status.json'
if status.exists():
 s=json.loads(status.read_text());proc=pathlib.Path('/proc/'+str(s.get('pid'))+'/cmdline')
 if s.get('state')=='awaiting_review' or (proc.exists() and str(root).encode() in proc.read_bytes()):
  print('DOWNLOAD_REPLY='+json.dumps(s));raise SystemExit(0)
 if not RETRY or s.get('state')!='failed':
  raise RuntimeError('Existing attempt requires explicit review, not automatic restart')
 history=root/'attempt-history'/str(time.time_ns());history.mkdir(parents=True)
 shutil.copy2(status,history/status.name)
 if (root/'review-worker.log').exists():shutil.copy2(root/'review-worker.log',history/'review-worker.log')
for name,value in [('config-full.json',p['config']),('reconstruction.json',p['spec'])]:
 q=root/name
 if q.exists():assert json.loads(q.read_text())==value,'Conflicting configuration'
 else:q.write_text(json.dumps(value,indent=2))
for name,text in p['files'].items():
 q=root/name
 if q.exists():assert q.read_text()==text
 else:q.write_text(text)
for name in ['scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction','outputs']:(root/name).mkdir(parents=True,exist_ok=True)
# Docker startup is performed separately with authorized sudo before this call.
assert subprocess.run(['docker','info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
with (root/'review-worker.log').open('a') as log:
 process=subprocess.Popen(['python3','-B','-u',str(root/'review_worker.py'),str(root)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('DOWNLOAD_REPLY='+json.dumps({'state':'starting','pid':process.pid,'root':str(root),'experiment':p['spec']['full_experiment']}))
'''.replace('ENCODED', repr(encoded)).replace('RETRY',repr(retry))
        try:
            results[assignment['node_tag']] = call(assignment['ip'], code)
        except Exception as exc:
            results[assignment['node_tag']] = {'state': 'launch_error', 'error': str(exc)}
        print(assignment['node_tag'], json.dumps(results[assignment['node_tag']]), flush=True)
        (STATE / 'reconstruction-launch.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--retry', action='store_true')
    parser.add_argument('--assignments', type=Path)
    parser.add_argument('--sequential', action='store_true')
    args = parser.parse_args()
    launch(args.retry, args.assignments, args.sequential)
