"""Read-only binary/SQLite track audit for original and mixed-rate 019."""
import json
import math
from pathlib import Path
import sqlite3
import statistics
import struct


def headers(path, mixed):
    infos = {}
    with path.open('rb') as stream:
        count, = struct.unpack('<Q', stream.read(8))
        for _ in range(count):
            image_id, qw, qx, qy, qz, tx, ty, tz, camera = struct.unpack('<i7di', stream.read(64))
            name = bytearray()
            while True:
                c = stream.read(1)
                if not c:
                    raise ValueError('Truncated image name')
                if c == b'\0':
                    break
                name.extend(c)
            name = name.decode()
            n, = struct.unpack('<Q', stream.read(8))
            offset = stream.tell()
            stream.seek(n*24, 1)
            norm = math.sqrt(qw*qw+qx*qx+qy*qy+qz*qz)
            w, x, y, z = [v/norm for v in (qw, qx, qy, qz)]
            rotation = [[1-2*y*y-2*z*z, 2*x*y-2*w*z, 2*x*z+2*w*y],
                        [2*x*y+2*w*z, 1-2*x*x-2*z*z, 2*y*z-2*w*x],
                        [2*x*z-2*w*y, 2*y*z+2*w*x, 1-2*x*x-2*y*y]]
            center = [-sum(rotation[k][j]*[tx,ty,tz][k] for k in range(3)) for j in range(3)]
            stem = Path(name).stem
            seconds = int(stem.split('_')[1])/1e6 if mixed else (int(stem.rsplit('_',1)[1])-1)/2
            assert seconds not in infos
            infos[seconds] = dict(id=image_id, name=name, count=n, offset=offset, center=center)
        assert stream.tell() == path.stat().st_size
    return infos


def observations(stream, info):
    stream.seek(info['offset'])
    data = stream.read(info['count']*24)
    assert len(data) == info['count']*24
    return list(struct.iter_unpack('<ddq', data))


def identity(db, info, obs):
    row = db.execute('SELECT image_id FROM images WHERE name=?', (info['name'],)).fetchone()
    assert row and row[0] == info['id'], 'DB/model image identity mismatch'
    rows, cols, data = db.execute('SELECT rows,cols,data FROM keypoints WHERE image_id=?', (info['id'],)).fetchone()
    assert rows == len(obs) and cols >= 2 and len(data) == rows*cols*4
    maximum = 0
    for i, (x,y,_) in enumerate(obs):
        u,v = struct.unpack_from('<ff', data, i*cols*4)
        maximum = max(maximum,abs(x-u),abs(y-v))
    assert maximum < 0.001, 'DB/model keypoint coordinates differ'
    return maximum


def pair(db, stream, left, right):
    a, b = observations(stream,left), observations(stream,right)
    differences = [identity(db,left,a), identity(db,right,b)]
    first, last = sorted([left['id'],right['id']])
    row = db.execute('SELECT rows,cols,data FROM two_view_geometries WHERE pair_id=?',
                     (2147483647*first+last,)).fetchone()
    groups = dict(both_missing=0, only_A_3D=0, only_B_3D=0, different_3D=0, same_3D=0)
    assert row is not None and row[1] == 2 and len(row[2]) == row[0]*8
    for i,j in struct.iter_unpack('<II',row[2]):
        if left['id'] > right['id']:
            i,j = j,i
        assert i < len(a) and j < len(b)
        pa,pb = a[i][2],b[j][2]
        if pa == -1 and pb == -1: key = 'both_missing'
        elif pb == -1: key = 'only_A_3D'
        elif pa == -1: key = 'only_B_3D'
        elif pa == pb: key = 'same_3D'
        else: key = 'different_3D'
        groups[key] += 1
    assert sum(groups.values()) == row[0]
    return dict(A=left['name'], B=right['name'], image_ids=[left['id'],right['id']],
                verified_matches=row[0], groups=groups,
                shared_points_any_observation=len({p[2] for p in a if p[2]>=0}&{p[2] for p in b if p[2]>=0}),
                center_distance=math.dist(left['center'],right['center']),
                max_keypoint_coordinate_difference_px=max(differences))


def audit(root, mixed):
    status = json.loads((root/'reconstruction-full-status.json').read_text())
    assert status['state'] == 'awaiting_review'
    out = root/'outputs/cuadra-019'/status['experiment']
    selected = (out/'colmap/best_model.txt').read_text().strip()
    assert selected.isdigit()
    model = out/'colmap/sparse'/selected/'images.bin'
    infos = headers(model,mixed)
    times = sorted(infos)
    edges = []
    for t,u in zip(times,times[1:]):
        d = math.dist(infos[t]['center'],infos[u]['center'])
        edges.append(dict(start_seconds=t,end_seconds=u,delta_seconds=u-t,
                          center_distance=d,speed=d/(u-t)))
    median = statistics.median(e['speed'] for e in edges if e['speed']>0)
    for e in edges:
        e['speed_ratio_to_global_positive_median'] = e['speed']/median
    edges.sort(key=lambda e:e['speed'],reverse=True)
    database = out/'colmap/database.db'
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db, model.open('rb') as stream:
        db.execute('PRAGMA query_only=ON')
        pairs = []
        targets = {(413.5,414.0),(247.0,247.5)}
        for start,end in [(412,416),(245.5,249)]:
            window = [t for t in times if start<=t<=end]
            targets.update(zip(window,window[1:]))
        for t,u in sorted(targets):
            result = pair(db,stream,infos[t],infos[u])
            result.update(start_seconds=t,end_seconds=u)
            pairs.append(result)
    return dict(root=str(root),model=str(model),database=str(database),
                images=len(infos),median_positive_speed_sfm_units_per_second=median,
                time_basis='mixed filename microseconds' if mixed else 'original sample index at 2fps',
                top_20_jumps=edges[:20],all_trajectory_edges=edges,pairs=pairs,
                caveat='Final associations cannot distinguish never triangulated from later filtered.')


if __name__ == '__main__':
    assert (Path.home()/'L507_004.txt').is_file()
    expected = EXPECTED_MAC
    assert expected in [p.read_text().strip() for p in Path('/sys/class/net').glob('*/address')]
    base = Path('/data/photogrammetry/campaigns')
    result = {
        'original':audit(base/'barranco-running-20261116/cuadra-019',False),
        'cut10fps':audit(base/'barranco-019-cut10fps-20261116/cuadra-019',True)}
    print('AUDIT019='+json.dumps(result))
