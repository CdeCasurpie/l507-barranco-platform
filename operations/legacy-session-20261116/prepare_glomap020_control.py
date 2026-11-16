exec(open('/tmp/opencode/collect_cut020_review.py').read().split('code="import pathlib,json')[0])
state=Path('/home/exitoso/lab-deploy/.state/campaigns/barranco-020-glomap-20261116')
state.mkdir(exist_ok=False)
files={'glomap_review_worker.py':Path('/home/exitoso/lab-deploy/tools/glomap_review_worker.py').read_text()}
code='FILES='+repr(files)+'\n'+Path('/tmp/opencode/prepare_glomap020_remote.py').read_text()
(state/'prepare-snapshot.py').write_text(code)
wrapped='import traceback,json\ntry:\n exec('+repr(code)+')\nexcept Exception:\n print("PREPARED="+json.dumps({"error":traceback.format_exc()}))'
r=run('ssh',opts+[site['ssh_user']+'@'+a['ip'],shlex.join(['python3','-B','-c',wrapped])],'PREPARED=')
assert 'error' not in r,r.get('error')
(state/'preparation.json').write_text(json.dumps(r,indent=2))
(state/'assignments.json').write_text(json.dumps({'assignments':[r['assignment']]},indent=2))
print(json.dumps({'prepared':r['root'],'runtime':r['runtime']}))
