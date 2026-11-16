import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from . import config, inventory
from .ssh import SSH
from .store import ROOT,CONFIG_ROOT, Store


def spec_for(site,tag,fingerprint):
    return {'tag':tag,'mac':site['nodes'][tag],'user':site['ssh_user'],'data_root':site['data_root'],
            'release_digest':fingerprint,'volume_bridge':(ROOT/'labdeploy/volume_bridge.py').read_text()}


def output(value):
    print(json.dumps(value,indent=2,ensure_ascii=False),flush=True)


def process_alive(record):
    pid=record.get('pid')
    if not pid:return False
    try:
        fields=(Path('/proc')/str(pid)/'stat').read_text().split()
        if fields[2]=='Z':return False
        if record.get('start_ticks') and fields[21]!=record['start_ticks']:return False
        if record.get('boot_id') and Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=record['boot_id']:return False
        return True
    except OSError:return False


def row(tag,record):
    facts=record.get('facts',{})
    current=facts.get('current') or {}
    return {'node':tag,'ip':record.get('ip'),'available':record.get('available',False),
            'driver':facts.get('driver'),'volume_mounted':facts.get('mounted'),
            'docker':facts.get('docker'),'active_release':current.get('release'),
            'error':record.get('error')}


def plan_rows(site,nodes,targets,release):
    rows=[]
    for tag in targets:
        record=nodes[tag]
        item=row(tag,record)
        facts=record.get('facts',{})
        if not record.get('available'):
            item['plan']='unavailable'
        elif not facts.get('driver'):
            item['plan']='blocked: driver not operational'
        elif len(facts.get('disks',[]))!=1:
            item['plan']='blocked: data partition ambiguous/missing'
        elif not facts.get('mounted'):
            item['plan']='open and inspect volume during deploy; existing contents currently unknown'
        elif facts.get('current',{}):
            item['plan']='verify existing release; no changes if healthy'
        else:
            item['plan']='inspect/adopt existing environment or stage release'
        item['requested_release']=release['name']
        rows.append(item)
    return rows


