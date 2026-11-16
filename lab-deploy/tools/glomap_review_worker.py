"""Isolated GLOMAP installation and sparse-only run, certified supervisor."""
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import sqlite3
import struct
import sys
import time
import subprocess
from sparse_review_worker import SparseWorker, digest


def database_signature(db):
    result={}
    for table in ['cameras','images','keypoints','descriptors','matches','two_view_geometries']:
        result[table]=db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
    result['verified_pairs']=db.execute('SELECT COUNT(*) FROM two_view_geometries WHERE rows>0').fetchone()[0]
    return result


class GlomapReviewWorker(SparseWorker):
    def docker_args(self,stage,role,argv,gpu=False):
        name,token,args=super().docker_args(stage,role,argv,gpu=False)
        index=args.index(self.spec['images'][role]['tag'])
        runtime=self.spec['glomap_runtime']
        args[index:index]=['--mount',f'type=bind,src={runtime},dst={runtime}'+('' if stage=='install' else ',readonly'),
                          '--mount',f'type=bind,src={self.spec["source_root"]},dst={self.spec["source_root"]},readonly',
                          '--mount',f'type=bind,src={self.root}/datasets,dst={self.root}/datasets,readonly']
        if stage=='install':
            args[args.index('--network')+1]='bridge'
        return name,token,args

    def run(self):
        self.preflight()
        assert float(subprocess.check_output(['nvidia-smi','--query-gpu=power.limit',
            '--format=csv,noheader,nounits'],text=True).strip())==100
        runtime=Path(self.spec['glomap_runtime'])
        env=runtime/'env'
        self.stage('install','reconstruction',[
            str(self.root/'micromamba'),'--no-rc','--root-prefix',str(runtime/'mamba'),
            'create','--yes','--prefix',str(env),'--channel','conda-forge',
            '--strict-channel-priority','glomap=1.1.0=h930c707_0'],gpu=False,timeout=3600)
        self.stage('glomap_help','reconstruction',[str(env/'bin/glomap'),'mapper','-h'],gpu=False,timeout=60)
        help_text=(self.log_dir/'glomap_help.log').read_text()
        assert 'database_path' in help_text and 'output_path' in help_text
        packages={}
        for path in sorted((env/'conda-meta').glob('*.json')):
            item=json.loads(path.read_text())
            packages[item['name']]={key:item.get(key) for key in ['version','build','sha256','url']}
        assert packages['glomap']['version']=='1.1.0'
        assert digest(env/'bin/glomap')  # Pin actual installed executable.
        (self.root/'runtime-receipt.json').write_text(json.dumps({
            'binary_sha256':digest(env/'bin/glomap'),'packages':packages,
            'installed_at':time.time(),'scope':'isolated /data runtime; certified release unchanged'},indent=2))
        out=self.root/'outputs/cuadra-020'/self.experiment
        out.mkdir(parents=True,exist_ok=True)
        (out/'config_resolved.yaml').write_text((self.root/'config-full.json').read_text())
        col=out/'colmap'
        col.mkdir(parents=True)
        source=Path(self.spec['source_database'])
        original_hash=digest(source)
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
            src.execute('PRAGMA query_only=ON')
            before=database_signature(src)
            assert before['images']==970 and before['verified_pairs']>0
            with sqlite3.connect(col/'database.db') as dst:
                src.backup(dst)
                assert dst.execute('PRAGMA quick_check').fetchone()[0]=='ok'
                assert database_signature(dst)==before
        assert digest(source)==original_hash
        (self.root/'database-copy.json').write_text(json.dumps({
            'source':str(source),'source_sha256':original_hash,
            'snapshot_sha256':digest(col/'database.db'),'tables':before,
            'method':'SQLite backup from read-only source; only derived DB writable'},indent=2))
        self.save(database_reused=before,source_database_sha256=original_hash)
        sparse=col/'sparse';sparse.mkdir()
        command=[str(env/'bin/glomap'),'mapper','--database_path',str(col/'database.db'),
                 '--image_path',self.spec['source_frames'],'--output_path',str(sparse)]
        self.stage('sfm','reconstruction',command,gpu=False,timeout=12*3600)
        assert digest(source)==original_hash,'Source database changed during mapping'
        models={}
        for path in sorted(sparse.glob('*/images.bin')):
            with path.open('rb') as stream:images,=struct.unpack('<Q',stream.read(8))
            with (path.parent/'points3D.bin').open('rb') as stream:points,=struct.unpack('<Q',stream.read(8))
            models[path.parent.name]=dict(registered_images=images,points3D=points)
        assert models,'No COLMAP binary component was exported; inspect without automatic retry'
        best=max(models,key=lambda k:models[k]['registered_images'])
        (col/'best_model.txt').write_text(best)
        (out/'metrics').mkdir()
        (out/'metrics/glomap_run.json').write_text(json.dumps({
            'engine':'GLOMAP','version':'1.1.0','components':models,'input_database':before,
            'source_database_unchanged':True,'geometry_approved':False},indent=2))
        self.save(state='awaiting_review',stage='sparse_review',sparse_ready=True,
            sparse_model=str(sparse/best),registered_images=models[best]['registered_images'],
            components=models,geometry_approved=False,dense_authorized=False,
            mesh_authorized=False,alignment_authorized=False,finished_at=time.time())


if __name__=='__main__':
    root=Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=GlomapReviewWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
        signal.signal(signal.SIGINT,lambda *_:setattr(worker,'cancelled',True))
        try:worker.run()
        except BaseException as error:
            worker.save(state='failed',error=str(error),finished_at=time.time())
            raise
