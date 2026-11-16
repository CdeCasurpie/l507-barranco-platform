"""Read-only Barranco status: no collection, retries, launches or local snapshots."""
import argparse
import concurrent.futures
import datetime
import json
from pathlib import Path
import shlex
import sys
import time

import pexpect

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from labdeploy.ssh import credentials

DEFAULT_CAMPAIGN = PROJECT / '.state/campaigns/barranco-running-20261116'
TERMINAL = {'failed', 'awaiting_review', 'completed', 'downloaded'}
REMOTE = r'''
import json,os,pathlib,subprocess,time
a=ASSIGNMENT
assert (pathlib.Path.home()/(a['node_tag']+'.txt')).is_file(),'Tag mismatch'
assert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')],'MAC mismatch'
root=pathlib.Path(a['work_root'])
assert root.is_relative_to('/data/photogrammetry/campaigns')
def read(path):
 try:return json.loads(path.read_text()) if path.is_file() else {}
 except (OSError,ValueError):return {}
download=read(pathlib.Path(a.get('download_root',str(root)))/'status.json')
status=read(root/'reconstruction-full-status.json')
launch=read(root/'sparse-launch.json')
pid=status.get('pid',launch.get('pid'))
proc=pathlib.Path('/proc/'+str(pid)+'/cmdline')
try:alive=bool(pid and proc.exists() and str(root).encode() in proc.read_bytes())
except OSError:alive=False
now=time.time()
state=status.get('state','starting' if alive else 'not_started')
if status and not alive and state not in ('failed','awaiting_review','completed'):
 observed='SIN WORKER'
else:observed=state
stage=status.get('stage','preflight' if alive else '-')
error=status.get('error') or status.get('observed_error')
gpu=None
try:
 p=subprocess.run(['nvidia-smi','--query-gpu=temperature.gpu,power.limit','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=6)
 if p.returncode==0:
  t,w=p.stdout.strip().splitlines()[0].split(',');gpu={'c':float(t),'limit_w':float(w)}
except (OSError,ValueError,subprocess.TimeoutExpired):pass
start=status.get('stage_started_at',status.get('started_at'))
end=status.get('finished_at',now)
elapsed=max(0,end-start) if isinstance(start,(int,float)) else None
age=max(0,now-status['updated_at']) if isinstance(status.get('updated_at'),(int,float)) else None
disk=os.statvfs('/')
data=os.statvfs('/data')
print('BARRANCO_STATUS='+json.dumps({
 'block':a['block_id'],'node':a['node_tag'],'group':a.get('group','nueva'),
 'download':download.get('state','-'),'download_done':download.get('completed_files'),
 'download_total':download.get('total_files'),'state':observed,'recorded_state':state,
 'stage':stage,'worker_alive':alive,'pid':pid,'gpu_live':gpu,
 'stage_seconds':elapsed,'status_age_seconds':age,'error':error,
 'registered_images':status.get('registered_images'),'components':status.get('components'),
 'completed_stages':status.get('completed_stages',[]),'work_root':str(root),
 'root_free_gib':disk.f_bavail*disk.f_frsize/2**30,
 'data_free_gib':data.f_bavail*data.f_frsize/2**30,
 'last_run_telemetry':status.get('telemetry'),'observed_at':now}))
'''


def assignments(campaign, site, history=True):
    rows = json.loads((campaign/'assignments.json').read_text())['assignments']
    rows = [dict(row) for row in rows]
    # Immutable terrestrial snapshot; original download assignment stays unchanged.
    terrestrial = campaign/'terrestrial-bindings.json'
    if terrestrial.exists():
        variant = json.loads(terrestrial.read_text())['assignments'][0]
        for row in rows:
            if row['block_id'] == variant['block_id']:
                row['download_root'] = row['work_root']
                row['work_root'] = variant['work_root']
    if history:
        for block, tag, ip, path in [
            ('006 multivideo','L507_006','192.0.2.64','barranco-inputs-20261115/cuadra-006-14nov'),
            ('026 parque','L507_019','192.0.2.63','barranco-inputs-20261115/cuadra-026-all'),
            ('006 horizontal','L507_010','192.0.2.100','barranco-006-horizontal-20261115/cuadra-006'),
        ]:
            rows.append({'block_id':block,'node_tag':tag,'mac':site['nodes'][tag],
                         'ip':ip,'group':'anterior',
                         'work_root':'/data/photogrammetry/campaigns/'+path})
        diagnostic = PROJECT/'.state/campaigns/barranco-006-horizontal-nomasks-20261116/assignments.json'
        if diagnostic.is_file():
            row = dict(json.loads(diagnostic.read_text())['assignments'][0])
            row.update(block_id='006 horiz s/m',group='anterior',
                       download_root='/data/photogrammetry/campaigns/barranco-006-horizontal-20261115/cuadra-006')
            rows.append(row)
        for block in ('019','020'):
            cut = PROJECT/f'.state/campaigns/barranco-{block}-cut10fps-20261116/assignments.json'
            if cut.is_file():
                row = dict(json.loads(cut.read_text())['assignments'][0])
                row.update(block_id=block+' corte 10fps',group='prueba',
                           download_root='/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-'+block)
                rows.append(row)
        vocabulary = PROJECT/'.state/campaigns/barranco-020-vocabloop-20261116/assignments.json'
        if vocabulary.is_file():
            row = dict(json.loads(vocabulary.read_text())['assignments'][0])
            row.update(block_id='020 vocab loop', group='prueba',
                       download_root='/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-020')
            rows.append(row)
        glomap = PROJECT/'.state/campaigns/barranco-020-glomap-20261116/assignments.json'
        if glomap.is_file():
            row = dict(json.loads(glomap.read_text())['assignments'][0])
            row.update(block_id='020 GLOMAP', group='prueba',
                       download_root='/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-020')
            rows.append(row)
    return rows


