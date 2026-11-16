"""Real browser, adjacent-only loading, gestures, GPU reuse and persistent cache.

State is isolated. No production jobs, approvals, remote calls or geometry edits.
Run with --fallback to exercise the non-WebGL renderer as well.
"""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from browser_check import CDP, ROOT, PYTHON


def main():
    fallback="--fallback" in sys.argv
    with tempfile.TemporaryDirectory(prefix="alignment-browser-",dir="/tmp/opencode") as directory:
        temp=Path(directory)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
        log=(temp/"process.log").open("w")
        app=subprocess.Popen([PYTHON,"-B",str(ROOT/"app.py"),"--port",str(port),"--state-dir",str(temp/"state")],
                             cwd=ROOT,stdout=log,stderr=log)
        chrome=None
        try:
            for _ in range(600):
                try:
                    with urlopen(f"http://127.0.0.1:{port}/api/health",timeout=1) as r:
                        if json.load(r)["status"]=="ready":break
                except OSError:
                    if app.poll() is not None:raise RuntimeError((temp/"process.log").read_text())
                    time.sleep(.1)
            profile=temp/"chrome"
            chrome=subprocess.Popen(["google-chrome","--headless",
                *(["--disable-webgl","--disable-gpu"] if fallback else ["--enable-unsafe-swiftshader"]),
                "--disable-background-networking","--no-first-run","--no-default-browser-check",
                "--remote-debugging-port=0","--remote-allow-origins=http://localhost",
                "--user-data-dir="+str(profile),"--window-size=1600,1100","about:blank"],stdout=log,stderr=log)
            for _ in range(100):
                active=profile/"DevToolsActivePort"
                if active.exists():break
                time.sleep(.1)
            debug_port=int(active.read_text().splitlines()[0])
            with urlopen(f"http://127.0.0.1:{debug_port}/json/list") as r:pages=json.load(r)
            cdp=CDP(next(p["webSocketDebuggerUrl"] for p in pages if p["type"]=="page"))
            cdp.call("Runtime.enable");cdp.call("Page.enable")
            cdp.call("Page.navigate",{"url":f"http://127.0.0.1:{port}"})
            cdp.wait('document.body.dataset.ready === "true"',timeout=90)
            assert cdp.js("roiApp.state.data === null")
            assert cdp.js("alignmentApp.state.geometry === null")
            assert cdp.js("alignmentApp.state.selected === false")
            assert cdp.js("document.getElementById('alignRGB').checked")
            assert cdp.js("document.getElementById('alignStart').disabled")
            assert cdp.js("performance.getEntriesByType('resource').filter(r=>/\\/api\\/(overview|dataset)|\\/cloud\\//.test(r.name)).length")==0
            cdp.screenshot("alignment-setup-"+("fallback" if fallback else "gpu")+".png")
            park=cdp.js("alignmentApp.state.catalog.pending.find(r=>r.block==='026').id")
            cdp.js(f"document.getElementById('alignIncoming').value={json.dumps(park)};document.getElementById('alignIncoming').dispatchEvent(new Event('change'))")
            cdp.js("document.querySelector('#alignAnchors input[value=\"001\"]').click();document.querySelector('#alignAnchors input[value=\"025\"]').click()")
            assert cdp.js("alignmentApp.cache.stats.network")==0
            cdp.js("document.getElementById('alignStart').click()")
            cdp.wait("alignmentApp.state.geometry?.views.length === 1577 && document.getElementById('alignLoading').hidden",timeout=90)
            assert cdp.js("Object.keys(alignmentApp.state.anchorGeometry).sort()")==["001","025"]
            assert cdp.js("alignmentApp.cache.stats.network")==3
            assert cdp.js("performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/overview')).length")==0
            assert cdp.js("document.getElementById('alignRun').disabled")
            assert cdp.js("document.getElementById('alignInspector').inert")
            assert cdp.js("document.getElementById('alignmentCanvas').clientWidth / document.getElementById('alignEditor').clientWidth")>.95
            cdp.js("document.getElementById('alignInspectorToggle').click()")
            assert not cdp.js("document.getElementById('alignInspector').inert")
            assert cdp.js("getComputedStyle(document.querySelector('.scene-header')).backgroundColor")=="rgb(16, 16, 16)"
            if fallback:assert cdp.js("alignmentApp.renderer.backend")=="Canvas optimizado"
            else:assert cdp.js("alignmentApp.renderer.backend")=="WebGL"
            initial=cdp.js("alignmentApp.state.matrix")
            pivot=cdp.js("alignmentApp.apply(alignmentApp.state.matrix,alignmentApp.state.geometry.origin)")
            uploads=cdp.js("alignmentApp.renderer.uploads")
            perf=cdp.js("""(async()=>{
              const slider=document.getElementById('sliderRz'),start=performance.now();
              alignmentApp.state.metrics.renderTimes=[];
              for(let i=0;i<60;i++){slider.value=i*.5;slider.dispatchEvent(new Event('input'));await new Promise(requestAnimationFrame);}
              slider.dispatchEvent(new Event('change'));await new Promise(requestAnimationFrame);
              const times=alignmentApp.state.metrics.renderTimes.slice().sort((a,b)=>a-b);
              return {renderer:alignmentApp.renderer.backend,elapsed_ms:performance.now()-start,
                frames:times.length,median_render_ms:times[Math.floor(times.length*.5)],p95_render_ms:times[Math.floor(times.length*.95)],
                point_count:alignmentApp.state.geometry.render_count+Object.values(alignmentApp.state.anchorGeometry).reduce((n,d)=>n+d.render_count,0)};
            })()""")
            assert cdp.js("alignmentApp.renderer.uploads")==uploads
            cdp.screenshot("alignment-monochrome-closed-"+("fallback" if fallback else "gpu")+".png")
            assert cdp.js("alignmentApp.state.undo.length")==1
            newpivot=cdp.js("alignmentApp.apply(alignmentApp.state.matrix,alignmentApp.state.geometry.origin)")
            assert max(abs(a-b) for a,b in zip(pivot,newpivot))<1e-8
            assert abs(cdp.js("alignmentApp.state.pose.angles[2]")-29.5)<1e-7
            cdp.js("document.getElementById('alignUndo').click()")
            assert cdp.js("alignmentApp.state.matrix")==initial
            cdp.js("document.getElementById('alignRedo').click()")
            # Scale slider, then height, preserve pivot semantics.
            cdp.js("document.getElementById('alignScaleSlider').value=50;document.getElementById('alignScaleSlider').dispatchEvent(new Event('input'));document.getElementById('alignScaleSlider').dispatchEvent(new Event('change'))")
            assert abs(cdp.js("alignmentApp.state.pose.scale")-2)<1e-8
            assert abs(cdp.js("alignmentApp.state.pose.angles[2]")-29.5)<1e-7
            old_z=cdp.js("alignmentApp.state.pose.position[2]")
            cdp.js("document.getElementById('alignHeightSlider').value=1.25;document.getElementById('alignHeightSlider').dispatchEvent(new Event('input'));document.getElementById('alignHeightSlider').dispatchEvent(new Event('change'))")
            assert abs(cdp.js("alignmentApp.state.pose.position[2]")-old_z-1.25)<1e-8
            assert abs(cdp.js("alignmentApp.state.pose.angles[2]")-29.5)<1e-7
            for axis,value in (("Rx",15),("Ry",-8)):
                cdp.js(f"document.getElementById('slider{axis}').value={value};document.getElementById('slider{axis}').dispatchEvent(new Event('input'));document.getElementById('slider{axis}').dispatchEvent(new Event('change'))")
            assert abs(cdp.js("alignmentApp.state.pose.angles[0]")-15)<1e-7
            assert abs(cdp.js("alignmentApp.state.pose.angles[1]")+8)<1e-7
            # Real pointer drag: no typing is required for placement.
            location=cdp.js("""(()=>{const c=document.getElementById('alignmentCanvas'),r=c.getBoundingClientRect();
              return [r.left+r.width*.6,r.top+r.height*.6,alignmentApp.state.camera.scale]})()""")
            x,y,scale=location
            before=cdp.js("alignmentApp.state.matrix[0][3]")
            cdp.js("alignmentApp.setTool('move')")
            cdp.call("Input.dispatchMouseEvent",{"type":"mousePressed","x":x,"y":y,"button":"left","clickCount":1})
            cdp.call("Input.dispatchMouseEvent",{"type":"mouseMoved","x":x+60,"y":y-20,"button":"left","buttons":1})
            cdp.call("Input.dispatchMouseEvent",{"type":"mouseReleased","x":x+60,"y":y-20,"button":"left"})
            assert abs(cdp.js("alignmentApp.state.matrix[0][3]")-before-60/scale)<1e-6
            cdp.js("document.querySelector('[data-tool=\"rotate\"]').click()")
            pivot_before=cdp.js("alignmentApp.apply(alignmentApp.state.matrix,alignmentApp.state.geometry.origin)")
            location=cdp.js("""(()=>{const c=document.getElementById('alignmentCanvas'),r=c.getBoundingClientRect(),
              p=alignmentApp.screen(alignmentApp.apply(alignmentApp.state.matrix,alignmentApp.state.geometry.origin));return [r.left+p[0],r.top+p[1]];})()""")
            x,y=location
            cdp.call("Input.dispatchMouseEvent",{"type":"mousePressed","x":x+80,"y":y,"button":"left","clickCount":1})
            cdp.call("Input.dispatchMouseEvent",{"type":"mouseMoved","x":x,"y":y-80,"button":"left","buttons":1})
            cdp.call("Input.dispatchMouseEvent",{"type":"mouseReleased","x":x,"y":y-80,"button":"left"})
            pivot_after=cdp.js("alignmentApp.apply(alignmentApp.state.matrix,alignmentApp.state.geometry.origin)")
            assert max(abs(a-b) for a,b in zip(pivot_before,pivot_after))<1e-8
            # Pointer offsets are rounded to CSS pixels by Chrome; sliders above
            # test exact angles, while this checks the real 80px mouse gesture.
            rotated=cdp.js("alignmentApp.state.pose.angles[2]")
            assert abs(rotated-119.5)<1,rotated
            cdp.js("document.querySelector('[data-tool=\"move\"]').click()")
            cdp.js("alignmentApp.setPanel('views')")
            cdp.wait("document.querySelector('#alignGallery input') !== null")
            cdp.js("document.querySelector('#alignGallery input').click()")
            cdp.js("document.getElementById('alignRole').value='validation';document.querySelectorAll('#alignGallery input')[1].click()")
            assert cdp.js("alignmentApp.state.edges[0].forward.views.length")==2
            cdp.js("document.getElementById('alignDirection').value='reverse';document.getElementById('alignDirection').dispatchEvent(new Event('change'))")
            cdp.js("document.querySelector('#alignGallery input').click()")
            assert cdp.js("alignmentApp.state.edges[0].reverse.views.length")==1
            saved=cdp.js("alignmentApp.save()")
            matrix=saved["matrix"]
            cdp.js("alignmentApp.setPanel('pose')")
            cdp.screenshot("alignment-workbench-"+("fallback" if fallback else "gpu")+".png")
            cdp.js(f"alignmentApp.loadSession({json.dumps(saved['id'])})")
            assert cdp.js("alignmentApp.state.matrix")==matrix
            assert cdp.js("alignmentApp.cache.stats.network")==3
            assert cdp.js("alignmentApp.cache.stats.memory")>=3
            assert cdp.js("alignmentApp.renderer.uploads")==uploads
            # An app reload uses IndexedDB, not another cloud transfer.
            cdp.js("alignmentApp.persistDraft()")
            cdp.wait("alignmentApp.cache.stored(alignmentApp.state.geometry.key).then(Boolean)")
            cdp.call("Page.reload")
            cdp.wait('window.alignmentApp?.state.catalog && alignmentApp.state.geometry === null && document.body?.dataset.ready === "true"',timeout=60)
            cdp.js(f"alignmentApp.openScene({json.dumps(park)},['001','025'])")
            cdp.wait("alignmentApp.state.geometry?.views.length === 1577 && document.getElementById('alignLoading').hidden",timeout=60)
            assert cdp.js("alignmentApp.cache.stats.disk")==3
            assert cdp.js("alignmentApp.cache.stats.network")==0
            assert cdp.js("alignmentApp.state.matrix")==matrix
            assert cdp.js("alignmentApp.state.edges[0].forward.views.length")==2
            assert cdp.js("alignmentApp.state.edges[0].reverse.views.length")==1
            assert cdp.js("alignmentApp.state.selected === false")
            assert cdp.js("document.getElementById('alignInspector').inert")
            assert cdp.js("document.getElementById('alignRGB').checked")
            assert cdp.js("alignmentApp.api('jobs')")==[]
            # Smooth navigation never changes the exact reconstruction matrix.
            matrix_before=cdp.js("JSON.stringify(alignmentApp.state.matrix)")
            frames_before=cdp.js("alignmentApp.state.metrics.frames")
            cdp.js("document.getElementById('alignmentCanvas').dispatchEvent(new WheelEvent('wheel',{deltaY:-120,bubbles:true,cancelable:true}))")
            cdp.wait(f"alignmentApp.state.metrics.frames > {frames_before}+3")
            assert cdp.js("JSON.stringify(alignmentApp.state.matrix)")==matrix_before
            cdp.call("Emulation.setEmulatedMedia",{"features":[{"name":"prefers-reduced-motion","value":"reduce"}]})
            assert cdp.js("matchMedia('(prefers-reduced-motion: reduce)').matches")
            assert cdp.js("getComputedStyle(document.getElementById('alignInspector')).transitionDuration")=="0s"
            cdp.call("Emulation.setEmulatedMedia",{"features":[]})
            # ROI remains lazy and functional.
            cdp.js("document.getElementById('roiTab').click()")
            cdp.wait("roiApp.state.data !== null && !roiApp.state.loading",timeout=90)
            assert cdp.js("roiApp.state.block")==""  # no implicit 025 / color highlight
            assert cdp.js("document.getElementById('drawBtn').disabled")
            cdp.js("document.getElementById('roiControlsToggle').click();document.getElementById('blockSelect').value='025';document.getElementById('blockSelect').dispatchEvent(new Event('change'))")
            cdp.wait("roiApp.state.data?.sparse_count === 70788",timeout=90)
            cdp.js("""(()=>{const a=roiApp.state.data.focus_bounds[0],b=roiApp.state.data.focus_bounds[1];
              const x=a[0]+(b[0]-a[0])*.2,y=a[1]+(b[1]-a[1])*.2,dx=(b[0]-a[0])*.3,dy=(b[1]-a[1])*.3;
              roiApp.state.vertices=[[x,y],[x+dx,y],[x+dx,y+dy],[x,y+dy]];roiApp.closePolygon();})()""")
            cdp.wait("roiApp.state.valid");cdp.js("roiApp.saveSelection()");assert cdp.js("!!roiApp.state.selection")
            cdp.js("roiApp.selectBlock('')")
            assert cdp.js("roiApp.state.block")=="" and not cdp.js("!!roiApp.state.selection")
            assert not cdp.errors,cdp.errors
            assert perf["p95_render_ms"]<100,perf
            Path("/tmp/opencode/alignment-perf-"+("fallback" if fallback else "gpu")+".json").write_text(json.dumps(perf,indent=2))
            print("BROWSER PASS",json.dumps(perf))
        finally:
            if chrome:chrome.terminate();chrome.wait(timeout=15)
            app.terminate();app.wait(timeout=15);log.close()


if __name__=="__main__":
    main()
