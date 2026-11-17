"""Isolated Chrome draft-only test. No save, BA, dense or source writes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen


def main():
    helper=Path('/home/exitoso/home/barranco-roi/tests/browser_check.py')
    spec=importlib.util.spec_from_file_location('cdp_helper',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    base='http://127.0.0.1:8790'
    rows=json.load(urlopen(base+'/api/datasets'))
    row=next(r for r in rows if r['label']=='019-corte-10fps')
    with tempfile.TemporaryDirectory(prefix='graph-draft-test-',dir='/tmp/opencode') as tmp:
        profile=Path(tmp)/'profile'
        with (Path(tmp)/'chrome.log').open('w') as log:
            process=subprocess.Popen(['google-chrome','--headless',
                '--use-angle=swiftshader','--enable-unsafe-swiftshader',
                '--disable-background-networking','--no-first-run','--no-default-browser-check',
                '--remote-debugging-port=0','--remote-allow-origins=http://localhost',
                '--user-data-dir='+str(profile),'--window-size=1600,1100','about:blank'],
                stdout=log,stderr=log)
            try:
                active=profile/'DevToolsActivePort'
                for _ in range(100):
                    if active.exists():break
                    if process.poll() is not None:raise RuntimeError('Isolated Chrome failed')
                    time.sleep(.1)
                port=int(active.read_text().splitlines()[0])
                pages=json.load(urlopen(f'http://127.0.0.1:{port}/json/list'))
                cdp=module.CDP(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'))
                cdp.call('Runtime.enable');cdp.call('Page.enable')
                cdp.call('Page.navigate',{'url':base+'/view/'+row['id']+'/editor/0'})
                cdp.wait("typeof meta!=='undefined' && meta && base && centers.length===1200 && $('notice').textContent.startsWith('Grafo listo')",timeout=120)
                target=cdp.js("""(()=>{
                    for(let i=0;i<centers.length;i++){
                        const p=project(centers[i]);
                        if(p.z< -1||p.z>1||p.x<60||p.y<60||p.x>canvas.clientWidth-80||p.y>canvas.clientHeight-80)continue;
                        if(pick(p.x,p.y)!==i)continue;
                        choose(i);$('move').checked=true;
                        const r=canvas.getBoundingClientRect();return {x:p.x+r.left,y:p.y+r.top,id:meta.cameras[i].id};
                    }throw Error('No pickable camera');
                })()""")
                cdp.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':target['x'],'y':target['y'],'button':'left','clickCount':1})
                cdp.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':target['x']+30,'y':target['y']+12,'button':'left','buttons':1})
                cdp.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':target['x']+30,'y':target['y']+12,'button':'left','clickCount':1})
                cdp.wait('!pending && !queued && pins.size===1',timeout=30)
                moved=cdp.js('({neighbors:delta.filter(v=>Math.hypot(...v)>1e-9).length,pins:pins.size})')
                assert moved['neighbors']>1
                cdp.js("$('undo').click()")
                cdp.wait('!pending && !queued && pins.size===0',timeout=30)
                cdp.js("$('redo').click()")
                cdp.wait('!pending && !queued && pins.size===1',timeout=30)
                cdp.js("choose(meta.cameras.findIndex(c=>pins.has(c.id)));$('rx').value=0;$('ry').value=20;$('rz').value=0;$('applyRotation').click()")
                cdp.wait('!pending && !queued && pins.size===1',timeout=30)
                rotation=cdp.js("({matrix:rotations[selected],direction:rotate(rotations[selected],meta.cameras[selected].direction),angles:pins.get(meta.cameras[selected].id).rotation})")
                assert rotation['angles']==[0,20,0]
                assert abs(rotation['matrix'][0][2])>.3
                cdp.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'r','code':'KeyR','windowsVirtualKeyCode':82})
                cdp.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'r','code':'KeyR','windowsVirtualKeyCode':82})
                assert cdp.js("mode==='rotate'")
                cdp.js("viewpoint('top');$('brushMode').click();paint(canvas.clientWidth/2,canvas.clientHeight/2,false)")
                assert cdp.js("brush && Math.abs(pitch-Math.PI/2)<1e-9")
                cdp.js("multi=new Set([meta.cameras[0].id,meta.cameras[1].id]);multiLabel();window.confirm=()=>true;$('deleteCamera').click()")
                cdp.wait('!pending && !queued && deleted.size===2',timeout=30)
                cdp.js("$('undo').click()")
                cdp.wait('!pending && !queued && deleted.size===0',timeout=30)
                rebuild_ms=cdp.js("(()=>{const t=performance.now();for(let i=0;i<5;i++)rebuild();return (performance.now()-t)/5;})()")
                result={'camera':target['id'],**moved,'drag':True,'undo_redo':True,
                        'preview_rebuild_ms_average':rebuild_ms,'rotation_and_direction':True,
                        'brush_top_view_bulk_delete_undo':True,
                        'production_save_or_adjustment':False}
                Path('/tmp/opencode/graph-editor-browser-result.json').write_text(json.dumps(result,indent=2))
                print(json.dumps(result))
            finally:
                process.terminate();process.wait(timeout=15)


if __name__=='__main__':main()
