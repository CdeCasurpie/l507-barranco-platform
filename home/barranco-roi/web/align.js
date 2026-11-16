/* Explicit adjacent-cloud workbench. Rendering is independent of scientific jobs. */
(() => {
'use strict';
const $=id=>document.getElementById(id), clone=v=>JSON.parse(JSON.stringify(v));
const identity=()=>[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]];
const apply=(m,p)=>[0,1,2].map(i=>m[i][0]*p[0]+m[i][1]*p[1]+m[i][2]*p[2]+m[i][3]);
const vector=(m,p)=>[0,1,2].map(i=>m[i][0]*p[0]+m[i][1]*p[1]+m[i][2]*p[2]);
const cache=new CloudCache();
const state={catalog:null,incoming:null,geometry:null,anchorGeometry:{},matrix:identity(),edges:[],saved:null,
  result:null,job:null,preview:false,undo:[],redo:[],camera:{center:[0,0,0],scale:1},view:'xy',
  page:0,epoch:0,busy:false,sceneOpen:false,editVersion:0,pose:null,panel:'pose',
  selected:false,inspectorOpen:false,metrics:{frames:0,renderTimes:[]},cache:cache.stats};
const root=$('alignWorkspace');
root.innerHTML=`
<section id="alignSetup" class="scene-setup">
 <div class="setup-heading"><span class="section-label">ESPACIO DE ALINEACIÓN</span><h1>Elige qué vas a alinear.</h1>
 <p>Una reconstrucción móvil y solo las referencias que necesitas.</p></div>
 <label class="setup-label" for="alignIncoming">Reconstrucción a colocar</label><select id="alignIncoming"></select>
 <div class="setup-label setup-neighbors-label">Manzanas adyacentes <span id="alignNeighborCount">0 seleccionadas</span></div>
 <div id="alignAnchors" class="neighbor-grid"></div>
 <p class="setup-footnote">Las referencias permanecen fijas. No se cargan otras nubes.</p>
 <div class="setup-actions"><button id="alignStart" class="primary" disabled>Abrir alineación <span>→</span></button>
 <button id="alignSetupHistory">Abrir revisión</button><button id="alignSetupCancel" hidden>Volver al editor</button></div>
</section>
<section id="alignEditor" class="alignment-editor" hidden>
 <header class="scene-header"><div><strong id="alignSceneTitle">Alineación</strong><span id="alignSceneContext"></span></div>
 <div class="scene-header-actions"><span id="alignSaveState">Sin guardar</span><button id="alignChange">Cambiar nubes</button>
  <button id="alignHistory">Historial</button><button id="alignInspectorToggle" aria-expanded="false">Controles</button>
  <button id="alignFullscreen" title="Pantalla completa" aria-label="Pantalla completa">⛶</button>
  <button id="alignSave" class="primary">Guardar</button></div></header>
 <div class="workbench">
  <div class="viewport-column">
   <div class="viewport-toolbar"><div class="tool-group" role="group" aria-label="Manipulación">
    <button data-tool="move" class="active" title="Mover nube · G">Mover <kbd>G</kbd></button>
    <button data-tool="rotate" title="Rotar nube · R">Girar <kbd>R</kbd></button>
    <button data-tool="scale" title="Escalar nube · S">Escalar <kbd>S</kbd></button>
    <button data-tool="pan" title="Mover la vista">Navegar</button></div>
    <details class="view-options"><summary>Vista</summary><div><select id="alignProjection" aria-label="Proyección"><option value="xy">Superior · XY</option>
    <option value="xz">Frontal · XZ</option><option value="yz">Lateral · YZ</option><option value="iso">3D ortográfica</option></select>
    <button id="alignFit" title="Encuadrar las nubes seleccionadas · F">Encuadrar</button><button id="alignFocus">Solo nueva</button></div></details></div>
   <div id="alignViewport" class="cloud-viewport">
    <canvas id="alignmentCloudCanvas" class="cloud-layer" aria-hidden="true"></canvas>
    <canvas id="alignmentCanvas" tabindex="0" aria-label="Mover, girar y escalar la nube móvil; referencias fijas"></canvas>
    <div class="viewport-legend"><button id="alignSelectCloud" aria-pressed="false">Seleccionar nube móvil</button>
     <button id="alignDeselect" hidden>Deseleccionar · Esc</button><span id="alignSelectionState">Sin selección · RGB original</span></div>
    <div id="alignLoading" class="scene-loading" hidden><span class="loading-ring"></span><span>Cargando selección…</span></div>
    <div class="viewport-bottom"><span id="alignGestureHelp">Arrastra para mover · rueda para zoom · espacio para desplazar la vista</span>
    <span id="alignRenderStatus"></span></div>
   </div>
   <div class="viewport-footer"><div class="tool-group"><button id="alignUndo" title="Deshacer · Ctrl+Z">↶</button><button id="alignRedo" title="Rehacer · Ctrl+Mayús+Z">↷</button></div>
     <details class="display-options"><summary>Visualización</summary><div>
     <label><input type="checkbox" id="alignRGB" checked> Color original</label><label>Punto <input type="range" id="alignPointSize" min="1" max="4" step=".25" value="1.75"></label></div></details>
    <span id="alignPointCount"></span></div>
   <div id="alignNotice" class="align-notice" role="status">Preparando catálogo…</div>
  </div>
   <aside class="inspector" id="alignInspector" data-open="false" inert aria-hidden="true">
    <button id="alignInspectorClose" class="inspector-close" aria-label="Cerrar controles">✕</button>
   <nav class="inspector-tabs"><button data-panel="pose" class="active">Colocar</button><button data-panel="views">Vistas</button><button data-panel="result">Resultado</button></nav>
   <section data-content="pose" class="inspector-content">
    <div class="inspector-heading"><h2>Transformación</h2><span>Solo la nube nueva</span></div>
    <p class="inspector-help">Arrastra en el visor. Gira con el ratón o con los deslizadores.</p>
    <div class="slider-section"><h3>Rotación</h3>
     ${[['Rx','X'],['Ry','Y'],['Rz','Z']].map(([n,l])=>`<label class="slider-heading" for="slider${n}"><span>Eje ${l}</span><output id="value${n}">0°</output></label>
     <input id="slider${n}" aria-label="Giro eje ${l}" type="range" min="-180" max="180" step=".1" value="0">`).join('')}
    </div>
    <div class="slider-section"><label class="slider-heading" for="alignScaleSlider"><span>Escala uniforme</span><output id="alignScaleValue">1×</output></label>
     <input id="alignScaleSlider" aria-label="Ajustar escala" type="range" min="-100" max="100" step=".1" value="0">
     <div class="slider-ends"><span>Reducir</span><span>Ampliar</span></div>
     <label class="slider-heading" for="alignHeightSlider"><span>Altura</span><output id="alignHeightValue">0 m</output></label>
     <input id="alignHeightSlider" aria-label="Ajustar altura" type="range" min="-10" max="10" step=".01" value="0">
    </div>
    <label class="field-label" for="alignPivot">Centro de giro y escala</label>
    <select id="alignPivot"><option value="center">Centro de la nube</option><option value="origin">Origen local</option></select>
    <div class="compact-actions"><button id="alignCenter">Centrar entre referencias</button><button id="alignReset">Restablecer</button></div>
    <details class="advanced"><summary>Valores exactos y matriz</summary><div class="pose-grid">
     ${['X','Y','Z','Rx','Ry','Rz','Escala'].map((n,i)=>`<label>${n}<input id="pose${n}" aria-label="${n} exacto" type="number" step="${i===6?'.001':'.1'}"></label>`).join('')}</div>
     <textarea id="alignMatrix" rows="7" aria-label="Matriz 4 por 4"></textarea><button id="alignApplyMatrix">Aplicar matriz</button>
    </details>
    <div class="inspector-heading bottom-heading"><h2>Revisión</h2></div>
    <input id="alignName" maxlength="150" placeholder="Nombre opcional" aria-label="Nombre de la revisión">
    <div class="compact-actions"><button id="alignDownload">Descargar JSON</button><button id="alignApproveManual">Aprobar manual → ROI</button></div>
    <p class="inspector-help">Guardar no ejecuta matching ni cambia los originales.</p>
   </section>
   <section data-content="views" class="inspector-content" hidden>
    <div class="inspector-heading"><h2>Vistas puente</h2><span id="alignViewCount"></span></div>
    <select id="alignAnchor" aria-label="Referencia para matching"></select>
    <select id="alignDirection" aria-label="Dirección"><option value="forward">Nueva → referencia</option><option value="reverse">Referencia → nueva · opcional</option></select>
    <div class="view-selection-toolbar"><button id="alignPick">Elegir en visor</button>
     <select id="alignRole" aria-label="Rol de las vistas"><option value="fit">Para ajuste</option><option value="validation">Para validación</option></select></div>
    <input id="alignSearch" placeholder="Buscar ID o nombre de imagen" aria-label="Buscar vistas">
    <details id="alignChosenDetails"><summary id="alignChosenCount">Vistas seleccionadas</summary><div id="alignSelected" class="align-selection"></div></details>
    <div class="gallery-pagination"><button id="alignPrevious" aria-label="Página anterior">←</button><span id="alignPage"></span><button id="alignNext" aria-label="Página siguiente">→</button></div>
    <div id="alignGallery" class="view-gallery"></div>
    <details id="alignMatchingDetails" class="advanced"><summary>Pares y parámetros de matching</summary>
     <div class="pose-grid"><label>Radio · m<input id="alignRadius" type="number" value="80" min="1" max="1000"></label>
     <label>Ángulo · °<input id="alignAngle" type="number" value="110" min="1" max="180"></label>
     <label>Soportes<input id="alignLimit" type="number" value="12" min="1" max="64"></label></div>
     <button id="alignPropose" class="full">Proponer pares para estas vistas</button>
     <div class="pair-entry"><input id="alignQueryId" type="number" placeholder="ID elegida" aria-label="ID query">
     <input id="alignSupportId" type="number" placeholder="ID soporte" aria-label="ID soporte"><button id="alignAddPair">＋</button></div>
     <p id="alignPairCount" class="inspector-help"></p>
     <div class="align-table-wrap"><table class="align-table"><thead><tr><th>Vista</th><th>Soporte</th><th>m</th><th>°</th><th></th></tr></thead><tbody id="alignPairs"></tbody></table></div>
     <p class="inspector-help">La cercanía propone pares, no demuestra solape. Las vistas se eligen manualmente.</p>
    </details>
    <div id="alignAvailability" class="availability"></div>
    <button id="alignRun" class="primary full">Matching y ajuste Sim(3)</button>
    <details class="advanced"><summary>BA y opciones avanzadas</summary>
     <button id="alignRunBA" class="full">Sim(3) + BA restringido</button>
     <p class="inspector-help">BA publica otra sparse. Su densa requerirá regeneración. Las referencias no se mueven.</p>
     <label>Error de centros · m<input id="alignCenterError" type="number" min=".01" step=".1" value="2"></label>
     <label>Error de giro · °<input id="alignRotationError" type="number" min=".1" step=".1" value="5"></label>
    </details>
    <details class="advanced"><summary>Preparar fotos y features</summary>
     <button id="alignFetchInputs" class="full">Traer insumos de su hija</button>
     <p class="inspector-help">Solo con confirmación. No modifica la hija ni sus corridas.</p>
     <input id="alignInputManifest" placeholder="/data/barranco/…/block.json" aria-label="Manifiesto local">
     <select id="alignInputMode"><option value="current">Adjuntar a la seleccionada</option><option value="auto">Registrar nueva / ancla</option></select>
     <button id="alignAttach" class="full">Adjuntar snapshot local</button>
    </details>
   </section>
   <section data-content="result" class="inspector-content" hidden>
    <div class="inspector-heading"><h2>Resultado</h2></div>
    <p id="alignJobStatus">Sin ejecución.</p>
    <button id="alignPreview" class="full" disabled>Comparar resultado / prior</button>
    <button id="alignApproveResult" class="primary full" disabled>Aprobar y abrir ROI</button>
    <div class="compact-actions"><button id="alignDownloadResult" disabled>Informe JSON</button><button id="alignCancel" disabled>Cancelar trabajo</button></div>
    <div class="align-table-wrap"><table class="align-table"><thead><tr><th>Ancla</th><th>Vista</th><th>Rol</th><th>m</th><th>°</th><th>Estado</th></tr></thead><tbody id="alignDiagnostics"></tbody></table></div>
    <details class="advanced"><summary>Informe por referencia y BA</summary><pre id="alignSummary"></pre><pre id="alignBAReport"></pre></details>
   </section>
  </aside>
 </div>
</section>
<dialog id="alignHistoryDialog" class="history-dialog"><div class="dialog-heading"><h2>Revisiones y trabajos</h2><button id="alignHistoryClose" aria-label="Cerrar historial">✕</button></div>
 <label for="alignSessions">Revisiones guardadas</label><select id="alignSessions"></select>
 <div class="compact-actions"><button id="alignLoad" class="primary">Abrir revisión</button><button id="alignRefresh">Actualizar</button></div>
 <h3>Trabajos</h3><div id="alignJobs" class="align-jobs"></div></dialog>`;
const canvas=$('alignmentCanvas'),ctx=canvas.getContext('2d'),renderer=new CloudRenderer($('alignmentCloudCanvas'));
let tool='pan',drag=null,gesture=null,space=false,renderPending=false,pollSerial=0,galleryKey='',draftTimer=null,bootPromise=null;
let pendingMove=null,navigation=null,lastFrame=0;
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)');
let inspectorDirty=true,setupSelection=new Set();
const DRAFT_KEY='barranco.alignment.drafts.v2';
async function api(path,data){
  const r=await fetch('/api/alignment/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-ROI-Client':'local-editor'},body:JSON.stringify(data)});
  const body=await r.json();if(!r.ok)throw new Error(body.error||r.statusText);return body;
}
function message(text,error=false){$('alignNotice').textContent=text;$('alignNotice').classList.toggle('error',error);if(!state.sceneOpen)$('alignSetup').dataset.error=error?text:'';}
const guard=fn=>async(...args)=>{try{return await fn(...args);}catch(e){message(e.message,true);console.error(e);}};
function edge(){return state.edges.find(e=>e.anchor===$('alignAnchor').value);}
function selection(){return edge()?.[$('alignDirection').value];}
function activeAnchor(){return state.catalog?.anchors.find(a=>a.id===$('alignAnchor').value);}
function queryGeometry(){return $('alignDirection').value==='forward'?state.geometry:state.anchorGeometry[$('alignAnchor').value];}
function record(id){return state.catalog?.pending.find(r=>r.id===id)||state.catalog?.anchors.find(r=>r.id===id);}
function pivot(){return $('alignPivot').value==='origin'||!state.geometry?[0,0,0]:state.geometry.origin;}
function readDrafts(){try{return JSON.parse(localStorage.getItem(DRAFT_KEY)||'{}');}catch(_){return {};}}
function persistDraft(){
  if(!state.incoming||!state.geometry)return;
  try{
    const rows=readDrafts();rows[state.incoming]={version:state.geometry.version,anchor_revision:state.catalog.anchor_revision,
      matrix:state.matrix,edges:state.edges,name:$('alignName').value,saved:state.saved,policy:currentSession().policy,at:Date.now()};
    const keys=Object.keys(rows).sort((a,b)=>rows[b].at-rows[a].at);
    for(const key of keys.slice(4))delete rows[key];
    localStorage.setItem(DRAFT_KEY,JSON.stringify(rows));
  }catch(_){$('alignSaveState').textContent='Guarda la revisión en el servidor';}
}
function scheduleDraft(){clearTimeout(draftTimer);draftTimer=setTimeout(persistDraft,500);}
function dirty(clearPairs=false){
  state.editVersion++;state.saved=null;state.result=null;state.preview=false;
  $('alignApproveResult').disabled=true;$('alignPreview').disabled=true;$('alignDownloadResult').disabled=true;
  $('alignSaveState').textContent='Cambios sin guardar';
  if(clearPairs){for(const e of state.edges)for(const d of ['forward','reverse'])e[d].pairs=[];updatePairs();}
  scheduleDraft();draw();
}
function checkpoint(){state.undo.push(clone(state.matrix));if(state.undo.length>100)state.undo.shift();state.redo=[];}
function poseFromMatrix(){
  const m=state.matrix,s=Math.hypot(m[0][0],m[1][0],m[2][0]),r=m.slice(0,3).map(row=>row.slice(0,3).map(x=>x/s));
  const y=Math.asin(Math.max(-1,Math.min(1,-r[2][0]))),cos=Math.cos(y);
  const x=Math.abs(cos)>1e-8?Math.atan2(r[2][1],r[2][2]):0;
  const z=Math.abs(cos)>1e-8?Math.atan2(r[1][0],r[0][0]):Math.atan2(-r[0][1],r[1][1]);
  state.pose={position:apply(m,pivot()),angles:[x,y,z].map(v=>v*180/Math.PI),scale:s};
}
function controlsFromMatrix(){
  poseFromMatrix();inspectorDirty=true;
  $('alignUndo').disabled=!state.undo.length;$('alignRedo').disabled=!state.redo.length;draw();
}
function syncInspector(){
  if(!inspectorDirty||!state.pose)return;inspectorDirty=false;
  const p=state.pose;
  ['X','Y','Z'].forEach((n,i)=>$('pose'+n).value=p.position[i].toPrecision(12));
  ['Rx','Ry','Rz'].forEach((n,i)=>{$('pose'+n).value=p.angles[i].toPrecision(12);$('slider'+n).value=p.angles[i];$('value'+n).textContent=p.angles[i].toFixed(1)+'°';});
  $('poseEscala').value=p.scale.toPrecision(12);$('alignScaleValue').textContent=p.scale.toFixed(4)+'×';
  $('alignHeightValue').textContent=p.position[2].toFixed(2)+' m';
  if(!$('alignMatrix').matches(':focus'))$('alignMatrix').value=JSON.stringify(state.matrix,null,2);
  $('alignUndo').disabled=!state.undo.length;$('alignRedo').disabled=!state.redo.length;
}
function matrixFromPose(p){
  const [x,y,z]=p.angles.map(v=>v*Math.PI/180),s=p.scale,cx=Math.cos(x),sx=Math.sin(x),cy=Math.cos(y),sy=Math.sin(y),cz=Math.cos(z),sz=Math.sin(z);
  const r=[[cz*cy,cz*sy*sx-sz*cx,cz*sy*cx+sz*sx],[sz*cy,sz*sy*sx+cz*cx,sz*sy*cx-cz*sx],[-sy,cy*sx,cy*cx]].map(row=>row.map(v=>v*s));
  const q=pivot();return [...r.map((row,i)=>[...row,p.position[i]-row.reduce((sum,v,j)=>sum+v*q[j],0)]),[0,0,0,1]];
}
function beginGesture(){
  if(gesture)return;
  selectCloud(true);
  poseFromMatrix();gesture={matrix:clone(state.matrix),pose:clone(state.pose),changed:false};
}
function gestureChanged(){
  if(!gesture)beginGesture();
  if(!gesture.changed){checkpoint();dirty(true);gesture.changed=true;}
}
function endGesture(cancel=false){
  if(!gesture)return;
  if(cancel&&gesture.changed){state.matrix=gesture.matrix;state.undo.pop();dirty(true);}
  gesture=null;$('alignScaleSlider').value=0;$('alignHeightSlider').value=0;controlsFromMatrix();scheduleDraft();draw();
}
function currentSession(){
  if(!state.incoming)throw new Error('Selecciona una reconstrucción.');
  return {reconstruction:state.incoming,anchor_revision:state.catalog.anchor_revision,matrix:state.matrix,edges:state.edges,
    name:$('alignName').value||'Colocación manual',policy:{...state.policyBase,max_center_error_m:Number($('alignCenterError').value),max_rotation_error_deg:Number($('alignRotationError').value)}};
}
function anchorCaption(a){return a.accepted_derived?a.block+' · revisión '+a.id.slice(2,8):'Manzana '+a.id;}
function populateSetup(){
  const source=$('alignIncoming').value||state.incoming;
  $('alignIncoming').replaceChildren(new Option('Selecciona una reconstrucción…',''));
  for(const r of state.catalog.pending)$('alignIncoming').add(new Option(`${r.block} · ${r.label} · componente ${r.component} · ${r.images.toLocaleString()} vistas`,r.id));
  $('alignIncoming').value=source||'';
  $('alignAnchors').replaceChildren();
  for(const a of state.catalog.anchors){
    const label=document.createElement('label'),cb=document.createElement('input'),text=document.createElement('span');
    cb.type='checkbox';cb.value=a.id;cb.checked=setupSelection.has(a.id);
    cb.disabled=a.reconstruction===$('alignIncoming').value;
    text.textContent=anchorCaption(a);label.append(cb,text);
    cb.onchange=()=>{cb.checked?setupSelection.add(a.id):setupSelection.delete(a.id);updateSetup();};
    $('alignAnchors').append(label);
  }updateSetup();
}
function updateSetup(){
  $('alignNeighborCount').textContent=setupSelection.size+' seleccionadas';
  $('alignStart').disabled=!$('alignIncoming').value||!setupSelection.size;
}
async function refresh(){
  state.catalog=await api('catalog');populateSetup();populateAnchors();updateAvailability();
  if(state.sceneOpen)gallery();
}
function populateAnchors(){
  const current=$('alignAnchor').value;$('alignAnchor').replaceChildren();
  for(const e of state.edges){const a=record(e.anchor);if(a)$('alignAnchor').add(new Option(anchorCaption(a),a.id));}
  if(state.edges.some(e=>e.anchor===current))$('alignAnchor').value=current;
  if(state.sceneOpen){$('alignSceneTitle').textContent=record(state.incoming)?.block+' / Alineación';
    $('alignSceneContext').textContent='Referencias: '+state.edges.map(e=>record(e.anchor)?.block||e.anchor).join(', ');}
}
async function history(){
  const [rows,jobs]=await Promise.all([api('sessions?summary=1'),api('jobs')]);
  $('alignSessions').replaceChildren();for(const s of rows)$('alignSessions').add(new Option(s.name+' · '+new Date(s.created_at*1000).toLocaleString(),s.id));
  $('alignJobs').replaceChildren();
  for(const j of jobs.slice(0,30)){const b=document.createElement('button');b.textContent=j.state+' · '+j.mode+' · '+new Date(j.created_at*1000).toLocaleTimeString();
    b.onclick=guard(async()=>{$('alignHistoryDialog').close();await loadSession(j.session_id);await watch(j.id);});$('alignJobs').append(b);}
}
async function chooseIncoming(id,neighbors=null){
  if(!state.catalog)await refresh();
  if(neighbors===null){$('alignIncoming').value=id;showSetup();populateSetup();return;}
  return openScene(id,neighbors);
}
async function openScene(id,neighbors,{session=null}={}){
  const source=record(id);if(!source)throw new Error('Reconstrucción desconocida.');
  neighbors=[...new Set(neighbors)].filter(k=>state.catalog.anchors.some(a=>a.id===k&&a.reconstruction!==id));
  persistDraft();const epoch=++state.epoch;pollSerial++;endGesture();
  $('alignSetup').hidden=true;$('alignEditor').hidden=false;$('alignLoading').hidden=false;
  state.sceneOpen=true;state.geometry=null;state.incoming=id;state.anchorGeometry={};galleryKey='';
  $('alignSceneTitle').textContent=source.block+' / Cargando…';$('alignGallery').replaceChildren();
  try{
    const ids=[id,...neighbors],data=await Promise.all(ids.map(k=>cache.get(k,record(k).geometry_version)));
    if(epoch!==state.epoch)return;
    state.geometry=data[0];neighbors.forEach((k,i)=>state.anchorGeometry[k]=data[i+1]);
    const draft=session||readDrafts()[id],valid=session||(draft?.version===source.geometry_version&&draft?.anchor_revision===state.catalog.anchor_revision);
    state.matrix=valid?clone(draft.matrix):identity();
    state.edges=neighbors.map(anchor=>valid&&draft.edges.find(e=>e.anchor===anchor)||{anchor,forward:{views:[],pairs:[]},reverse:{views:[],pairs:[]}});
    state.edges=clone(state.edges);state.saved=session||(valid&&JSON.stringify(draft.edges.map(e=>e.anchor))===JSON.stringify(neighbors)?draft.saved:null);
    $('alignName').value=valid?draft.name||'':'';
    state.policyBase=valid?clone(draft.policy||{}):{};
    $('alignCenterError').value=valid?draft.policy?.max_center_error_m||2:2;
    $('alignRotationError').value=valid?draft.policy?.max_rotation_error_deg||5:5;
    state.undo=[];state.redo=[];state.result=null;state.preview=false;state.derivedGeometry=null;state.page=0;state.editVersion++;
    setupSelection=new Set(neighbors);populateAnchors();controlsFromMatrix();
    if(!valid)centerIncoming(false);
    $('alignSetupCancel').hidden=false;$('alignSaveState').textContent=state.saved?'Revisión guardada':'Borrador local';
    $('alignApproveResult').disabled=true;$('alignPreview').disabled=true;$('alignDownloadResult').disabled=true;
    $('alignPointCount').textContent=`${data.reduce((n,d)=>n+d.render_count,0).toLocaleString()} puntos visibles · ${data.length} nubes`;
    renderer.retain(data.map(d=>d.key));gallery();updatePairs();updateAvailability();fitScene();setPanel('pose',false);selectCloud(false);setTool('pan');
    message(valid?'Colocación recuperada. Solo están cargadas las referencias seleccionadas.':'Referencias fijas. La nueva está centrada como punto de partida; arrástrala o gírala para colocarla.');
    scheduleDraft();
  }finally{if(epoch===state.epoch)$('alignLoading').hidden=true;}
}
function showSetup(){
  persistDraft();$('alignSetup').hidden=false;$('alignEditor').hidden=true;setupSelection=new Set(state.edges.map(e=>e.anchor));
  $('alignIncoming').value=state.incoming||'';populateSetup();
}
function centerIncoming(check=true){
  if(!state.geometry||!state.edges.length)return;
  if(check)checkpoint();
  const centers=state.edges.map(e=>apply(record(e.anchor).matrix,state.anchorGeometry[e.anchor].origin));
  const target=[0,1,2].map(i=>centers.reduce((s,p)=>s+p[i],0)/centers.length),current=apply(state.matrix,pivot());
  for(let i=0;i<3;i++)state.matrix[i][3]+=target[i]-current[i];
  if(check)dirty(true);controlsFromMatrix();
}
function updateAvailability(){
  if(!state.catalog)return;
  const rows=[record(state.incoming),...state.edges.map(e=>record(e.anchor))].filter(Boolean),missing=rows.filter(r=>!r.matching_ready);
  $('alignAvailability').textContent=missing.length?'Para matching faltan insumos: '+missing.map(r=>r.block+' — '+r.missing.join(', ')).join(' / '):'Insumos de matching disponibles.';
  $('alignAvailability').classList.toggle('missing',!!missing.length);
  $('alignRun').disabled=!state.geometry||!state.edges.length||!!missing.length||state.busy;
  $('alignRunBA').disabled=$('alignRun').disabled;
}
function selectedRole(id,role){
  const query=$('alignDirection').value==='forward'?state.incoming:$('alignAnchor').value;
  for(const e of state.edges)for(const d of ['forward','reverse']){
    const q=d==='forward'?state.incoming:e.anchor;if(q===query){const v=e[d].views.find(v=>v.id===id);if(v)v.role=role;}
  }
}
function toggleView(id,checked){
  const s=selection();if(!s)return;
  if(checked&&!s.views.some(v=>v.id===id)){s.views.push({id,role:$('alignRole').value});selectedRole(id,$('alignRole').value);}
  if(!checked){s.views=s.views.filter(v=>v.id!==id);s.pairs=s.pairs.filter(p=>p.query!==id);}
  dirty();gallery();updatePairs();draw();
}
function gallery(){
  const data=queryGeometry(),s=selection();if(!data||!s){$('alignGallery').replaceChildren();return;}
  const selected=new Map(s.views.map(v=>[v.id,v.role])),term=$('alignSearch').value.toLowerCase();
  const views=data.views.filter(v=>(v.id+' '+v.name).toLowerCase().includes(term)),pages=Math.max(1,Math.ceil(views.length/24));
  state.page=Math.min(state.page,pages-1);$('alignPage').textContent=`${state.page+1} / ${pages}`;
  $('alignPrevious').disabled=state.page===0;$('alignNext').disabled=state.page===pages-1;
  $('alignViewCount').textContent=s.views.length+' elegidas';$('alignChosenCount').textContent=`${s.views.length} elegidas · ${s.views.filter(v=>v.role==='validation').length} reservadas`;
  $('alignSelected').replaceChildren();
  for(const v of s.views){
    const row=document.createElement('div'),label=document.createElement('span'),role=document.createElement('select'),remove=document.createElement('button');
    row.className='selected-view';label.textContent=v.id;role.add(new Option('Ajuste','fit'));role.add(new Option('Validación','validation'));role.value=v.role;
    role.onchange=()=>{selectedRole(v.id,role.value);dirty();gallery();};
    remove.textContent='✕';remove.setAttribute('aria-label','Quitar vista '+v.id);remove.onclick=()=>toggleView(v.id,false);
    row.append(label,role,remove);$('alignSelected').append(row);
  }
  const id=$('alignDirection').value==='forward'?state.incoming:$('alignAnchor').value,ready=record(id);
  const hasPhotos=!ready.missing?.includes('fotos originales');
  const key=data.key+'/'+state.page+'/'+term+'/'+hasPhotos;
  if(galleryKey!==key){
    galleryKey=key;$('alignGallery').replaceChildren();
    for(const v of views.slice(state.page*24,(state.page+1)*24)){
      const card=document.createElement('label');card.className='view-card';card.dataset.id=v.id;
      const cb=document.createElement('input');cb.type='checkbox';cb.value=v.id;cb.onchange=()=>toggleView(v.id,cb.checked);
      if(hasPhotos){const img=document.createElement('img');img.loading='lazy';img.decoding='async';
        img.src='/api/alignment/thumbnail/'+id+'/'+v.id;img.alt='Vista '+v.id;img.onerror=()=>img.hidden=true;card.append(img);}
      const name=document.createElement('span');name.textContent='Vista '+v.id;
      const small=document.createElement('small');small.textContent=v.name;card.title=v.name;card.append(cb,name,small);$('alignGallery').append(card);
    }
  }
  for(const card of $('alignGallery').children){const id=Number(card.dataset.id);card.classList.toggle('chosen',selected.has(id));card.querySelector('input').checked=selected.has(id);}
}
function updatePairs(){
  const pairs=selection()?.pairs||[],total=state.edges.reduce((n,e)=>n+e.forward.pairs.length+e.reverse.pairs.length,0);
  $('alignPairCount').textContent=`${pairs.length} pares aquí · ${total} en la sesión${pairs.length>150?' · mostrando los primeros 150':''}`;
  $('alignPairs').replaceChildren();
  for(const [index,p] of pairs.slice(0,150).entries()){
    const tr=document.createElement('tr');
    for(const value of [p.query,p.support,p.distance_m?.toFixed(1)??'—',p.angle_deg?.toFixed(1)??'—']){const td=document.createElement('td');td.textContent=value;tr.append(td);}
    const td=document.createElement('td'),b=document.createElement('button');b.textContent='✕';
    b.onclick=()=>{selection().pairs.splice(index,1);dirty();updatePairs();};td.append(b);tr.append(td);$('alignPairs').append(tr);
  }
}
function basis(){
  if(state.view==='xz')return [[1,0,0],[0,0,1]];
  if(state.view==='yz')return [[0,1,0],[0,0,1]];
  if(state.view==='iso'){const y=state.yaw??-.7,p=state.pitch??.7;return [[Math.cos(y),Math.sin(y),0],[-Math.sin(y)*Math.sin(p),Math.cos(y)*Math.sin(p),Math.cos(p)]];}
  return [[1,0,0],[0,1,0]];
}
function screen(point){
  const [u,v]=basis(),d=point.map((x,i)=>x-state.camera.center[i]);
  return [canvas.clientWidth/2+(d[0]*u[0]+d[1]*u[1]+d[2]*u[2])*state.camera.scale,
    canvas.clientHeight/2-(d[0]*v[0]+d[1]*v[1]+d[2]*v[2])*state.camera.scale];
}
function visibleClouds(){
  const clouds=state.edges.filter(e=>state.anchorGeometry[e.anchor]).map(e=>({data:state.anchorGeometry[e.anchor],matrix:record(e.anchor).matrix,
    highlight:false,tint:[.65,.65,.65]}));
  if(state.geometry)clouds.push({data:state.preview&&state.derivedGeometry||state.geometry,
    matrix:state.preview?(state.derivedGeometry?identity():state.result.matrix):state.matrix,
    highlight:state.selected&&!state.preview,tint:state.selected?[.36,.78,.96]:[.8,.8,.8]});
  return clouds;
}
function fitScene(incomingOnly=false){
  navigation=null;
  const clouds=visibleClouds().filter(c=>!incomingOnly||c.data===state.geometry||c.data===state.derivedGeometry);if(!clouds.length)return;
  const points=[];
  for(const {data,matrix} of clouds){const [a,b]=data.bounds;for(let n=0;n<8;n++)points.push(apply(matrix,[n&1?b[0]:a[0],n&2?b[1]:a[1],n&4?b[2]:a[2]]));}
  const lo=[0,1,2].map(i=>Math.min(...points.map(p=>p[i]))),hi=[0,1,2].map(i=>Math.max(...points.map(p=>p[i])));
  state.camera.center=lo.map((v,i)=>(v+hi[i])/2);const [u,v]=basis();let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  for(const p of points){const d=p.map((x,i)=>x-state.camera.center[i]),x=d[0]*u[0]+d[1]*u[1]+d[2]*u[2],y=d[0]*v[0]+d[1]*v[1]+d[2]*v[2];
    minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
  state.camera.scale=Math.max(.0001,Math.min((canvas.clientWidth-100)/Math.max(1,maxX-minX),(canvas.clientHeight-100)/Math.max(1,maxY-minY)));
  state.depth=Math.max(100,Math.hypot(...hi.map((x,i)=>x-lo[i]))*4);draw();
}
function draw(){if(!renderPending&&!root.hidden&&state.sceneOpen){renderPending=true;requestAnimationFrame(render);}}
function render(){
  renderPending=false;if(root.hidden||$('alignEditor').hidden)return;
  if(pendingMove){const e=pendingMove;pendingMove=null;renderPending=true;handlePointerMove(e);renderPending=false;}
  const now=performance.now(),dt=Math.min(40,now-(lastFrame||now-16));lastFrame=now;
  if(navigation){
    const alpha=reduceMotion.matches?1:1-Math.exp(-dt/32);
    state.camera.scale+=alpha*(navigation.scale-state.camera.scale);
    for(let i=0;i<3;i++)state.camera.center[i]+=alpha*(navigation.center[i]-state.camera.center[i]);
    if(Math.abs(Math.log(navigation.scale/state.camera.scale))<.0002&&
       Math.hypot(...navigation.center.map((v,i)=>(v-state.camera.center[i])*state.camera.scale))<.05){
      state.camera= navigation;navigation=null;
    }
  }
  const begin=performance.now(),w=canvas.clientWidth,h=canvas.clientHeight,dpr=Math.min(devicePixelRatio||1,2);if(!w||!h)return;
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  const clouds=visibleClouds();
  let depth=100;
  for(const {data,matrix} of clouds){
    const center=apply(matrix,data.origin),scale=Math.hypot(matrix[0][0],matrix[1][0],matrix[2][0]);
    const radius=Math.hypot(...data.bounds[1].map((v,i)=>v-data.bounds[0][i]))*scale;
    depth=Math.max(depth,2*(Math.hypot(...center.map((v,i)=>v-state.camera.center[i]))+radius));
  }
  renderer.draw(clouds,state.camera,basis(),w,h,{interacting:!!gesture||!!drag||!!navigation,rgb:$('alignRGB').checked,size:Number($('alignPointSize').value),depth});
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  if(state.geometry){
    const worldPivot=apply(state.matrix,pivot()),p=screen(worldPivot);
    if(state.selected&&state.panel!=='result'&&!state.preview){
      ctx.strokeStyle='#dedede';ctx.lineWidth=1;ctx.beginPath();ctx.arc(p[0],p[1],tool==='rotate'?42:6,0,Math.PI*2);ctx.stroke();
      if(tool==='move')for(const [i,color] of ['#eeeeee','#bbbbbb','#999999'].entries()){
        const q=worldPivot.slice();q[i]+=60/state.camera.scale;const end=screen(q);if(Math.hypot(end[0]-p[0],end[1]-p[1])<10)continue;
        ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...end);ctx.stroke();
        ctx.beginPath();ctx.arc(end[0],end[1],3,0,Math.PI*2);ctx.fill();ctx.font='11px system-ui';ctx.fillText('XYZ'[i],end[0]+6,end[1]-5);
      }
    }
    if(state.panel==='views'&&state.inspectorOpen){
      const data=queryGeometry(),m=$('alignDirection').value==='forward'?state.matrix:activeAnchor()?.matrix;
      const chosen=new Set((selection()?.views||[]).map(v=>v.id));
      for(const camera of data?.views||[]){
        if((drag||gesture)&&!chosen.has(camera.id))continue;const pos=screen(apply(m,camera.center));
        if(pos[0]<0||pos[1]<0||pos[0]>w||pos[1]>h)continue;
        ctx.fillStyle=chosen.has(camera.id)?'#f6d775':'#9eafbf';ctx.fillRect(pos[0]-1,pos[1]-1,chosen.has(camera.id)?5:2,chosen.has(camera.id)?5:2);
        if(chosen.has(camera.id)){ctx.font='10px system-ui';ctx.fillText(camera.id,pos[0]+7,pos[1]-4);}
      }
    }
  }
  syncInspector();state.metrics.frames++;state.metrics.renderTimes.push(performance.now()-begin);
  if(state.metrics.renderTimes.length>120)state.metrics.renderTimes.shift();
  $('alignRenderStatus').textContent=renderer.backend+' · '+(state.view==='xy'?'XY':state.view.toUpperCase());
  if(navigation)draw();
}
function selectCloud(selected){
  state.selected=selected;
  if(!selected)$('alignRGB').checked=true;
  $('alignSelectCloud').setAttribute('aria-pressed',String(selected));
  $('alignSelectCloud').hidden=selected;$('alignDeselect').hidden=!selected;
  $('alignSelectionState').textContent=selected?'Nube móvil seleccionada':'Sin selección · RGB original';
  draw();
}
function setInspector(open){
  state.inspectorOpen=open;const panel=$('alignInspector');
  panel.dataset.open=String(open);panel.inert=!open;panel.setAttribute('aria-hidden',String(!open));
  $('alignInspectorToggle').setAttribute('aria-expanded',String(open));draw();
}
function setTool(value){
  if(['move','rotate','scale'].includes(value))selectCloud(true);
  tool=value;document.querySelectorAll('[data-tool]').forEach(b=>b.classList.toggle('active',b.dataset.tool===value));
  $('alignPick').classList.toggle('active',value==='pick');canvas.style.cursor=value==='pan'?'grab':value==='pick'?'crosshair':'default';
  $('alignGestureHelp').textContent=({move:'Arrastra la nube · flechas para mover por eje · espacio para mover la vista',
    rotate:'Arrastra alrededor del centro para girar · sliders para X, Y y Z',scale:'Arrastra horizontalmente para escalar · Mayús para ajuste fino',
    pan:'Arrastra para desplazar la vista · rueda para zoom',pick:'Clic en una cámara para elegirla · las poses no cambian'})[value];
  draw();
}
function setPanel(value,open=true){
  setInspector(open);
  state.panel=value;document.querySelectorAll('[data-panel]').forEach(b=>b.classList.toggle('active',b.dataset.panel===value));
  document.querySelectorAll('[data-content]').forEach(p=>p.hidden=p.dataset.content!==value);
  if(value==='views')gallery();if(value!=='views'&&tool==='pick')setTool('move');draw();
}
function rotateAround(matrix,axis,angle){
  const c=Math.cos(angle),s=Math.sin(angle),t=1-c,[x,y,z]=axis;
  const r=[[t*x*x+c,t*x*y-s*z,t*x*z+s*y],[t*x*y+s*z,t*y*y+c,t*y*z-s*x],[t*x*z-s*y,t*y*z+s*x,t*z*z+c]];
  const m=clone(matrix),world=apply(matrix,pivot());
  for(let i=0;i<3;i++)for(let j=0;j<3;j++)m[i][j]=r[i][0]*matrix[0][j]+r[i][1]*matrix[1][j]+r[i][2]*matrix[2][j];
  const moved=vector(m,pivot());for(let i=0;i<3;i++)m[i][3]=world[i]-moved[i];return m;
}
async function save(){
  endGesture();const version=state.editVersion,payload=clone(currentSession()),s=await api('sessions',payload);
  if(version===state.editVersion){state.saved=s;$('alignSaveState').textContent='Guardado '+new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});persistDraft();}
  message(version===state.editVersion?'Revisión guardada. No se ejecutó ningún trabajo.':'Se guardó la revisión anterior; tienes cambios posteriores.');return s;
}
async function loadSession(id){
  if(!id)return;const s=await api('sessions/'+id);await refresh();await openScene(s.reconstruction,s.edges.map(e=>e.anchor),{session:s});
  $('alignHistoryDialog').close();message('Revisión recuperada con su matriz y selección exactas.');
}
function diagnostics(rows,localized=false){
  $('alignDiagnostics').replaceChildren();
  for(const r of rows){const tr=document.createElement('tr');
    const values=[r.anchor,(r.direction==='reverse'?'← ':'→ ')+r.original_id,r.role==='validation'?'valid.':'ajuste',
      r.center_error_m?.toFixed(3)??'—',r.rotation_error_deg?.toFixed(2)??'—',localized?(r.registered?'localizada':r.reason||'fallida'):(r.inlier?'válida':'rechazada')];
    for(const value of values){const td=document.createElement('td');td.textContent=value;tr.append(td);}$('alignDiagnostics').append(tr);}
}
async function run(mode){
  if(mode==='ba'&&!confirm('BA crea una sparse derivada y requerirá regenerar su densa. ¿Continuar?'))return;
  endGesture();const s=state.saved||await save();state.result=null;state.preview=false;state.busy=true;updateAvailability();setPanel('result');
  try{const j=await api('jobs',{session_id:s.id,mode});await watch(j.id);}catch(e){state.busy=false;updateAvailability();throw e;}
}
async function watch(id){
  const serial=++pollSerial;setPanel('result');
  const step=async()=>{
    const j=await api('jobs/'+id);if(serial!==pollSerial)return;state.job=j;state.busy=['queued','running'].includes(j.state);updateAvailability();
    $('alignJobStatus').textContent=j.state+' · '+j.stage+(j.error?' · '+j.error:'');$('alignCancel').disabled=!state.busy;
    if(state.busy){setTimeout(()=>step().catch(e=>message(e.message,true)),1500);return;}
    if(j.state==='completed'&&state.saved?.id!==j.session_id){message('Terminó un trabajo de otra revisión. Ábrelo desde el historial.');return;}
    if(j.state==='completed'){
      const version=state.editVersion;
      const result=await api('jobs/'+id+'/result');if(serial!==pollSerial)return;
      if(result.inputs_manifest){await api('inputs',{manifest:result.inputs_manifest,reconstruction:result.reconstruction});await refresh();message('Fotos y features verificados.');return;}
      // Derived geometry keeps the existing compatible endpoint; decode into the
      // same resident format without touching the original model.
      let derivedGeometry=null;
      if(result.derived_model){
        const payload=await api('jobs/'+id+'/geometry'),positions=payload.points;
        const bounds=payload.bounds,origin=bounds[0].map((v,i)=>(v+bounds[1][i])/2),bytes=new ArrayBuffer(positions.length*16);
        const f=new Float32Array(bytes),c=new Uint8Array(bytes);
        positions.forEach((p,i)=>{f[i*4]=p[0]-origin[0];f[i*4+1]=p[1]-origin[1];f[i*4+2]=p[2]-origin[2];c.set([p[3],p[4],p[5],255],i*16+12);});
        derivedGeometry={key:id,buffer:bytes,offset:0,vertices:f,colors:c,origin,render_count:positions.length,bounds};
      }
      if(serial!==pollSerial||version!==state.editVersion||state.saved?.id!==j.session_id)return;
      state.result=result;state.derivedGeometry=derivedGeometry;diagnostics(result.diagnostics);
      $('alignPreview').disabled=false;$('alignDownloadResult').disabled=false;$('alignApproveResult').disabled=!result.validated;
      $('alignSummary').textContent=JSON.stringify({by_anchor:result.by_anchor,leave_one_anchor_out:result.leave_one_anchor_out,validation_scope:result.validation_scope},null,2);
      $('alignBAReport').textContent=result.ba?JSON.stringify(result.ba,null,2):'Sim(3): geometría interna conservada.';
      message(result.validated?'Resultado listo para revisar; no se aprueba automáticamente.':'La validación no pasó. Revisa vistas y referencias.',!result.validated);
    }else{message(j.error||j.state,true);diagnostics(await api('jobs/'+id+'/localizations'),true);}
  };await step();
}
async function showTab(align){
  root.hidden=!align;$('roiWorkspace').hidden=align;document.body.classList.toggle('alignment-mode',align);
  $('alignTab').classList.toggle('active',align);$('roiTab').classList.toggle('active',!align);
  if(align){if(!bootPromise)bootPromise=refresh().catch(e=>{bootPromise=null;throw e;});await bootPromise;draw();}
  else await window.roiApp.ensureReady();
}
async function approve(calculated){
  if(!calculated&&!confirm('Aprobarás una colocación MANUAL SIN VALIDACIÓN por matches. ¿Continuar al ROI?'))return;
  const s=state.saved||await save(),p=await api('approve',{session_id:s.id,job_id:calculated?state.job?.id:null,confirm_manual:!calculated});
  await showTab(false);await window.roiApp.refreshCatalog();await window.roiApp.refreshOverview();await window.roiApp.selectBlock(p.id);await refresh();
}
function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);}
document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>setTool(b.dataset.tool));
document.querySelectorAll('[data-panel]').forEach(b=>b.onclick=()=>setPanel(b.dataset.panel));
$('alignStart').onclick=guard(()=>openScene($('alignIncoming').value,[...setupSelection]));
$('alignIncoming').onchange=()=>{setupSelection=new Set([...setupSelection].filter(id=>record(id)?.reconstruction!==$('alignIncoming').value));populateSetup();};
$('alignChange').onclick=showSetup;$('alignSetupCancel').onclick=()=>{$('alignSetup').hidden=true;$('alignEditor').hidden=false;draw();};
$('alignInspectorToggle').onclick=()=>setInspector(!state.inspectorOpen);
$('alignInspectorClose').onclick=()=>{setInspector(false);$('alignInspectorToggle').focus();};
$('alignSelectCloud').onclick=()=>{selectCloud(true);setTool('move');};
$('alignDeselect').onclick=()=>{selectCloud(false);setTool('pan');};
$('alignFullscreen').onclick=guard(async()=>{
  if(document.fullscreenElement)await document.exitFullscreen();else await $('alignEditor').requestFullscreen();
});
$('alignTab').onclick=guard(()=>showTab(true));$('roiTab').onclick=guard(()=>showTab(false));
for(const id of ['alignSetupHistory','alignHistory'])$(id).onclick=guard(async()=>{await history();$('alignHistoryDialog').showModal();});
$('alignHistoryClose').onclick=()=>$('alignHistoryDialog').close();
$('alignLoad').onclick=guard(()=>loadSession($('alignSessions').value));$('alignRefresh').onclick=guard(async()=>{await refresh();await history();});
$('alignAnchor').onchange=()=>{state.page=0;galleryKey='';gallery();updatePairs();draw();};
$('alignDirection').onchange=$('alignAnchor').onchange;
$('alignSearch').oninput=()=>{state.page=0;gallery();};
$('alignPrevious').onclick=()=>{state.page--;gallery();};$('alignNext').onclick=()=>{state.page++;gallery();};
$('alignPick').onclick=()=>setTool('pick');
$('alignProjection').onchange=()=>{state.view=$('alignProjection').value;fitScene();};
$('alignFit').onclick=()=>fitScene();$('alignFocus').onclick=()=>fitScene(true);
$('alignRGB').onchange=draw;$('alignPointSize').oninput=draw;$('alignPivot').onchange=controlsFromMatrix;
$('alignCenter').onclick=()=>centerIncoming();
for(const [i,n] of ['Rx','Ry','Rz'].entries()){
  const slider=$('slider'+n);slider.onpointerdown=beginGesture;
  slider.oninput=()=>{gestureChanged();poseFromMatrix();state.pose.angles[i]=Number(slider.value);state.matrix=matrixFromPose(state.pose);controlsFromMatrix();};
  slider.onchange=()=>endGesture();slider.onpointercancel=()=>endGesture(true);
}
for(const name of ['Scale','Height']){
  const slider=$('align'+name+'Slider');slider.onpointerdown=beginGesture;
  slider.oninput=()=>{
    gestureChanged();const p=clone(gesture.pose);
    if(name==='Scale')p.scale*=2**(Number(slider.value)/50);else p.position[2]+=Number(slider.value);
    state.matrix=matrixFromPose(p);controlsFromMatrix();
  };slider.onchange=()=>endGesture();slider.onpointercancel=()=>endGesture(true);
}
for(const [i,n] of ['X','Y','Z','Rx','Ry','Rz','Escala'].entries())$('pose'+n).onchange=guard(async()=>{
  const value=Number($('pose'+n).value);if(!Number.isFinite(value)||(i===6&&value<=0))throw new Error('Introduce un valor finito y escala positiva.');
  poseFromMatrix();checkpoint();if(i<3)state.pose.position[i]=value;else if(i<6)state.pose.angles[i-3]=value;else state.pose.scale=value;
  state.matrix=matrixFromPose(state.pose);dirty(true);controlsFromMatrix();
});
$('alignUndo').onclick=()=>{endGesture();if(state.undo.length){state.redo.push(clone(state.matrix));state.matrix=state.undo.pop();dirty(true);controlsFromMatrix();}};
$('alignRedo').onclick=()=>{endGesture();if(state.redo.length){state.undo.push(clone(state.matrix));state.matrix=state.redo.pop();dirty(true);controlsFromMatrix();}};
$('alignReset').onclick=()=>{checkpoint();state.matrix=identity();dirty(true);controlsFromMatrix();};
$('alignApplyMatrix').onclick=guard(async()=>{
  const version=state.editVersion,checked=await api('validate',{...currentSession(),matrix:JSON.parse($('alignMatrix').value)});
  if(version!==state.editVersion)throw new Error('La colocación cambió; aplica la matriz de nuevo.');
  checkpoint();state.matrix=checked.matrix;dirty(true);controlsFromMatrix();
});
for(const n of ['alignName','alignCenterError','alignRotationError'])$(n).onchange=()=>dirty();
$('alignPropose').onclick=guard(async()=>{
  const s=selection();if(!s?.views.length)throw new Error('Selecciona primero las vistas puente.');
  const version=state.editVersion,anchor=$('alignAnchor').value,direction=$('alignDirection').value;
  const result=await api('candidates',{session:currentSession(),anchor,direction,radius:Number($('alignRadius').value),angle:Number($('alignAngle').value),limit:Number($('alignLimit').value)});
  if(version!==state.editVersion)throw new Error('La colocación cambió durante la búsqueda. Propón los pares de nuevo.');
  s.pairs=result.pairs;dirty();updatePairs();message(result.pairs.length+' pares propuestos. Revísalos antes de ejecutar.');
});
$('alignAddPair').onclick=guard(async()=>{
  const s=selection(),q=Number($('alignQueryId').value),t=Number($('alignSupportId').value);
  if(!s?.views.some(v=>v.id===q))throw new Error('La query debe ser una vista elegida.');
  const g=$('alignDirection').value==='forward'?state.anchorGeometry[$('alignAnchor').value]:state.geometry;
  if(!g.viewById.has(t))throw new Error('La vista de soporte no está registrada.');
  if(!s.pairs.some(p=>p.query===q&&p.support===t))s.pairs.push({query:q,support:t,reason:'explicit_user_pair'});dirty();updatePairs();
});
$('alignSave').onclick=guard(save);$('alignDownload').onclick=guard(async()=>{const s=state.saved||await save();download(s,s.id+'.json');});
$('alignAttach').onclick=guard(async()=>{await api('inputs',{manifest:$('alignInputManifest').value,reconstruction:$('alignInputMode').value==='current'?state.incoming:null});await refresh();message('Snapshot registrado.');});
$('alignFetchInputs').onclick=guard(async()=>{
  if(!confirm('¿Traer fotos y features desde su hija? Puede transferir varios GiB. No modifica la hija.'))return;
  const s=state.saved||await save(),j=await api('jobs',{session_id:s.id,mode:'inputs'});await watch(j.id);
});
$('alignRun').onclick=guard(()=>run('sim3'));$('alignRunBA').onclick=guard(()=>run('ba'));
$('alignCancel').onclick=guard(async()=>{if(state.job){await api('jobs/'+state.job.id+'/cancel',{});await watch(state.job.id);}});
$('alignApproveManual').onclick=guard(()=>approve(false));$('alignApproveResult').onclick=guard(()=>approve(true));
$('alignPreview').onclick=()=>{state.preview=!state.preview;draw();message(state.preview?'Mostrando resultado calculado.':'Mostrando tu colocación manual.');};
$('alignDownloadResult').onclick=()=>{if(state.result)download(state.result,state.job.id+'-result.json');};
canvas.oncontextmenu=e=>e.preventDefault();
canvas.addEventListener('wheel',e=>{
  e.preventDefault();
  if(!navigation)navigation={center:[...state.camera.center],scale:state.camera.scale};
  const old=navigation.scale,next=Math.max(.0001,Math.min(1e5,old*Math.exp(-e.deltaY*.0015))),[u,v]=basis();
  const dx=e.offsetX-canvas.clientWidth/2,dy=e.offsetY-canvas.clientHeight/2;
  for(let i=0;i<3;i++)navigation.center[i]+=(u[i]*dx-v[i]*dy)*(1/old-1/next);
  navigation.scale=next;draw();
},{passive:false});
canvas.onpointerdown=e=>{
  if(!state.geometry)return;canvas.focus();canvas.setPointerCapture(e.pointerId);
  navigation=null;pendingMove=null;
  const pan=space||e.button===1||(e.button===2&&state.view!=='iso')||tool==='pan';
  const p=screen(apply(state.matrix,pivot())),b=basis(),normal=[b[0][1]*b[1][2]-b[0][2]*b[1][1],b[0][2]*b[1][0]-b[0][0]*b[1][2],b[0][0]*b[1][1]-b[0][1]*b[1][0]];
  drag={x:e.offsetX,y:e.offsetY,center:[...state.camera.center],matrix:clone(state.matrix),pan,orbit:e.button===2&&state.view==='iso',
    yaw:state.yaw??-.7,pitch:state.pitch??.7,pivot:p,angle:Math.atan2(p[1]-e.offsetY,e.offsetX-p[0]),normal,tool,moved:false,axis:null};
  if(!pan&&!drag.orbit&&tool!=='pick'){
    beginGesture();
    if(tool==='move'){const world=apply(state.matrix,pivot());for(let i=0;i<3;i++){const q=world.slice();q[i]+=60/state.camera.scale;const end=screen(q);
      if(Math.hypot(end[0]-p[0],end[1]-p[1])>10&&Math.hypot(end[0]-e.offsetX,end[1]-e.offsetY)<10)drag.axis=i;}}
  }e.preventDefault();
};
function handlePointerMove(e){
  if(!drag)return;const dx=e.offsetX-drag.x,dy=e.offsetY-drag.y;drag.moved||=Math.hypot(dx,dy)>2;if(!drag.moved)return;
  if(drag.orbit){state.yaw=drag.yaw+dx*.007;state.pitch=Math.max(-1.5,Math.min(1.5,drag.pitch+dy*.007));}
  else if(drag.pan){const [u,v]=basis();state.camera.center=drag.center.map((x,i)=>x-(u[i]*dx-v[i]*dy)/state.camera.scale);}
  else if(drag.tool!=='pick'){
    gestureChanged();const fine=e.shiftKey ? .15 : 1;
    if(drag.tool==='move'){
      const [u,v]=basis(),delta=u.map((x,i)=>(x*dx-v[i]*dy)/state.camera.scale*fine);
      if(drag.axis!==null){const i=drag.axis,den=u[i]*u[i]+v[i]*v[i],amount=(u[i]*dx-v[i]*dy)/(state.camera.scale*den)*fine;delta.fill(0);delta[i]=amount;}
      state.matrix=clone(drag.matrix);for(let i=0;i<3;i++)state.matrix[i][3]+=delta[i];
    }else if(drag.tool==='rotate'){
      let angle=Math.hypot(drag.x-drag.pivot[0],drag.y-drag.pivot[1])<30?dx*.008:Math.atan2(drag.pivot[1]-e.offsetY,e.offsetX-drag.pivot[0])-drag.angle;
      if(angle>Math.PI)angle-=2*Math.PI;if(angle<-Math.PI)angle+=2*Math.PI;
      state.matrix=rotateAround(drag.matrix,drag.normal,angle*fine);
    }else if(drag.tool==='scale'){const p=clone(gesture.pose);p.scale*=Math.exp(dx*.006*fine);state.matrix=matrixFromPose(p);}
    controlsFromMatrix();
  }draw();
}
canvas.onpointermove=e=>{
  if(!drag)return;
  pendingMove={offsetX:e.offsetX,offsetY:e.offsetY,shiftKey:e.shiftKey};draw();
};
canvas.onpointerup=e=>{
  if(pendingMove){const move=pendingMove;pendingMove=null;handlePointerMove(move);}
  if(!drag)return;
  if(drag.tool==='pick'&&!drag.moved){
    const g=queryGeometry(),m=$('alignDirection').value==='forward'?state.matrix:activeAnchor()?.matrix;let best=null,distance=12;
    for(const v of g?.views||[]){const p=screen(apply(m,v.center)),d=Math.hypot(p[0]-e.offsetX,p[1]-e.offsetY);if(d<distance){distance=d;best=v.id;}}
    if(best!==null)toggleView(best,!selection()?.views.some(v=>v.id===best));
  }
  const clicked=drag&&!drag.moved&&drag.tool!=='pick';
  drag=null;endGesture();
  if(clicked){selectCloud(false);setTool('pan');}
  draw();
};
canvas.onpointercancel=()=>{pendingMove=null;drag=null;endGesture(true);draw();};
document.addEventListener('keydown',e=>{
  if(root.hidden||!state.sceneOpen)return;
  if(e.key==='Escape'&&!$('alignHistoryDialog').open){
    pendingMove=null;drag=null;endGesture(true);selectCloud(false);setTool('pan');setInspector(false);canvas.focus();e.preventDefault();return;
  }
  if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))return;
  if(e.code==='Space'){space=true;e.preventDefault();}
  if(e.ctrlKey||e.metaKey){if(e.key.toLowerCase()==='z'){e.preventDefault();$(e.shiftKey?'alignRedo':'alignUndo').click();}return;}
  const key=e.key.toLowerCase();if(key==='g')setTool('move');if(key==='r')setTool('rotate');if(key==='s')setTool('scale');if(key==='f')fitScene();
});
document.addEventListener('keyup',e=>{if(e.code==='Space')space=false;});
window.addEventListener('blur',()=>{space=false;pendingMove=null;drag=null;endGesture();});
window.addEventListener('beforeunload',persistDraft);
renderer.onRestore=draw;new ResizeObserver(draw).observe($('alignViewport'));
window.alignmentApp={state,api,chooseIncoming,openScene,currentSession,loadSession,save,apply,screen,controlsFromMatrix,refresh,fitScene,
  cache,renderer,draw,setPanel,setTool,selectCloud,setInspector,showSetup,showTab,persistDraft};
guard(async()=>{await showTab(location.hash!=='#roi');document.body.dataset.ready='true';})();
})();
