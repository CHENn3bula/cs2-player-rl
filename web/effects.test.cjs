const test = require('node:test');
const assert = require('node:assert/strict');
const effects = require('./effects.js');

function recordingContext() {
  const calls=[];
  const ctx=new Proxy({}, {
    get(target,key) {
      if(key==='createRadialGradient') return (...args)=>{calls.push([key,...args]);return {addColorStop:(...stop)=>calls.push(['stop',...stop])};};
      return (...args)=>calls.push([key,...args]);
    },
    set(target,key,value){calls.push([key,typeof value==='object'?'gradient':value]);return true;}
  });
  return {ctx,calls};
}
const scene={smokes:[{x:100,y:150,z:0,entity_id:'123456789012345678',effect_age:4}],fires:[{x:200,y:250,z:0,entity_id:'2'}],projectiles:[],pulses:[]};
const options={project:p=>({x:p.x/4.4,y:-p.y/4.4}),worldScale:1/4.4,time:20};
test('effect footprints scale with the radar projection, not the viewport pixel size',()=>{
  assert.equal(effects.footprint('smoke',2/4.4),effects.footprint('smoke',1/4.4)*2);
  assert.equal(effects.footprint('fire',.5),effects.footprint('molotov',.5));
});
test('paused and rewound VFX are deterministic while playback animates',()=>{
  const a=recordingContext(), b=recordingContext(), c=recordingContext();
  effects.drawUtilities(a.ctx,scene,options);
  effects.drawUtilities(b.ctx,scene,{...options,time:21});
  effects.drawUtilities(c.ctx,scene,options);
  assert.deepEqual(a.calls,c.calls);
  assert.notDeepEqual(a.calls,b.calls);
  assert.equal(a.calls.filter(c=>c[0]==='save').length,a.calls.filter(c=>c[0]==='restore').length);
  assert.ok(a.calls.every(c=>c.slice(1).every(v=>typeof v!=='number'||Number.isFinite(v))));
});
test('a corrupt future trail sample does not draw a future trajectory',()=>{
  const marker={x:2,y:3,z:0,kind:'flash',trail:[{x:1,y:2,time:19},{x:2,y:3,time:20}]};
  const a=recordingContext(),b=recordingContext();
  const base={smokes:[],fires:[],pulses:[],projectiles:[marker]};
  effects.drawUtilities(a.ctx,base,options);
  effects.drawUtilities(b.ctx,{...base,projectiles:[{...marker,trail:[...marker.trail,{x:999,y:999,time:21}]}]},options);
  assert.deepEqual(a.calls,b.calls);
});
test('grenade icon markup uses fixed geometry for unknown labels',()=>{
  for(const kind of ['smoke','flash','he','fire','decoy']) assert.match(effects.iconSvg(kind),/<svg/);
  assert.doesNotMatch(effects.iconSvg('<script>alert(1)</script>'),/script|alert/);
});
