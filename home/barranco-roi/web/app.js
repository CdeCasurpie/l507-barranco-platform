'use strict';

const $ = id => document.getElementById(id);
const number = value => new Intl.NumberFormat('es-PE').format(value);
const clone = value => JSON.parse(JSON.stringify(value));
const state = {data: null, vertices: [], closed: false, valid: false, mode: 'pan', selected: -1,
  undo: [], redo: [], selection: null,
  camera: {x: 0, y: 0, scale: 1}, width: 1, height: 1, busy: false,
  drawing: false, space: false, hover: null, version: 0,
  block: '', blocks: [], overview: null, overviewView: false, overviewVersion: 0,
  drafts: {}, epoch: 0, loading: true};
const canvas = $('mapCanvas');
const ctx = canvas.getContext('2d', {alpha: false});
const pointsCanvas = document.createElement('canvas');
let rasterKey = '';
let redrawPending = false;
let validationTimer;
let validationSerial = 0;
let selectionLoadSerial = 0;
let drag = null;

async function api(path, payload, block = state.block) {
  if (block) path += (path.includes('?') ? '&' : '?') + 'block=' + encodeURIComponent(block);
  const response = await fetch(path, payload === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-ROI-Client': 'local-editor'},
    body: JSON.stringify({...payload, block})
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'No se pudo completar la solicitud.');
  return body;
}

function notice(text, kind = '') {
  $('notice').textContent = text;
  $('notice').className = 'notice' + (kind ? ' ' + kind : '');
}

function snapshot() { return {vertices: clone(state.vertices), closed: state.closed}; }
function checkpoint() {
  state.undo.push(snapshot());
  if (state.undo.length > 80) state.undo.shift();
  state.redo = [];
}
function changed() {
  state.version++;
  validationSerial++;
  state.valid = false;
  state.selection = null;
  $('savedInfo').textContent = 'Cambios sin guardar. Guarda una nueva revisión.';
  $('configInfo').textContent = 'El contorno actual tiene cambios sin guardar.';
  $('areaValue').textContent = '—';
  $('sparseKept').textContent = '—';
  rasterKey = '';
  controls();
  scheduleRender();
  clearTimeout(validationTimer);
  if (state.closed) validationTimer = setTimeout(() => validate().catch(showError), 180);
}
function showError(error) { notice(error.message || String(error), 'error'); }

function controls() {
  const unavailable = state.loading || !state.data || !state.block;
  $('vertexCount').textContent = state.vertices.length;
  $('closeBtn').disabled = unavailable || state.closed || state.vertices.length < 3 || state.busy;
  $('saveBtn').disabled = unavailable || !state.valid || state.busy;
  $('downloadJsonBtn').disabled = unavailable || !state.selection;
  $('undoBtn').disabled = !state.undo.length || state.busy;
  $('redoBtn').disabled = !state.redo.length || state.busy;
  for (const name of ['drawBtn', 'editBtn', 'panBtn', 'clearBtn', 'loadBtn']) {
    $(name).disabled = unavailable || state.busy || (name === 'loadBtn' && !$('savedSelect').value);
  }
  $('panBtn').disabled = !state.data;
  $('refreshBtn').disabled = !state.block;
  $('savedSelect').disabled = !state.block;
  $('focusBlockBtn').disabled = !state.block;
  $('selectionStatus').textContent = state.valid ? (state.selection ? 'Revisión guardada' : 'Contorno válido · sin guardar')
    : state.closed ? 'Comprobando contorno…' : state.vertices.length ? 'Contorno en dibujo' : 'Sin contorno';
  $('selectionStatus').className = 'selection-status' + (state.valid ? ' valid' : '');
}

async function refreshCatalog() {
  const rows = await api('/api/blocks');
  state.blocks = rows;
  const select = $('blockSelect');
  select.replaceChildren(new Option('Sin manzana activa · RGB original', ''));
  for (const row of rows) {
    const option = document.createElement('option');option.value = row.block;
    option.textContent = `${row.selected ? '✓ ' : ''}${row.title || row.block} · ${row.node || 'sin asignar'}`;
    select.append(option);
  }
  select.value = state.block;
  $('catalogProgress').textContent = `${rows.filter(r => r.selected).length} / ${rows.length} polígonos guardados`;
}