def manager(request_path,state_path):
    store=Store(state_path)
    request=json.loads(Path(request_path).read_text())
    site=request['site']
    release=request['release']
    fingerprint=request['release_digest']
    nodes=request['inventory']
    ssh=SSH(site,store)
    result={'id':request['id'],'release':release['name'],'status':'running','started':time.time(),
            'nodes':{},'sources':{},'pid':os.getpid(),
            'start_ticks':Path('/proc/self/stat').read_text().split()[21],
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    lock=threading.Lock()
    source_locks={}
    usage={tag:0 for tag in site['sources']}
    def save():
        store.write('runs/'+request['id']+'.json',result)
    def get_source(target,avoid=None):
        with lock:
            eligible=[tag for tag in site['sources'] if tag!=target and nodes.get(tag,{}).get('available')]
            eligible.sort(key=lambda tag:(tag==avoid,usage[tag],site['sources'].index(tag)))
            for tag in eligible:
                if tag not in source_locks:
                    handle=(store.root/('source-'+tag+'.lock')).open('a')
                    fcntl.flock(handle,fcntl.LOCK_EX)
                    source_locks[tag]=handle
                    spec=spec_for(site,tag,fingerprint)
                    facts=ssh.call(nodes[tag]['ip'],'probe',{'spec':spec})
                    was_mounted=facts['mounted']
                    pending=store.read('sources/'+tag+'.json',{}).get('pending_restore',False)
                    result['sources'][tag]={'initially_mounted':was_mounted,'opened_by_controller':pending or not was_mounted}
                    save()
                    if pending or not was_mounted:
                        store.write('sources/'+tag+'.json',{'pending_restore':True,'owner':request['id']})
                    if not was_mounted:
                        ssh.call(nodes[tag]['ip'],'volume',{'spec':spec,'operation':'open'},sudo=True,timeout=180)
                        save()
                usage[tag]+=1
                return {'tag':tag,'mac':site['nodes'][tag],'ip':nodes[tag]['ip'],
                        'user':site['ssh_user'],'home':nodes[tag].get('facts',{}).get('home','/home/'+site['ssh_user'])}
        return None
    def one(tag):
        record=nodes[tag]
        with lock:
            result['nodes'][tag]={'status':'starting','ip':record.get('ip')}
            save()
        if not record.get('available'):
            with lock:
                result['nodes'][tag].update(status='unavailable',error=record.get('error'))
                save()
            return
        spec=spec_for(site,tag,fingerprint)
        spec['job']=uuid.uuid4().hex[:12]
        source=None
        try:
            old=ssh.call(record['ip'],'status',{'spec':spec})
            if old.get('status')=='running':
                if old.get('release_digest')!=fingerprint:
                    raise RuntimeError('Node has a running deployment of a different manifest')
                spec['job']=old['job']
                source=get_source(tag)
                response=old
            else:
                assess=ssh.call(record['ip'],'assess',{'spec':spec,'release':release},timeout=180)
                need_source=assess.get('needs_source',not assess['locally_ready'])
                source=get_source(tag,request.get('avoid_sources',{}).get(tag)) if need_source else None
                if need_source and source is None:
                    raise RuntimeError('No registered source available')
                response=ssh.call(record['ip'],'start',{'spec':spec,'release':release,'source':source},sudo=True,timeout=180)
            with lock:
                result['nodes'][tag].update(status='running',job=response['job'])
                save()
            deadline=time.monotonic()+10800
            while time.monotonic()<deadline:
                try:
                    value=ssh.call(record['ip'],'status',{'spec':spec})
                except Exception as exc:
                    with lock:
                        result['nodes'][tag]['poll_error']=str(exc)
                        save()
                    time.sleep(request.get('poll',15))
                    continue
                if value.get('job')!=spec['job']:
                    time.sleep(2)
                    continue
                with lock:
                    result['nodes'][tag]=dict(value,ip=record['ip'],source=source['tag'] if source else None)
                    save()
                if value['status']!='running':break
                time.sleep(request.get('poll',15))
            else:raise RuntimeError('Remote job deadline exceeded; inspect before retrying')
        except Exception as exc:
            with lock:
                result['nodes'][tag].update(status='controller-error',error=str(exc))
                save()
        finally:
            if source:
                with lock:usage[source['tag']]-=1
    save()
    try:
        # Existing seed nodes first, before serving artifacts to new machines.
        targets=sorted(request['targets'],key=lambda tag:tag not in site['sources'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=request['parallel']) as pool:
            list(pool.map(one,targets))
    finally:
        for tag,handle in source_locks.items():
            try:
                if result['sources'].get(tag,{}).get('opened_by_controller'):
                    if any(n.get('status')=='controller-error' and n.get('job') for n in result['nodes'].values()):
                        result['sources'][tag]['restore_deferred']='Unknown remote worker state; retry/status before closing source'
                        continue
                    ssh.call(nodes[tag]['ip'],'volume',{'spec':spec_for(site,tag,fingerprint),'operation':'close'},sudo=True,timeout=180)
                    result['sources'][tag]['restored_closed']=True
                    store.write('sources/'+tag+'.json',{'pending_restore':False,'owner':request['id']})
            except Exception as exc:
                result['sources'][tag]['restore_error']=str(exc)
            finally:
                handle.close()
        clean_sources=not any(v.get('restore_error') or v.get('restore_deferred') for v in result['sources'].values())
        result['status']='success' if clean_sources and all(v['status']=='success' for v in result['nodes'].values()) else 'partial'
        result['finished']=time.time()
        save()
        store.event({'event':'deployment-finished','run':request['id'],'status':result['status']})


def submit(site,store,nodes,targets,release,fingerprint,parallel,avoid_sources=None):
    identifier=uuid.uuid4().hex[:12]
    request={'id':identifier,'site':site,'inventory':nodes,'targets':targets,'release':release,
             'release_digest':fingerprint,'parallel':parallel,'avoid_sources':avoid_sources or {}}
    path=store.root/'requests'/(identifier+'.json')
    store.write('requests/'+identifier+'.json',request)
    with (store.root/('manager-'+identifier+'.log')).open('a') as log:
        child=subprocess.Popen([sys.executable,'-m','labdeploy','_manage','--request',str(path),'--state',str(store.root)],
                               cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    store.write('latest.json',{'id':identifier,'pid':child.pid,'request':str(path)})
    return identifier


def wait(store,identifier,interval=15):
    last=None
    while True:
        record=store.read('runs/'+identifier+'.json',{})
        summary={tag:{key:value.get(key) for key in ['status','phase','changed','error']}
                 for tag,value in record.get('nodes',{}).items()}
        if summary!=last:
            output({'run':identifier,'status':record.get('status','starting'),'nodes':summary})
            last=summary
        if record.get('status') in ['success','partial']:
            return 0 if record['status']=='success' else 1
        latest=store.read('latest.json',{})
        pid=record.get('pid') or (latest.get('pid') if latest.get('id')==identifier else None)
        if pid and not process_alive(record if record.get('pid') else latest):
            raise RuntimeError('Coordinator exited; remote workers may continue. Use status --refresh and retry')
        time.sleep(interval)


def main(argv=None):
    parser=argparse.ArgumentParser(description='L507 deployment controller (independent of the master Makefile)')
    parser.add_argument('--site')
    parser.add_argument('--state')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('discover',help='Observe tag/MAC/IP, GPU and storage')
    sub.add_parser('releases',help='List versioned deployment manifests')
    p=sub.add_parser('check-release',help='Validate a manifest without connecting to daughters')
    p.add_argument('--release',required=True)
    p=sub.add_parser('audit',help='Read host preservation checks after enrollment')
    targets=p.add_mutually_exclusive_group(required=True)
    targets.add_argument('--targets')
    targets.add_argument('--all',action='store_true')
    p=sub.add_parser('mount',help='Mount and inspect the 488 GB data partition')
    targets=p.add_mutually_exclusive_group(required=True)
    targets.add_argument('--targets')
    targets.add_argument('--all',action='store_true')
    for command in ['plan','deploy','rollback']:
        p=sub.add_parser(command)
        targets=p.add_mutually_exclusive_group(required=True)
        targets.add_argument('--targets')
        targets.add_argument('--all',action='store_true')
        p.add_argument('--release',required=True)
        if command=='deploy':
            p.add_argument('--parallel',type=int)
            p.add_argument('--wait',action='store_true')
    p=sub.add_parser('status')
    p.add_argument('--run')
    p.add_argument('--refresh',action='store_true')
    p.add_argument('--details',action='store_true')
    p=sub.add_parser('wait')
    p.add_argument('--run')
    p=sub.add_parser('logs')
    p.add_argument('--node',required=True)
    p.add_argument('--run')
    p=sub.add_parser('retry')
    p.add_argument('--failed',action='store_true',required=True)
    p.add_argument('--run')
    p.add_argument('--wait',action='store_true')
    p=sub.add_parser('_manage',help=argparse.SUPPRESS)
    p.add_argument('--request',required=True)
    p.add_argument('--state',required=True)
    args=parser.parse_args(argv)
    if args.command=='_manage':
        manager(args.request,args.state)
        return 0
    site=config.site(args.site)
    store=Store(args.state)
    ssh=SSH(site,store)
    try:
        if args.command=='releases':
            output([{'name':config.release(str(p))[0]['name'],'commit':config.release(str(p))[0]['git']['commit']}
                    for p in sorted((CONFIG_ROOT/'releases').glob('*.json'))])
        elif args.command=='check-release':
            value,fingerprint=config.release(args.release)
            output({'valid':True,'release':value['name'],'digest':fingerprint,'artifacts':len(value['artifacts'])})
        elif args.command=='audit':
            targets=inventory.selected(site,args)
            nodes=inventory.discover(site,store,ssh)
            records={tag:ssh.call(nodes[tag]['ip'],'audit',{'spec':spec_for(site,tag,'')},sudo=True) if nodes[tag]['available']
                     else {'unavailable':True} for tag in targets}
            store.write('last-audit.json',records)
            output(records)
        elif args.command=='discover':
            nodes=inventory.discover(site,store,ssh)
            output([row(tag,record) for tag,record in sorted(nodes.items())])
        elif args.command=='mount':
            targets=inventory.selected(site,args)
            nodes=inventory.discover(site,store,ssh)
            values={}
            for tag in targets:
                record=nodes[tag]
                if not record.get('available'):
                    values[tag]={'status':'error','error':record.get('error')}
                    continue
                try:
                    values[tag]=dict(ssh.call(record['ip'],'mount',{'spec':spec_for(site,tag,'')},sudo=True,timeout=180),status='mounted')
                except Exception as exc:
                    values[tag]={'status':'error','error':str(exc)}
            store.write('mounts.json',values)
            output(values)
        elif args.command in ['plan','deploy','rollback']:
            release,fingerprint=config.release(args.release)
            targets=inventory.selected(site,args)
            nodes=inventory.discover(site,store,ssh)
            if args.command=='plan':output(plan_rows(site,nodes,targets,release))
            elif args.command=='rollback':
                values={tag:ssh.call(nodes[tag]['ip'],'rollback',{'spec':spec_for(site,tag,fingerprint),'release':release},sudo=True,timeout=180)
                        for tag in targets if nodes[tag].get('available')}
                output({tag:{'status':value['status'],**{k:value['active'].get(k) for k in ['release','code_root','data_root','env_file']}}
                        for tag,value in values.items()})
            else:
                parallel=args.parallel or site['max_parallel']
                if not 1<=parallel<=6:raise ValueError('Parallel must be 1..6')
                identifier=submit(site,store,nodes,targets,release,fingerprint,parallel)
                output({'run':identifier,'status':'submitted','persistent':True})
                if args.wait:return wait(store,identifier)
        else:
            latest=store.read('latest.json',{})
            identifier=getattr(args,'run',None) or latest.get('id')
            if not identifier:raise ValueError('No deployment run has been submitted')
            record=store.read('runs/'+identifier+'.json',{})
            if args.command=='wait':return wait(store,identifier)
            if args.command=='logs':
                node=record['nodes'][args.node]
                print(ssh.call(node['ip'],'tail',{'spec':spec_for(site,args.node,''),'job':node['job']},sudo=True)['log'],end='')
            elif args.command=='status':
                if args.refresh:
                    for tag,item in record.get('nodes',{}).items():
                        if item.get('ip') and item.get('job'):
                            try:item.update(ssh.call(item['ip'],'status',{'spec':spec_for(site,tag,'')}))
                            except Exception as exc:item['refresh_error']=str(exc)
                if args.details:output(record)
                else:
                    summary={tag:{k:value.get(k) for k in ['ip','status','phase','active_release','changed','source','error']}
                             | {'partial_mib':round(sum(p['bytes'] for p in value.get('transfer_partials',[]))/1024**2)}
                             for tag,value in record.get('nodes',{}).items()}
                    output({'run':identifier,'release':record.get('release'),'status':record.get('status'),
                            'nodes':summary,'sources':record.get('sources',{})})
            elif args.command=='retry':
                request=store.read('requests/'+identifier+'.json')
                terminal_failures={'failed','blocked','unavailable','controller-error','interrupted'}
                targets=[tag for tag,value in record.get('nodes',{}).items()
                         if value['status'] in terminal_failures or (value['status']!='success' and not process_alive(record))]
                if not targets:
                    pending=[tag for tag in site['sources'] if store.read('sources/'+tag+'.json',{}).get('pending_restore')]
                    if not pending:
                        output({'status':'nothing-to-retry'})
                        return 0
                    nodes=inventory.discover(site,store,ssh)
                    restored={}
                    for tag in pending:
                        lease=None
                        try:
                            lease=(store.root/('source-'+tag+'.lock')).open('a')
                            fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            if not nodes[tag]['available']:raise RuntimeError('Source unavailable')
                            if nodes[tag]['facts']['mounted']:
                                ssh.call(nodes[tag]['ip'],'volume',{'spec':spec_for(site,tag,request['release_digest']),'operation':'close'},sudo=True,timeout=180)
                            store.write('sources/'+tag+'.json',{'pending_restore':False})
                            restored[tag]='closed'
                        except Exception as exc:restored[tag]=str(exc)
                        finally:
                            if lease:lease.close()
                    output({'source_restoration':restored})
                    return 0 if all(value=='closed' for value in restored.values()) else 1
                nodes=inventory.discover(site,store,ssh)
                avoid={tag:record['nodes'][tag].get('source') for tag in targets}
                new=submit(site,store,nodes,targets,request['release'],request['release_digest'],request['parallel'],avoid)
                output({'run':new,'retried':targets})
                if args.wait:return wait(store,new)
        return 0
    except (ValueError,KeyError,RuntimeError,OSError) as exc:
        print('labctl:',str(exc),file=sys.stderr)
        return 1
