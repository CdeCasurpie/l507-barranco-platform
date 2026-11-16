import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from labdeploy.cli import manager
from labdeploy.store import Store


class FakeSSH:
    calls=[]
    jobs={}
    fail_first_poll=False
    failed=False
    def __init__(self,site,store):pass
    def call(self,ip,action,payload,**kw):
        tag=payload['spec']['tag']
        self.calls.append((tag,action,payload.get('operation')))
        if action=='status':
            if tag not in self.jobs:return {}
            if self.fail_first_poll and not self.failed:
                type(self).failed=True
                raise RuntimeError('temporary connection loss')
            return self.jobs[tag]
        if action=='assess':return {'locally_ready':False}
        if action=='probe':return {'mounted':False}
        if action=='volume':return {'output':'ok'}
        if action=='start':
            self.jobs[tag]={'job':payload['spec']['job'],'status':'success','release_digest':'a'*64}
            return {'job':payload['spec']['job']}
        raise AssertionError(action)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state')
        FakeSSH.calls=[];FakeSSH.jobs={};FakeSSH.failed=False;FakeSSH.fail_first_poll=False
        self.request={'id':'test-run','site':{'sources':['L507_014'],'nodes':{'L507_014':'mac14','L507_015':'mac15'},
                         'ssh_user':'utec_alumno','data_root':'/data/photogrammetry'},
                      'release':{'name':'test'},'release_digest':'a'*64,'parallel':1,'poll':0,
                      'targets':['L507_015'], 'inventory':{'L507_014':{'available':True,'ip':'source'},
                                                         'L507_015':{'available':True,'ip':'target'}}}

    def execute(self):
        path=self.store.root/'request.json';path.write_text(json.dumps(self.request))
        with patch('labdeploy.cli.SSH',FakeSSH),patch('labdeploy.cli.time.sleep',return_value=None):
            manager(path,self.store.root)
        return self.store.read('runs/test-run.json')

    def test_source_opened_and_restored_after_success(self):
        result=self.execute()
        self.assertEqual(result['status'],'success')
        operations=[p for p in FakeSSH.calls if p[1]=='volume']
        self.assertEqual(operations,[('L507_014','volume','open'),('L507_014','volume','close')])
        self.assertFalse(self.store.read('sources/L507_014.json')['pending_restore'])

    def test_transient_ssh_failure_does_not_abandon_running_worker(self):
        FakeSSH.fail_first_poll=True
        result=self.execute()
        self.assertTrue(FakeSSH.failed)
        self.assertEqual(result['status'],'success')
        self.assertEqual(sum(action=='start' for _,action,_ in FakeSSH.calls),1)

    def test_retry_reattaches_instead_of_starting_duplicate_worker(self):
        FakeSSH.jobs['L507_015']={'job':'existing','status':'running','release_digest':'a'*64}
        original=FakeSSH.call
        reads=[]
        def call(self,ip,action,payload,**kw):
            if action=='status' and payload['spec']['tag']=='L507_015':
                reads.append(1)
                if len(reads)>1:FakeSSH.jobs['L507_015']['status']='success'
            return original(self,ip,action,payload,**kw)
        with patch.object(FakeSSH,'call',call):result=self.execute()
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['nodes']['L507_015']['job'],'existing')
        self.assertFalse(any(action=='start' for _,action,_ in FakeSSH.calls))

    def test_unreachable_node_is_reported_without_remote_mutations(self):
        self.request['inventory']['L507_015']['available']=False
        result=self.execute()
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['nodes']['L507_015']['status'],'unavailable')
        self.assertFalse(FakeSSH.calls)


@unittest.skipUnless(shutil.which('rsync'),'rsync unavailable')
class RsyncResumeTests(unittest.TestCase):
    def test_interrupted_copy_with_bad_prefix_is_verified_and_repaired(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            original=root/'source';target=root/'partial'
            data=bytes(range(256))*8192
            original.write_bytes(data)
            target.write_bytes(b'wrong-prefix'+data[12:100000])
            result=subprocess.run(['rsync','-a','--partial','--append-verify',str(original),str(target)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),hashlib.sha256(data).hexdigest())


if __name__=='__main__':unittest.main()
