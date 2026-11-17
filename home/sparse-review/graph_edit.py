"""Graph deformation drafts. Sources remain immutable; no dense execution."""
from array import array
import base64
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import threading
import time
import uuid
import shutil
import subprocess

from app import read_cameras, read_points, encode_cloud

STATE = Path('/data/barranco/manual-graph-editor')
LOCK = threading.RLock()


def fingerprint(model):
    hashes = {}
    for name in ('cameras.bin', 'images.bin', 'points3D.bin'):
        h = hashlib.sha256()
        with (model/name).open('rb') as f:
            for b in iter(lambda: f.read(4*1024**2), b''):
                h.update(b)
        hashes[name] = h.hexdigest()
    return hashes


def family(name):
    path = Path(name)
    if re.fullmatch(r'frame_\d+_[bc]', path.stem):
        return str(path.parent/'frame')
    return str(path.parent/re.sub(r'_\d+$', '', path.stem))


@lru_cache(maxsize=1)
def graph(model_string, signatures):
    import numpy as np
    model = Path(model_string)
    hashes = fingerprint(model)
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    cameras = read_cameras(model/'images.bin')
    if not 2 <= len(cameras) < 65535:
        raise ValueError('Editor supports 2–65534 views')
    lookup = {c['id']: i for i, c in enumerate(cameras)}
    covariance = np.zeros((len(cameras), len(cameras)), dtype=np.int32)
    points = read_points(model/'points3D.bin', budget=80_000)
    binary, info = encode_cloud(points, cameras)
    offsets, memberships = array('I', [0]), array('H')
    with (model/'points3D.bin').open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        step = max(1, math.ceil(count/80_000))
        for i in range(count):
            _, x,y,z,red,green,blue,error,n = struct.unpack('<QdddBBBdQ', f.read(51))
            if n > 10_000_000:
                raise ValueError('Invalid track length')
            track = f.read(n*8)
            if len(track) != n*8:
                raise ValueError('Truncated track')
            members = sorted({lookup[a] for a,b in struct.iter_unpack('<II', track) if a in lookup})
            if members:
                covariance[np.ix_(members, members)] += 1
            if i % step == 0 and all(math.isfinite(v) for v in (x,y,z,error)):
                memberships.extend(members)
                offsets.append(len(memberships))
    assert len(offsets)-1 == info['points']
    np.fill_diagonal(covariance, 0)
    edges = {}
    for i in range(len(cameras)):
        neighbors = np.argsort(covariance[i])[-6:]
        for j in neighbors:
            shared = int(covariance[i,j])
            if shared >= 10:
                a,b = sorted((i,int(j)))
                edges[a,b] = dict(a=a,b=b,weight=min(5., math.sqrt(shared)/10),
                                  kind='visual',shared_points=shared)
    groups = defaultdict(list)
    for i,c in enumerate(cameras):
        groups[family(c['name'])].append(i)
    for indices in groups.values():
        indices.sort(key=lambda i:cameras[i]['name'])
        for k,i in enumerate(indices):
            for lag,j in enumerate(indices[k+1:k+6],1):
                a,b = sorted((i,j))
                edges.setdefault((a,b), dict(a=a,b=b,weight=.15/lag,
                    kind='temporal_prior',shared_points=int(covariance[a,b])))
    meta = dict(revision=revision,source_hashes=hashes,**info,edges=list(edges.values()),
                offsets=base64.b64encode(offsets.tobytes()).decode(),
                memberships=base64.b64encode(memberships.tobytes()).decode(),
                preview_only=True,dense_authorized=False,
                note='Visual edges are track support; temporal edges are movement priors, NOT verified matches.')
    return meta,binary


def get_graph(model):
    signatures = tuple((model/n).stat().st_mtime_ns for n in ('cameras.bin','images.bin','points3D.bin'))
    with LOCK:
        return graph(str(model), signatures)


