/* Read-only sparse overview. No POST endpoints, model edits or placement writes. */
(()=>{
'use strict';
const root=document.getElementById('sparseViewWorkspace'),tab=document.getElementById('sparseViewTab');
root.innerHTML=`<div style="padding:14px;display:flex;gap:12px;flex-wrap:wrap;align-items:center">
<strong>Visualizador sparse · solo lectura</strong>
<select id="svProjection" aria-label="Proyección"><option value="ortho">Ortográfica</option><option value="perspective">Perspectiva</option></select>
<select id="svColor" aria-label="Color"><option value="block">Color por manzana</option><option value="rgb">RGB original</option></select>
<label>Puntos <input id="svSize" type="range" min="1" max="10" step=".5" value="2"></label>
<label><input id="svGrid" type="checkbox" checked>Cuadrícula XY</label>
<button id="svTop">Arriba · 7</button><button id="svOrbit">Oblicua</button><button id="svFit">Encuadrar · F</button>
<button id="svReload">Actualizar colocaciones</button><span id="svStatus">Sin cargar</span>
</div><div style="display:flex;height:calc(100vh - 155px);min-height:400px">
<aside style="width:210px;overflow:auto;padding:12px;flex-shrink:0"><button id="svAll">Todas</button> <button id="svNone">Ninguna</button><div id="svLayers"></div>
<p>Arrastra: orbitar<br>Mayús / botón derecho: desplazar<br>Rueda: zoom<br>7: superior · F: encuadrar</p>
<small>Sparse muestreadas para visualizar; no son las nubes densas. No modifica nada.</small></aside>
<canvas id="svCanvas" tabindex="0" aria-label="Nubes sparse 3D" style="width:100%;height:100%;min-width:0;touch-action:none;background:#11151b"></canvas></div>`;
const $=id=>document.getElementById(id),canvas=$('svCanvas');
const gl=canvas.getContext('webgl',{antialias:true,alpha:false});
if(!gl){$('svStatus').textContent='WebGL no disponible';return;}
const shader=(type,text)=>{const s=gl.createShader(type);gl.shaderSource(s,text);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
const program=gl.createProgram();
gl.attachShader(program,shader(gl.VERTEX_SHADER,`attribute vec3 pos;attribute vec3 color;uniform mat4 matrix;uniform float size;varying vec3 rgb;void main(){gl_Position=matrix*vec4(pos,1.);gl_PointSize=size;rgb=color;}`));
gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`precision mediump float;varying vec3 rgb;uniform bool circular;void main(){if(circular&&distance(gl_PointCoord,vec2(.5))>.5)discard;gl_FragColor=vec4(rgb,1.);}`));
gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
const locations={pos:gl.getAttribLocation(program,'pos'),color:gl.getAttribLocation(program,'color'),matrix:gl.getUniformLocation(program,'matrix'),size:gl.getUniformLocation(program,'size'),circular:gl.getUniformLocation(program,'circular')};
let layers=[],loaded=false,loading=false,center=[0,0,0],span=400,distance=800,yaw=-Math.PI/4,pitch=.8,drag=null,grid=null,gridCount=0;
const multiply=(a,b)=>{const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o;};
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const unit=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
function matrix(){
 const back=[Math.cos(pitch)*Math.cos(yaw),Math.cos(pitch)*Math.sin(yaw),Math.sin(pitch)];
 const right=unit(cross([0,0,1],back)),up=cross(back,right),eye=center.map((v,i)=>v+back[i]*distance);
 const view=new Float32Array([right[0],up[0],back[0],0,right[1],up[1],back[1],0,right[2],up[2],back[2],0,-dot(right,eye),-dot(up,eye),-dot(back,eye),1]);
 const aspect=canvas.width/canvas.height,near=Math.max(.001,distance*.0001),far=Math.max(distance+span*100,1000);
 let projection;
 if($('svProjection').value==='perspective'){
  const f=1/Math.tan(Math.PI/8);projection=new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0]);
 }else{const h=distance*.42,w=h*aspect;projection=new Float32Array([1/w,0,0,0,0,1/h,0,0,0,0,-2/(far-near),0,0,0,-(far+near)/(far-near),1]);}
 return multiply(projection,view);
}
function bind(buffer){gl.bindBuffer(gl.ARRAY_BUFFER,buffer);for(const [name,offset] of [['pos',0],['color',12]]){gl.enableVertexAttribArray(locations[name]);gl.vertexAttribPointer(locations[name],3,gl.FLOAT,false,24,offset);}}
function draw(){
 if(root.hidden)return;
 const ratio=Math.min(devicePixelRatio||1,2),w=Math.max(1,Math.round(canvas.clientWidth*ratio)),h=Math.max(1,Math.round(canvas.clientHeight*ratio));
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 gl.viewport(0,0,w,h);gl.clearColor(.055,.07,.09,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.useProgram(program);
 gl.uniformMatrix4fv(locations.matrix,false,matrix());gl.uniform1f(locations.size,Number($('svSize').value)*ratio);
 gl.uniform1i(locations.circular,0);
 if(grid&&$('svGrid').checked){gl.depthMask(false);bind(grid);gl.drawArrays(gl.LINES,0,gridCount);gl.depthMask(true);}
 gl.uniform1i(locations.circular,1);
 for(const layer of layers)if(layer.visible){bind(layer.buffer);gl.drawArrays(gl.POINTS,0,layer.count);}
}
function rebuildColors(){
 for(const layer of layers){
  const data=layer.data;
  for(let i=0;i<layer.count;i++)for(let k=0;k<3;k++)data[i*6+3+k]=($('svColor').value==='rgb'?layer.rgb[i]?.[k]??180:layer.color[k])/255;
  gl.bindBuffer(gl.ARRAY_BUFFER,layer.buffer);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
 }draw();
}
function fit(){
 const visible=layers.filter(l=>l.visible);if(!visible.length){draw();return;}
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
 for(const l of visible)for(let k=0;k<3;k++){lo[k]=Math.min(lo[k],l.bounds[0][k]);hi[k]=Math.max(hi[k],l.bounds[1][k]);}
 center=lo.map((v,k)=>(v+hi[k])/2);span=Math.max(1,Math.hypot(...hi.map((v,k)=>v-lo[k])));distance=span*1.5;
 const step=10**Math.floor(Math.log10(span/15)),extent=Math.ceil(span/step)*step,vertices=[];
 for(let i=-20;i<=20;i++){
  const x=center[0]+i*step,y=center[1]+i*step,c=i===0?.32:.17;
  vertices.push(x,center[1]-extent,0,c,c,c,x,center[1]+extent,0,c,c,c,center[0]-extent,y,0,c,c,c,center[0]+extent,y,0,c,c,c);
 }
 // World XYZ axes, with ground grid at map Z=0.
 for(const [end,color] of [[[extent,0,0],[.8,.18,.18]],[[0,extent,0],[.18,.8,.25]],[[0,0,extent],[.2,.4,1]]])vertices.push(0,0,0,...color,...end,...color);
 if(grid)gl.deleteBuffer(grid);grid=gl.createBuffer();gridCount=vertices.length/6;
 gl.bindBuffer(gl.ARRAY_BUFFER,grid);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.STATIC_DRAW);
 draw();
}
async function load(){
 if(loading)return;loading=true;$('svStatus').textContent='Cargando sparse…';
 try{
  const response=await fetch('/api/overview');if(!response.ok)throw Error('No se pudo cargar el mapa');
  const overview=await response.json();
  for(const l of layers)gl.deleteBuffer(l.buffer);layers=[];$('svLayers').replaceChildren();
  const count=overview.blocks.length;
  for(const [index,block] of overview.blocks.entries()){
   const hue=index/count*6,c=255,x=Math.round((1-Math.abs(hue%2-1))*255);
   const palette=[[c,x,55],[x,c,55],[55,c,x],[55,x,c],[x,55,c],[c,55,x]][Math.floor(hue)%6];
   const points=block.points,data=new Float32Array(points.length*6);
   for(let i=0;i<points.length;i++)data.set(points[i],i*6);
   const layer={id:block.block,label:block.label||block.block,count:points.length,data,rgb:block.rgb,color:palette,buffer:gl.createBuffer(),bounds:block.focus_bounds,visible:true};
   layers.push(layer);
   const label=document.createElement('label');label.style.cssText='display:block;padding:6px 0';
   const input=document.createElement('input');input.type='checkbox';input.checked=true;
   input.onchange=()=>{layer.visible=input.checked;draw();};
   const marker=document.createElement('span');marker.textContent=' ● ';marker.style.color=`rgb(${palette.join(',')})`;
   label.append(input,marker,document.createTextNode(layer.label));$('svLayers').append(label);
  }
  loaded=true;rebuildColors();fit();$('svStatus').textContent=`${layers.length} manzanas · ${layers.reduce((s,l)=>s+l.count,0).toLocaleString()} puntos de vista previa`;
 }catch(error){$('svStatus').textContent=error.message;}finally{loading=false;}
}
tab.onclick=()=>{root.hidden=false;$('alignWorkspace').hidden=true;$('roiWorkspace').hidden=true;document.body.classList.remove('alignment-mode');tab.classList.add('active');$('alignTab').classList.remove('active');$('roiTab').classList.remove('active');if(!loaded)load();else draw();};
for(const id of ['alignTab','roiTab'])$(id).addEventListener('click',()=>{root.hidden=true;tab.classList.remove('active');});
$('svReload').onclick=load;
$('svProjection').onchange=draw;$('svColor').onchange=rebuildColors;$('svSize').oninput=draw;$('svGrid').onchange=draw;
$('svTop').onclick=()=>{pitch=Math.PI/2-.0001;yaw=-Math.PI/2;draw();};
$('svOrbit').onclick=()=>{pitch=.8;yaw=-Math.PI/4;draw();};$('svFit').onclick=fit;
for(const [id,value] of [['svAll',true],['svNone',false]])$(id).onclick=()=>{layers.forEach(l=>l.visible=value);$('svLayers').querySelectorAll('input').forEach(i=>i.checked=value);draw();};
canvas.oncontextmenu=e=>e.preventDefault();
canvas.onpointerdown=e=>{canvas.focus();canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,pan:e.shiftKey||e.button!==0};};
canvas.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
 if(drag.pan||e.shiftKey){const factor=distance*.0009;center[0]+=(-dx*Math.sin(yaw)+dy*Math.cos(yaw))*factor;center[1]+=(dx*Math.cos(yaw)+dy*Math.sin(yaw))*factor;}
 else{yaw-=dx*.006;pitch=Math.max(-Math.PI/2+.001,Math.min(Math.PI/2-.001,pitch+dy*.006));}
 drag.x=e.clientX;drag.y=e.clientY;draw();};
canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;};
canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(.02,Math.min(1e7,distance*Math.exp(e.deltaY*.001)));draw();},{passive:false});
canvas.onkeydown=e=>{if(e.key.toLowerCase()==='f'){e.preventDefault();fit();}if(e.key==='7')$('svTop').click();};
new ResizeObserver(draw).observe(canvas);
})();
