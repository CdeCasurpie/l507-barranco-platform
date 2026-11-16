import argparse
import concurrent.futures
import json
from pathlib import Path
import shlex
import sys
import pexpect

sys.path.insert(0, '/home/exitoso/lab-deploy/tools')
import review_experiments as control

parser = argparse.ArgumentParser()
parser.add_argument('payload')
parser.add_argument('--nodes', default='002,004,005,007,008,009,011,015,021,022')
parser.add_argument('--sudo', action='store_true')
parser.add_argument('--output', required=True)
parser.add_argument('--bindings')
args = parser.parse_args()
site = json.loads(Path('/home/exitoso/lab-deploy/config/site.json').read_text())
password, sudo_password = control.credentials(site)
ips = {'002':'54','004':'44','005':'103','006':'64','007':'71','008':'77',
       '009':'78','010':'100','011':'65','015':'61','021':'80','022':'101'}
payload = Path(args.payload).read_text()
bindings = json.loads(Path(args.bindings).read_text()) if args.bindings else {}

def inspect(number):
    tag = 'L507_' + number
    prefix = (
        'import pathlib\n'
        f'assert (pathlib.Path("/home/utec_alumno")/({tag!r}+".txt")).is_file()\n'
        f'assert {site["nodes"][tag]!r} in [p.read_text().strip() for p in pathlib.Path("/sys/class/net").glob("*/address")]\n'
        f'NODE_TAG={tag!r}\n'
        f'import json\nBINDINGS=json.loads({json.dumps(bindings)!r})\n'
    )
    command = ['python3', '-B', '-c', prefix + payload]
    if args.sudo:
        command = ['sudo', '-S', '-p', 'ADMIN_AUTH:', '--'] + command
    options = ['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
               '-o','UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts']
    alias = {'005':'58','010':'66','022':'67'}.get(number)
    if alias:
        options += ['-o', 'HostKeyAlias=10.100.41.' + alias]
    child = None
    try:
        child = pexpect.spawn('ssh', options + [
            site['ssh_user'] + '@10.100.41.' + ips[number],
            shlex.join(command)], encoding='utf-8', echo=False, timeout=240)
        chunks = []
        while True:
            event = child.expect(['[Pp]assword:', 'ADMIN_AUTH:', pexpect.EOF, pexpect.TIMEOUT])
            chunks.append(child.before)
            if event == 0:
                child.sendline(password)
            elif event == 1:
                child.sendline(sudo_password)
            elif event == 2:
                break
            else:
                raise RuntimeError('SSH operation timed out; check remote state before retry')
        child.close()
        text = ''.join(chunks)
        if 'ADMIN_REPLY=' not in text:
            return {'tag': tag, 'error': text[-1200:]}
        return json.loads(text.rsplit('ADMIN_REPLY=', 1)[1].splitlines()[0])
    except Exception as error:
        if child is not None:
            child.close(force=True)
        return {'tag': tag, 'error': str(error)}

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    results = list(pool.map(inspect, args.nodes.split(',')))
Path(args.output).write_text(json.dumps(results, indent=2))
for result in results:
    print(json.dumps(result))