def validate_request(model, body):
    meta,_ = get_graph(model)
    if body.get('revision') != meta['revision']:
        raise ValueError('Source revision changed; reload without overwriting draft')
    pins = body.get('pins', [])
    if not isinstance(pins,list) or len(pins)>200:
        raise ValueError('At most 200 camera constraints')
    known = {c['id']:c for c in meta['cameras']}
    deleted=body.get('deleted',[])
    if not isinstance(deleted,list) or any(type(i) is not int or i not in known for i in deleted) or len(deleted)!=len(set(deleted)):
        raise ValueError('Invalid excluded camera IDs')
    if len(known)-len(deleted)<2:
        raise ValueError('Keep at least two cameras')
    seen = set()
    for pin in pins:
        image = pin.get('id')
        if image not in known or image in deleted or image in seen or pin.get('kind') not in ('move','anchor'):
            raise ValueError('Invalid or duplicate camera constraint')
        seen.add(image)
        target = pin.get('target')
        if not isinstance(target,list) or len(target)!=3 or not all(
                type(v) in (int,float) and math.isfinite(v) for v in target):
            raise ValueError('Finite XYZ required')
        center = known[image]['center']
        if math.dist(target,center)>meta['display_radius']*5:
            raise ValueError('Displacement exceeds safety bound')
        if pin['kind']=='anchor' and math.dist(target,center)>1e-10:
            raise ValueError('Fixed anchors must keep their original centers')
        angles=pin.get('rotation',[0,0,0])
        if not isinstance(angles,list) or len(angles)!=3 or not all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=3600 for v in angles):
            raise ValueError('Finite XYZ rotation angles required')
        if pin['kind']=='anchor' and any(abs(v)>1e-10 for v in angles):
            raise ValueError('Fixed anchors cannot rotate')
    stiffness = body.get('stiffness',1.)
    if type(stiffness) not in (int,float) or not math.isfinite(stiffness) or not .01<=stiffness<=100:
        raise ValueError('Stiffness must be 0.01–100')
    radius=body.get('radius',10)
    if type(radius) is not int or not 1<=radius<=200:
        raise ValueError('Graph radius must be 1–200 connections')
    if body.get('influence_mode','elastic') not in ('elastic','legacy'):
        raise ValueError('Invalid influence mode')
    return meta,pins,float(stiffness)


def solve(model,body):
    import numpy as np
    from scipy.sparse import coo_matrix,eye
    from scipy.sparse.linalg import spsolve
    from scipy.spatial.transform import Rotation
    meta,pins,stiffness = validate_request(model,body)
    n = len(meta['cameras'])
    rows,cols,values = [],[],[]
    for edge in meta['edges']:
        a,b,w = edge['a'],edge['b'],edge['weight']
        if meta['cameras'][a]['id'] in body.get('deleted',[]) or meta['cameras'][b]['id'] in body.get('deleted',[]):
            continue
        rows += [a,b,a,b];cols += [a,b,b,a];values += [w,w,-w,-w]
    matrix = coo_matrix((values,(rows,cols)),shape=(n,n)).tocsr()+stiffness*eye(n,format='csr')
    lookup={c['id']:i for i,c in enumerate(meta['cameras'])}
    displacement=np.zeros((n,3))
    rotations=np.tile(np.eye(3),(n,1,1))
    fixed=np.array([lookup[p['id']] for p in pins],dtype=int)
    if len(fixed):
        free=np.array(sorted(set(range(n))-set(fixed)),dtype=int)
        influence=np.zeros((n,len(pins)))
        influence[fixed]=np.eye(len(pins))
        if body.get('influence_mode','elastic')=='elastic':
            from collections import deque
            neighbors=[set() for _ in range(n)]
            deleted=set(body.get('deleted',[]))
            for edge in meta['edges']:
                a,b=edge['a'],edge['b']
                if meta['cameras'][a]['id'] in deleted or meta['cameras'][b]['id'] in deleted:continue
                neighbors[a].add(b);neighbors[b].add(a)
            radius=1 if body.get('direct_only',False) else body.get('radius',10)
            blocked=set(fixed)
            for j,root in enumerate(fixed):
                distances={int(root):0};queue=deque([int(root)])
                while queue:
                    a=queue.popleft()
                    if distances[a]>=radius:continue
                    for b in neighbors[a]:
                        if b in distances or (b in blocked and b!=root):continue
                        distances[b]=distances[a]+1;queue.append(b)
                for i,d in distances.items():
                    # Rigid inner third, smooth decay; no effect outside graph radius.
                    x=max(0.,min(1.,(d-radius*.33)/max(1.,radius*.67)))
                    influence[i,j]=1.-x*x*(3.-2.*x)
                    if radius==1 and d==1:influence[i,j]=.75
            totals=influence.sum(axis=1)
            influence/=np.maximum(1.,totals)[:,None]
            influence[fixed]=np.eye(len(pins))
        elif len(free):
            weights=spsolve(matrix[free][:,free],-matrix[free][:,fixed].toarray())
            influence[free]=np.asarray(weights).reshape(len(free),len(pins))
        centers=np.array([c['center'] for c in meta['cameras']])
        vectors=[]
        for j,pin in enumerate(pins):
            origin=centers[fixed[j]]
            rotation=Rotation.from_euler('xyz',pin.get('rotation',[0,0,0]),degrees=True)
            if pin.get('rotation_space')=='camera':
                camera_rotation=np.array(meta['cameras'][fixed[j]]['rotation'])
                rotation=Rotation.from_matrix(camera_rotation.T@rotation.as_matrix()@camera_rotation)
            vectors.append(rotation.as_rotvec())
            induced=rotation.apply(centers-origin)+np.array(pin['target'])-centers
            displacement+=influence[:,j,None]*induced
        rotations=Rotation.from_rotvec(influence@np.array(vectors)).as_matrix()
    if not np.isfinite(displacement).all():
        raise ValueError('Invalid deformation solution')
    return dict(revision=meta['revision'],displacements=displacement.tolist(),rotations=rotations.tolist(),
                preview_only=True,geometry_approved=False,dense_authorized=False)


