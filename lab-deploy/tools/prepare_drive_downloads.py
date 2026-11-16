"""Freeze reviewed Drive inventory into block/node download assignments."""
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from labdeploy.store import atomic_json


def main(inventory_path):
    campaign_id = 'barranco-full-v1'
    state = PROJECT / '.state/campaigns' / campaign_id
    if (state / 'assignments.json').exists():
        raise RuntimeError('Campaign already exists; preserve its immutable assignments')
    site = json.loads((PROJECT / 'config/site.json').read_text())
    nodes = json.loads((PROJECT / '.state/inventory.json').read_text())
    drive = json.loads(Path(inventory_path).read_text())
    release = json.loads((PROJECT / 'releases/l507-segmentation-v1.json').read_text())
    known = {Path(a['target']).name: a for a in release['artifacts']
             if a.get('target', '').endswith(('.MP4', '.SRT'))}
    # Prefer matching labels; non-existent node labels use idle daughters.
    mapping = {b: b for b in ['001', '002', '003', '004', '005', '007', '008', '009', '012', '023', '024']}
    mapping.update({'013': '006', '017': '010', '018': '011', '025': '015'})
    mapping['TODO'] = '019'
    order = ['025', '005', '009', '018', '001', '002', '003', '004', '007', '008', '012', '013', '017', '023', '024', 'TODO']
    assignments = []
    created = time.time()
    for block in order:
        tag = 'L507_' + mapping[block]
        record = nodes[tag]
        if not record.get('available'):
            raise RuntimeError('Node was unavailable in last validated inventory: ' + tag)
        dataset = 'unclassified-TODO' if block == 'TODO' else 'cuadra-' + block
        root = '/data/photogrammetry/campaigns/' + campaign_id + '/' + dataset
        files = []
        for entry in drive:
            parts = entry['path'].split('/')
            if len(parts) != 3 or parts[1] != block:
                continue
            name = parts[2]
            suffix = Path(name).suffix.upper()
            if suffix not in ('.MP4', '.SRT', '.PNG'):
                continue
            file = {'id': entry['id'], 'name': name, 'bytes': int(entry['metadata'][13]),
                    'drive_modified_at_ms': entry['metadata'][10],
                    'relative_path': ('reference/' if suffix == '.PNG' else 'datasets/raw/' + dataset + '/drone/') + name}
            if name in known:
                artifact = known[name]
                if artifact['bytes'] != file['bytes']:
                    raise RuntimeError('Drive size differs from known certified artifact: ' + name)
                file['sha256'] = artifact['sha256']
                current_root = (record.get('facts') or {}).get('current', {}).get('data_root')
                file['local_candidates'] = ['/data/photogrammetry/' + artifact['target']]
                if current_root:
                    file['local_candidates'].append(current_root + '/' + artifact['target'])
            files.append(file)
        videos = {Path(f['name']).stem for f in files if f['name'].endswith('.MP4')}
        subtitles = {Path(f['name']).stem for f in files if f['name'].endswith('.SRT')}
        if not videos or videos != subtitles:
            raise RuntimeError('Incomplete MP4/SRT pairs: ' + block)
        assignment = {'schema': 1, 'campaign_id': campaign_id, 'block_id': block, 'node_tag': tag,
                      'mac': site['nodes'][tag], 'ip': record['ip'], 'work_root': root,
                      'operation': 'download_only', 'created_at': created,
                      'drive_folder_id': next(e['id'] for e in drive if e['path'] == 'data/' + block),
                      'files': sorted(files, key=lambda f: (not f['name'].endswith('.SRT'), f['name']))}
        assignments.append(assignment)
        atomic_json(state / 'assignments' / (block + '.json'), assignment)
    campaign = {'schema': 1, 'campaign_id': campaign_id, 'created_at': created, 'max_parallel': 4,
                'operation': 'download_only', 'assignments': assignments,
                'waiting_for_input': ['006', '010', '011', '014', '015', '016', '019', '020', '021', '022'],
                'unclassified_folder': {'name': 'TODO', 'node_tag': 'L507_019', 'process': False}}
    atomic_json(state / 'assignments.json', campaign)
    for a in assignments:
        print(a['block_id'], a['node_tag'], len(a['files']), round(sum(f['bytes'] for f in a['files']) / 1024**3, 3), 'GiB')
    print('STATE', state)
    print('TOTAL', sum(len(a['files']) for a in assignments), 'files',
          round(sum(f['bytes'] for a in assignments for f in a['files']) / 1024**3, 3), 'GiB')


if __name__ == '__main__':
    main(sys.argv[1])