def inspect(row, site, password):
    trusted = [PROJECT/'.state/known_hosts',
               PROJECT/'.state/campaigns/barranco-inputs-20261115/known_hosts']
    opts = ['-o','ConnectTimeout=6','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+' '.join(str(p) for p in trusted if p.is_file()),
            '-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no',
            '-o','NumberOfPasswordPrompts=1','-o','LogLevel=ERROR']
    # Verify against previously trusted keys across these observed DHCP changes.
    alias = {'L507_005':'192.0.2.58','L507_022':'192.0.2.67'}.get(row['node_tag'])
    if alias:
        opts += ['-o','HostKeyAlias='+alias]
    child = None
    try:
        code = REMOTE.replace('ASSIGNMENT', repr(row))
        child = pexpect.spawn('ssh',opts+[site['ssh_user']+'@'+row['ip'],
                              shlex.join(['python3','-B','-c',code])],
                              encoding='utf-8',echo=False,timeout=22)
        chunks = []
        attempts = 0
        while True:
            event=child.expect(['[Pp]assword:',pexpect.EOF,pexpect.TIMEOUT])
            chunks.append(child.before)
            if event==0:
                attempts+=1
                if attempts>1:
                    raise RuntimeError('SSH authentication failed')
                child.sendline(password)
            elif event==1:
                break
            else:
                raise RuntimeError('SSH query timed out; no remote job was changed')
        child.close()
        text=''.join(chunks)
        if 'BARRANCO_STATUS=' not in text:
            # Do not echo arbitrary remote output or credential prompts.
            if 'Host key verification failed' in text or 'REMOTE HOST IDENTIFICATION' in text:
                raise RuntimeError('SSH host key not validated; identity verification required')
            raise RuntimeError('No valid reply; SSH or remote inspection failed')
        return json.loads(text.rsplit('BARRANCO_STATUS=',1)[1].splitlines()[0])
    except Exception as exc:
        return {'block':row['block_id'],'node':row['node_tag'],
                'group':row.get('group','nueva'),'state':'CONSULTA FALLIDA',
                'stage':'-','download':'-','error':str(exc),'worker_alive':None}
    finally:
        if child is not None and child.isalive():
            child.close(force=True)  # Local SSH query only, never a pipeline worker.


def duration(seconds):
    if seconds is None:
        return '-'
    seconds=int(seconds)
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'


def display(rows):
    print('Barranco · consulta SSH de solo lectura · '+datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'))
    print('GPU = temperatura ACTUAL; tiempo = duración de la etapa, no avance estimado.\n')
    header=f'{"BLOQUE":<16} {"MAQUINA":<10} {"DESCARGA":<12} {"ESTADO":<17} {"ETAPA":<14} {"WORKER":<7} {"GPU":>6} {"LIMITE":>6} {"TIEMPO":>8} {"/ LIBRE":>8}'
    print(header)
    print('-'*len(header))
    previous_group=None
    for row in rows:
        if previous_group and previous_group!=row.get('group'):
            print('-'*len(header))
        previous_group=row.get('group')
        state={'running':'ejecutando','failed':'FALLO','awaiting_review':'REVISAR',
               'completed':'terminado','not_started':'no iniciado',
               'starting':'iniciando','waiting_cooldown':'enfriando'}.get(row['state'],row['state'])
        down={'downloaded':'lista','downloading':'descargando'}.get(row.get('download'),row.get('download','-'))
        alive='sí' if row.get('worker_alive') is True else ('no' if row.get('worker_alive') is False else '?')
        gpu=row.get('gpu_live') or {}
        temp=f'{gpu["c"]:.0f}°C' if 'c' in gpu else '-'
        power=f'{gpu["limit_w"]:.0f} W' if 'limit_w' in gpu else '-'
        free=f'{row["root_free_gib"]:.1f} GiB' if 'root_free_gib' in row else '-'
        print(f'{row["block"]:<16} {row["node"]:<10} {down:<12} {state:<17} {row.get("stage","-"):<14} {alive:<7} {temp:>6} {power:>6} {duration(row.get("stage_seconds")):>8} {free:>8}')
        if row.get('error'):
            print('  ↳ '+str(row['error']).replace('\n',' ')[:240])
        if row.get('registered_images') is not None:
            print(f'  ↳ {row["registered_images"]} vistas registradas; requiere revisión geométrica.')
    print('\nFALLO térmico: sin reintento automático. GPU fría ahora no borra el incidente anterior.')
    print('Esta consulta no inicia, reintenta, descarga ni recoge reconstrucciones.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,default=DEFAULT_CAMPAIGN)
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--no-history',action='store_true')
    options=parser.parse_args()
    site=json.loads((PROJECT/'config/site.json').read_text())
    password,_=credentials(site)
    rows=assignments(options.campaign,site,not options.no_history)
    with concurrent.futures.ThreadPoolExecutor(max_workers=13) as pool:
        results=list(pool.map(lambda row:inspect(row,site,password),rows))
    if options.json:
        print(json.dumps({'observed_at':time.time(),'nodes':results},indent=2))
    else:
        display(results)


if __name__=='__main__':
    main()