def save_revision(model,body,dataset_id,component):
    meta,pins,stiffness=validate_request(model,body)
    STATE.mkdir(parents=True,exist_ok=True)
    identity='g-'+uuid.uuid4().hex
    record=dict(id=identity,dataset_id=dataset_id,component=component,
                source_model=str(model),source_hashes=meta['source_hashes'],
                revision=meta['revision'],pins=pins,stiffness=stiffness,deleted=body.get('deleted',[]),
                radius=body.get('radius',10),direct_only=bool(body.get('direct_only',False)),
                influence_mode=body.get('influence_mode','elastic'),
                created_at=time.time(),status='manual_draft_unvalidated',
                geometry_approved=False,dense_authorized=False)
    receipt=model.parents[2]/'collection.json'
    if receipt.is_file():
        source=json.loads(receipt.read_text())
        record['source_lineage']={key:source.get(key) for key in ('root','tag','node','block','destination')}
    with (STATE/(identity+'.json')).open('x') as f:
        json.dump(record,f,indent=2)
    return record


def start_job(model,body,dataset_id,component):
    import numpy as np
    meta,pins,stiffness=validate_request(model,body)
    database=model.parents[1]/'database.db'
    if not database.is_file():
        raise ValueError('Falta preparar la BD de matches local de esta variante para retriangular sin BA')
    if len(pins)<2 or not any(p['kind']=='move' for p in pins) or not any(p['kind']=='anchor' for p in pins):
        raise ValueError('Require a moved camera and a separate fixed anchor')
    centers=np.array([p['target'] for p in pins])
    if np.max(np.linalg.norm(centers-centers[0],axis=1))<meta['display_radius']*.001:
        raise ValueError('Constraints too close to fix scale reliably')
    with LOCK:
        jobs=STATE/'jobs';jobs.mkdir(parents=True,exist_ok=True)
        for status in jobs.glob('*/status.json'):
            if json.loads(status.read_text()).get('state') in ('starting','running'):
                raise ValueError('An editor job is already active; do not launch duplicates')
        memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(memory['MemAvailable'].split()[0])/1024**2<44:
            raise ValueError('Insufficient RAM reserve for a 40 GiB adjustment')
        if shutil.disk_usage(STATE).free<50*2**30:
            raise ValueError('Insufficient /data reserve')
        draft=save_revision(model,body,dataset_id,component)
        result=solve(model,body)
        identity='j-'+uuid.uuid4().hex
        job=jobs/identity;job.mkdir()
        request=dict(draft=draft,camera_ids=[c['id'] for c in meta['cameras']],
                     displacements=result['displacements'],rotations=result['rotations'],
                     database_path=str(database),mode='triangulation_only')
        (job/'request.json').write_text(json.dumps(request))
        for name in ('graph_job.py','graph_edit.py','app.py'):
            shutil.copy2(Path(__file__).parent/name,job/name)
        (job/'status.json').write_text(json.dumps(dict(state='starting',id=identity,
            dataset_id=dataset_id,component=component,geometry_approved=False,dense_authorized=False)))
        unit='barranco-manual-'+identity
        command=['systemd-run','--user','--unit='+unit,
                 '-p','MemoryMax=40G','-p','MemorySwapMax=0','-p','CPUQuota=400%',
                 '-p','RuntimeMaxSec=3600','-p','Nice=10',
                 '-E','OMP_NUM_THREADS=4','-E','OPENBLAS_NUM_THREADS=4',
                 '/data/barranco/runtime/alignment311/bin/python','-B',str(job/'graph_job.py'),str(job)]
        p=subprocess.run(command,capture_output=True,text=True,timeout=15)
        if p.returncode:
            (job/'status.json').write_text(json.dumps(dict(state='failed',error='Failed to start bounded service')))
            raise ValueError('Could not start bounded service; preserved request')
        return dict(id=identity,unit=unit,state='starting',draft_id=draft['id'],
                    geometry_approved=False,dense_authorized=False)
