"""Create a local-only canary release to exercise staging and rollback."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from labdeploy.config import release
from labdeploy.store import Store

value,_=release('l507-segmentation-v1')
value['name']='labctl-lifecycle-smoke'
store=Store()
store.write('lifecycle-release.json',value)
print(store.root/'lifecycle-release.json')
