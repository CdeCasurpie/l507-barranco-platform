"""Standalone remote agent: stdlib bootstrap, guarded background jobs, no secrets on disk."""
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request

MARKER = 'LABCTL_RESULT='
PACKAGES = {
    'docker-ce': '5:29.9.2-1~ubuntu.24.04~noble',
    'docker-ce-cli': '5:29.9.2-1~ubuntu.24.04~noble',
    'containerd.io': '2.4.2-3~ubuntu.24.04~noble',
    'docker-buildx-plugin': '0.38.1-1~ubuntu.24.04~noble',
    'nvidia-container-toolkit': '1.20.1-1',
    'nvidia-container-toolkit-base': '1.20.1-1',
    'libnvidia-container1': '1.20.1-1',
    'libnvidia-container-tools': '1.20.1-1',
}


class Blocked(RuntimeError):
    pass


def run(argv, check=True, timeout=1800, user=None, cwd=None, env=None):
    if user and os.geteuid() == 0:
        argv = ['runuser', '-u', user, '--', *argv]
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        if check:
            raise
        return subprocess.CompletedProcess(argv, 127, '', 'Command unavailable')
    if check and result.returncode:
        raise RuntimeError(f'{argv[0]} failed ({result.returncode}): {(result.stderr + result.stdout)[-3000:]}')
    return result


def atomic(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def safe_relative(value):
    p = Path(value)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise Blocked('Unsafe relative path: ' + value)
    return p


def guard(spec):
    tag = spec['tag']
    if not re.fullmatch(r'L507_\d{3}', tag):
        raise Blocked('Master/unknown tag is never an operational target')
    account = pwd.getpwnam(spec['user'])
    if account.pw_uid == 0:
        raise Blocked('SSH account must be unprivileged')
    tags = sorted(p.stem for p in Path(account.pw_dir).glob('L507_*.txt'))
    if tags != [tag]:
        raise Blocked(f'Expected one tag {tag}, observed {tags}')
    addresses = [x.get('address', '').lower() for x in json.loads(run(['ip', '-j', 'link']).stdout)]
    if spec['mac'].lower() not in addresses:
        raise Blocked('MAC mismatch')
    root = Path(spec['data_root'])
    if not root.is_absolute() or root.parent != Path('/data') or root.name.startswith('.'):
        raise Blocked('Data root must be an immediate project directory under /data')
    return account


def disks():
    raw = json.loads(run(['lsblk', '-bJ', '-o', 'PATH,SIZE,FSTYPE,UUID,MOUNTPOINTS,TYPE']).stdout)
    flat = []
    def walk(items):
        for item in items:
            flat.append(item)
            walk(item.get('children', []))
    walk(raw['blockdevices'])
    return [p for p in flat if p.get('type') == 'part' and p.get('fstype') == 'ext4'
            and 400 * 1024**3 < int(p.get('size') or 0) < 600 * 1024**3
            and '/' not in (p.get('mountpoints') or [])]


def probe(spec=None):
    if spec:
        account = guard(spec)
    else:
        account = pwd.getpwuid(os.getuid())
    tags = sorted(p.stem for p in Path(account.pw_dir).glob('L507_*.txt'))
    links = json.loads(run(['ip', '-j', 'link']).stdout)
    gpu = run(['nvidia-smi', '--query-gpu=name,driver_version,compute_cap', '--format=csv,noheader'], check=False)
    driver = gpu.stdout.strip().split(',')[1].strip() if gpu.returncode == 0 and ',' in gpu.stdout else None
    root = Path(spec['data_root'] if spec else '/data/photogrammetry')
    current = load(root / '.lab-deploy/current/meta.json') if os.path.ismount('/data') else None
    candidates = disks()
    return {'tags': tags, 'home':account.pw_dir, 'macs': [x.get('address') for x in links], 'driver': driver,
            'gpu': gpu.stdout.strip(), 'disks': candidates, 'mounted': os.path.ismount('/data'),
            'docker': bool(shutil.which('docker')), 'toolkit': bool(shutil.which('nvidia-ctk')),
            'current': current, 'data_free': shutil.disk_usage('/data').free if os.path.ismount('/data') else None,
            'root_free': shutil.disk_usage('/').free, 'controller': load('/var/lib/lab-deploy/status.json')}


def idle():
    if shutil.which('docker'):
        result = run(['docker', 'ps', '-q'], check=False, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            raise Blocked('Containers are running; finish workloads before deployment')
    gpu = run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], check=False, timeout=30)
    if gpu.returncode == 0 and gpu.stdout.strip():
        raise Blocked('GPU compute workload is active')
    if run(['pgrep', '-af', r'^docker (build|buildx)'], check=False).returncode == 0:
        raise Blocked('Docker build is active')


def own_dir(path, account, mode=0o700):
    path = Path(path)
    if path.is_symlink():
        raise Blocked('Unexpected directory symlink: ' + str(path))
    if path.exists() and path.stat().st_uid not in (0, account.pw_uid):
        raise Blocked('Directory belongs to another user: ' + str(path))
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    os.chown(path, account.pw_uid, account.pw_gid)
    return path


def user_parents(path,base,account):
    current=Path(base)
    for part in Path(path).relative_to(base).parts:
        current=current/part
        own_dir(current,account)


def backup_file(source, backup):
    source = Path(source)
    target = Path(backup) / source.relative_to('/')
    if not source.exists() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target)