async function refreshOverview() {
  state.overview = await api('/api/overview');
  state.overviewVersion++;
  rasterKey = '';scheduleRender();
}

function rememberDraft() {
  if (!state.data || state.loading || !state.block) return;
  state.drafts[state.block] = {vertices: clone(state.vertices), closed: state.closed,
    selection: state.selection, name: $('selectionName').value,
    undo: clone(state.undo), redo: clone(state.redo), camera: {...state.camera},
    version: state.version};
}

async function selectBlock(block, initial = false) {
  if (!initial) rememberDraft();
  const epoch = ++state.epoch;
  validationSerial++;
  clearTimeout(validationTimer);
  drag = null;state.hover = null;
  state.block = block;state.loading = true;state.version++;
  state.valid = false;state.busy = false;
  state.selection = null;
  state.vertices = [];state.closed = false;state.undo = [];state.redo = [];state.selected = -1;
  state.overviewView = false;
  $('blockSelect').value = block;
  $('activeBlock').textContent = block;
  $('blockTitle').textContent = 'Manzana ' + block;
  $('loadingTitle').textContent = 'Preparando la manzana ' + block;
  $('loading').hidden = false;
  $('areaValue').textContent = '—';$('sparseKept').textContent = '—';$('configInfo').textContent = '';
  $('selectionName').value = '';
  if (!block) {
    state.data = {title: 'Conjunto sparse · sin selección', sparse_count: 0,
      points: [], focus_bounds: state.overview.bounds, world_origin: state.overview.world_origin};
    state.loading = false;state.overviewView = true;
    $('activeBlock').textContent = '—';$('blockTitle').textContent = 'Sin manzana activa';
    $('placementNote').textContent = 'Colores RGB originales, sin resaltar ninguna manzana.';
    $('sparseTotal').textContent = '—';$('nodeName').textContent = '—';
    $('loading').hidden = true;$('pilotPanel').hidden = true;
    $('savedSelect').replaceChildren(new Option('Elige una manzana para ver sus revisiones', ''));
    resize();fit(state.overview.bounds);mode('pan');controls();rasterKey='';scheduleRender();
    notice('Ninguna manzana seleccionada. Elige una solo cuando quieras delimitar su ROI.');
    return;
  }
  controls();
  try {
    const data = await api('/api/dataset', undefined, block);
    if (epoch !== state.epoch) return;
    data.points.sort((a, b) => a[2] - b[2]);
    state.data = data;
    $('sparseTotal').textContent = number(data.sparse_count);
    $('nodeName').textContent = data.node;
    $('blockTitle').textContent = data.title;
    $('placementNote').textContent = data.placement === 'existing_alignment'
      ? 'Ancla aceptada · colocación fija' : 'Revisión aprobada · '+data.placement;
    canvas.setAttribute('aria-label', `Sparse de la manzana activa ${block}. El contexto de otras manzanas no se recorta.`);
    const draft = state.drafts[block];
    if (draft) {
      state.vertices = clone(draft.vertices);state.closed = draft.closed;
      state.selection = draft.selection;
      state.undo = clone(draft.undo);state.redo = clone(draft.redo);
      $('selectionName').value = draft.name;
    }
    $('loading').hidden = true;
    resize();fit(data.focus_bounds);mode(state.closed ? 'edit' : 'pan');
    const saved = await refreshSelections(state.selection?.id || '', block, epoch);
    if (epoch !== state.epoch) return;
    if (draft?.closed) await validate();
    else if (!draft && saved.length) await loadSelection(saved[0].id);
    if (epoch !== state.epoch) return;
    if (state.selection) showConfigLocation();
    if (initial && state.overview) {state.overviewView = true;fit(state.overview.bounds);}
    notice(`Manzana ${block} activa · ${data.node}. El polígono conserva únicamente puntos de esta manzana.`);
    state.loading=false;
    refreshPilot();controls();rasterKey = '';scheduleRender();
  } catch (error) {
    if (epoch !== state.epoch) return;
    state.loading = false;$('loading').hidden = true;showError(error);controls();
    throw error;
  }
}

