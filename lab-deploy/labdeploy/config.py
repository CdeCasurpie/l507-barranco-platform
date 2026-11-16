import hashlib
import json
from pathlib import Path
import re

from .store import ROOT,CONFIG_ROOT


def site(path=None):
    data=json.loads(Path(path or CONFIG_ROOT/'config/site.json').read_text())
    if data['max_parallel']<1 or data['max_parallel']>4:
        raise ValueError('Parallel limit must be 1..4')
    if Path(data['data_root']).parent!=Path('/data'):
        raise ValueError('Data root must be under /data')
    for tag,mac in data['nodes'].items():
        if not re.fullmatch(r'L507_\d{3}',tag) or not re.fullmatch(r'[0-9a-f]{2}(?::[0-9a-f]{2}){5}',mac):
            raise ValueError('Invalid node identity: '+tag)
    if len(set(data['nodes'].values()))!=len(data['nodes']):
        raise ValueError('Duplicate MAC registry entry')
    if not data.get('sources') or any(tag not in data['nodes'] for tag in data['sources']):
        raise ValueError('Sources must be registered daughter nodes')
    return data


def validate_release(data):
    if data.get('schema')!=1:
        raise ValueError('Unsupported release manifest schema')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',data['name']) or '..' in data['name']:
        raise ValueError('Invalid release name')
    if not re.fullmatch(r'[a-f0-9]{40}',data['git']['commit']) or not data['git']['url'].startswith('https://github.com/'):
        raise ValueError('Release must pin a GitHub HTTPS commit')
    names=set()
    for item in data['artifacts']:
        if item['name'] in names:
            raise ValueError('Duplicate artifact name')
        names.add(item['name'])
        if not re.fullmatch(r'[a-f0-9]{64}',item['sha256']) or not isinstance(item['bytes'],int) or item['bytes']<=0:
            raise ValueError('Artifact must have a checksum and positive size')
        paths=[*item.get('local_candidates',[]),*[p for v in item['source_paths'].values() for p in v]]
        if item.get('target'):paths.append(item['target'])
        for value in paths:
            path=Path(value)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Unsafe artifact path')
    for image in data['images']:
        if image['archive'] not in names or not re.fullmatch(r'sha256:[a-f0-9]{64}',image['id']):
            raise ValueError('Image must reference an archive and immutable ID')
    for tag_key,id_key in [('IMAGE','PG_EXPECTED_IMAGE_ID'),('PG_SEG_IMAGE','PG_SEG_IMAGE_ID')]:
        if tag_key in data['environment'] and id_key in data['environment']:
            if not any(p['tag']==data['environment'][tag_key] and p['id']==data['environment'][id_key] for p in data['images']):
                raise ValueError('Environment image tag/ID must match the declared images')
    for key in data['environment']:
        if not re.fullmatch(r'[A-Z_][A-Z_0-9]*',key) or any(word in key for word in ['TOKEN','PASSWORD','SECRET']):
            raise ValueError('Credentials do not belong in release manifests')
    if data['verify'].get('metrics'):
        path=Path(data['verify']['metrics'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe verification metrics path')
    if not data['verify']['commands'] or any(not isinstance(c,list) or not all(isinstance(x,str) for x in c) for c in data['verify']['commands']):
        raise ValueError('Verification commands must be argv arrays')
    return data


def release(name):
    path=Path(name)
    if path.suffix!='.json':path=CONFIG_ROOT/'releases'/(name+'.json')
    data=validate_release(json.loads(path.read_text()))
    fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    return data,fingerprint
