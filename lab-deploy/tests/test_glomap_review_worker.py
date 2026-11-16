import importlib.util
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch


def load():
    module=types.ModuleType('sparse_review_worker')
    class Base:
        def docker_args(self,*args,**kw):
            return 'name','token',['docker','--network','none','certified-image','command']
    module.SparseWorker=Base
    module.digest=lambda path:'test'
    with patch.dict(sys.modules,{'sparse_review_worker':module}):
        spec=importlib.util.spec_from_file_location('glomap_test',
            Path(__file__).resolve().parents[1]/'tools/glomap_review_worker.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


class GlomapTests(unittest.TestCase):
    def test_network_only_during_install_and_source_always_ro(self):
        m=load();worker=m.GlomapReviewWorker()
        worker.root=Path('/data/run')
        worker.spec={'images':{'reconstruction':{'tag':'certified-image'}},
                     'source_root':'/data/original','glomap_runtime':'/data/runtime/glomap'}
        for stage in ['install','sfm']:
            _,_,args=worker.docker_args(stage,'reconstruction',['command'])
            self.assertEqual(args[args.index('--network')+1],'bridge' if stage=='install' else 'none')
            mounts=[args[i+1] for i,v in enumerate(args) if v=='--mount']
            self.assertTrue(any('src=/data/original,' in v and v.endswith(',readonly') for v in mounts))
            self.assertTrue(any('src=/data/run/datasets,' in v and v.endswith(',readonly') for v in mounts))
            if stage=='sfm':self.assertTrue(all(v.endswith(',readonly') for v in mounts))
            self.assertNotIn('--gpus',args)

    def test_database_signature(self):
        m=load()
        with sqlite3.connect(':memory:') as db:
            for table in ['cameras','images','keypoints','descriptors','matches']:
                db.execute('CREATE TABLE '+table+' (id INTEGER)')
            db.execute('CREATE TABLE two_view_geometries (rows INTEGER)')
            db.executemany('INSERT INTO two_view_geometries VALUES (?)',[(0,),(100,)])
            result=m.database_signature(db)
            self.assertEqual(result['verified_pairs'],1)
            self.assertEqual(result['two_view_geometries'],2)


if __name__=='__main__':unittest.main()