def snapshot_host(backup,sources,packages=None):
    backup=Path(backup)
    receipt=backup/'snapshot.json'
    if receipt.exists():return
    if (backup/'packages.tsv').exists():
        atomic(receipt,{'legacy_unsealed':True,'note':'Earlier enrollment backup retained as-is; absence of a path was not recorded'})
        return
    present={str(source):Path(source).exists() for source in sources}
    for source in sources:backup_file(source,backup)
    text=packages if packages is not None else run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n']).stdout
    (backup/'packages.tsv').write_text(text)
    atomic(receipt,{'legacy_unsealed':False,'captured':time.time(),'present_before':present})


def mount_volume(spec):
    candidates = disks()
    if len(candidates) != 1:
        raise Blocked(f'Expected one data partition, found {len(candidates)}')
    disk = candidates[0]
    mount = Path('/data')
    if os.path.ismount(mount):
        source = json.loads(run(['findmnt', '-J', '--mountpoint', '/data']).stdout)['filesystems'][0]['source']
        if os.path.realpath(source) != os.path.realpath(disk['path']):
            raise Blocked('/data contains another filesystem')
        return disk
    if any(disk.get('mountpoints') or []):
        raise Blocked('Data partition is mounted elsewhere; inspect before moving it')
    if mount.exists() and any(mount.iterdir()):
        raise Blocked('Unmounted /data contains files; refusing to hide them')
    mount.mkdir(mode=0o755,exist_ok=True)
    run(['mount', '-t', 'ext4', '-o', 'ro,nodev,nosuid,noload', disk['path'], '/data'])
    try:
        allowed = {'lost+found', Path(spec['data_root']).name}
        extra = set(p.name for p in mount.iterdir()) - allowed
        marker = Path(spec['data_root']) / 'NODE_TAG.txt'
        if extra or (marker.parent.exists() and (not marker.exists() or marker.read_text().strip() != spec['tag'])):
            raise Blocked('Existing partition content needs manual enrollment; nothing was formatted')
    finally:
        run(['umount', '/data'])
    run(['mount', '-t', 'ext4', '-o', 'nodev,nosuid', disk['path'], '/data'])
    return disk


def prepare(spec, account, backup):
    disk = mount_volume(spec)
    root = Path(spec['data_root'])
    marker = root / 'NODE_TAG.txt'
    if root.exists() and (not marker.exists() or marker.read_text().strip() != spec['tag']):
        raise Blocked('Project directory has no matching enrollment marker')
    own_dir(root, account)
    if not marker.exists():
        marker.write_text(spec['tag'] + '\n')
        os.chown(marker, account.pw_uid, account.pw_gid)
    for relative in ['runtime', 'runtime/docker', 'runtime/containerd', '.lab-deploy', '.lab-deploy/cache', '.lab-deploy/releases']:
        own_dir(root / relative, account)
    if shutil.disk_usage('/data').free < 40 * 1024**3:
        raise Blocked('Need at least 40 GiB free for enrollment')
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    recover_policy(backup)
    snapshot_host(backup,['/etc/fstab','/etc/docker','/etc/containerd','/etc/nvidia-container-runtime',
                          '/etc/apt/sources.list.d','/etc/apt/keyrings','/usr/sbin/policy-rc.d'])
    # These conditions exist before APT can install/enable daemon units.
    for service in ['docker.service','docker.socket','containerd.service']:
        directory=Path('/etc/systemd/system')/(service+'.d')
        directory.mkdir(parents=True,exist_ok=True)
        (directory/'lab-deploy.conf').write_text('[Unit]\nConditionPathIsMountPoint=/data\nConditionPathExists='+str(root/'NODE_TAG.txt')+'\nConditionPathExists=/var/lib/lab-deploy/runtime-ready\n')
    cpath=Path('/etc/containerd/config.toml')
    if load('/etc/docker/daemon.json',{}).get('data-root')==str(root/'runtime/docker') and cpath.exists() and tomllib.loads(cpath.read_text()).get('root')==str(root/'runtime/containerd'):
        Path('/var/lib/lab-deploy/runtime-ready').touch()
    run(['systemctl','daemon-reload'])
    return disk


def recover_policy(backup, policy='/usr/sbin/policy-rc.d'):
    policy=Path(policy)
    if not policy.exists() or 'temporary lab-deploy service-start suppression' not in policy.read_text(errors='replace'):
        return
    saved=Path(backup)/'usr/sbin/policy-rc.d'
    if saved.exists():
        if 'temporary lab-deploy service-start suppression' in saved.read_text(errors='replace'):
            raise Blocked('Original service-start policy needs manual recovery from backup')
        shutil.copy2(saved,policy)
    else:
        policy.unlink()


@contextlib.contextmanager
def temporary_policy(path='/usr/sbin/policy-rc.d'):
    policy = Path(path)
    original = (policy.read_bytes(), policy.stat()) if policy.exists() else None
    if policy.is_symlink():
        raise Blocked('Inspect existing policy-rc.d symlink before installing packages')
    try:
        policy.write_text('#!/bin/sh\n# temporary lab-deploy service-start suppression\nexit 101\n')
        policy.chmod(0o755)
        yield
    finally:
        if original:
            policy.write_bytes(original[0])
            os.chmod(policy, original[1].st_mode & 0o777)
            os.chown(policy, original[1].st_uid, original[1].st_gid)
        elif policy.exists():
            policy.unlink()


