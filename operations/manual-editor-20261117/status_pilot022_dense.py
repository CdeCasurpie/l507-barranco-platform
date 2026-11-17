exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
launch=json.loads(Path('/tmp/opencode/pilot022-dense-launch.json').read_text())
code=f'''
import pathlib,json,subprocess
assert (pathlib.Path.home()/'L507_011.txt').is_file()
assert {macs['L507_011']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
p=root/'reconstruction-full-status.json'
result=dict(status=json.loads(p.read_text()) if p.exists() else None)
result['service']=subprocess.run(['systemctl','--user','show',{launch['unit']!r},'-p','ActiveState','-p','SubState','-p','Result'],capture_output=True,text=True).stdout
result['logs']={{str(p.relative_to(root)):p.read_text(errors='replace')[-2500:] for p in (root/'logs').rglob('*.log')}}
print('STATUS='+json.dumps(result))
'''
result=run('ssh',opts+[site['ssh_user']+'@192.0.2.65',shlex.join(['python3','-B','-c',code])],'STATUS=')
print(json.dumps(result,indent=2))
