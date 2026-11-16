"""Persistent gated campaign: pilots, bounded waves, verified collection, alignment."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from reconstruct_campaign import prepare,start,status
from campaign_power import power
from drive_download_campaign import remote
from collect_reconstruction import collect
sys.path.insert(0,str(PROJECT))
from labdeploy.store import atomic_json

CENTRAL=Path('/data/barranco/campaigns/barranco-full-v1')
PYTHON=Path('/data/barranco/runtime/alignment313/bin/python')


class Campaign:
    def __init__(self):
        self.site=json.loads((PROJECT/'config/site.json').read_text())
        entries=json.loads((CENTRAL/'assignments.json').read_text())['assignments']
        self.entries={a['block_id']:a for a in entries if a['block_id']!='TODO'}
        overrides=CENTRAL/'execution-overrides.json'
        if overrides.exists():
            for block,a in json.loads(overrides.read_text()).items():
                if block not in self.entries or a['block_id']!=block:raise RuntimeError('Invalid execution override')
                self.entries[block]=a
        self.state={'campaign_id':'barranco-full-v1','state':'running','phase':'pilots',
                    'manager_pid':os.getpid(),'nodes':{},'collections':{},'imports':{},'power':{},'started_at':time.time()}
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.collection_futures={}
        self.retry_holds=set()
        self.imports={}
        self.restored=set()
        previous=CENTRAL/'execution-status.json'
        if previous.exists():
            saved=json.loads(previous.read_text())
            if saved.get('phase') in ['remaining-blocks','collection','alignment']:
                self.state=saved
                self.state.setdefault('manager_restarts',[]).append({'old_pid':saved.get('manager_pid'),'at':time.time()})
                self.state.update(manager_pid=os.getpid(),state='running')
                self.state.pop('error',None)
                self.imports=dict(saved.get('imports',{}))
                self.restored={b for b,v in saved.get('power',{}).items() if v.get('state') in ['restored','not_applied','operator_changed_limit']}
                for block,a in self.entries.items():
                    expected=a.get('full_experiment')
                    if expected and expected not in self.imports.get(block,''):
                        self.imports.pop(block,None)
                        previous=self.state.get('collections',{}).pop(block,None)
                        if previous:self.state.setdefault('superseded_collections',{})[block]=previous
                        self.restored.discard(block)
                self.state['imports']=dict(self.imports)

    def save(self):
        self.state['updated_at']=time.time();atomic_json(CENTRAL/'execution-status.json',self.state)

    def scoped(self,name,argv,log_path):
        unit='barranco-alignment-'+name+'-'+str(int(time.time()))
        command=['systemd-run','--user','--scope','--unit='+unit,'--quiet',
                 '-p','MemoryMax=40G','-p','MemorySwapMax=0','-p','CPUQuota=800%',str(PYTHON),'-B',*map(str,argv)]
        env=dict(os.environ,TMPDIR='/data/barranco/runtime/test-tmp',PATH=str(PYTHON.parent)+os.pathsep+os.environ['PATH'])
        with log_path.open('a') as log:
            p=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env)
        if p.returncode:raise RuntimeError(name+' exited '+str(p.returncode)+'; see '+str(log_path))

    def collect_and_import(self,block):
        a=self.entries[block]
        destination=collect(self.site,a,'full')
        output=Path('/data/barranco/alignment-inputs/barranco-full-v1')/block/destination.name
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists() and not (output/'adaptation.json').exists():
            output.rename(output.with_name(output.name+'-interrupted-'+str(int(time.time()))))
        if not (output/'adaptation.json').exists():
            self.scoped('import-'+block,[PROJECT/'tools/import_alignment_run.py','--run',destination,'--output',output,'--block',block],CENTRAL/('import-'+block+'.log'))
        return {'destination':str(destination),'manifest':str(output/'block.json'),'adaptation':str(output/'adaptation.json')}

    def poll(self,blocks):
        if (CENTRAL/'STOP_EXPANSION').exists():
            raise RuntimeError('Operator requested no further expansion; daughter supervisors remain active')
        def inspect(block):
            try:return block,status(self.site,self.entries[block],'full')
            except Exception as exc:return block,{'state':'unreachable','error':str(exc),'node_tag':self.entries[block]['node_tag']}
        with ThreadPoolExecutor(max_workers=5) as pool:
            for block,value in pool.map(inspect,blocks):
                if value.get('state') in ['starting','running']:
                    self.restored.discard(block)
                self.state['nodes'][block]=value
                terminal=value.get('state') in ['completed','partial','failed']
                if terminal and block not in self.restored:
                    try:self.state['power'][block]=power(self.site,self.entries[block],restore=True);self.restored.add(block)
                    except Exception as exc:self.state['power'][block]={'restore_error':str(exc)}
                if value.get('state') in ['completed','partial'] and not value.get('worker_alive') and block not in self.collection_futures and block not in self.imports:
                    self.collection_futures[block]=self.pool.submit(self.collect_and_import,block)
                    self.state['collections'][block]={'state':'queued'}
        for block,future in self.collection_futures.items():
            if future.done() and self.state['collections'][block]['state']=='queued':
                try:
                    result=future.result();self.state['collections'][block]={'state':'verified',**result}
                    self.imports[block]=result['manifest'];self.state['imports'][block]=result['manifest']
                except Exception as exc:self.state['collections'][block]={'state':'failed','error':str(exc)}
        self.save()

    def enable(self,block):
        a=self.entries[block]
        self.state['power'][block]=power(self.site,a)
        self.save()
        result=start(self.site,a,'full')
        print('START',block,result.get('state'),flush=True)

    def resolve_legacy_admission(self,block):
        value=self.state['nodes'].get(block,{})
        if value.get('state')!='failed' or block in self.retry_holds:return
        a=self.entries[block]
        hold=remote(self.site,a['ip'],f'''
import json
from pathlib import Path
p=Path({a['work_root']!r})/'dense-admission-hold.json'
print('DOWNLOAD_REPLY='+json.dumps(json.loads(p.read_text()) if p.exists() else {{}}))
''')
        if hold.get('worker_pid')!=value.get('pid') or '4K all-view fusion' not in hold.get('reason',''):return
        print('RESOLVING DOCUMENTED DENSE ADMISSION HOLD',block,flush=True)
        time.sleep(15)
        prepare(self.site,a,update=True)
        self.state['power'][block]=power(self.site,a)
        result=start(self.site,a,'full',retry=True)
        self.retry_holds.add(block);self.restored.discard(block)
        self.state['nodes'][block]=result;self.save()

    def wait_pilots(self):
        while True:
            self.poll(['025','005','009'])
            for block in ['005','009']:self.resolve_legacy_admission(block)
            values=[self.state['nodes'][b] for b in ['025','005','009']]
            if all(v.get('state')=='completed' for v in values):return
            failures=[(b,self.state['nodes'][b].get('error')) for b in ['025','005','009'] if self.state['nodes'][b].get('state') in ['failed','partial']]
            if failures:
                # A just-resolved admission hold has already been replaced by starting.
                raise RuntimeError('Pilot requires review: '+str(failures))
            print('PILOTS',[(b,self.state['nodes'][b].get('state'),self.state['nodes'][b].get('stage')) for b in ['005','009']],flush=True)
            time.sleep(30)

    def run(self):
        resuming=self.state.get('phase') in ['remaining-blocks','collection','alignment']
        if not resuming:
            self.wait_pilots()
            self.state['phase']='wave-six';self.save()
            first=['001','002','003','004','018','012']
            second=['007','008','013','017','023','024']
            # Do not modify a live bundle. These blocks have only preflight metadata.
            for block in first+second:prepare(self.site,self.entries[block],update=True)
            for block in first:self.enable(block);time.sleep(10)
            started=time.monotonic();stable=0
            while True:
                self.poll(list(self.entries))
                failed=[b for b in first if self.state['nodes'][b].get('state')=='failed']
                if failed:raise RuntimeError('First parallel wave requires review: '+str(failed))
                terminal=all(self.state['nodes'][b].get('state') in ['completed','partial'] for b in first)
                healthy=all(self.state['nodes'][b].get('telemetry',{}).get('gpu_c',100)<80
                            and self.state['nodes'][b].get('telemetry',{}).get('cpu_c',100)<90
                            and self.state['nodes'][b].get('state')!='unreachable' for b in first)
                stable=stable+1 if healthy else 0
                if terminal or (time.monotonic()-started>=600 and stable>=3):break
                time.sleep(30)
            self.state['phase']='remaining-blocks';self.save()
            for block in second:self.enable(block);time.sleep(10)
        while True:
            self.poll(list(self.entries))
            if all(v.get('state') in ['completed','partial','failed'] for v in self.state['nodes'].values()):break
            time.sleep(30)
        self.state['phase']='collection';self.save()
        while any(not f.done() for f in self.collection_futures.values()):
            self.poll(list(self.entries));time.sleep(30)
        self.poll(list(self.entries))
        if not self.imports:raise RuntimeError('No collected inputs available for alignment')
        self.state['phase']='alignment';self.save()
        workspace=Path('/data/barranco/alignment/barranco-full-v1')
        self.scoped('campaign',[PROJECT/'tools/local_alignment.py','campaign','--workspace',workspace,
                    '--manifests',*[self.imports[b] for b in sorted(self.imports)]],CENTRAL/'alignment.log')
        runs=sorted((workspace/'runs').glob('*/result.json'),key=lambda p:p.stat().st_mtime)
        result=json.loads(runs[-1].read_text());mapping=result['largest_map']
        self.state['alignment']=result;self.save()
        self.scoped('dense-export',[PROJECT/'tools/local_alignment.py','export','--workspace',workspace,'--map',mapping],CENTRAL/'dense-export.log')
        self.scoped('sparse-preview',[PROJECT/'tools/local_alignment.py','export','--workspace',workspace,'--map',mapping,'--sparse','--color','by_block'],CENTRAL/'sparse-export.log')
        self.state['phase']='finished'
        connected=(len(result['components'])==1 and result['components'][0]['blocks']==len(self.entries)
                   and not result.get('audit_rejections') and result.get('technical_failures',0)==0)
        self.state['state']='completed' if all(v.get('state')=='completed' for v in self.state['nodes'].values()) and len(self.imports)==len(self.entries) and connected else 'partial'
        self.save()


if __name__=='__main__':
    with (CENTRAL/'execution-manager.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manager=Campaign()
        try:manager.run()
        except BaseException as exc:
            manager.state.update(state='needs_review',error=str(exc));manager.save();raise
