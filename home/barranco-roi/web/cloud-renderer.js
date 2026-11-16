/* Resident GPU buffers: changing a pose updates uniforms, not the point arrays. */
(() => {
'use strict';
const shaderSource={
 vertex:`attribute vec3 position; attribute vec4 color;
 uniform mat3 model; uniform vec3 translation; uniform vec3 axisU; uniform vec3 axisV; uniform vec3 axisN;
 uniform vec2 clipScale; uniform float depthScale; uniform float pointSize;
 varying vec4 rgb;
 void main(){vec3 p=model*position+translation;
 gl_Position=vec4(dot(p,axisU)*clipScale.x,dot(p,axisV)*clipScale.y,-dot(p,axisN)*depthScale,1.0);
 gl_PointSize=pointSize;rgb=color;}`,
 fragment:`precision mediump float; varying vec4 rgb; uniform vec3 tint; uniform float original;
 void main(){gl_FragColor=vec4(mix(tint,rgb.rgb,original),1.0);}`
};
class CloudRenderer {
  constructor(canvas){
    this.canvas=canvas;this.buffers=new Map();this.uploads=0;this.frames=0;this.lastMs=0;this.colorCache=new WeakMap();
    this.gl=canvas.getContext('webgl',{alpha:false,antialias:false,preserveDrawingBuffer:false,powerPreference:'high-performance'});
    if(this.gl){try{this.initialize();}catch(e){console.warn('WebGL no disponible:',e);this.gl=null;}}
    if(!this.gl){
      // A separate canvas is necessary if a WebGL context was obtained then failed.
      this.fallback=document.createElement('canvas');canvas.after(this.fallback);
      this.fallback.className=canvas.className;this.fallback.setAttribute('aria-hidden','true');canvas.hidden=true;
      this.ctx=this.fallback.getContext('2d',{alpha:false});this.backend='Canvas optimizado';
    }else this.backend='WebGL';
    canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();this.lost=true;});
    canvas.addEventListener('webglcontextrestored',()=>{this.buffers.clear();this.lost=false;this.initialize();this.onRestore?.();});
  }
  initialize(){
    const gl=this.gl,program=gl.createProgram();
    for(const [type,text] of [[gl.VERTEX_SHADER,shaderSource.vertex],[gl.FRAGMENT_SHADER,shaderSource.fragment]]){
      const shader=gl.createShader(type);gl.shaderSource(shader,text);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));
      gl.attachShader(program,shader);gl.deleteShader(shader);
    }
    gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));
    this.program=program;this.uniforms={};
    for(const key of ['model','translation','axisU','axisV','axisN','clipScale','depthScale','pointSize','tint','original'])
      this.uniforms[key]=gl.getUniformLocation(program,key);
    this.position=gl.getAttribLocation(program,'position');this.color=gl.getAttribLocation(program,'color');
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.clearColor(.025,.025,.025,1);
  }
  buffer(data){
    const gl=this.gl;if(this.buffers.has(data.key)){const b=this.buffers.get(data.key);this.buffers.delete(data.key);this.buffers.set(data.key,b);return b;}
    const full=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,full);
    gl.bufferData(gl.ARRAY_BUFFER,new Uint8Array(data.buffer,data.offset),gl.STATIC_DRAW);
    const step=Math.max(1,Math.ceil(data.render_count/18000)),small=new Uint8Array(Math.ceil(data.render_count/step)*16);
    const source=new Uint8Array(data.buffer,data.offset);
    for(let i=0,j=0;i<data.render_count;i+=step,j+=16)small.set(source.subarray(i*16,i*16+16),j);
    const lod=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,lod);gl.bufferData(gl.ARRAY_BUFFER,small,gl.STATIC_DRAW);
    const result={full,lod,count:small.byteLength/16};this.buffers.set(data.key,result);this.uploads++;
    while(this.buffers.size>24){const key=this.buffers.keys().next().value,b=this.buffers.get(key);gl.deleteBuffer(b.full);gl.deleteBuffer(b.lod);this.buffers.delete(key);}
    return result;
  }
  draw(clouds,camera,basis,width,height,{interacting=false,rgb=false,size=1.6,depth=1000}={}){
    const begin=performance.now(),dpr=Math.min(devicePixelRatio||1,2),target=this.gl?this.canvas:this.fallback;
    if(target.width!==Math.round(width*dpr)||target.height!==Math.round(height*dpr)){target.width=Math.round(width*dpr);target.height=Math.round(height*dpr);}
    if(!width||!height||this.lost)return;
    const [u,v]=basis,n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];
    if(this.gl){
      const gl=this.gl,U=this.uniforms;gl.viewport(0,0,target.width,target.height);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      gl.useProgram(this.program);gl.uniform3fv(U.axisU,u);gl.uniform3fv(U.axisV,v);gl.uniform3fv(U.axisN,n);
      gl.uniform2f(U.clipScale,2*camera.scale/width,2*camera.scale/height);gl.uniform1f(U.depthScale,1/Math.max(depth,1));
      gl.uniform1f(U.pointSize,size*dpr);gl.uniform1f(U.original,rgb?1:0);
      for(const {data,matrix:m,tint,highlight} of clouds){
        gl.uniform1f(U.original,rgb&&!highlight?1:0);
        const b=this.buffer(data);gl.bindBuffer(gl.ARRAY_BUFFER,interacting?b.lod:b.full);
        gl.enableVertexAttribArray(this.position);gl.vertexAttribPointer(this.position,3,gl.FLOAT,false,16,0);
        gl.enableVertexAttribArray(this.color);gl.vertexAttribPointer(this.color,4,gl.UNSIGNED_BYTE,true,16,12);
        gl.uniformMatrix3fv(U.model,false,[m[0][0],m[1][0],m[2][0],m[0][1],m[1][1],m[2][1],m[0][2],m[1][2],m[2][2]]);
        const o=data.origin;
        gl.uniform3fv(U.translation,[0,1,2].map(i=>m[i][0]*o[0]+m[i][1]*o[1]+m[i][2]*o[2]+m[i][3]-camera.center[i]));
        gl.uniform3fv(U.tint,tint);gl.drawArrays(gl.POINTS,0,interacting?b.count:data.render_count);
      }
    }else{
      const ctx=this.ctx;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#070707';ctx.fillRect(0,0,width,height);
      // Allocation-free projection, bounded LOD even without a GPU.
      for(const {data,matrix:m,tint,highlight} of clouds){
        const original=rgb&&!highlight;
        let cssColors=this.colorCache.get(data);
        if(original&&!cssColors){
          cssColors=new Array(data.render_count);const palette=new Map(),c=data.colors;
          for(let i=0;i<data.render_count;i++){
            const k=i*16,key=(c[k+12]<<16)|(c[k+13]<<8)|c[k+14];
            if(!palette.has(key))palette.set(key,`rgb(${c[k+12]},${c[k+13]},${c[k+14]})`);
            cssColors[i]=palette.get(key);
          }
          this.colorCache.set(data,cssColors);
        }
        const p=data.vertices,o=data.origin,step=interacting?Math.max(1,Math.ceil(data.render_count/9000)):1;
        const t=[0,1,2].map(i=>m[i][0]*o[0]+m[i][1]*o[1]+m[i][2]*o[2]+m[i][3]-camera.center[i]);
        const au=[0,1,2].map(j=>u[0]*m[0][j]+u[1]*m[1][j]+u[2]*m[2][j]);
        const av=[0,1,2].map(j=>v[0]*m[0][j]+v[1]*m[1][j]+v[2]*m[2][j]);
        const tx=t[0]*u[0]+t[1]*u[1]+t[2]*u[2],ty=t[0]*v[0]+t[1]*v[1]+t[2]*v[2];
        ctx.fillStyle=`rgb(${tint.map(c=>Math.round(c*255)).join(',')})`;
        for(let i=0;i<data.render_count;i+=step){
          const at=i*4,x=width/2+(au[0]*p[at]+au[1]*p[at+1]+au[2]*p[at+2]+tx)*camera.scale;
          const y=height/2-(av[0]*p[at]+av[1]*p[at+1]+av[2]*p[at+2]+ty)*camera.scale;
          if(x<0||y<0||x>=width||y>=height)continue;
          if(original)ctx.fillStyle=cssColors[i];
          ctx.fillRect(x,y,size,size);
        }
      }
    }
    this.frames++;this.lastMs=performance.now()-begin;
  }
  retain(keys){
    if(!this.gl)return;const wanted=new Set(keys);
    // A small GPU LRU is retained between scenes, not disposed on every tab switch.
    if(this.buffers.size<=20)return;
    for(const [key,b] of this.buffers){if(!wanted.has(key)){this.gl.deleteBuffer(b.full);this.gl.deleteBuffer(b.lod);this.buffers.delete(key);}}
  }
}
window.CloudRenderer=CloudRenderer;
})();
