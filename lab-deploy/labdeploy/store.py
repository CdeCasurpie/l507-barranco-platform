import json
import os
from pathlib import Path
import tempfile
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = ROOT if (ROOT/'releases').is_dir() else Path(sys.prefix)/'share/l507-lab-deploy'


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Store:
    def __init__(self, root=None):
        default=ROOT/'.state' if (ROOT/'pyproject.toml').exists() else Path.home()/'.local/state/lab-deploy'
        self.root = Path(root or os.environ.get('LABCTL_STATE', default)).expanduser()
        if self.root.resolve() in [Path('/'),Path.home().resolve(),ROOT.resolve()]:
            raise ValueError('Choose a dedicated controller-state directory')
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.root.chmod(0o700)

    def read(self, name, default=None):
        path = self.root / name
        return json.loads(path.read_text()) if path.exists() else default

    def write(self, name, value):
        atomic_json(self.root / name, value)

    def event(self, value):
        value = {'at': time.time(), **value}
        with (self.root / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(value) + '\n')
