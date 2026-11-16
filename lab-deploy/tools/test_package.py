"""Verify a normal wheel install without installing packages into the master OS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import venv

repo=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='labctl-package-') as temporary:
    root=Path(temporary)
    venv.create(root/'venv',with_pip=False,system_site_packages=True)
    metadata=json.loads(urllib.request.urlopen('https://pypi.org/pypi/pip/25.3/json',timeout=30).read())
    item=next(p for p in metadata['urls'] if p['filename'].endswith('.whl'))
    data=urllib.request.urlopen(item['url'],timeout=60).read()
    assert hashlib.sha256(data).hexdigest()==item['digests']['sha256']
    wheel=root/item['filename'];wheel.write_bytes(data)
    env=dict(os.environ,PYTHONPATH=str(wheel))
    python=str(root/'venv/bin/python')
    subprocess.run([python,'-m','pip','install','--no-deps','--no-build-isolation',str(repo)],env=env,check=True)
    subprocess.run([str(root/'venv/bin/labctl'),'--state',str(root/'state'),
                    'check-release','--release','l507-segmentation-v1'],cwd=root,check=True)
print('Normal installation works outside the Git checkout; master packages unchanged')