def driver_packages():
    values = dict(line.split('\t', 1) for line in run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n']).stdout.splitlines())
    return {k: v for k, v in values.items() if ('nvidia' in k and 'container' not in k)
            or k.startswith(('linux-image', 'linux-modules', 'linux-headers'))}


def install_packages(spec):
    missing_docker = not shutil.which('docker')
    missing_toolkit = not shutil.which('nvidia-ctk')
    missing_pexpect = run(['python3', '-c', 'import pexpect'], check=False).returncode != 0
    missing_tools=[name for name in ['git','rsync'] if not shutil.which(name)]
    if not (missing_docker or missing_toolkit or missing_pexpect or missing_tools):
        return False
    root_free=shutil.disk_usage('/').free
    if root_free < 1536 * 1024**2:
        raise Blocked('Root filesystem has less than 1.5 GiB free; clean APT/journal caches before enrollment')
    os_info=dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if os_info.get('ID','').strip('"')!='ubuntu' or os_info.get('VERSION_ID','').strip('"')!='24.04':
        raise Blocked('The bootstrap package profile supports Ubuntu 24.04 only')
    before = driver_packages()
    keys = Path('/etc/apt/keyrings')
    keys.mkdir(exist_ok=True, mode=0o755)
    sources = Path('/etc/apt/sources.list.d')
    definitions = []
    if missing_docker:
        definitions.append(('lab-deploy-docker', 'https://download.docker.com/linux/ubuntu/gpg',
                            'https://download.docker.com/linux/ubuntu noble stable'))
    if missing_toolkit:
        definitions.append(('lab-deploy-nvidia', 'https://nvidia.github.io/libnvidia-container/gpgkey',
                            'https://nvidia.github.io/libnvidia-container/stable/deb/amd64 /'))
    for name, url, repository in definitions:
        key = keys / (name + '.asc')
        data = urllib.request.urlopen(url, timeout=60).read()
        if b'BEGIN PGP PUBLIC KEY BLOCK' not in data:
            raise RuntimeError('Invalid repository signing key')
        key.write_bytes(data)
        key.chmod(0o644)
        (sources / (name + '.list')).write_text(f'deb [arch=amd64 signed-by={key}] {repository}\n')
    wanted = [f'{name}={version}' for name, version in PACKAGES.items()
              if (missing_docker and name in ['docker-ce', 'docker-ce-cli', 'containerd.io', 'docker-buildx-plugin'])
              or (missing_toolkit and name not in ['docker-ce', 'docker-ce-cli', 'containerd.io', 'docker-buildx-plugin'])]
    if missing_pexpect:
        wanted.append('python3-pexpect')
    wanted.extend(missing_tools)
    apt_root = Path(spec['data_root']) / '.lab-deploy/apt'
    for directory in [apt_root/'lists', apt_root/'lists/partial', apt_root/'archives', apt_root/'archives/partial']:
        directory.mkdir(parents=True, exist_ok=True)
    try:
        import grp
        apt_group = grp.getgrnam('_apt').gr_gid
        for directory in [apt_root/'lists', apt_root/'lists/partial', apt_root/'archives', apt_root/'archives/partial']:
            os.chown(directory, -1, apt_group)
    except (KeyError, PermissionError):
        pass
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', TMPDIR=spec['data_root'] + '/.lab-deploy')
    base = ['apt-get', '-o', 'Dir::State::Lists='+str(apt_root/'lists'),
            '-o', 'Dir::Cache::archives='+str(apt_root/'archives'), '-o', 'DPkg::Lock::Timeout=180']
    def apt_call(args, allow_failure=False):
        for attempt in range(31):
            result = run(base + args, check=False, env=env)
            text = result.stderr + result.stdout
            lock = ('No se pudo obtener un bloqueo' in text or 'Could not get lock' in text
                    or 'Unable to acquire the dpkg frontend lock' in text or 'No se pudo bloquear' in text)
            if result.returncode == 0:
                return result
            if lock and attempt < 30:
                print('Waiting for another APT process to release its locks...', flush=True)
                time.sleep(20)
                continue
            if allow_failure:
                print('APT update reported errors; continuing with the indexes that were fetched', flush=True)
                print(text[-1200:], flush=True)
                return result
            raise RuntimeError(f'apt-get failed ({result.returncode}): {text[-3000:]}')
        raise RuntimeError('apt-get lock wait exhausted')
    with temporary_policy():
        apt_call(['update'], allow_failure=True)
        simulation = apt_call(['-s', 'install', '--no-install-recommends', *wanted]).stdout
        for line in simulation.splitlines():
            if line.startswith('Inst '):
                package = line.split()[1]
                if ('nvidia' in package and 'container' not in package) or package.startswith(('linux-image', 'linux-modules', 'linux-headers')):
                    raise Blocked('Package resolver proposes driver/kernel changes: ' + package)
        print(apt_call(['install', '-y', '--no-install-recommends', *wanted]).stdout, flush=True)
    if driver_packages() != before:
        raise RuntimeError('Unexpected driver/kernel package change')
    return True


def configure_runtime(spec, account, backup, disk):
    idle()
    root = Path(spec['data_root'])
    daemon_path = Path('/etc/docker/daemon.json')
    daemon = load(daemon_path, {})
    cpath = Path('/etc/containerd/config.toml')
    ctext = cpath.read_text() if cpath.exists() else 'version = 3\n'
    old_docker = daemon.get('data-root', '/var/lib/docker')
    old_containerd = tomllib.loads(ctext).get('root', '/var/lib/containerd')
    target_docker, target_containerd = str(root / 'runtime/docker'), str(root / 'runtime/containerd')
    needs_change = (old_docker != target_docker or old_containerd != target_containerd
                    or 'nvidia' not in daemon.get('runtimes', {}))
    if needs_change:
        observed=run(['docker','info','--format','{{.DockerRootDir}}'],check=False,timeout=30)
        if observed.returncode==0 and observed.stdout.strip()!=old_docker:
            raise Blocked('Docker uses a nonstandard configuration/storage root; inspect before migration')
        for source in [daemon_path, cpath]:
            backup_file(str(source), backup / 'runtime-before-change')
        run(['systemctl', 'stop', 'docker.socket', 'docker.service', 'containerd.service'], check=False)
        if run(['docker','info','--format','{{.DockerRootDir}}'],check=False,timeout=15).returncode==0:
            raise Blocked('Docker remains active outside managed systemd units; no cold copy was attempted')
        for old, target in [(old_docker, target_docker), (old_containerd, target_containerd)]:
            if old == target or not Path(old).exists() or not any(Path(old).iterdir()):
                continue
            required = int(run(['du', '-sb', old]).stdout.split()[0])
            if shutil.disk_usage('/data').free < required + 25 * 1024**3:
                raise Blocked('Insufficient migration space; original runtime remains untouched')
            run(['rsync', '-aHAX', '--numeric-ids', old + '/', target + '/'])
            check = run(['rsync', '-aHAXn', '--numeric-ids', '--checksum', '--itemize-changes', old + '/', target + '/'])
            if check.stdout.strip():
                raise RuntimeError('Cold runtime copy failed verification; configuration was not switched')
        daemon.update({'data-root': target_docker, 'log-driver': 'local', 'log-opts': {'max-size': '20m', 'max-file': '3'}})
        daemon_path.parent.mkdir(exist_ok=True)
        atomic(daemon_path, daemon, 0o644)
        if re.search(r'^root\s*=', ctext, re.M):
            ctext = re.sub(r'^root\s*=.*$', 'root = ' + json.dumps(target_containerd), ctext, count=1, flags=re.M)
        else:
            ctext = 'root = ' + json.dumps(target_containerd) + '\n' + ctext
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(ctext)
        run(['nvidia-ctk', 'runtime', 'configure', '--runtime=docker', '--config=' + str(daemon_path)])
    for service in ['docker.service', 'docker.socket', 'containerd.service']:
        directory = Path('/etc/systemd/system') / (service + '.d')
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'lab-deploy.conf').write_text('[Unit]\nConditionPathIsMountPoint=/data\nConditionPathExists=' + str(root / 'NODE_TAG.txt') + '\nConditionPathExists=/var/lib/lab-deploy/runtime-ready\n')
        run(['systemctl', 'disable', service])
    run(['usermod', '-aG', 'docker', account.pw_name])
    run(['systemctl', 'daemon-reload'])
    Path('/var/lib/lab-deploy/runtime-ready').touch()
    run(['systemctl', 'start', 'containerd.service', 'docker.service'])
    actual = run(['docker', 'info', '--format', '{{.DockerRootDir}}']).stdout.strip()
    if actual != target_docker:
        raise RuntimeError('Docker is not using the data volume')
    if tomllib.loads(cpath.read_text()).get('root') != target_containerd:
        raise RuntimeError('containerd is not using the data volume')
    bridge = Path('/usr/local/sbin/lab-volume')
    bridge_code = spec['volume_bridge']
    if not bridge.exists() or bridge.read_text() != bridge_code:
        bridge.write_text(bridge_code)
        bridge.chmod(0o755)
    atomic('/etc/lab-deploy/node.json', {k: spec[k] for k in ['tag', 'mac', 'user', 'data_root']}
           | {'device': disk['path'], 'uuid': disk['uuid']})
    return needs_change


