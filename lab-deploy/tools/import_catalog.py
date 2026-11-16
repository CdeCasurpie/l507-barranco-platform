"""Create the public, secret-free manifest from an already certified seed."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from labdeploy import config
from labdeploy.cli import spec_for
from labdeploy.ssh import SSH
from labdeploy.store import ROOT,Store,atomic_json

site=config.site()
store=Store()
nodes=store.read('inventory.json',{})
tag='L507_014'
node=nodes[tag]
assert node['available'] and node['facts']['mounted']
catalog=SSH(site,store).call(node['ip'],'catalog',{'spec':spec_for(site,tag,'')},timeout=180)
cfg='configs/experiments/segmentation-025-0-10s/combined.yaml'
baseline=catalog['baseline']['image_id']
segmentation=catalog['release']['segmentation_image_id']
release={
    'schema':1,'name':'l507-segmentation-v1',
    'git':{'url':'https://github.com/AaronCS25/photogrammetry-pipeline.git','commit':catalog['release']['commit']},
    'images':[{'tag':'photogrammetry:l507-v1-pycolmap','id':baseline,'archive':'photogrammetry-baseline.tar'},
              {'tag':'photogrammetry-seg:l507-v1','id':segmentation,'archive':'segmentation-image.tar'}],
    'artifacts':catalog['artifacts'],
    'environment':{'IMAGE':'photogrammetry:l507-v1-pycolmap','PG_EXPECTED_IMAGE_ID':baseline,
                   'PG_SEG_IMAGE':'photogrammetry-seg:l507-v1','PG_SEG_IMAGE_ID':segmentation,
                   'PG_MIN_FREE_GIB':20,'PG_CPUS':8,'PG_MEMORY':'48g','PG_QUIET_ENTRYPOINT':1,'PG_NETWORK':'none'},
    'verify':{'commands':[
        ['bash','containers/lab-run.sh','doctor','--profile','dense','--scene','cuadra-025','--config',cfg,'--json'],
        ['bash','containers/lab-segment.sh','doctor','--profile','segmentation','--scene','cuadra-025','--config',cfg,'--json'],
        ['bash','containers/docker-run.sh','python3','-B','-m','unittest','discover','-s','tests','-v'],
        ['bash','containers/lab-experiment.sh','--scene','cuadra-025','--config',cfg]],
        'metrics':'outputs/cuadra-025/seg025_0_10s_combined_v1/metrics/metrics.json'}
}
config.validate_release(release)
path=ROOT/'releases/l507-segmentation-v1.json'
if path.exists():raise SystemExit('Refusing to overwrite release manifest')
atomic_json(path,release)
print('Manifest created:',path,'artifacts:',len(release['artifacts']))
