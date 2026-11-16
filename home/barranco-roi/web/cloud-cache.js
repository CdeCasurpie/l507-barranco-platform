/* Revision-keyed, bounded render-only cache. Never stores alignment approvals. */
(() => {
'use strict';
const MAX_BYTES=64*1024*1024, MAX_ITEMS=24;
class CloudCache {
  constructor(){this.memory=new Map();this.pending=new Map();this.stats={network:0,memory:0,disk:0};this.db=null;}
  async database(){
    if(!this.db)this.db=new Promise(resolve=>{
      if(!window.indexedDB){resolve(null);return;}
      const r=indexedDB.open('barranco-render-v2',1);
      r.onupgradeneeded=()=>r.result.createObjectStore('clouds',{keyPath:'key'});
      r.onsuccess=()=>{r.result.onversionchange=()=>r.result.close();resolve(r.result);};
      r.onerror=()=>resolve(null);r.onblocked=()=>resolve(null);
    });return this.db;
  }
  async stored(key){
    const db=await this.database();if(!db)return null;
    return new Promise(resolve=>{try{
      const r=db.transaction('clouds').objectStore('clouds').get(key);
      r.onsuccess=()=>resolve(r.result?.buffer||null);r.onerror=()=>resolve(null);
    }catch(_){resolve(null);}});
  }
  async persist(key,buffer){
    const db=await this.database();if(!db)return;
    try{
      const tx=db.transaction('clouds','readwrite'),store=tx.objectStore('clouds');
      store.put({key,buffer,bytes:buffer.byteLength,used:Date.now()});
      const all=store.getAll();all.onsuccess=()=>{
        const rows=all.result.sort((a,b)=>b.used-a.used);let bytes=0;
        rows.forEach((r,i)=>{bytes+=r.bytes;if(i>=MAX_ITEMS||bytes>MAX_BYTES)store.delete(r.key);});
      };
      tx.onerror=()=>{};tx.onabort=()=>{};
    }catch(_){/* Cache unavailability must not block editing. */}
  }
  decode(buffer,key){
    const size=new DataView(buffer).getUint32(0,true);
    if(size>buffer.byteLength-4||size%4)throw new Error('Cabecera de nube inválida.');
    const meta=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,4,size)));
    const offset=4+size;
    if(meta.format!==2||buffer.byteLength-offset!==meta.render_count*16)throw new Error('Nube visual incompleta.');
    return {...meta,key,buffer,offset,vertices:new Float32Array(buffer,offset,meta.render_count*4),
      colors:new Uint8Array(buffer,offset),viewById:new Map(meta.views.map(v=>[v.id,v]))};
  }
  remember(key,data){
    this.memory.delete(key);this.memory.set(key,data);
    let bytes=Array.from(this.memory.values()).reduce((n,v)=>n+v.buffer.byteLength,0);
    while(this.memory.size>MAX_ITEMS||bytes>MAX_BYTES){
      const oldest=this.memory.keys().next().value;bytes-=this.memory.get(oldest).buffer.byteLength;this.memory.delete(oldest);
    }
  }
  async get(id,version){
    if(!version)throw new Error('Falta la revisión visual; actualiza el catálogo.');
    const key=id+'/'+version;
    if(this.memory.has(key)){this.stats.memory++;const data=this.memory.get(key);this.remember(key,data);return data;}
    if(this.pending.has(key))return this.pending.get(key);
    const promise=(async()=>{
      let buffer=await this.stored(key),data;
      if(buffer){try{data=this.decode(buffer,key);this.stats.disk++;}catch(_){buffer=null;}}
      if(!buffer){
        const r=await fetch('/api/alignment/cloud/'+encodeURIComponent(id)+'?v='+encodeURIComponent(version));
        if(!r.ok){const body=await r.json();throw new Error(body.error||'No se pudo cargar la nube.');}
        buffer=await r.arrayBuffer();data=this.decode(buffer,key);this.stats.network++;
      }
      if(data.version!==version||data.id!==id)throw new Error('La caché no corresponde a esta reconstrucción.');
      this.remember(key,data);void this.persist(key,buffer);return data;
    })();
    this.pending.set(key,promise);
    try{return await promise;}finally{this.pending.delete(key);}
  }
}
window.CloudCache=CloudCache;
})();
