"""Real Chrome camera picking; isolated browser profile, no source/state writes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen

helper=Path('/home/exitoso/home/barranco-roi/tests/browser_check.py')
spec=importlib.util.spec_from_file_location('cdp_helper',helper)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    with tempfile.TemporaryDirectory(prefix='sparse-camera-test-',dir='/tmp/opencode') as tmp:
        root=Path(tmp);profile=root/'chrome'
        with (root/'chrome.log').open('w') as log:
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
                    if process.poll() is not None:raise RuntimeError((root/'chrome.log').read_text())
                    time.sleep(.1)
                port=int(active.read_text().splitlines()[0])
                with urlopen(f'http://127.0.0.1:{port}/json/list') as response:
                    pages=json.load(response)
                cdp=module.CDP(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'))
                cdp.call('Runtime.enable');cdp.call('Page.enable')
                cdp.call('Page.navigate',{'url':'http://127.0.0.1:8783/'})
                cdp.wait("typeof info!=='undefined' && info?.camera_count===970 && count>0",timeout=90)
                chosen=cdp.js("""(()=>{
                  $('onlyCameras').checked=true;draw();
                  for(const c of info.cameras){
                    const p=projectCamera(c);
                    if(p&&p.x>30&&p.x<canvas.clientWidth-90&&p.y>70&&p.y<canvas.clientHeight-70&&pickCamera(p.x,p.y)?.id===c.id){
                      const r=canvas.getBoundingClientRect();return {id:c.id,name:c.name,x:p.x+r.left,y:p.y+r.top};
                    }
                  }throw Error('No pickable camera');
                })()""")
                cdp.click(chosen['x'],chosen['y'])
                assert cdp.js(f'groups.A.has({chosen["id"]})')
                cdp.js("$('groupB').click();$('cameraSearch').value=String(info.cameras.find(c=>!groups.A.has(c.id)).id);fillCameraList();$('addCamera').click()")
                report=cdp.js('selectionReport()')
                assert len(report['A'])==len(report['B'])==1
                assert report['A'][0]['id']==chosen['id']
                assert report['A'][0]['name']==chosen['name']
                assert report['A'][0]['id']!=report['B'][0]['id']
                assert report['geometry_modified'] is False
                cdp.js("window.beforeDrag=JSON.stringify(selectionReport());")
                cdp.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':chosen['x'],'y':chosen['y'],'button':'left','clickCount':1})
                cdp.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':chosen['x']+60,'y':chosen['y']+20,'button':'left','buttons':1})
                cdp.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':chosen['x']+60,'y':chosen['y']+20,'button':'left','clickCount':1})
                assert cdp.js('JSON.stringify(selectionReport())===window.beforeDrag')
                cdp.js("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copied=text}}});")
                cdp.js("document.getElementById('copySelection').onclick()")
                assert str(chosen['id']) in cdp.js('window.copied')
                cdp.js("window.savedBlob=null;URL.createObjectURL=blob=>{window.savedBlob=blob;return 'blob:isolated-test'};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=function(){};$('downloadSelection').click()")
                exported=cdp.js('window.savedBlob.text().then(JSON.parse)')
                assert exported['A']==report['A'] and exported['B']==report['B']
                cdp.call('Page.reload',{'ignoreCache':True})
                cdp.wait("typeof info!=='undefined' && info?.camera_count===970 && count>0",timeout=60)
                restored=cdp.js('selectionReport()')
                assert restored['A']==report['A'] and restored['B']==report['B']
                cdp.js("$('clearSelection').click()")
                assert cdp.js('groups.A.size+groups.B.size')==0
                assert not cdp.errors,cdp.errors
                print(json.dumps({'passed':True,'browser':'Chrome SwiftShader','cameras':970,
                     'picked_id':chosen['id'],'tests':['projected camera click','A/B groups','drag does not select',
                     'exact IDs/names','clipboard','JSON export','reload persistence','clear marks']}))
            finally:
                process.terminate()
                process.wait(timeout=20)


if __name__=='__main__':
    main()
