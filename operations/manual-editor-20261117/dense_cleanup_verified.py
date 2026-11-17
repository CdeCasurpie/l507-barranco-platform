"""Delete only authorized depth-map caches after verifying retained dense inputs."""
import hashlib
import json
from pathlib import Path
import stat
import time

AUTHORIZED={'006','010','011','014','015','020','021','027'}
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(8*1024**2),b''):h.update(data)
    return h.hexdigest()

def cleanup_verified_chunk(directory,done):
    directory=Path(directory)
    # These are our derived run directories, never the original campaign.
    root=next((p for p in directory.parents if (p/'cleanup-authorization.json').is_file()),None)
    if root is None:raise RuntimeError('Missing explicit cleanup authorization')
    authorization=json.loads((root/'cleanup-authorization.json').read_text())
    assert authorization['block'] in AUTHORIZED and authorization['block']!='026'
    assert authorization['allowed_suffix']=='.dmap' and authorization['completed_only'] is True
    assert directory.resolve().is_relative_to(root.resolve())
    assert not directory.is_symlink()
    receipt=directory/'batch-receipt.json'
    # JSON serializes schema tuples as lists; compare the serialized content,
    # not the incidental in-memory representation of a newly completed batch.
    assert receipt.is_file() and json.loads(receipt.read_text())==json.loads(json.dumps(done))
    scalar=directory/'scene_dense_scalar.ply'
    native=directory/'scene_dense.ply'
    scene=directory/'scene_dense.mvs'
    assert scalar.is_file() and native.is_file() and scene.is_file() and scene.stat().st_size>0
    cloud=done['cloud']
    assert cloud['vertices']>0
    assert sha(scalar)==cloud['sha256'],'Scalar dense cloud changed'
    assert sha(native)==cloud['source_sha256'],'Native dense cloud changed'
    paths=[]
    for path in directory.rglob('*.dmap'):
        if path.is_symlink():continue
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode):continue
        assert path.resolve().is_relative_to(directory.resolve())
        paths.append((path,info))
    log=root/'cleanup-audit.jsonl'
    removed=0
    for path,info in paths:
        # Record exact targets before removal. No directory-wide deletion.
        with log.open('a') as stream:
            stream.write(json.dumps(dict(action='delete_verified_depth_cache',path=str(path),
                bytes=info.st_size,mtime_ns=info.st_mtime_ns,at=time.time(),
                scalar_sha256=cloud['sha256'],native_sha256=cloud['source_sha256']))+'\n')
        now=path.lstat()
        assert (now.st_ino,now.st_size,now.st_mtime_ns)==(info.st_ino,info.st_size,info.st_mtime_ns)
        path.unlink()
        removed+=info.st_size
    return dict(chunk=directory.name,removed_files=len(paths),removed_bytes=removed)
