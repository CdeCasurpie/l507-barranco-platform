"""Read camera tables in OpenMVS MVSI 1..7 without loading dense points."""
from pathlib import Path
import struct


def camera_table(path):
    with Path(path).open('rb') as f:
        def read(fmt):
            size = struct.calcsize('<' + fmt)
            raw = f.read(size)
            if len(raw) != size:
                raise ValueError('Truncated MVSI camera table')
            return struct.unpack('<' + fmt, raw)

        def text():
            size, = read('Q')
            if size > 1024 * 1024:
                raise ValueError('Invalid MVSI string size')
            return f.read(size).decode()

        if f.read(4) != b'MVSI':
            raise ValueError('Expected MVSI interface archive')
        version, reserved = read('II')
        if not 1 <= version <= 7:
            raise ValueError('Unsupported MVSI version')
        platforms = []
        count, = read('Q')
        if count > 10000:
            raise ValueError('Invalid platform count')
        for _ in range(count):
            name = text()
            cameras = []
            n, = read('Q')
            for _ in range(n):
                cname = text()
                band = text() if version > 3 else ''
                width, height = read('II')
                k, r, c = read('9d'), read('9d'), read('3d')
                cameras.append(dict(name=cname, band=band, width=width, height=height, K=k, R=r, C=c))
            n, = read('Q')
            poses = [(read('9d'), read('3d')) for _ in range(n)]
            platforms.append(dict(name=name, cameras=cameras, poses=poses))
        prefix_end = f.tell()
        n, = read('Q')
        if n > 100000:
            raise ValueError('Invalid image count')
        images = []
        for index in range(n):
            name = text()
            mask = text() if version > 4 else ''
            start = f.tell()
            platform, camera, pose = read('III')
            global_id, = read('I') if version > 2 else (index,)
            if version > 6:
                read('3f')
                scores, = read('Q')
                f.seek(scores * 24, 1)
            end = f.tell()
            f.seek(start)
            tail = f.read(end - start)
            p = platforms[platform]
            cam = p['cameras'][camera]
            rotation, center = p['poses'][pose]
            # All campaign scenes use one camera rigidly coincident with its platform.
            if cam['R'] != (1.,0.,0.,0.,1.,0.,0.,0.,1.) or any(cam['C']):
                raise ValueError('Nonidentity platform camera requires explicit composition')
            images.append(dict(index=index, name=name, mask=mask, tail=tail,
                               global_id=global_id, camera=cam, R=rotation, C=center))
        return dict(version=version, platforms=platforms, images=images,
                    prefix_end=prefix_end, images_end=f.tell())


def key(name):
    # Frame filenames are unique within each manzana; collisions are rejected below.
    return Path(name).name


def camera_mapping(global_table, batch_table):
    lookup = {key(im['name']): im for im in global_table['images']}
    if len(lookup) != len(global_table['images']):
        raise ValueError('Ambiguous image basenames')
    mapping = []
    max_delta = 0.
    for im in batch_table['images']:
        target = lookup[key(im['name'])]
        for attr in ['R', 'C']:
            delta = max(abs(a-b) for a,b in zip(im[attr], target[attr]))
            max_delta = max(max_delta, delta)
            if delta > 1e-9:
                raise ValueError('Camera pose mismatch: ' + im['name'])
        a, b = im['camera'], target['camera']
        # Dense scenes may save intrinsics normalized by max image dimension.
        def normalized(cam):
            scale = max(cam['width'], cam['height']) or 1
            return tuple(v / scale if i < 6 else v for i,v in enumerate(cam['K']))
        delta = max(abs(x-y) for x,y in zip(normalized(a), normalized(b)))
        if delta > 1e-8:
            raise ValueError('Camera intrinsics mismatch: ' + im['name'])
        mapping.append(target['index'])
    return mapping, max_delta


def relocate_scene(source, destination, table, image_root):
    source = Path(source)
    raw = source.read_bytes()
    def text(value):
        value = value.encode()
        return struct.pack('<Q', len(value)) + value
    temporary = Path(str(destination) + '.new')
    with temporary.open('wb') as f:
        f.write(raw[:table['prefix_end']])
        f.write(struct.pack('<Q', len(table['images'])))
        for im in table['images']:
            parts = Path(im['name']).parts
            if 'images' not in parts:
                raise ValueError('Scene image is not relative to images/: ' + im['name'])
            relative = Path(*parts[parts.index('images') + 1:])
            image = Path(image_root) / relative
            if not image.is_file():
                raise ValueError('Missing undistorted image: ' + str(image))
            f.write(text(str(image)))
            if table['version'] > 4:
                # Masks were already applied during densification. Keep any original
                # mask reference absolute when present rather than inventing one.
                mask = str((source.parent / im['mask']).resolve()) if im['mask'] else ''
                f.write(text(mask))
            f.write(im['tail'])
        f.write(raw[table['images_end']:])
    temporary.replace(destination)
