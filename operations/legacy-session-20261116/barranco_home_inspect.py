import json
import subprocess
from pathlib import Path

def cmd(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=100)
    return {'rc': p.returncode, 'out': p.stdout[-11000:], 'err': p.stderr[-300:]}

result = {'tag': NODE_TAG,
          'home': cmd(['du','-x','-B1','--max-depth=3','/home'])}
for key in ('home',):
    lines = result[key]['out'].splitlines()
    lines = sorted(lines, key=lambda x: int(x.split()[0]), reverse=True)
    result[key]['out'] = '\n'.join(lines[:45])
print('ADMIN_REPLY='+json.dumps(result))
