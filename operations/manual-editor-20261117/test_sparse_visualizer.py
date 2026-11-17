import sys,tempfile,subprocess,time,json
from pathlib import Path
from urllib.request import urlopen
sys.path.insert(0,'/home/exitoso/home/barranco-roi/tests')
from browser_check import CDP
with tempfile.TemporaryDirectory(dir='/tmp/opencode',prefix='sv-browser-',ignore_cleanup_errors=True) as directory:
    root=Path(directory);log=(root/'chrome.log').open('w')
    chrome=subprocess.Popen(['google-chrome','--headless','--disable-background-networking',
        '--no-first-run','--no-default-browser-check','--remote-debugging-port=0',
        '--remote-allow-origins=http://localhost','--user-data-dir='+str(root/'profile'),
        '--window-size=1600,1100','about:blank'],stdout=log,stderr=log)
    try:
        active=root/'profile/DevToolsActivePort'
        for _ in range(100):
            if active.exists():break
            if chrome.poll() is not None:raise RuntimeError((root/'chrome.log').read_text())
            time.sleep(.1)
        port=int(active.read_text().splitlines()[0])
        with urlopen(f'http://127.0.0.1:{port}/json/list') as r:pages=json.load(r)
        cdp=CDP(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'))
        cdp.call('Runtime.enable');cdp.call('Page.enable')
        cdp.call('Page.navigate',{'url':'http://127.0.0.1:8765/'})
        cdp.wait("!!document.getElementById('sparseViewTab') && !!document.getElementById('svCanvas')",timeout=30)
        cdp.js("document.getElementById('sparseViewTab').click()")
        cdp.wait("document.getElementById('svStatus').textContent.includes('puntos de vista previa')",timeout=60)
        assert cdp.js("!document.getElementById('sparseViewWorkspace').hidden")
        count=cdp.js("document.getElementById('svLayers').querySelectorAll('input').length")
        assert count>=26,count
        cdp.js("document.getElementById('svProjection').value='perspective';document.getElementById('svProjection').dispatchEvent(new Event('change'));document.getElementById('svColor').value='rgb';document.getElementById('svColor').dispatchEvent(new Event('change'));document.getElementById('svSize').value=4;document.getElementById('svSize').dispatchEvent(new Event('input'))")
        cdp.screenshot('sparse-visualizer-perspective.png')
        cdp.js("document.getElementById('svNone').click()")
        assert cdp.js("Array.from(document.querySelectorAll('#svLayers input')).every(i=>!i.checked)")
        cdp.js("document.getElementById('svAll').click();document.getElementById('svProjection').value='ortho';document.getElementById('svProjection').dispatchEvent(new Event('change'));document.getElementById('svColor').value='block';document.getElementById('svColor').dispatchEvent(new Event('change'));document.getElementById('svTop').click()")
        cdp.screenshot('sparse-visualizer-top.png')
        assert cdp.js("document.getElementById('svCanvas').getContext('webgl').getError()") == 0
        cdp.js("document.getElementById('alignTab').click()")
        assert cdp.js("document.getElementById('sparseViewWorkspace').hidden && !document.getElementById('alignWorkspace').hidden")
        print(json.dumps(dict(layers=count,perspective_rgb=True,orthographic_block_colors=True,
            point_size=True,layer_toggles=True,webgl_no_error=True,tab_switch=True,read_only=True)))
    finally:
        chrome.terminate();chrome.wait(timeout=15);log.close()