def cache_file(path, artifact, cache, account):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != artifact['bytes'] or digest(path) != artifact['sha256']:
        return None
    target = cache / artifact['sha256']
    if target.exists() and (target.stat().st_size != artifact['bytes'] or digest(target) != artifact['sha256']):
        target.rename(cache / (artifact['sha256'] + '.corrupt-' + str(time.time_ns())))
    if not target.exists():
        os.link(path, target)
    return target


def source_command(source, argv, secret, known_hosts):
    import pexpect
    options = ['-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=accept-new',
               '-o', 'UserKnownHostsFile=' + str(known_hosts), '-o', 'LogLevel=ERROR',
               '-o', 'PreferredAuthentications=password', '-o', 'PubkeyAuthentication=no', '-o', 'NumberOfPasswordPrompts=1']
    command = ['ssh', *options, source['user'] + '@' + source['ip'], shlex.join(argv)]
    if argv[0] == 'RSYNC':
        command = ['rsync', '-a', '--partial', '--append-verify', '--info=stats2', '-e', shlex.join(['ssh', *options]), *argv[1:]]
    c = pexpect.spawn(command[0], command[1:], encoding='utf-8', timeout=3600, echo=False)
    output = []
    while True:
        event = c.expect(['[Pp]assword:', pexpect.EOF, pexpect.TIMEOUT])
        output.append(c.before.replace('\r', ''))
        if event == 0:
            c.sendline(secret)
        elif event == 1:
            c.close()
            if c.exitstatus:
                raise RuntimeError('Source transfer failed: ' + ''.join(output)[-1500:])
            return ''.join(output)
        else:
            c.close(force=True)
            raise RuntimeError('Source transfer timeout; partial file retained')