function showConfigLocation() {
  $('configInfo').textContent = state.selection
    ? `JSON listo para ${state.data.node}: state/exports/roi_${state.block}.json · envío y mallado pendientes.` : '';
}

function mode(value) {
  state.mode = value;
  state.selected = -1;
  for (const [id, name] of [['drawBtn', 'draw'], ['editBtn', 'edit'], ['panBtn', 'pan']]) {
    $(id).classList.toggle('active', value === name);
  }
  canvas.style.cursor = value === 'draw' ? 'crosshair' : value === 'edit' ? 'default' : 'grab';
  $('helpText').textContent = value === 'draw'
    ? 'Clic: vértice · clic inicial o Enter: cerrar · Backspace: quitar último · botón central: mover.'
    : value === 'edit'
      ? 'Arrastra vértices · doble clic en un lado: añadir · Supr: eliminar vértice seleccionado.'
      : 'Rueda: zoom · arrastrar: desplazar · espacio + arrastre mueve la vista en cualquier modo.';
  scheduleRender();
}

function screen(point) {
  return [(point[0] - state.camera.x) * state.camera.scale + state.width / 2,
    state.height / 2 - (point[1] - state.camera.y) * state.camera.scale];
}
function world(point) {
  return [(point[0] - state.width / 2) / state.camera.scale + state.camera.x,
    (state.height / 2 - point[1]) / state.camera.scale + state.camera.y];
}
function eventPoint(event) {
  const r = canvas.getBoundingClientRect();
  return [event.clientX - r.left, event.clientY - r.top];
}
function fit(bounds) {
  if (!bounds) return;
  const dx = Math.max(bounds[1][0] - bounds[0][0], 1);
  const dy = Math.max(bounds[1][1] - bounds[0][1], 1);
  state.camera = {x: (bounds[0][0] + bounds[1][0]) / 2,
    y: (bounds[0][1] + bounds[1][1]) / 2,
    scale: Math.min((state.width - 100) / dx, (state.height - 100) / dy)};
  rasterKey = '';
  scheduleRender();
}
function zoom(factor, position = [state.width / 2, state.height / 2]) {
  const before = world(position);
  state.camera.scale = Math.min(100000, Math.max(.002, state.camera.scale * factor));
  const after = world(position);
  state.camera.x += before[0] - after[0];
  state.camera.y += before[1] - after[1];
  scheduleRender();
}
function pointInPolygon(x, y) {
  let result = false;
  const v = state.vertices;
  for (let i = 0, j = v.length - 1; i < v.length; j = i++) {
    const [ax, ay] = v[j], [bx, by] = v[i];
    const cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax);
    if (Math.abs(cross) <= 1e-9 * Math.max(1, Math.hypot(bx - ax, by - ay))
      && x >= Math.min(ax, bx) - 1e-9 && x <= Math.max(ax, bx) + 1e-9
      && y >= Math.min(ay, by) - 1e-9 && y <= Math.max(ay, by) + 1e-9) return true;
    if ((ay > y) !== (by > y) && x < (bx - ax) * (y - ay) / (by - ay) + ax) result = !result;
  }
  return result;
}
function rasterize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.round(state.width * dpr), h = Math.round(state.height * dpr);
  pointsCanvas.width = w;
  pointsCanvas.height = h;
  const pc = pointsCanvas.getContext('2d');
  const image = pc.createImageData(w, h), pixels = image.data;
  const scale = state.camera.scale*dpr, ox=w/2-state.camera.x*scale, oy=h/2+state.camera.y*scale;
  if ($('contextToggle').checked && state.overview) {
    for (const block of state.overview.blocks) {
      if (block.block === state.block) continue;
      const dim=state.block ? .55 : 1;
      for (let i=0;i<block.points.length;i++) {
        const point=block.points[i],rgb=block.rgb?.[i]||[170,170,170];
        const x = Math.round(point[0]*scale+ox), y = Math.round(oy-point[1]*scale);
        if (x < 0 || y < 0 || x >= w || y >= h) continue;
        const offset = (y * w + x) * 4;
        pixels[offset] = rgb[0]*dim;pixels[offset+1] = rgb[1]*dim;pixels[offset+2] = rgb[2]*dim;pixels[offset+3] = 255;
      }
    }
  }
  const points = state.data.points;
  const color = $('colorMode').value;
  const size = Math.max(1, Math.round(Number($('pointSize').value) * dpr));
  const zmin = state.data.focus_bounds[0][2], zrange = Math.max(1, state.data.focus_bounds[1][2] - zmin);
  for (const p of points) {
    const x = Math.round(p[0]*scale+ox), y = Math.round(oy-p[1]*scale);
    if (x < -size || y < -size || x >= w || y >= h) continue;
    const selected = !state.valid || !state.closed || pointInPolygon(p[0], p[1]);
    let rgb = [p[3], p[4], p[5]];
    if (color === 'mono') rgb = [205, 205, 205];
    if (color === 'height') {
      const t = Math.min(1, Math.max(0, (p[2] - zmin) / zrange));
      rgb = [50 + 190 * t, 200 - 40 * t, 235 - 150 * t];
    }
    if (!selected) rgb = rgb.map(c => 7 + (c - 7) * .23);
    for (let sy = Math.max(0, y); sy < Math.min(h, y + size); sy++) {
      for (let sx = Math.max(0, x); sx < Math.min(w, x + size); sx++) {
        const o = (sy * w + sx) * 4;
        pixels[o] = rgb[0]; pixels[o + 1] = rgb[1]; pixels[o + 2] = rgb[2]; pixels[o + 3] = 255;
      }
    }
  }
  pc.putImageData(image, 0, 0);
}
function render() {
  redrawPending = false;
  if ($('roiWorkspace').hidden || state.width < 1 || state.height < 1) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#070707'; ctx.fillRect(0, 0, state.width, state.height);
  if (!state.data) return;
  const metres = 85 / state.camera.scale;
  const magnitude = 10 ** Math.floor(Math.log10(metres));
  const grid = [1, 2, 5, 10].map(n => n * magnitude).find(n => n >= metres);
  const lower = world([0, state.height]), upper = world([state.width, 0]);
  ctx.strokeStyle = '#202020'; ctx.lineWidth = .5; ctx.beginPath();
  for (let x = Math.ceil(lower[0] / grid) * grid; x <= upper[0]; x += grid) {
    const s = screen([x, 0])[0]; ctx.moveTo(s, 0); ctx.lineTo(s, state.height);
  }
  for (let y = Math.ceil(lower[1] / grid) * grid; y <= upper[1]; y += grid) {
    const s = screen([0, y])[1]; ctx.moveTo(0, s); ctx.lineTo(state.width, s);
  }
  ctx.stroke();
  const key = JSON.stringify([state.block, state.overviewVersion, $('contextToggle').checked, state.camera, state.width, state.height,
    $('colorMode').value, $('pointSize').value, state.vertices, state.valid, state.closed]);
  if (key !== rasterKey) { rasterize(); rasterKey = key; }
  ctx.drawImage(pointsCanvas, 0, 0, state.width, state.height);
  if ($('contextToggle').checked && state.overview) {
    for (const saved of state.overview.saved_polygons || []) {
      if (saved.block === state.block) continue;
      ctx.beginPath();saved.vertices.forEach((p,i) => {const s=screen(p);i ? ctx.lineTo(...s) : ctx.moveTo(...s);});
      ctx.closePath();ctx.lineWidth=1;ctx.strokeStyle='#99999960';ctx.stroke();
    }
    for (const block of state.overview.blocks) {
      const pos=screen(block.center);
      if (pos[0]<5 || pos[1]<20 || pos[0]>state.width-35 || pos[1]>state.height-35) continue;
      if (!state.overviewView && block.block===state.block) continue;
      const label=(block.label||block.block)+(block.block==='023' ? ' *' : '');
      ctx.font='bold 12px system-ui';const tw=ctx.measureText(label).width;
      ctx.fillStyle='#111111e0';ctx.fillRect(pos[0]-5,pos[1]-16,tw+10,23);
      ctx.fillStyle=block.block===state.block ? '#ffffff' : '#aaaaaa';
      ctx.fillText(label,pos[0],pos[1]);
    }
  }
  if (state.vertices.length) {
    ctx.beginPath();
    state.vertices.forEach((p, i) => { const s = screen(p); i ? ctx.lineTo(...s) : ctx.moveTo(...s); });
    if (state.closed) {
      ctx.closePath(); ctx.fillStyle = '#ffffff10'; ctx.fill();
    } else if (state.hover && state.mode === 'draw') ctx.lineTo(...state.hover);
    ctx.strokeStyle = state.valid || !state.closed ? '#eeeeee' : '#888888';
    ctx.lineWidth = 2; ctx.stroke();
    state.vertices.forEach((p, i) => {
      const s = screen(p);
      ctx.beginPath();ctx.arc(...s, state.selected === i ? 6 : 4.5, 0, Math.PI * 2);
      ctx.fillStyle = state.selected === i ? '#ffffff' : '#cccccc';ctx.fill();
      ctx.strokeStyle = '#111111';ctx.lineWidth = 2;ctx.stroke();
      ctx.fillStyle = '#dddddd';ctx.font = '10px system-ui';ctx.fillText(String(i + 1), s[0] + 9, s[1] - 7);
    });
  }
  $('scaleLabel').textContent = 'Cuadrícula: ' + (grid < 1 ? grid.toPrecision(2) : number(grid)) + ' m';
   $('layerLabel').textContent = state.block
     ? state.data.title + ' · ' + number(state.data.sparse_count) + ' puntos sparse'
     : 'Conjunto sparse · RGB original · sin selección';
}
function scheduleRender() {
  if (!redrawPending) { redrawPending = true; requestAnimationFrame(render); }
}
function resize() {
  const rect = $('canvasShell').getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return;
  state.width = rect.width;state.height = rect.height;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * dpr);canvas.height = Math.round(rect.height * dpr);
  rasterKey = '';scheduleRender();
}

