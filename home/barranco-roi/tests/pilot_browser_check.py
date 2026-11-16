"""Read-only browser check against the running, published user pilot."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen
from browser_check import CDP


def main():
    with urlopen('http://127.0.0.1:8765/api/pilot') as response:
        report=json.load(response)
    assert report['status']=='completed'
    assert report['selection_id']=='s-1794364122096131540'
    with tempfile.TemporaryDirectory(prefix='roi-pilot-browser-',dir='/tmp/opencode') as directory:
        root=Path(directory);log=(root/'chrome.log').open('w')
        chrome=subprocess.Popen(['google-chrome','--headless','--disable-gpu','--disable-background-networking',
            '--no-first-run','--no-default-browser-check','--remote-debugging-port=0',
            '--remote-allow-origins=http://localhost','--user-data-dir='+str(root/'profile'),
            '--window-size=1700,1200','about:blank'],stdout=log,stderr=log)
        try:
            active=root/'profile/DevToolsActivePort'
            for _ in range(100):
                if active.exists():break
                if chrome.poll() is not None:raise RuntimeError((root/'chrome.log').read_text())
                time.sleep(.1)
            port=int(active.read_text().splitlines()[0])
            with urlopen(f'http://127.0.0.1:{port}/json/list') as response:pages=json.load(response)
            cdp=CDP(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'))
            cdp.call('Runtime.enable');cdp.call('Page.enable')
            cdp.call('Page.navigate',{'url':'http://127.0.0.1:8765/pilot/'})
            cdp.wait('document.readyState === "complete"')
            cdp.js("document.querySelectorAll('img').forEach(i=>i.loading='eager')")
            cdp.wait("document.images.length === 25 && [...document.images].every(i=>i.complete && i.naturalWidth===1600)")
            assert cdp.js("getComputedStyle(document.body).backgroundColor")=='rgb(11, 19, 30)'
            assert cdp.js("document.body.textContent.includes('s-1794364122096131540')")
            assert cdp.js("document.querySelectorAll('table tr').length")==4
            cdp.screenshot('roi-pilot-gallery-browser.png')
            assert not cdp.errors
            cdp.socket.close()
            print(json.dumps({'page':'http://127.0.0.1:8765/pilot/','status':'completed',
                'loaded_full_resolution_images':25,'methods':3,'stylesheet_verified':True,
                'javascript_errors':[],'source_selection':report['selection_id']},indent=2))
        finally:
            chrome.terminate()
            try:chrome.wait(timeout=10)
            except subprocess.TimeoutExpired:chrome.kill();chrome.wait()
            log.close()


if __name__=='__main__':main()