def fetch(artifact, spec, source, secret, account):
    root = Path(spec['data_root'])
    cache = root / '.lab-deploy/cache'
    target = cache / artifact['sha256']
    if cache_file(target, artifact, cache, account):
        return target, False
    for relative in artifact.get('local_candidates', []):
        candidate = root / safe_relative(relative)
        if not candidate.resolve().is_relative_to(root.resolve()):
            continue
        if cache_file(candidate, artifact, cache, account):
            return target, False
    if not source:
        raise Blocked('No source available for ' + artifact['name'])
    code = "import json,pathlib,subprocess,os; " + \
           f"assert pathlib.Path({source['home']!r}, {source['tag']!r}+'.txt').is_file(); " + \
           f"assert {source['mac']!r} in [x.get('address') for x in json.loads(subprocess.check_output(['ip','-j','link'],text=True))]; " + \
           f"assert os.path.ismount('/data'); r=pathlib.Path({spec['data_root']!r}); " + \
           f"paths=[r/'.lab-deploy/cache'/{artifact['sha256']!r}]+[r/p for p in {artifact['source_paths'].get(source['tag'], artifact.get('local_candidates', []))!r}]; " + \
           "p=next((p for p in paths if p.is_file()),None); assert p is not None,'Artifact missing on source'; print(str(p))"
    output = source_command(source, ['python3', '-c', code], secret, root / '.lab-deploy/source-known-hosts')
    remote_path = output.strip().splitlines()[-1]
    if not remote_path.startswith(spec['data_root'] + '/'):
        raise Blocked('Source returned an invalid artifact path')
    partial = cache / (artifact['sha256'] + '.part')
    if partial.is_symlink():
        partial.rename(cache/(artifact['sha256']+'.corrupt-link-'+str(time.time_ns())))
    if partial.exists() and partial.stat().st_size>=artifact['bytes']:
        if partial.stat().st_size==artifact['bytes'] and digest(partial)==artifact['sha256']:
            partial.replace(target)
            os.chown(target,account.pw_uid,account.pw_gid)
            return target,False
        partial.rename(cache/(artifact['sha256']+'.corrupt-part-'+str(time.time_ns())))
    if shutil.disk_usage('/data').free<artifact['bytes']+20*1024**3:
        raise Blocked('Insufficient free space for artifact and 20 GiB reserve')
    print('TRANSFER', artifact['name'], 'bytes', artifact['bytes'], flush=True)
    source_command(source, ['RSYNC', source['user'] + '@' + source['ip'] + ':' + remote_path, str(partial)],
                   secret, root / '.lab-deploy/source-known-hosts')
    if partial.stat().st_size != artifact['bytes'] or digest(partial) != artifact['sha256']:
        raise RuntimeError('Checksum mismatch; untrusted partial retained: ' + artifact['name'])
    partial.replace(target)
    os.chown(target, account.pw_uid, account.pw_gid)
    return target, True


def image_ok(image):
    result = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']], check=False, timeout=30)
    return result.returncode == 0 and result.stdout.strip() == image['id']


def image_namespace(release,previous):
    known={image['tag']:image['id'] for record in previous for image in record.get('images',[])}
    for image in release['images']:
        if image['tag'] in known and known[image['tag']]!=image['id']:
            raise Blocked('Image tag belongs to a previous release; use a new versioned tag: '+image['tag'])


def code_ok(path, release, account):
    path = Path(path)
    if not (path / '.git').exists():
        return False
    head = run(['git', '-C', str(path), 'rev-parse', 'HEAD'], user=account.pw_name, check=False)
    status = run(['git', '-C', str(path), 'status', '--porcelain'], user=account.pw_name, check=False)
    return head.returncode == status.returncode == 0 and head.stdout.strip() == release['git']['commit'] and not status.stdout.strip()


def healthy(meta, spec, release, account):
    if not meta or meta.get('release_digest') != spec['release_digest']:
        return False
    if not code_ok(meta['code_root'], release, account) or not all(image_ok(image) for image in release['images']):
        return False
    env_path = Path(meta['env_file'])
    if not env_path.exists() or digest(env_path) != meta.get('env_sha256'):
        return False
    driver = run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'], check=False).stdout.strip()
    if driver != meta.get('driver'):
        return False
    daemon=load('/etc/docker/daemon.json',{})
    cpath=Path('/etc/containerd/config.toml')
    if daemon.get('data-root')!=spec['data_root']+'/runtime/docker' or not cpath.exists():
        return False
    if tomllib.loads(cpath.read_text()).get('root')!=spec['data_root']+'/runtime/containerd':
        return False
    for artifact in release['artifacts']:
        if artifact.get('target'):
            path = Path(meta['data_root']) / safe_relative(artifact['target'])
            if not path.is_file() or path.stat().st_size != artifact['bytes'] or digest(path) != artifact['sha256']:
                return False
    return True


