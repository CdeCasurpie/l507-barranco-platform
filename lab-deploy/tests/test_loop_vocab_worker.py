import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class LoopWorkerTests(unittest.TestCase):
    def test_inputs_are_readonly_but_output_root_remains_writable(self):
        fake = types.ModuleType('sparse_review_worker')

        class Base:
            def docker_args(self, *args, **kwargs):
                return 'container', 'token', ['docker', '--mount', 'root-rw', 'image:certified', 'command']

        fake.SparseWorker = Base
        fake.digest = lambda path: None
        source = Path(__file__).resolve().parents[1]/'tools/loop_vocab_worker.py'
        with patch.dict(sys.modules, {'sparse_review_worker': fake}):
            spec = importlib.util.spec_from_file_location('loop_under_test', source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        worker = module.LoopVocabWorker()
        worker.root = Path('/data/test-run')
        worker.spec = {'images': {'reconstruction': {'tag': 'image:certified'}}}
        worker.assignment = {'block_id': '020'}
        worker.experiment = 'test'
        name, token, args = worker.docker_args('sfm', 'reconstruction', ['command'])
        self.assertEqual((name, token), ('container', 'token'))
        mounts = [args[i+1] for i, item in enumerate(args) if item == '--mount']
        self.assertEqual(mounts[0], 'root-rw')
        self.assertEqual(len(mounts), 5)
        for mount in mounts[1:]:
            self.assertTrue(mount.endswith(',readonly'))
        self.assertEqual(args[-2:], ['image:certified', 'command'])


if __name__ == '__main__':
    unittest.main()
