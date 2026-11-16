import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch


TOOLS=Path(__file__).resolve().parents[1]/'tools'


def module(name):
    spec=importlib.util.spec_from_file_location(name,TOOLS/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


worker=module('reconstruction_worker')
post=module('campaign_post')
import sys
sys.path.insert(0,str(TOOLS))
batches=module('dense_batches')


class ReconstructionGuardTests(unittest.TestCase):
    def setUp(self):
        self.normal={'gpu_c':40,'cpu_c':50,'ssd_c':30,'root_free_gib':4.24,'data_free_gib':300,'ram_available_gib':56}

    def test_low_root_admission_margin_is_not_arbitrary_five_gib(self):
        self.assertEqual(worker.Guard().evaluate(self.normal,0),[])
        self.assertIn('root_free_gib',worker.Guard().evaluate(dict(self.normal,root_free_gib=3.4),0))
        with self.assertRaisesRegex(RuntimeError,'SAFETY STOP'):
            worker.Guard().evaluate(dict(self.normal,root_free_gib=2.9),0)

    def test_sustained_threshold_resets_after_cooling(self):
        g=worker.Guard();hot=dict(self.normal,gpu_c=80)
        g.evaluate(hot,0);g.evaluate(hot,29);g.evaluate(self.normal,29.5)
        g.evaluate(hot,30);g.evaluate(hot,59)
        with self.assertRaisesRegex(RuntimeError,'sustained'):
            g.evaluate(hot,60)

    def test_severe_temperature_and_disk_pressure_stop_immediately(self):
        for key,value in [('gpu_c',85),('cpu_c',95),('ssd_c',80),('data_free_gib',49)]:
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'SAFETY STOP'):
                worker.Guard().evaluate(dict(self.normal,**{key:value}),0)

    def test_cannot_stop_other_runs_container(self):
        w=worker.Worker.__new__(worker.Worker)
        response=type('Response',(),{'returncode':0,'stdout':json.dumps({'photogrammetry.run':'someone-else','photogrammetry.campaign':'barranco-full-v1'})})()
        with patch.object(worker.subprocess,'run',return_value=response) as command:
            with self.assertRaisesRegex(RuntimeError,'not owned'):
                w.stop_owned('some-container','this-run')
            self.assertEqual(command.call_count,1)


class DenseAdapterTests(unittest.TestCase):
    def test_assembly_accepts_cached_json_and_fresh_property_representations(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=root/'a.ply';b=root/'b.ply'
            header=b'ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n'
            a.write_bytes(header+struct.pack('<fff',1,2,3));b.write_bytes(header+struct.pack('<fff',4,5,6))
            fresh={'vertices':1,'properties':[('float','x'),('float','y'),('float','z')]}
            cached=json.loads(json.dumps(fresh))
            target=root/'combined.ply';result=batches.assemble([(a,cached),(b,fresh)],target)
            self.assertEqual(result['vertices'],2)
            self.assertEqual(target.read_bytes().split(b'end_header\n')[1],struct.pack('<ffffff',1,2,3,4,5,6))

    def test_batches_cover_every_camera_once_as_core_and_respect_memory_bound(self):
        views={i:{'name':f'video_{i:04d}.jpg'} for i in range(151)}
        tracks={i:((0,0,0),list(range(i,min(i+8,151)))) for i in range(151)}
        plan=batches.plan_batches(views,tracks)
        self.assertEqual(sorted(i for p in plan for i in p['core']),list(views))
        for p in plan:
            self.assertLessEqual(len(p['selected']),64)
            self.assertEqual(set(p['selected']),set(p['core'])|set(p['halo']))
            self.assertFalse(set(p['core'])&set(p['halo']))

    def cloud(self,path,truncated=False):
        header=b'ply\nformat binary_little_endian 1.0\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nproperty list uchar uint view_indices\nproperty list uchar float view_weights\nend_header\n'
        scalars=[struct.pack('<fffBBB',1,2,3,4,5,6),struct.pack('<fffBBB',-7,8,9,10,11,12)]
        payload=scalars[0]+b'\x02'+struct.pack('<II',1,5)+b'\x02'+struct.pack('<ff',.1,.9)
        payload+=scalars[1]+b'\x01'+struct.pack('<I',3)+b'\x01'+struct.pack('<f',.5)
        path.write_bytes(header+payload[:-1] if truncated else header+payload)
        return scalars

    def test_preserves_scalar_bytes_and_original_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.ply';target=Path(directory)/'scalar.ply'
            scalars=self.cloud(source);before=source.read_bytes()
            receipt=post.scalar_ply(source,target)
            self.assertEqual(receipt['vertices'],2)
            self.assertEqual(target.read_bytes().split(b'end_header\n')[1],b''.join(scalars))
            self.assertEqual(source.read_bytes(),before)

    def test_truncated_visibility_payload_is_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.ply';target=Path(directory)/'scalar.ply'
            self.cloud(source,truncated=True)
            with self.assertRaisesRegex(RuntimeError,'Truncated'):
                post.scalar_ply(source,target)
            self.assertFalse(target.exists())