def legacy(spec, release, account):
    if release['name']!='l507-segmentation-v1':
        return None
    root = Path(spec['data_root'])
    if not all(image_ok(image) for image in release['images']):
        return None
    for path in [root / 'repo', root / 'segmentation-repo']:
        if not code_ok(path, release, account):
            continue
        for env in [root / 'node.env', root / 'node-segmentation.env']:
            if not env.exists():
                continue
            text = env.read_text()
            if spec['tag'] not in text or not all(image['id'] in text for image in release['images']):
                continue
            values={}
            for line in text.splitlines():
                words=shlex.split(line,comments=True)
                if len(words)==1 and '=' in words[0]:
                    key,value=words[0].split('=',1)
                    values[key]=value
            if any(values.get(key)!=str(value) for key,value in release['environment'].items()):
                continue
            meta = {'code_root': str(path), 'env_file': str(env), 'data_root': str(root),
                    'env_sha256': digest(env), 'driver': run(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader']).stdout.strip(),
                    'release_digest': spec['release_digest'], 'adopted': True}
            old = load(root / 'logs/setup014/final-qc.json')
            if old and old.get('driver_after') == meta['driver'] and healthy(meta, spec, release, account):
                return meta
    return None


def activate(root, directory, meta):
    atomic(directory / 'meta.json', meta, 0o644)
    current = root / '.lab-deploy/current'
    temporary = root / '.lab-deploy/current.new'
    if temporary.is_symlink():
        temporary.unlink()
    if temporary.exists() or (current.exists() and not current.is_symlink()):
        raise Blocked('Unexpected current-release path; preserving existing files')
    temporary.symlink_to(directory, target_is_directory=True)
    os.replace(temporary, current)


def deploy(spec, release, source, secret, status, account):
    root = Path(spec['data_root'])
    state_root = Path('/var/lib/lab-deploy')
    backup = state_root / 'backups/initial'
    previous_driver = probe(spec)['driver']
    if not previous_driver:
        raise Blocked('NVIDIA driver is not operational; no automatic driver replacement')
    idle()
    def phase(name):
        status.update(phase=name, updated=time.time())
        atomic(state_root / 'status.json', status, 0o644)
        print('PHASE', name, flush=True)
    phase('prepare-volume')
    disk = prepare(spec, account, backup)
    directory = root / '.lab-deploy/releases' / release['name']
    own_dir(directory, account)
    current = load(root / '.lab-deploy/current/meta.json')
    recorded=load(directory/'release.json')
    if recorded and recorded!=release:
        raise Blocked('Release name is immutable; use a new name for a changed manifest')
    image_namespace(release,[load(p,{}) for p in (root/'.lab-deploy/releases').glob('*/release.json')])
    if healthy(current, spec, release, account):
        atomic('/var/lib/lab-deploy/active.json',current,0o644)
        status.update(changed=False, result=current)
        return
    phase('packages')
    install_packages(spec)
    phase('runtime')
    configure_runtime(spec, account, backup, disk)
    adopted = legacy(spec, release, account)
    if adopted:
        adopted.update(release=release['name'], validated=time.time())
        activate(root, directory, adopted)
        atomic('/var/lib/lab-deploy/active.json',adopted,0o644)
        atomic(directory / 'release.json', release, 0o644)
        status.update(changed=False, adopted=True, result=adopted)
        return
    phase('artifacts')
    data = own_dir(directory / 'data', account)
    for folder in ['models','datasets/raw','outputs','scratch','logs']:
        user_parents(data/folder,data,account)
    marker=data/'NODE_TAG.txt'
    marker.write_text(spec['tag']+'\n')
    os.chown(marker,account.pw_uid,account.pw_gid)
    for image in release['images']:
        if image_ok(image):
            continue
        artifact = next(a for a in release['artifacts'] if a['name'] == image['archive'])
        cached, _ = fetch(artifact, spec, source, secret, account)
        if shutil.disk_usage('/data').free<image.get('unpacked_bytes',20*1024**3)+20*1024**3:
            raise Blocked('Insufficient image expansion space plus 20 GiB reserve')
        print(run(['docker', 'image', 'load', '-i', str(cached)]).stdout, flush=True)
        if not image_ok(image):
            raise RuntimeError('Loaded image ID does not match manifest')
    for artifact in release['artifacts']:
        if not artifact.get('target'):
            continue
        cached, _ = fetch(artifact, spec, source, secret, account)
        destination = data / safe_relative(artifact['target'])
        if not destination.resolve().is_relative_to(data.resolve()):
            raise Blocked('Candidate artifact path resolves outside release data')
        user_parents(destination.parent,data,account)
        if destination.exists():
            if digest(destination) != artifact['sha256']:
                raise Blocked('Candidate file was modified; choose a new release name: ' + str(destination))
        else:
            os.link(cached, destination)
    phase('code')
    code = directory / 'code'
    if code.is_symlink():
        raise Blocked('Candidate checkout cannot be a symlink')
    if code.exists():
        if not code_ok(code, release, account):
            raise Blocked('Candidate checkout differs; no reset/overwrite will be performed')
    else:
        run(['git','clone','--no-checkout',release['git']['url'],str(code)], user=account.pw_name)
        run(['git','-C',str(code),'checkout','--detach',release['git']['commit']], user=account.pw_name)
    environment = {k:str(v).replace('${DATA_ROOT}',str(data)).replace('${NODE_TAG}',spec['tag']) for k,v in release['environment'].items()}
    environment.update(PG_DATA_ROOT=str(data), PG_NODE_TAG=spec['tag'], PG_REQUIRE_MOUNT='/data')
    env_path = directory / 'node.env'
    env_path.write_text(''.join(k + '=' + shlex.quote(str(v)) + '\n' for k, v in sorted(environment.items())))
    env_path.chmod(0o600)
    os.chown(env_path, account.pw_uid, account.pw_gid)
    phase('verify')
    env = dict(os.environ, **environment)
    env.update(HOME=account.pw_dir,PG_ENV_FILE=str(env_path))
    checks = []
    for index, argv in enumerate(release['verify']['commands']):
        print('VERIFY', index + 1, shlex.join(argv), flush=True)
        result = run(argv, user=account.pw_name, cwd=code, env=env, timeout=1800)
        (directory / f'verify-{index+1}.log').write_text(result.stdout + result.stderr)
        checks.append({'command': argv, 'returncode': result.returncode})
    metrics = load(data / safe_relative(release['verify']['metrics'])) if release['verify'].get('metrics') else {}
    expectations=release['verify'].get('expectations',[
        {'field':'frames_total','equals':20}, {'field':'sparse.registered_images','equals':20},
        {'field':'dense.openmvs_points','min':1}, {'field':'environment.node_tag','equals':'${NODE_TAG}'}
    ] if release['verify'].get('metrics') else [])
    validate_metrics(metrics,expectations,spec['tag'])
    if run(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader']).stdout.strip() != previous_driver:
        raise RuntimeError('Driver changed during deployment')
    meta = {'release': release['name'], 'release_digest': spec['release_digest'], 'code_root': str(code),
            'env_file': str(env_path), 'env_sha256': digest(env_path), 'data_root': str(data),
            'driver': previous_driver, 'validated': time.time(), 'checks': checks,
            'smoke': metrics, 'adopted':False}
    phase('activate')
    atomic(directory / 'release.json', release, 0o644)
    activate(root, directory, meta)
    atomic('/var/lib/lab-deploy/active.json',meta,0o644)
    status.update(changed=True, result=meta)


def validate_metrics(metrics,expectations,tag):
    for expected in expectations:
        value=metrics
        for part in expected['field'].split('.'):
            if not isinstance(value,dict) or part not in value:
                raise RuntimeError('Missing validation metric: '+expected['field'])
            value=value[part]
        if 'equals' in expected:
            target=expected['equals']
            if isinstance(target,str):target=target.replace('${NODE_TAG}',tag)
            if value!=target:raise RuntimeError('Unexpected validation metric: '+expected['field'])
        if 'min' in expected and (not isinstance(value,(float,int)) or value<expected['min']):
            raise RuntimeError('Validation metric below minimum: '+expected['field'])


def start_job(spec, release, source):
    account = guard(spec)
    if os.geteuid() != 0:
        raise Blocked('Deployment requires sudo')
    root = Path('/var/lib/lab-deploy')
    root.mkdir(mode=0o755, exist_ok=True)
    root.chmod(0o755)
    lock = (root / 'deployment.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise Blocked('A deployment already holds this node lease') from exc
    print('LABCTL_SOURCE_SECRET:', flush=True)
    secret = sys.stdin.readline().strip()
    if not secret:
        raise Blocked('Missing in-memory transfer credential')
    pid = os.fork()
    if pid:
        return {'job': spec['job'], 'pid': pid, 'status':'started'}
    os.setsid()
    log_path = root / ('job-' + spec['job'] + '.log')
    os.umask(0o077)
    with open('/dev/null') as stdin, log_path.open('a', buffering=1) as log:
        os.dup2(stdin.fileno(), 0)
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    status = {'job':spec['job'],'node':spec['tag'],'release':release['name'],'status':'running',
              'release_digest':spec['release_digest'],
              'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().split()[21],
              'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'started':time.time()}
    try:
        atomic(root / 'status.json', status, 0o644)
        deploy(spec, release, source, secret, status, account)
        status.update(status='success', phase='complete', finished=time.time())
    except BaseException as exc:
        status.update(status='blocked' if isinstance(exc, Blocked) else 'failed', error=str(exc), finished=time.time())
        print(type(exc).__name__, str(exc), flush=True)
    atomic(root / 'status.json', status, 0o644)
    atomic(root / ('job-' + spec['job'] + '.json'), status, 0o644)
    lock.close()
    os._exit(0 if status['status'] == 'success' else 1)


def status_result(spec=None):
    value = load('/var/lib/lab-deploy/status.json', {})
    if value.get('status') == 'running':
        try:
            stat = Path('/proc') / str(value['pid']) / 'stat'
            content = stat.read_text().split()
            if content[2] == 'Z' or content[21] != value['start_ticks'] or Path('/proc/sys/kernel/random/boot_id').read_text().strip() != value['boot_id']:
                raise ValueError
        except (OSError, ValueError):
            value = {**value, 'status':'interrupted','error':'Worker exited or node rebooted; retry will inspect existing products'}
    if spec and os.path.ismount('/data'):
        cache=Path(spec['data_root'])/'.lab-deploy/cache'
        value={**value,'transfer_partials':[{'sha256':p.stem,'bytes':p.stat().st_size}
                                           for p in cache.glob('*.part') if re.fullmatch(r'[a-f0-9]{64}',p.stem)]}
    meta=load(Path(spec['data_root'])/'.lab-deploy/current/meta.json',{}) if spec and os.path.ismount('/data') else {}
    value={**value,'active_release':(meta or load('/var/lib/lab-deploy/active.json',{})).get('release')}
    return value


def main():
    action = sys.argv[1]
    payload = json.loads(base64.b64decode(sys.argv[2]))
    spec = payload.get('spec')
    if spec:
        guard(spec)
    if action == 'probe':
        result = probe(spec)
    elif action == 'start':
        result = start_job(spec, payload['release'], payload.get('source'))
    elif action == 'status':
        result = status_result(spec)
    elif action == 'assess':
        account = pwd.getpwnam(spec['user'])
        root = Path(spec['data_root'])
        current = load(root/'.lab-deploy/current/meta.json') if os.path.ismount('/data') else None
        ready = False
        if os.path.ismount('/data') and shutil.which('docker'):
            ready = healthy(current,spec,payload['release'],account) or bool(legacy(spec,payload['release'],account))
        needs_source=not ready
        if not ready and os.path.ismount('/data'):
            images=payload['release']['images']
            archive_needed={p['archive'] for p in images if not image_ok(p)}
            def available(artifact):
                paths=[root/'.lab-deploy/cache'/artifact['sha256']]+[root/safe_relative(p) for p in artifact.get('local_candidates',[])]
                return any(p.is_file() and p.stat().st_size==artifact['bytes'] and digest(p)==artifact['sha256'] for p in paths)
            needs_source=any(not available(a) for a in payload['release']['artifacts'] if a.get('target') or a['name'] in archive_needed)
        result = {'locally_ready':ready,'needs_source':needs_source}
    elif action == 'catalog':
        root=Path(spec['data_root'])
        release=load(root/'imports/release.json') or load(root/'checkpoints/segmentation-release-v1/release.json')
        baseline=load(root/'imports/baseline-checkpoint.json') or load(root/'checkpoints/baseline-before-segmentation-v1/checkpoint.json')
        if not release or not baseline:
            raise Blocked('Certified source metadata unavailable; open its volume first')
        artifacts=[]
        for name,sha in [('photogrammetry-baseline.tar',baseline['image_archive_sha256']),
                         ('segmentation-image.tar',release['files']['segmentation-image.tar']['sha256'])]:
            alternate='checkpoints/baseline-before-segmentation-v1/'+name if name.startswith('photogrammetry') else 'checkpoints/segmentation-release-v1/'+name
            paths=['imports/'+name,alternate]
            actual=next((root/p for p in paths if (root/p).is_file()),None)
            if not actual:raise Blocked('Source archive missing: '+name)
            artifacts.append({'name':name,'sha256':sha,'bytes':actual.stat().st_size,
                              'local_candidates':paths,'source_paths':{'L507_014':paths,'L507_012':list(reversed(paths))}})
        files=[]
        for name in ['segformer','sam3']:
            folder=root/'models'/name
            files.extend(p for p in folder.iterdir() if p.is_file())
        files.extend(p for p in (root/'datasets/raw/cuadra-025/drone').iterdir() if p.is_file() and not p.name.endswith('.part'))
        for path in sorted(files):
            relative=str(path.relative_to(root))
            artifacts.append({'name':relative,'target':relative,'sha256':digest(path),'bytes':path.stat().st_size,
                              'local_candidates':[relative],'source_paths':{'L507_014':[relative],'L507_012':[relative]}})
        result={'artifacts':artifacts,'baseline':baseline,'release':release}
    elif action == 'audit':
        if os.geteuid()!=0:raise Blocked('Host audit requires sudo to read the private enrollment backup')
        backup=Path('/var/lib/lab-deploy/backups/initial')
        before=dict(line.split('\t',1) for line in (backup/'packages.tsv').read_text().splitlines())
        drivers={k:v for k,v in before.items() if ('nvidia' in k and 'container' not in k) or k.startswith(('linux-image','linux-modules','linux-headers'))}
        after=driver_packages()
        changes={k:{'before':drivers.get(k),'after':after.get(k)} for k in set(drivers)|set(after) if drivers.get(k)!=after.get(k)}
        policy=Path('/usr/sbin/policy-rc.d');original=backup/'usr/sbin/policy-rc.d'
        restored=policy.exists()==original.exists() and (not original.exists() or policy.read_bytes()==original.read_bytes())
        result={'driver_kernel_changes':changes,'driver_kernel_packages_checked':len(drivers),
                'fstab_unchanged':Path('/etc/fstab').read_bytes()==(backup/'etc/fstab').read_bytes(),
                'service_policy_restored':restored,
                'boot_services':run(['systemctl','is-enabled','docker.service','docker.socket','containerd.service'],check=False).stdout.splitlines(),
                'driver':run(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader']).stdout.strip(),
                'root_free_gib':round(shutil.disk_usage('/').free/1024**3,2),
                'data_free_gib':round(shutil.disk_usage('/data').free/1024**3,2)}
    elif action == 'tail':
        job = payload['job']
        if not re.fullmatch(r'[a-f0-9]{12}', job):
            raise Blocked('Invalid job ID')
        path = Path('/var/lib/lab-deploy') / ('job-' + job + '.log')
        result = {'log':path.read_text()[-16000:] if path.exists() else ''}
    elif action == 'mount':
        if os.geteuid() != 0:
            raise Blocked('Mounting the data partition requires sudo')
        disk = mount_volume(spec)
        result = {'tag': spec['tag'], 'device': disk['path'], 'uuid': disk.get('uuid'),
                  'size_gib': round(int(disk['size']) / 1024**3, 2), 'mounted': os.path.ismount('/data'),
                  'free_gib': round(shutil.disk_usage('/data').free / 1024**3, 2)}
    elif action == 'volume':
        if os.geteuid() != 0:
            raise Blocked('Volume control requires sudo')
        idle()
        helper = next((p for p in ['/usr/local/sbin/lab-volume','/usr/local/sbin/photogrammetry-volume'] if Path(p).exists()), None)
        if not helper or payload['operation'] not in ['open','close']:
            raise Blocked('Enrolled volume helper is unavailable')
        if helper.endswith('/lab-volume'):
            result = {'output': run([helper,payload['operation']]).stdout}
        else:
            directory=Path('/var/lib/lab-deploy')
            directory.mkdir(mode=0o755,exist_ok=True)
            lock=(directory/'deployment.lock').open('a')
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result = {'output': run([helper,payload['operation']]).stdout}
    elif action == 'rollback':
        if os.geteuid() != 0:
            raise Blocked('Activation requires sudo')
        idle()
        root = Path(spec['data_root'])
        directory = root / '.lab-deploy/releases' / payload['release']['name']
        meta = load(directory/'meta.json')
        if not healthy(meta,spec,payload['release'],pwd.getpwnam(spec['user'])):
            raise Blocked('Rollback release is not complete/healthy; deploy it first')
        lock = Path('/var/lib/lab-deploy/deployment.lock').open('a')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        activate(root,directory,meta)
        atomic('/var/lib/lab-deploy/active.json',meta,0o644)
        result = {'status':'success','active':meta}
    else:
        raise Blocked('Unknown action')
    print(MARKER + json.dumps({'ok':True,'result':result}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        print(MARKER + json.dumps({'ok':False,'error':str(exc),'kind':type(exc).__name__}),flush=True)
        raise SystemExit(1)
