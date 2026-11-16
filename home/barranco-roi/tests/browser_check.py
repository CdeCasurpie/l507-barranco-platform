"""Real Chrome + real 025 data, isolated state. No dense export or mesh generation."""
import base64
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PYTHON = '/data/barranco/runtime/alignment313/bin/python'


class CDP:
    def __init__(self, url):
        u = urlsplit(url)
        self.socket = socket.create_connection((u.hostname, u.port), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f'GET {u.path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\n'
                   f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n'
                   'Origin: http://localhost\r\n\r\n')
        self.socket.sendall(request.encode())
        response = b''
        while b'\r\n\r\n' not in response:
            response += self.socket.recv(4096)
        head, self.buffer = response.split(b'\r\n\r\n', 1)
        if head.split(b'\r\n', 1)[0].split()[1:2] != [b'101']:
            raise RuntimeError(head.decode())
        self.serial = 0
        self.errors = []

    def read(self, count):
        while len(self.buffer) < count:
            block = self.socket.recv(max(4096, count - len(self.buffer)))
            if not block:
                raise RuntimeError('CDP connection closed')
            self.buffer += block
        result, self.buffer = self.buffer[:count], self.buffer[count:]
        return result

    def send(self, value):
        raw = json.dumps(value).encode()
        size = len(raw)
        head = b'\x81' + (bytes([128 + size]) if size < 126 else b'\xfe' + struct.pack('!H', size)
                           if size <= 65535 else b'\xff' + struct.pack('!Q', size))
        mask = os.urandom(4)
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(raw))
        self.socket.sendall(head + mask + payload)

    def receive(self):
        a, b = self.read(2)
        size = b & 127
        if size == 126:
            size = struct.unpack('!H', self.read(2))[0]
        elif size == 127:
            size = struct.unpack('!Q', self.read(8))[0]
        if b & 128:
            raise RuntimeError('Unexpected masked server frame')
        data = self.read(size)
        if a & 15 == 8:
            raise RuntimeError('WebSocket closed')
        return json.loads(data)

    def call(self, method, params=None):
        self.serial += 1
        key = self.serial
        self.send({'id': key, 'method': method, 'params': params or {}})
        while True:
            response = self.receive()
            if response.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(response['params'])
            if response.get('id') == key:
                if 'error' in response:
                    raise RuntimeError(response['error'])
                return response.get('result', {})

    def js(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
        if result.get('exceptionDetails'):
            raise RuntimeError(result['exceptionDetails'])
        return result.get('result', {}).get('value')

    def wait(self, expression, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if self.js(expression):
                    return
            except RuntimeError as error:
                if 'Inspected target navigated or closed' not in str(error) and 'Execution context was destroyed' not in str(error):
                    raise
            time.sleep(.2)
        raise RuntimeError('Browser timeout: ' + expression + ' ' + str(self.js('document.body.innerText'))[-2000:])

    def click(self, x, y, count=1):
        self.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})
        self.call('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'clickCount': count})
        self.call('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'clickCount': count})

    def screenshot(self, name):
        result = self.call('Page.captureScreenshot', {'format': 'png'})
        Path('/tmp/opencode/' + name).write_bytes(base64.b64decode(result['data']))


def main():
    with tempfile.TemporaryDirectory(prefix='roi-browser-', dir='/tmp/opencode') as directory:
        temp = Path(directory)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        log = (temp / 'process.log').open('w')
        app = subprocess.Popen([PYTHON, '-B', str(ROOT / 'app.py'), '--port', str(port),
                                '--state-dir', str(temp / 'state')], stdout=log, stderr=log,
                               cwd=ROOT, env=dict(os.environ, OPENBLAS_NUM_THREADS='2'))
        chrome = None
        try:
            for _ in range(100):
                try:
                    with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                        assert json.load(response)['sparse_count'] == 70788
                    break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError((temp / 'process.log').read_text())
                    time.sleep(.1)
            profile = temp / 'chrome'
            chrome = subprocess.Popen(['google-chrome', '--headless', '--disable-gpu',
                '--disable-background-networking', '--no-first-run', '--no-default-browser-check',
                '--remote-debugging-port=0', '--remote-allow-origins=http://localhost',
                '--user-data-dir=' + str(profile), '--window-size=1600,1200', 'about:blank'],
                stdout=log, stderr=log)
            for _ in range(100):
                active = profile / 'DevToolsActivePort'
                if active.exists():
                    break
                if chrome.poll() is not None:
                    raise RuntimeError((temp / 'process.log').read_text())
                time.sleep(.1)
            debug_port = int(active.read_text().splitlines()[0])
            with urlopen(f'http://127.0.0.1:{debug_port}/json/list') as response:
                pages = json.load(response)
            cdp = CDP(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page'))
            cdp.call('Runtime.enable')
            cdp.call('Page.enable')
            cdp.call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#roi'})
            cdp.wait('document.body.dataset.ready === "true"')
            cdp.js("roiApp.selectBlock('025')")
            cdp.wait('roiApp.state.data?.block === "025" && !roiApp.state.loading')
            assert cdp.js('window.roiApp.state.data.points.length') == 70788
            assert cdp.js('window.roiApp.state.data.block') == '025'
            assert cdp.js('window.roiApp.state.vertices.length') == 0
            cdp.screenshot('roi-selector-initial.png')
            cdp.js("document.getElementById('focusBlockBtn').click()")
            # Mouse drawing: a concave six-vertex region, solely a diagnostic fixture.
            points = cdp.js('''(() => {
              const a=roiApp.state.data.focus_bounds[0],b=roiApp.state.data.focus_bounds[1];
              const x=a[0]+(b[0]-a[0])*.2,y=a[1]+(b[1]-a[1])*.2;
              const dx=(b[0]-a[0])*.5,dy=(b[1]-a[1])*.5;
              const v=[[x,y],[x+dx,y],[x+dx,y+dy*.5],[x+dx*.6,y+dy*.5],[x+dx*.6,y+dy],[x,y+dy]];
              const r=document.getElementById('mapCanvas').getBoundingClientRect();
              return v.map(p=>{const q=roiApp.screen(p);return [q[0]+r.left,q[1]+r.top]});
            })()''')
            cdp.js("document.getElementById('drawBtn').click()")
            for x, y in points:
                cdp.click(x, y)
            assert cdp.js('roiApp.state.vertices.length') == 6
            cdp.js("document.getElementById('closeBtn').click()")
            cdp.wait('roiApp.state.valid')
            original_vertices = cdp.js('JSON.stringify(roiApp.state.vertices)')
            position = cdp.js('''(() => {const p=roiApp.screen(roiApp.state.vertices[2]);
                const r=document.getElementById('mapCanvas').getBoundingClientRect();
                return [p[0]+r.left,p[1]+r.top]})()''')
            x, y = position
            cdp.call('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
            cdp.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x + 15, 'y': y - 8, 'button': 'left', 'buttons': 1})
            cdp.call('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x + 15, 'y': y - 8, 'button': 'left', 'clickCount': 1})
            cdp.wait('roiApp.state.valid')
            assert cdp.js('JSON.stringify(roiApp.state.vertices)') != original_vertices
            cdp.js("document.getElementById('undoBtn').click()")
            cdp.wait('roiApp.state.valid')
            assert cdp.js('JSON.stringify(roiApp.state.vertices)') == original_vertices
            cdp.js("document.getElementById('redoBtn').click()")
            cdp.wait('roiApp.state.valid')
            assert cdp.js('JSON.stringify(roiApp.state.vertices)') != original_vertices
            cdp.js("document.getElementById('undoBtn').click()")
            cdp.wait('roiApp.state.valid')
            midpoint = cdp.js('''(() => {const a=roiApp.state.vertices[0],b=roiApp.state.vertices[1];
                const p=roiApp.screen([(a[0]+b[0])/2,(a[1]+b[1])/2]);
                const r=document.getElementById('mapCanvas').getBoundingClientRect();return [p[0]+r.left,p[1]+r.top]})()''')
            cdp.click(*midpoint, count=2)
            cdp.wait('roiApp.state.valid && roiApp.state.vertices.length === 7')
            cdp.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Delete', 'code': 'Delete', 'windowsVirtualKeyCode': 46})
            cdp.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Delete', 'code': 'Delete', 'windowsVirtualKeyCode': 46})
            cdp.wait('roiApp.state.valid && roiApp.state.vertices.length === 6')
            assert cdp.js('JSON.stringify(roiApp.state.vertices)') == original_vertices
            cdp.js("document.getElementById('selectionName').value='PRUEBA AUTOMÁTICA — no usar como contorno';document.getElementById('saveBtn').click()")
            cdp.wait('!!roiApp.state.selection')
            selection_id = cdp.js('roiApp.state.selection.id')
            cdp.screenshot('roi-selector-selection.png')
            # Reload and restore saved selection through the actual interface.
            cdp.call('Page.reload')
            cdp.wait('document.body.dataset.ready === "true"')
            cdp.js(f"document.getElementById('savedSelect').value={json.dumps(selection_id)};document.getElementById('savedSelect').dispatchEvent(new Event('change'));document.getElementById('loadBtn').click()")
            cdp.wait('!!roiApp.state.selection && roiApp.state.valid && !document.getElementById("analyzeBtn").disabled')
            assert cdp.js('roiApp.state.vertices.length') == 6
            cdp.js("document.getElementById('analyzeBtn').click()")
            cdp.wait('!!roiApp.state.analysis && !!roiApp.state.densePreview && !roiApp.state.busy && !document.getElementById("denseLayerBtn").disabled', timeout=120)
            result = cdp.js('roiApp.state.analysis.result')
            assert result['source_points'] == 60755108
            assert 0 < result['kept'] < result['source_points']
            assert result['kept'] + result['discarded'] == result['source_points']
            assert result['source_sha256_verified'] == '5369ea3f9cf83e470200bb43058c75a53183c42270f29140fab7e7274ea59b0c'
            cdp.js("document.getElementById('denseLayerBtn').click()")
            assert cdp.js('roiApp.state.layer') == 'dense'
            cdp.screenshot('roi-selector-dense.png')
            # Select every block through the actual dropdown. No dense jobs are
            # started for these checks; only sparse geometry is transferred.
            blocks=cdp.js('roiApp.state.blocks.map(b=>b.block)')
            assert len(blocks)==15
            for block in blocks:
                cdp.js(f"document.getElementById('blockSelect').value='{block}';document.getElementById('blockSelect').dispatchEvent(new Event('change'))")
                cdp.wait(f"!roiApp.state.loading && roiApp.state.data.block === '{block}' && roiApp.state.block === '{block}'")
                assert cdp.js('roiApp.state.data.points.length') > 0
            for block,count in [('001',6),('023',4)]:
                cdp.js(f"document.getElementById('blockSelect').value='{block}';document.getElementById('blockSelect').dispatchEvent(new Event('change'))")
                cdp.wait(f"!roiApp.state.loading && roiApp.state.data.block === '{block}'")
                cdp.js("document.getElementById('focusBlockBtn').click();document.getElementById('drawBtn').click()")
                vertices=cdp.js('''(() => {
                  const [a,b]=roiApp.state.data.focus_bounds, dx=b[0]-a[0],dy=b[1]-a[1];
                  const x=a[0]+dx*.25,y=a[1]+dy*.25;
                  const four=[[x,y],[x+dx*.4,y],[x+dx*.4,y+dy*.4],[x,y+dy*.4]];
                  const six=[[x,y],[x+dx*.4,y],[x+dx*.4,y+dy*.2],[x+dx*.2,y+dy*.2],[x+dx*.2,y+dy*.4],[x,y+dy*.4]];
                  const points=roiApp.state.block==='001'?six:four;
                  const r=document.getElementById('mapCanvas').getBoundingClientRect();
                  return points.map(p=>{const q=roiApp.screen(p);return [q[0]+r.left,q[1]+r.top]});
                })()''')
                for x,y in vertices:cdp.click(x,y)
                cdp.js("document.getElementById('closeBtn').click()")
                cdp.wait('roiApp.state.valid')
                cdp.js(f"document.getElementById('selectionName').value='ISOLATED BROWSER {block}';document.getElementById('saveBtn').click()")
                cdp.wait(f"!!roiApp.state.selection && roiApp.state.selection.block === '{block}'")
                exported=cdp.js(f"fetch('/api/roi.json?block={block}').then(r=>r.json())")
                assert exported['block']==block
                assert len(exported['vertices'])==count
                assert exported['deployment_status']=='not_submitted'
                assert exported['node_tag']=='L507_'+block
                assert (temp/'state/exports'/f'roi_{block}.json').is_file()
            assert exported['placement']=='manual_023_relative_to_025'
            cdp.screenshot('roi-selector-manual-023.png')
            # Switching back restores only the 001 polygon, never the 023 one.
            cdp.js("document.getElementById('blockSelect').value='001';document.getElementById('blockSelect').dispatchEvent(new Event('change'))")
            cdp.wait("roiApp.state.data.block==='001' && roiApp.state.valid && roiApp.state.selection?.block==='001'")
            assert cdp.js('roiApp.state.vertices.length')==6
            cdp.wait('!document.getElementById("analyzeBtn").disabled')
            cdp.js("document.getElementById('analyzeBtn').click()")
            cdp.wait('roiApp.state.busy && !!roiApp.state.job')
            background_id=cdp.js('roiApp.state.job.id')
            cdp.js("document.getElementById('blockSelect').value='023';document.getElementById('blockSelect').dispatchEvent(new Event('change'))")
            cdp.wait("!roiApp.state.loading && roiApp.state.data.block==='023' && roiApp.state.valid")
            cdp.js("document.getElementById('saveBtn').click()")
            cdp.wait("!!roiApp.state.selection && roiApp.state.selection.block==='023'")
            background=cdp.js(f'''(async()=>{{
              for(let i=0;i<240;i++){{
                const j=await fetch('/api/jobs/{background_id}?block=001').then(r=>r.json());
                if(!['running','queued'].includes(j.status))return j;
                await new Promise(r=>setTimeout(r,200));
              }} throw new Error('Background check timed out');
            }})()''')
            assert background['status']=='completed',background
            assert background['block']=='001'
            assert cdp.js('roiApp.state.block')=='023'
            assert cdp.js('roiApp.state.vertices.length')==4
            # Race two asynchronous loads: only the last requested block may paint.
            cdp.js("roiApp.selectBlock('003');roiApp.selectBlock('023')")
            cdp.wait("!roiApp.state.loading && roiApp.state.data.block==='023' && roiApp.state.valid")
            assert cdp.js('roiApp.state.vertices.length')==4
            cdp.js("document.getElementById('overviewBtn').click()")
            cdp.screenshot('roi-selector-all-blocks.png')
            assert not cdp.errors, cdp.errors
            print(json.dumps({'browser': 'Chrome headless', 'sparse_points': 70788,
                'vertices_drawn_with_mouse': 6, 'drag_undo_redo_insert_delete': True,
                'save_reload': True, 'dense_result': result,
                'all_15_blocks_loaded':True,'multi_block_polygon_isolation':True,'rapid_switch_race':True,
                'background_analysis_isolation':True,
                'browser_errors': cdp.errors, 'state_isolated': True, 'dense_export_created': False},
                indent=2, ensure_ascii=False))
            cdp.socket.close()
        finally:
            for process in (chrome, app):
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            log.close()
            Path('/tmp/opencode/roi-browser-last.log').write_bytes((temp/'process.log').read_bytes())


if __name__ == '__main__':
    main()
