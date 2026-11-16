import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from labdeploy import agent,config,inventory
from labdeploy.cli import plan_rows
from labdeploy.store import atomic_json


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.release,_=config.release('l507-segmentation-v1')
        self.site=config.site(Path(__file__).resolve().parents[1]/'config/site.example.json')

    def test_certified_catalog_pins_real_images_and_weights(self):
        self.assertEqual(len(self.release['git']['commit']),40)
        self.assertEqual(len(self.release['images']),2)
        self.assertTrue(any(a.get('target')=='models/sam3/sam3.pt' for a in self.release['artifacts']))

    def test_artifact_cannot_escape_project(self):
        self.release['artifacts'][0]['target']='../../etc/passwd'
        with self.assertRaises(ValueError):config.validate_release(self.release)

    def test_credentials_rejected_in_manifest(self):
        self.release['environment']['HF_TOKEN']='not-a-real-secret'
        with self.assertRaises(ValueError):config.validate_release(self.release)

    def test_duplicate_artifact_names_rejected(self):
        self.release['artifacts'].append(self.release['artifacts'][0])
        with self.assertRaises(ValueError):config.validate_release(self.release)

    def test_master_is_not_selectable(self):
        with self.assertRaises(ValueError):
            inventory.selected(self.site,SimpleNamespace(all=False,targets='L507_MAESTRA'))

    def test_all_selects_registered_daughters_only(self):
        tags=inventory.selected(self.site,SimpleNamespace(all=True))
        self.assertTrue(all(t.startswith('L507_') and t[-3:].isdigit() for t in tags))
        self.assertNotIn('L507_MAESTRA',tags)

    def test_short_target_numbers_are_normalized_and_still_registered(self):
        self.assertEqual(inventory.selected(self.site,SimpleNamespace(all=False,targets='14,015,L507_014')),['L507_014','L507_015'])

    def test_plan_does_not_pretend_to_inspect_closed_volume(self):
        facts={'available':True,'ip':'10.0.0.1','facts':{'driver':'595.99.02','disks':[{}],'mounted':False}}
        value=plan_rows(self.site,{'L507_014':facts},['L507_014'],self.release)
        self.assertIn('unknown',value[0]['plan'])

    def test_future_pipeline_can_define_its_own_validation_metrics(self):
        self.release['verify']={'commands':[['python3','check_model.py']], 'metrics':None}
        config.validate_release(self.release)
        agent.validate_metrics({'model':{'loaded':True}},[{'field':'model.loaded','equals':True}],'L507_015')

    def test_wrong_node_in_metrics_is_rejected(self):
        with self.assertRaises(RuntimeError):
            agent.validate_metrics({'node':'L507_001'},[{'field':'node','equals':'${NODE_TAG}'}],'L507_015')

    def test_changed_image_cannot_reuse_old_release_tag(self):
        previous=[{'images':[{'tag':'image:v1','id':'old'}]}]
        with self.assertRaises(agent.Blocked):
            agent.image_namespace({'images':[{'tag':'image:v1','id':'new'}]},previous)
        agent.image_namespace({'images':[{'tag':'image:v2','id':'new'}]},previous)


class StateAndArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_concurrent_state_writers_always_leave_complete_json(self):
        path=self.root/'state.json'
        def writer(index):
            atomic_json(path,{'index':index,'body':'x'*2000})
            self.assertIn('index',json.loads(path.read_text()))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(writer,range(20)))
        self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_corrupt_cache_is_quarantined_and_original_file_unchanged(self):
        cache=self.root/'cache';cache.mkdir()
        original=self.root/'model';original.write_bytes(b'valid-model')
        sha=hashlib.sha256(original.read_bytes()).hexdigest()
        (cache/sha).write_bytes(b'corrupted')
        artifact={'sha256':sha,'bytes':len(b'valid-model')}
        result=agent.cache_file(original,artifact,cache,None)
        self.assertEqual(result.read_bytes(),b'valid-model')
        self.assertEqual(original.read_bytes(),b'valid-model')
        self.assertEqual(len(list(cache.glob('*.corrupt-*'))),1)

    def test_changed_unverified_asset_is_not_accepted(self):
        cache=self.root/'cache';cache.mkdir()
        file=self.root/'weights';file.write_bytes(b'wrong')
        artifact={'bytes':10,'sha256':'0'*64}
        self.assertIsNone(agent.cache_file(file,artifact,cache,None))
        self.assertFalse(any(cache.iterdir()))

    def test_policy_restored_after_install_failure(self):
        file=self.root/'policy';file.write_text('original policy');file.chmod(0o700)
        with self.assertRaises(RuntimeError):
            with agent.temporary_policy(file):
                self.assertIn('exit 101',file.read_text())
                raise RuntimeError('APT failed')
        self.assertEqual(file.read_text(),'original policy')
        self.assertEqual(file.stat().st_mode&0o777,0o700)

    def test_temporary_policy_removed_when_absent_originally(self):
        file=self.root/'policy'
        with agent.temporary_policy(file):self.assertTrue(file.exists())
        self.assertFalse(file.exists())

    def test_policy_left_by_killed_worker_is_recovered(self):
        file=self.root/'policy'
        file.write_text('#!/bin/sh\n# temporary lab-deploy service-start suppression\nexit 101\n')
        backup=self.root/'backup';backup.mkdir()
        agent.recover_policy(backup,file)
        self.assertFalse(file.exists())

    def test_existing_policy_recovered_after_abrupt_interruption(self):
        file=self.root/'policy'
        file.write_text('# temporary lab-deploy service-start suppression\n')
        backup=self.root/'backup'
        saved=backup/'usr/sbin/policy-rc.d';saved.parent.mkdir(parents=True)
        saved.write_text('original custom policy')
        agent.recover_policy(backup,file)
        self.assertEqual(file.read_text(),'original custom policy')

    def test_activation_retains_old_release_for_rollback(self):
        root=self.root
        a=root/'.lab-deploy/releases/a';a.mkdir(parents=True)
        b=root/'.lab-deploy/releases/b';b.mkdir(parents=True)
        agent.activate(root,a,{'release':'a'})
        agent.activate(root,b,{'release':'b'})
        self.assertEqual((root/'.lab-deploy/current').resolve(),b)
        self.assertEqual(json.loads((a/'meta.json').read_text())['release'],'a')
        agent.activate(root,a,{'release':'a'})
        self.assertEqual((root/'.lab-deploy/current').resolve(),a)

    def test_unsafe_existing_current_directory_is_not_deleted(self):
        current=self.root/'.lab-deploy/current';current.mkdir(parents=True)
        (current/'user-file').write_text('keep')
        candidate=self.root/'release';candidate.mkdir()
        with self.assertRaises(agent.Blocked):agent.activate(self.root,candidate,{})
        self.assertEqual((current/'user-file').read_text(),'keep')

    def test_release_directories_work_with_private_worker_umask(self):
        account=SimpleUser()
        old=os.umask(0o077)
        try:
            agent.user_parents(self.root/'datasets/raw/scene/drone',self.root,account)
        finally:os.umask(old)
        for relative in ['datasets','datasets/raw','datasets/raw/scene','datasets/raw/scene/drone']:
            self.assertEqual((self.root/relative).stat().st_uid,os.getuid())

    def test_initial_snapshot_does_not_back_up_new_configs_as_originals(self):
        backup=self.root/'backup';backup.mkdir()
        absent=self.root/'absent'
        agent.snapshot_host(backup,[str(absent)],packages='pkg\t1\n')
        absent.write_text('created during installation')
        agent.snapshot_host(backup,[str(absent)],packages='pkg\t2\n')
        self.assertFalse((backup/absent.relative_to('/')).exists())
        self.assertFalse(json.loads((backup/'snapshot.json').read_text())['present_before'][str(absent)])
        self.assertEqual((backup/'packages.tsv').read_text(),'pkg\t1\n')


class SimpleUser:
    pw_uid=os.getuid()
    pw_gid=os.getgid()


class IdentityAndDiscoveryTests(unittest.TestCase):
    def test_remote_agent_rejects_master_before_account_access(self):
        with self.assertRaises(agent.Blocked):agent.guard({'tag':'L507_MAESTRA'})

    def test_local_disk_selection_excludes_os_even_with_cloned_uuid(self):
        data={'blockdevices':[{'path':'/dev/nvme0','children':[
            {'path':'/dev/nvme0p1','type':'part','fstype':'ext4','size':500*1024**3,'uuid':'cloned','mountpoints':['/']},
            {'path':'/dev/nvme0p6','type':'part','fstype':'ext4','size':488*1024**3,'uuid':'cloned','mountpoints':[None]}]}]}
        response=subprocess.CompletedProcess([],0,json.dumps(data),'')
        with patch.object(agent,'run',return_value=response):
            result=agent.disks()
        self.assertEqual([p['path'] for p in result],['/dev/nvme0p6'])

    def test_gpu_workload_blocks_enrollment(self):
        def fake(command,**kw):
            return subprocess.CompletedProcess(command,0,'1234\n' if command[0]=='nvidia-smi' else '','')
        with patch.object(agent,'run',side_effect=fake),patch.object(agent.shutil,'which',return_value=None):
            with self.assertRaises(agent.Blocked):agent.idle()


if __name__=='__main__':unittest.main()
