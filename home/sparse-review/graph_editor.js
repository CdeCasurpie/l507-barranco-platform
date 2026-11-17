'use strict';
const ctx=window.EDITOR_CONTEXT,$=id=>document.getElementById(id),canvas=$('view'),overlay=$('overlay'),ink=overlay.getContext('2d');
const api='/api/editor/'+ctx.dataset+'/'+ctx.component+'/';
let meta=null,base=null,data=null,offsets=null,members=null,centers=[],delta=[],selected=-1,pins=new Map(),history=[],undo=[],redo=[],revisionId='',jobId='';
let yaw=.5,pitch=-.35,distance=3.2,pan=[0,0],mvp=null,inverse=null,drag=null,sequence=0,queued=false,pending=false,dirty=0,lastSaved=-1;
let mode='move',rotations=[];
$('stiffness').disabled=true;$('stiffness').parentElement.style.display='none';
let deleted=new Set();
let multi=new Set(),brush=false,brushCursor=null;
function multiLabel(){$('multiSummary').textContent=multi.size+' cámaras seleccionadas';}
function clearMulti(){multi.clear();brush=false;brushCursor=null;multiLabel();draw();}
$('clearMulti').onclick=clearMulti;
$('brushMode').onclick=()=>{brush=!brush;$('move').checked=false;$('notice').textContent=brush?'Pincel: arrastra para seleccionar · Mayús resta · rueda cambia tamaño':'Pincel desactivado';draw();};
function viewpoint(kind){if(kind==='top'){yaw=0;pitch=Math.PI/2;}if(kind==='front'){yaw=0;pitch=0;}if(kind==='side'){yaw=Math.PI/2;pitch=0;}if(kind==='opposite'){yaw+=Math.PI;pitch=-pitch;}draw();}
$('topView').onclick=()=>viewpoint('top');$('frontView').onclick=()=>viewpoint('front');$('sideView').onclick=()=>viewpoint('side');
function paint(x,y,subtract){if(!meta)return;const radius=Number($('brushRadius').value);centers.forEach((c,i)=>{const id=meta.cameras[i].id;if(deleted.has(id))return;const p=project(c);if(p.z< -1||p.z>1)return;if((p.x-x)**2+(p.y-y)**2<=radius*radius){if(subtract)multi.delete(id);else multi.add(id);}});multiLabel();draw();}
window.addEventListener('keydown',e=>{
 if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))return;
 const key=e.key.toLowerCase(),mod=e.ctrlKey||e.metaKey;
 if(mod&&key==='s'){e.preventDefault();$('save').click();return;}
 if(mod&&key==='z'){e.preventDefault();$(e.shiftKey?'redo':'undo').click();return;}
 if(mod&&key==='y'){e.preventDefault();$('redo').click();return;}
 if(mod&&key==='a'){e.preventDefault();if(meta){multi=new Set(meta.cameras.filter(c=>!deleted.has(c.id)).map(c=>c.id));multiLabel();draw();}return;}
 if(key==='c'){$('brushMode').click();e.preventDefault();}
 if(key==='escape'){clearMulti();$('move').checked=false;}
 if(key==='7'||e.code==='Numpad7')viewpoint('top');
 if(key==='1'||e.code==='Numpad1')viewpoint('front');
 if(key==='3'||e.code==='Numpad3')viewpoint('side');
 if(key==='9'||e.code==='Numpad9')viewpoint('opposite');
 if(key==='h'){$('showGraph').checked=!$('showGraph').checked;draw();}
 if(key==='f'){pan=[0,0];distance=3.2;draw();}
});
const rotate=(r,v)=>r.map(row=>row.reduce((s,x,k)=>s+x*v[k],0));
function setMode(value){mode=value;brush=false;brushCursor=null;$('move').checked=true;$('modeLabel').textContent=value==='move'?'G · arrastra una cámara para moverla':'R · arrastra para girar solo sobre el eje local X/Y/Z elegido.';draw();}
$('modeMove').onclick=()=>setMode('move');$('modeRotate').onclick=()=>setMode('rotate');
window.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))return;if(e.key.toLowerCase()==='g')setMode('move');if(e.key.toLowerCase()==='r')setMode('rotate');});
window.addEventListener('keydown',e=>{if(e.key==='Delete'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)){e.preventDefault();$('deleteCamera').click();}});
const gl=canvas.getContext('webgl',{antialias:true,alpha:false});
if(!gl)throw Error('WebGL requerido');
const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
const program=gl.createProgram();
gl.attachShader(program,shader(gl.VERTEX_SHADER,'attribute vec3 p;attribute vec3 c;uniform mat4 m;varying vec3 color;void main(){gl_Position=m*vec4(p,1.);gl_PointSize=2.;color=c;}'));
gl.attachShader(program,shader(gl.FRAGMENT_SHADER,'precision mediump float;varying vec3 color;void main(){gl_FragColor=vec4(color,1.);}'));
gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
for(const [name,offset] of [['p',0],['c',12]]){const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,3,gl.FLOAT,false,32,offset);}
const matrixUniform=gl.getUniformLocation(program,'m');
function mul(a,b){const o=new Float64Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o;}
function invert(m){let a=Array.from({length:4},(_,r)=>Array.from({length:8},(_,c)=>c<4?m[c*4+r]:+(c-4===r)));for(let c=0;c<4;c++){let p=c;for(let r=c+1;r<4;r++)if(Math.abs(a[r][c])>Math.abs(a[p][c]))p=r;[a[c],a[p]]=[a[p],a[c]];if(Math.abs(a[c][c])<1e-15)return null;let v=a[c][c];for(let j=0;j<8;j++)a[c][j]/=v;for(let r=0;r<4;r++)if(r!==c){v=a[r][c];for(let j=0;j<8;j++)a[r][j]-=v*a[c][j];}}return Array.from({length:16},(_,i)=>a[i%4][4+Math.floor(i/4)]);}
function transform(m,p){const q=[...p,1],v=Array.from({length:4},(_,r)=>q.reduce((s,x,k)=>s+m[k*4+r]*x,0));return v.slice(0,3).map(x=>x/v[3]);}
function project(center){if(!mvp||!meta)return null;const q=transform(mvp,center.map((x,k)=>(x-meta.center[k])/meta.display_radius));return{x:(q[0]+1)*canvas.clientWidth/2,y:(1-q[1])*canvas.clientHeight/2,z:q[2]};}
function unproject(x,y,z){return transform(inverse,[x/canvas.clientWidth*2-1,1-y/canvas.clientHeight*2,z]).map((v,k)=>v*meta.display_radius+meta.center[k]);}
function draw(){
 const dpr=Math.min(2,devicePixelRatio||1),w=Math.max(1,Math.round(canvas.clientWidth*dpr)),h=Math.max(1,Math.round(canvas.clientHeight*dpr));
 canvas.width=w;canvas.height=h;overlay.width=w;overlay.height=h;ink.setTransform(dpr,0,0,dpr,0,0);
 gl.viewport(0,0,w,h);gl.clearColor(.04,.055,.065,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
 const c=Math.cos(yaw),s=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
 const ry=[c,0,-s,0,0,1,0,0,s,0,c,0,0,0,0,1],rx=[1,0,0,0,0,cp,sp,0,0,-sp,cp,0,0,0,0,1],t=[1,0,0,0,0,1,0,0,0,0,1,0,pan[0],pan[1],-distance,1];
 const f=1/Math.tan(Math.PI/8),near=.001,far=Math.max(1000,distance*100),projection=[f/(w/h),0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0];
 mvp=mul(projection,mul(t,mul(rx,ry)));inverse=invert(mvp);gl.uniformMatrix4fv(matrixUniform,false,new Float32Array(mvp));if(data)gl.drawArrays(gl.POINTS,0,data.length/8);
 if(!meta)return;
 const projected=centers.map(project);
 for(let i=0;i<projected.length;i++)if(deleted.has(meta.cameras[i].id))projected[i]={x:0,y:0,z:2};
 if($('showGraph').checked){ink.lineWidth=.5;for(const e of meta.edges.slice(0,1500)){let a=projected[e.a],b=projected[e.b];if(a.z>1||b.z>1||a.z< -1||b.z< -1)continue;ink.strokeStyle=e.kind==='visual'?'#65b89644':'#aaaaaa33';ink.beginPath();ink.moveTo(a.x,a.y);ink.lineTo(b.x,b.y);ink.stroke();}}
 meta.cameras.forEach((camera,i)=>{const p=projected[i];if(p.z>1||p.z< -1)return;const pin=pins.get(camera.id);ink.fillStyle=i===selected?'#fff':pin?.kind==='anchor'?'#58e3a4':pin?'#ff6c6c':'#ff983d';ink.beginPath();ink.arc(p.x,p.y,i===selected?6:pin?4:2,0,Math.PI*2);ink.fill();if(i===selected){ink.font='bold 13px system-ui';ink.fillText('#'+camera.id,p.x+10,p.y);}});
 meta.cameras.forEach((camera,i)=>{if(i!==selected&&pins.size&& !pins.has(camera.id))return;const a=projected[i];if(a.z>1||a.z< -1)return;const direction=rotations.length?rotate(rotations[i],camera.direction):camera.direction;const b=project(centers[i].map((v,k)=>v+direction[k]*meta.display_radius*(i===selected?.12:.035)));if(b.z>1||b.z< -1)return;ink.strokeStyle=i===selected?'#fff':'#ffb86b';ink.lineWidth=i===selected?2:1;ink.beginPath();ink.moveTo(a.x,a.y);ink.lineTo(b.x,b.y);const angle=Math.atan2(b.y-a.y,b.x-a.x);for(const off of [-.5,.5]){ink.moveTo(b.x,b.y);ink.lineTo(b.x-7*Math.cos(angle+off),b.y-7*Math.sin(angle+off));}ink.stroke();});
 meta.cameras.forEach((c,i)=>{if(!multi.has(c.id)||deleted.has(c.id))return;const p=projected[i];if(p.z< -1||p.z>1)return;ink.strokeStyle='#5cf';ink.lineWidth=2;ink.beginPath();ink.arc(p.x,p.y,7,0,Math.PI*2);ink.stroke();});
 if(brush&&brushCursor){ink.strokeStyle='#fff';ink.lineWidth=1;ink.setLineDash([4,3]);ink.beginPath();ink.arc(brushCursor.x,brushCursor.y,Number($('brushRadius').value),0,Math.PI*2);ink.stroke();ink.setLineDash([]);}
}
function rebuild(){
 if(!meta||!base)return;data=new Float32Array(base);
 for(let p=0;p<meta.points;p++){let count=0;let sum=[0,0,0];const xyz=[0,1,2].map(k=>base[p*8+k]*meta.display_radius+meta.center[k]);for(let j=offsets[p];j<offsets[p+1];j++){const i=members[j];if(deleted.has(meta.cameras[i].id))continue;count++;const c=meta.cameras[i].center,r=rotations[i];for(let k=0;k<3;k++){let v=delta[i][k];if(r)for(let l=0;l<3;l++)v+=(r[k][l]-(k===l?1:0))*(xyz[l]-c[l]);sum[k]+=v;}}if(!count){data[p*8]=1e20;continue;}for(let k=0;k<3;k++)data[p*8+k]+=sum[k]/count/meta.display_radius;}
 centers=meta.cameras.map((c,i)=>c.center.map((x,k)=>x+delta[i][k]));
 centers.forEach((c,i)=>c.forEach((x,k)=>data[(meta.points+i)*8+k]=deleted.has(meta.cameras[i].id)?1e20:(x-meta.center[k])/meta.display_radius));
 gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,data,gl.DYNAMIC_DRAW);draw();
}
const payload=()=>({revision:meta.revision,pins:[...pins.values()],deleted:[...deleted],stiffness:10**Number($('stiffness').value),radius:Number($('radius').value),direct_only:$('directOnly').checked,influence_mode:'elastic'});
async function request(url,body){const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Barranco-Editor':'1'},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());return r.json();}
function schedule(){queued=true;if(!pending)void solve();}
async function solve(){if(!queued||!meta)return;queued=false;pending=true;try{const result=await request(api+'solve',payload());delta=result.displacements;rotations=result.rotations;for(const pin of pins.values()){const i=meta.cameras.findIndex(c=>c.id===pin.id);delta[i]=pin.target.map((v,k)=>v-meta.cameras[i].center[k]);}rebuild();$('notice').textContent='Borrador visual no validado · originales intactos';}catch(e){$('notice').textContent=e.message;}finally{pending=false;if(queued)void solve();}}
function snapshot(){undo.push(JSON.stringify(payload()));if(undo.length>100)undo.shift();redo=[];}
function applyState(value){const p=JSON.parse(value);pins=new Map(p.pins.map(v=>[v.id,v]));deleted=new Set(p.deleted||[]);selected=-1;$('stiffness').value=Math.log10(p.stiffness);$('radius').value=p.radius||10;$('directOnly').checked=!!p.direct_only;updateRadius();dirty++;$('search').oninput();renderPins();schedule();}
function renderPins(){$('pins').textContent=[...pins.values()].map(p=>(p.kind==='anchor'?'Fija ':'Mover ')+'#'+p.id).join(' · ')+' · Excluidas: '+deleted.size;showSelected();}
function showSelected(){if(selected<0)return;const c=meta.cameras[selected],pin=pins.get(c.id),target=pin?.target||centers[selected];$('selected').textContent='#'+c.id+' · '+c.name;['x','y','z'].forEach((id,k)=>$(id).value=target[k]);['rx','ry','rz'].forEach((id,k)=>$(id).value=pin?.rotation?.[k]||0);}
function choose(i){selected=i;showSelected();draw();}
function setTarget(target,angles=null){const c=meta.cameras[selected];pins.set(c.id,{id:c.id,target,kind:'move',rotation:angles||pins.get(c.id)?.rotation||[0,0,0],rotation_space:angles?'camera':pins.get(c.id)?.rotation_space||'world'});dirty++;renderPins();schedule();}
function pick(x,y){let best=-1,d=144;centers.forEach((c,i)=>{if(deleted.has(meta.cameras[i].id))return;const p=project(c);if(p.z< -1||p.z>1)return;const v=(p.x-x)**2+(p.y-y)**2;if(v<d){d=v;best=i;}});return best;}
canvas.oncontextmenu=e=>e.preventDefault();
canvas.onpointerdown=e=>{
 if(!meta)return;const rect=canvas.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;
 if(brush&&e.button===0){drag={brush:true};brushCursor={x,y};paint(x,y,e.shiftKey);canvas.setPointerCapture(e.pointerId);return;}
 const hit=pick(x,y);const moving=$('move').checked&&e.button===0&&!e.shiftKey;
 if(hit>=0)choose(hit);
 if(moving&&hit<0)return;
 drag={x:e.clientX,y:e.clientY,move:moving,pan:e.shiftKey||e.button!==0,started:false};
 if(moving){const pin=pins.get(meta.cameras[selected].id);if(pin?.kind==='anchor'){$('notice').textContent='Quita primero la restricción fija para mover esta cámara';drag=null;return;}snapshot();drag.depth=project(centers[selected]).z;drag.target=[...(pin?.target||centers[selected])];drag.angles=[...(pin?.rotation||[0,0,0])];}
 canvas.setPointerCapture(e.pointerId);
};
canvas.onpointermove=e=>{if(brush){const rect=canvas.getBoundingClientRect();brushCursor={x:e.clientX-rect.left,y:e.clientY-rect.top};if(drag?.brush){paint(brushCursor.x,brushCursor.y,e.shiftKey);return;}if(!drag){draw();return;}}if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)<1)return;drag.started=true;if(drag.move){if(mode==='rotate'){const axis={x:0,y:1,z:2}[$('rotationAxis').value];drag.angles[axis]+=(dx-dy)*.4;setTarget(drag.target,[...drag.angles]);}else{const rect=canvas.getBoundingClientRect();setTarget(unproject(e.clientX-rect.left,e.clientY-rect.top,drag.depth));}}else if(drag.pan){pan[0]+=dx/canvas.clientHeight*distance*.7;pan[1]-=dy/canvas.clientHeight*distance*.7;draw();}else{yaw+=dx*.007;pitch+=dy*.007;draw();}drag.x=e.clientX;drag.y=e.clientY;};
for(const event of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(event,()=>drag=null);
function updateRadius(){$('radiusLabel').textContent=($('directOnly').checked?'Solo vecinas directas':$('radius').value+' conexiones')+' · núcleo rígido, caída suave';}
canvas.addEventListener('wheel',e=>{e.preventDefault();if(brush){$('brushRadius').value=Math.max(5,Math.min(150,Number($('brushRadius').value)+(e.deltaY<0?5:-5)));draw();}else if(drag?.move){$('radius').value=Math.max(1,Math.min(100,Number($('radius').value)+(e.deltaY<0?1:-1)));$('directOnly').checked=false;updateRadius();dirty++;schedule();}else{distance=Math.max(.02,Math.min(10000,distance*Math.exp(e.deltaY*.001)));draw();}},{passive:false});
$('radius').onpointerdown=()=>{if(meta)snapshot();};
$('radius').oninput=()=>{updateRadius();dirty++;schedule();};
$('directOnly').onchange=()=>{snapshot();updateRadius();dirty++;schedule();};
$('showGraph').onchange=draw;
$('search').oninput=()=>{if(!meta)return;const q=$('search').value.trim().toLowerCase();$('cameras').replaceChildren();meta.cameras.forEach((c,i)=>{if(deleted.has(c.id))return;if(q&&(!(/^\d+$/.test(q)?String(c.id)===q:c.name.toLowerCase().includes(q))))return;if($('cameras').options.length>=100)return;const o=document.createElement('option');o.value=i;o.textContent='#'+c.id+' '+c.name;$('cameras').append(o);});};
$('choose').onclick=()=>{if($('cameras').value!=='')choose(Number($('cameras').value));};
$('apply').onclick=()=>{if(selected<0)return;const target=['x','y','z'].map(id=>Number($(id).value));if(!target.every(Number.isFinite))return;snapshot();setTarget(target);};
$('applyRotation').onclick=()=>{if(selected<0)return;const angles=['rx','ry','rz'].map(id=>Number($(id).value));if(!angles.every(Number.isFinite))return;snapshot();setTarget(pins.get(meta.cameras[selected].id)?.target||[...centers[selected]],angles);};
$('anchor').onclick=()=>{if(selected<0)return;snapshot();const c=meta.cameras[selected];pins.set(c.id,{id:c.id,target:[...c.center],kind:'anchor'});dirty++;renderPins();schedule();};
$('release').onclick=()=>{if(selected<0)return;snapshot();pins.delete(meta.cameras[selected].id);dirty++;renderPins();schedule();};
$('deleteCamera').onclick=()=>{if(!meta)return;const targets=multi.size?[...multi].filter(i=>!deleted.has(i)):selected>=0?[meta.cameras[selected].id]:[];if(!targets.length)return;if(meta.cameras.length-deleted.size-targets.length<2){alert('Conserva al menos dos cámaras');return;}if(targets.length>1&&!confirm('¿Excluir '+targets.length+' cámaras de esta copia? Puedes deshacer.'))return;snapshot();for(const id of targets){deleted.add(id);pins.delete(id);}multi.clear();multiLabel();selected=-1;dirty++;$('selected').textContent=targets.length+' cámaras excluidas · puedes deshacer';$('search').oninput();renderPins();schedule();};
$('stiffness').onchange=()=>{dirty++;schedule();};
$('undo').onclick=()=>{if(!undo.length)return;redo.push(JSON.stringify(payload()));applyState(undo.pop());};
$('redo').onclick=()=>{if(!redo.length)return;undo.push(JSON.stringify(payload()));applyState(redo.pop());};
$('reset').onclick=()=>{if(!meta)return;snapshot();pins.clear();deleted.clear();dirty++;$('search').oninput();renderPins();schedule();};
async function historyRefresh(){history=await request(api+'history');$('history').replaceChildren();for(const r of history){let o=document.createElement('option');o.value=r.id;o.textContent=r.id.slice(0,12)+' · '+new Date(r.created_at*1000).toLocaleString();$('history').append(o);}}
$('restore').onclick=()=>{const r=history.find(r=>r.id===$('history').value);if(!r)return;if(r.revision!==meta.revision){alert('La fuente cambió; no se carga una revisión incompatible');return;}snapshot();applyState(JSON.stringify(r));lastSaved=dirty;};
$('save').onclick=async()=>{try{const r=await request(api+'save',payload());revisionId=r.id;lastSaved=dirty;$('notice').textContent='Revisión guardada: '+r.id+' · no validada';await historyRefresh();}catch(e){$('notice').textContent=e.message;}};
async function jobPoll(){if(!jobId)return;try{const r=await request('/api/job/'+jobId);$('job').textContent=JSON.stringify(r,null,2);if(['starting','running'].includes(r.state))setTimeout(jobPoll,2500);else $('cancel').disabled=true;}catch(e){$('job').textContent=e.message;}}
$('adjust').onclick=async()=>{if(!meta||!confirm('¿Retriangular una copia desde matches existentes, manteniendo TODAS las cámaras editadas fijas? SIN BA ni densificación.'))return;try{const r=await request(api+'adjust',payload());jobId=r.id;$('cancel').disabled=false;lastSaved=dirty;await jobPoll();}catch(e){$('job').textContent=e.message;}};
$('cancel').onclick=async()=>{if(jobId&&confirm('¿Cancelar solo este ajuste?')){await request('/api/cancel/'+jobId,{});void jobPoll();}};
window.addEventListener('beforeunload',e=>{if(meta&&dirty!==lastSaved&&(pins.size||deleted.size)){e.preventDefault();e.returnValue='';}});
new ResizeObserver(draw).observe(canvas);
(async()=>{try{
 $('title').textContent=ctx.label+' · editor manual';$('back').href='/view/'+ctx.dataset+'/';
 meta=await request(api+'graph');const response=await fetch(api+'cloud.bin');if(!response.ok)throw Error(await response.text());base=new Float32Array(await response.arrayBuffer());
 const decode=(value,Type)=>{const bytes=Uint8Array.from(atob(value),c=>c.charCodeAt(0));return new Type(bytes.buffer);};
 offsets=decode(meta.offsets,Uint32Array);members=decode(meta.memberships,Uint16Array);delta=meta.cameras.map(()=>[0,0,0]);rotations=meta.cameras.map(()=>[[1,0,0],[0,1,0],[0,0,1]]);
 rebuild();$('search').oninput();await historyRefresh();lastSaved=dirty;
 $('notice').textContent='Grafo listo · '+meta.cameras.length+' cámaras · selecciona cámaras móviles y fijas. Original intacto.';
}catch(e){$('notice').textContent=e.message;}})();
