"""Download only: one immutable block assignment, directly from public Drive."""
import fcntl
import hashlib
import http.cookiejar
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.parse
import urllib.request


def atomic(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024**2), b''):
            digest.update(chunk)
    return digest.hexdigest()


class Confirmation(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form' and attrs.get('id') == 'download-form':
            self.action = attrs.get('action')
        if tag == 'input' and attrs.get('name'):
            self.fields[attrs['name']] = attrs.get('value', '')


def open_download(file_id, offset):
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    url = 'https://drive.usercontent.google.com/download?' + urllib.parse.urlencode(
        {'id': file_id, 'export': 'download', 'confirm': 't'})
    for _ in range(4):
        headers = {'User-Agent': 'L507-Drive-Download/1.0', 'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        response = opener.open(urllib.request.Request(url, headers=headers), timeout=90)
        if 'text/html' not in response.headers.get('Content-Type', '').lower():
            return response
        page = response.read(1024**2).decode('utf-8', errors='replace')
        response.close()
        form = Confirmation()
        form.feed(page)
        if not form.action or urllib.parse.urlparse(form.action).hostname != 'drive.usercontent.google.com':
            raise RuntimeError('Drive returned a quota/login/error page instead of file content')
        url = form.action + '?' + urllib.parse.urlencode(form.fields)
    raise RuntimeError('Drive download confirmation exhausted')


class Worker:
    def __init__(self, root):
        self.root = root.resolve()
        self.assignment = json.loads((root / 'assignment.json').read_text())
        self.files = self.assignment['files']
        self.status = {'campaign_id': self.assignment['campaign_id'],
                       'block_id': self.assignment['block_id'],
                       'node_tag': self.assignment['node_tag'],
                       'state': 'starting', 'pid': os.getpid(), 'files': {}}
        old = root / 'status.json'
        if old.exists():
            self.status['files'] = json.loads(old.read_text()).get('files', {})

    def save(self, **values):
        self.status.update(values, updated_at=time.time())
        self.status['completed_files'] = sum(v.get('state') == 'verified' for v in self.status['files'].values())
        self.status['total_files'] = len(self.files)
        self.status['completed_bytes'] = sum(v.get('bytes', 0) for v in self.status['files'].values() if v.get('state') == 'verified')
        self.status['total_bytes'] = sum(f['bytes'] for f in self.files)
        atomic(self.root / 'status.json', self.status)

    def check(self):
        if not os.path.ismount('/data'):
            raise RuntimeError('/data is not mounted; refusing to write on root filesystem')
        if not (Path.home() / (self.assignment['node_tag'] + '.txt')).is_file():
            raise RuntimeError('Node tag mismatch')
        macs = [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')]
        if self.assignment['mac'].lower() not in macs:
            raise RuntimeError('Node MAC mismatch')
        if shutil.disk_usage(self.root).free < 30 * 1024**3:
            raise RuntimeError('Less than 30 GiB free on data volume')

    def verify(self, path, spec):
        if path.stat().st_size != spec['bytes']:
            raise RuntimeError('File size does not match Drive inventory')
        with path.open('rb') as stream:
            prefix = stream.read(8192)
        suffix = Path(spec['name']).suffix.lower()
        if suffix == '.mp4' and b'ftyp' not in prefix[:64]:
            raise RuntimeError('Not an MP4 container')
        if suffix == '.srt' and b'-->' not in prefix:
            raise RuntimeError('Not an SRT subtitle file')
        if suffix == '.png' and not prefix.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('Not a PNG image')
        digest = sha256(path)
        if spec.get('sha256') and spec['sha256'] != digest:
            raise RuntimeError('Known SHA256 mismatch')
        return digest

    def download(self, spec):
        target = self.root / spec['relative_path']
        if not target.resolve().is_relative_to(self.root) or target.is_symlink():
            raise RuntimeError('Unsafe download destination')
        target.parent.mkdir(parents=True, exist_ok=True)
        receipt = target.with_name(target.name + '.fetch.json')
        if target.exists():
            # This directory is dedicated to this immutable assignment. A crash
            # between rename and receipt publication can safely be recovered.
            digest = self.verify(target, spec)
            if receipt.exists():
                old = json.loads(receipt.read_text())
                if old['drive_file_id'] != spec['id'] or old['sha256'] != digest:
                    raise RuntimeError('Existing file receipt mismatch')
            atomic(receipt, {'drive_file_id': spec['id'], 'bytes': spec['bytes'], 'sha256': digest})
            return {'state': 'verified', 'bytes': spec['bytes'], 'sha256': digest, 'reused': True}
        # Reuse only an existing local file with a separately known content hash.
        if spec.get('sha256'):
            for candidate in spec.get('local_candidates', []):
                source = Path(candidate)
                if source.is_file() and source.stat().st_size == spec['bytes'] and sha256(source) == spec['sha256']:
                    shutil.copyfile(source, target)
                    digest = self.verify(target, spec)
                    atomic(receipt, {'drive_file_id': spec['id'], 'bytes': spec['bytes'], 'sha256': digest,
                                     'reused_local_source': str(source)})
                    return {'state': 'verified', 'bytes': spec['bytes'], 'sha256': digest, 'reused': True}
        partial = target.with_name(target.name + '.part')
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > spec['bytes']:
            raise RuntimeError('Partial exceeds expected file size')
        if offset < spec['bytes']:
            with open_download(spec['id'], offset) as response:
                if offset and response.status == 206:
                    if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise RuntimeError('Invalid resumed Content-Range')
                elif response.status == 200:
                    offset = 0  # Drive may ignore Range; restart this unpublished file.
                else:
                    raise RuntimeError(f'Unexpected HTTP response: {response.status}')
                total = offset
                last = 0
                with partial.open('ab' if offset else 'wb') as stream:
                    for chunk in iter(lambda: response.read(1024**2), b''):
                        total += len(chunk)
                        if total > spec['bytes']:
                            raise RuntimeError('Response exceeds inventoried file size')
                        stream.write(chunk)
                        if time.monotonic() - last >= 5:
                            self.check()
                            self.save(current_file=spec['name'], current_bytes=total, current_total=spec['bytes'])
                            last = time.monotonic()
                    stream.flush()
                    os.fsync(stream.fileno())
        digest = self.verify(partial, spec)
        os.replace(partial, target)
        atomic(receipt, {'drive_file_id': spec['id'], 'bytes': spec['bytes'], 'sha256': digest,
                         'verified_at': time.time()})
        return {'state': 'verified', 'bytes': spec['bytes'], 'sha256': digest}

    def run(self):
        self.check()
        self.save(state='downloading', error=None)
        failures = []
        for spec in self.files:
            for attempt in range(10):
                try:
                    self.check()
                    self.save(current_file=spec['name'], attempt=attempt + 1, error=None)
                    self.status['files'][spec['name']] = self.download(spec)
                    self.save(current_bytes=0, current_total=0)
                    print('VERIFIED', spec['name'], flush=True)
                    break
                except Exception as exc:
                    self.status['files'][spec['name']] = {'state': 'retrying', 'error': str(exc)}
                    self.save(error=str(exc))
                    print('RETRY', spec['name'], attempt + 1, str(exc), flush=True)
                    if attempt < 9:
                        time.sleep(min(30 * 2**attempt, 600))
                    else:
                        self.status['files'][spec['name']]['state'] = 'failed'
                        failures.append(spec['name'])
        self.save(state='failed' if failures else 'downloaded', current_file=None,
                  current_bytes=0, current_total=0, failed_files=failures,
                  error='Some files could not be downloaded' if failures else None)


if __name__ == '__main__':
    root = Path(sys.argv[1])
    with (root / 'download.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker = Worker(root)
        try:
            worker.run()
        except BaseException as exc:
            worker.save(state='failed', error=str(exc))
            raise