function nearestVertex(position) {
  let best = -1, distance = 11;
  state.vertices.forEach((p, i) => {const s = screen(p), d = Math.hypot(s[0] - position[0], s[1] - position[1]);
    if (d < distance) {best = i;distance = d;}});
  return best;
}
function nearestEdge(position) {
  let best = -1, distance = 12;
  const count = state.closed ? state.vertices.length : state.vertices.length - 1;
  for (let i = 0; i < count; i++) {
    const a = screen(state.vertices[i]), b = screen(state.vertices[(i + 1) % state.vertices.length]);
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((position[0] - a[0]) * dx + (position[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    const d = Math.hypot(position[0] - a[0] - t * dx, position[1] - a[1] - t * dy);
    if (d < distance) {best = i;distance = d;}
  }
  return best;
}
canvas.addEventListener('contextmenu', event => event.preventDefault());
canvas.addEventListener('wheel', event => {event.preventDefault();zoom(Math.exp(-event.deltaY * .0015), eventPoint(event));}, {passive: false});
canvas.addEventListener('pointerdown', event => {
  canvas.focus();
  const p = eventPoint(event);
  const move = state.mode === 'pan' || state.space || event.button === 1 || event.button === 2;
  const vertex = state.mode === 'edit' && !state.busy && !move ? nearestVertex(p) : -1;
  drag = {start: p, camera: {...state.camera}, move, vertex, changed: false, travelled: false};
  if (vertex >= 0) {checkpoint();state.selected = vertex;}
  canvas.setPointerCapture(event.pointerId);
  if (move) canvas.style.cursor = 'grabbing';
  event.preventDefault();
});
canvas.addEventListener('pointermove', event => {
  const p = eventPoint(event);state.hover = p;
  const xy = world(p), origin = state.data?.world_origin || [0, 0];
  $('coordinates').textContent = `E ${(xy[0] + origin[0]).toFixed(2)} · N ${(xy[1] + origin[1]).toFixed(2)} m`;
  if (drag) {
    const dx = p[0] - drag.start[0], dy = p[1] - drag.start[1];
    drag.travelled ||= Math.hypot(dx, dy) > 4;
    if (drag.move) {
      state.camera.x = drag.camera.x - dx / state.camera.scale;
      state.camera.y = drag.camera.y + dy / state.camera.scale;
    } else if (drag.vertex >= 0 && !state.busy) {
      state.vertices[drag.vertex] = xy;drag.changed = true;
      state.valid = false;
    }
  }
  scheduleRender();
});
canvas.addEventListener('pointerup', event => {
  if (!drag) return;
  const current = drag;drag = null;
  if (current.changed) changed();
  if (!current.move && current.vertex < 0 && !current.travelled && state.mode === 'draw' && !state.busy) {
    const p = eventPoint(event);
    if (state.vertices.length >= 3 && nearestVertex(p) === 0) closePolygon();
    else if (!state.closed) {
      const previous = state.vertices.at(-1);
      if (!previous || Math.hypot(...screen(previous).map((v, i) => v - p[i])) > 4) {
        checkpoint();state.vertices.push(world(p));changed();
      }
    }
  }
  canvas.style.cursor = state.mode === 'draw' ? 'crosshair' : state.mode === 'pan' ? 'grab' : 'default';
  controls();scheduleRender();
});
canvas.addEventListener('pointercancel', () => {if (drag?.changed) changed();drag = null;});
canvas.addEventListener('dblclick', event => {
  if (state.busy) return;
  if (state.mode === 'draw') return closePolygon();
  if (state.mode === 'edit') {
    const p = eventPoint(event), edge = nearestEdge(p);
    if (edge >= 0 && nearestVertex(p) < 0) {
      checkpoint();state.vertices.splice(edge + 1, 0, world(p));state.selected = edge + 1;changed();
    }
  }
});

async function validate() {
  if (!state.closed) return null;
  const serial = ++validationSerial, version = state.version, epoch = state.epoch, block = state.block;
  try {
    const result = await api('/api/validate', {vertices: state.vertices, fingerprint: state.data.fingerprint}, block);
    if (serial !== validationSerial || version !== state.version || epoch !== state.epoch) return null;
    state.valid = true;
    $('areaValue').textContent = number(Math.round(result.area_m2)) + ' m²';
    $('sparseKept').textContent = number(result.sparse_kept) + ' / ' + number(result.sparse_total);
    notice('Contorno válido. El interior y el borde se conservarán en todas las alturas. Guarda la selección y su JSON.');
    controls();rasterKey = '';scheduleRender();
    return result;
  } catch (error) {
    if (serial === validationSerial && epoch === state.epoch) {
      state.valid = false;controls();$('selectionStatus').textContent = 'Contorno inválido';showError(error);
    }
    return null;
  }
}
function closePolygon() {
  if (state.closed || state.vertices.length < 3 || state.busy) return;
  checkpoint();state.closed = true;changed();mode('edit');
}
function restore(item) {
  state.vertices = clone(item.vertices);state.closed = item.closed;
  state.selected = -1;changed();
}
function undo() {
  if (!state.undo.length || state.busy) return;
  state.redo.push(snapshot());restore(state.undo.pop());
}
function redo() {
  if (!state.redo.length || state.busy) return;
  state.undo.push(snapshot());restore(state.redo.pop());
}
async function refreshSelections(selected = '', block = state.block, epoch = state.epoch) {
  const list = await api('/api/selections', undefined, block);
  if (epoch !== state.epoch || block !== state.block) return list;
  $('savedSelect').replaceChildren();
  const placeholder = document.createElement('option');placeholder.value = '';
  placeholder.textContent = list.length ? 'Elegir una revisión…' : 'Ninguna selección guardada';
  $('savedSelect').append(placeholder);
  for (const item of list) {
    const option = document.createElement('option');option.value = item.id;
    option.textContent = item.name + ' · ' + new Date(item.created_at * 1000).toLocaleString('es-PE');
    $('savedSelect').append(option);
  }
  $('savedSelect').value = selected;controls();
  return list;
}
async function saveSelection() {
  if (state.busy || !state.valid) return;
  const version = state.version, epoch = state.epoch, block = state.block;
  const item = await api('/api/selections', {vertices: state.vertices, fingerprint: state.data.fingerprint,
    name: $('selectionName').value}, block);
  if (epoch !== state.epoch || block !== state.block) {
    const draft=state.drafts[block];
    if (draft && draft.version===version) draft.selection=item;
    await refreshCatalog();await refreshOverview();return;
  }
  if (version !== state.version) return notice('Se guardó una revisión anterior a los últimos cambios. Guarda de nuevo el contorno actual.');
  state.selection = item;
  $('savedInfo').textContent = 'Guardada: ' + item.id;
  await refreshSelections(item.id);
  await refreshCatalog();await refreshOverview();
  if (epoch !== state.epoch) return;
  showConfigLocation();
  notice(`Polígono y JSON guardados. No se ha enviado ni lanzado ningún mallado.`);controls();
}
async function loadSelection(id) {
  const block=state.block,epoch=state.epoch,load=++selectionLoadSerial;
  state.selection=null;state.valid=false;controls();
  const item = await api('/api/selections/' + encodeURIComponent(id), undefined, block);
  if (epoch!==state.epoch || load!==selectionLoadSerial) return;
  if (item.fingerprint !== state.data.fingerprint) throw new Error('La revisión pertenece a otra transformación o fuente.');
  checkpoint();state.vertices = clone(item.vertices);state.closed = true;changed();
  $('selectionName').value = item.name;
  clearTimeout(validationTimer);
  const valid=await validate();
  if (epoch!==state.epoch || load!==selectionLoadSerial || !valid) return;
  state.selection = item;$('savedInfo').textContent = 'Revisión abierta: ' + item.id;
  showConfigLocation();mode('edit');controls();notice('Revisión guardada recuperada. Puedes editarla y guardar una nueva versión.');
}
async function refreshPilot() {
  try {
    const epoch=state.epoch;
    const pilot = await api('/api/pilot');
    if (epoch!==state.epoch) return;
    $('pilotPanel').hidden = pilot.status === 'not_started';
    $('pilotStatus').textContent = pilot.status === 'completed'
      ? 'Delaunay, Ball Pivoting y parches RANSAC disponibles desde las mismas cámaras.'
      : 'Piloto en ejecución · ' + pilot.methods.length + ' de 3 métodos terminados.';
    $('pilotLink').hidden = pilot.status !== 'completed';
    if (pilot.status === 'running') setTimeout(refreshPilot, 5000);
  } catch (_) { /* Optional gallery is independent of selection editing. */ }
}

$('drawBtn').addEventListener('click', () => {
  if (state.overviewView) {state.overviewView=false;fit(state.data.focus_bounds);}
  if (state.closed) {checkpoint();state.vertices = [];state.closed = false;changed();}
  mode('draw');notice('Haz clic alrededor de la región que quieras conservar. Cierra el contorno con Enter o el botón.');
});
function setROIControls(open) {
  $('roiWorkspace').classList.toggle('roi-controls-open',open);
  $('roiInspector').inert=!open;$('roiInspector').setAttribute('aria-hidden',String(!open));
  $('roiControlsToggle').setAttribute('aria-expanded',String(open));
}
$('roiControlsToggle').addEventListener('click',()=>setROIControls(!$('roiWorkspace').classList.contains('roi-controls-open')));
$('roiControlsClose').addEventListener('click',()=>{setROIControls(false);$('roiControlsToggle').focus();});
$('editBtn').addEventListener('click', () => mode('edit'));
$('panBtn').addEventListener('click', () => mode('pan'));
$('blockSelect').addEventListener('change', () => selectBlock($('blockSelect').value).catch(showError));
$('overviewBtn').addEventListener('click', () => {
  if (!state.overview) return;
  state.overviewView=true;$('contextToggle').checked=true;
  fit(state.overview.bounds);mode('pan');controls();
  notice(`Conjunto de manzanas activas. La activa es ${state.block}; elige una para delimitar su ROI.`);
});
$('focusBlockBtn').addEventListener('click', () => {state.overviewView=false;fit(state.data?.focus_bounds);});
$('contextToggle').addEventListener('change', () => {
  if (!$('contextToggle').checked && state.overviewView) {state.overviewView=false;fit(state.data?.focus_bounds);}
  rasterKey='';scheduleRender();
});
$('nextBlockBtn').addEventListener('click', () => {
  const start=state.blocks.findIndex(b=>b.block===state.block);
  const ordered=[...state.blocks.slice(start+1),...state.blocks.slice(0,start+1)];
  const next=ordered.find(b=>!b.selected);
  if (next) selectBlock(next.block).catch(showError);
  else notice('Las manzanas activas tienen un polígono guardado. Puedes revisar cualquiera desde el selector.');
});
$('downloadJsonBtn').addEventListener('click', () => {
  if (!state.selection) return;
  const link=document.createElement('a');
  link.href='/api/roi.json?block='+encodeURIComponent(state.block)+'&selection_id='+encodeURIComponent(state.selection.id);
  link.download='roi_'+state.block+'.json';link.click();
});
$('closeBtn').addEventListener('click', closePolygon);
$('undoBtn').addEventListener('click', undo);$('redoBtn').addEventListener('click', redo);
$('clearBtn').addEventListener('click', () => {checkpoint();state.vertices = [];state.closed = false;changed();notice('Contorno retirado de la vista. Las revisiones guardadas se conservan.');});
$('focusBtn').addEventListener('click', () => {state.overviewView=false;fit(state.data?.focus_bounds);});
$('fitBtn').addEventListener('click', () => {state.overviewView=false;fit(state.data?.full_bounds);});
$('zoomInBtn').addEventListener('click', () => zoom(1.4));$('zoomOutBtn').addEventListener('click', () => zoom(1 / 1.4));
$('colorMode').addEventListener('change', scheduleRender);$('pointSize').addEventListener('input', scheduleRender);
$('saveBtn').addEventListener('click', () => saveSelection().catch(showError));
$('refreshBtn').addEventListener('click', () => refreshSelections(state.selection?.id).catch(showError));
$('savedSelect').addEventListener('change', controls);
$('loadBtn').addEventListener('click', () => loadSelection($('savedSelect').value).catch(showError));
document.addEventListener('keydown', event => {
  if ($('roiWorkspace').hidden) return;
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
  if (event.code === 'Space') {state.space = true;event.preventDefault();}
  if (state.busy) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault();event.shiftKey ? redo() : undo();return;
  }
  if (event.key === 'Enter') {event.preventDefault();closePolygon();}
  if (event.key === 'Escape') mode('pan');
  if (['Delete', 'Backspace'].includes(event.key)) {
    const index = !state.closed ? state.vertices.length - 1 : state.selected;
    if (index >= 0) {
      event.preventDefault();checkpoint();state.vertices.splice(index, 1);state.selected = -1;
      if (state.vertices.length < 3) state.closed = false;
      changed();
    }
  }
});
document.addEventListener('keyup', event => {if (event.code === 'Space') state.space = false;});
window.addEventListener('blur', () => {state.space = false;drag = null;});
new ResizeObserver(resize).observe($('canvasShell'));

async function boot() {
  try {
    await Promise.all([refreshCatalog(),refreshOverview()]);
    await selectBlock('',true);
    document.body.dataset.ready = 'true';
  } catch (error) {
    $('loading').hidden = true;showError(error);document.body.dataset.ready = 'error';
  }
}

// Expose only editor state/coordinate helpers for reproducible local browser checks.
let bootPromise = null;
function ensureReady() {
  if (!bootPromise) bootPromise = boot();
  return bootPromise;
}
window.roiApp = {state, screen, world, fit, validate, closePolygon, saveSelection, loadSelection, selectBlock,
  refreshCatalog, refreshOverview, ensureReady};
