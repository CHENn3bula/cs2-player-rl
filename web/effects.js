/* Replay VFX. Footprints are illustrative, never collision or damage geometry. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.IGLEffects = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const TAU = Math.PI * 2;
  const SMOKE_RADIUS = 144; // Awpy analysis convention; not an engine boundary.
  const FIRE_RADIUS = 150; // Illustrative patch around a recorded inferno origin.
  const COLORS = {smoke:"#c9d4d8", flash:"#fff2b2", he:"#cfdd87", fire:"#ffa05a", decoy:"#bda9e3"};
  const kindOf = (kind) => ["molotov", "incendiary"].includes(kind) ? "fire" : kind;
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const valid = (p) => p && Number.isFinite(p.x) && Number.isFinite(p.y);
  function seed(effect) {
    const key = String(effect.entity_id ?? `${effect.x}:${effect.y}:${effect.z}`);
    let value = 2166136261;
    for (let i = 0; i < key.length; i++) value = Math.imul(value ^ key.charCodeAt(i), 16777619);
    return (value >>> 0) / 4294967296 * TAU;
  }
  function footprint(kind, worldScale) {
    return (kindOf(kind) === "smoke" ? SMOKE_RADIUS : FIRE_RADIUS) * worldScale;
  }
  function iconSvg(kind) {
    const shape = {
      smoke:'<path d="M8 8h8v13H8zM10 5h4v3M16 5h3v6M9 12h6M9 17h6"/><path d="M10 2c-2 1 2 2 0 3M14 1c-2 1 2 2 0 3"/>',
      flash:'<path d="M8 7h8v15H8zM10 4h4v3M16 4h3v6M8 11h8M8 17h8M11 8v2M13 8v2M11 18v3M13 18v3"/>',
      he:'<path d="M10 3h5v5M15 4h4v7M10 8C4 9 5 21 12 22c7-1 8-13 2-14zM7 13h10M7 17h10M10 9v12M14 9v12"/>',
      fire:'<path d="M11 8V3h4v5l3 5v8H7v-8zM11 3l-2-2M14 4c6-5 7 2 4 3M9 14h7v4H9z"/>',
      decoy:'<path d="M9 7h6v15H9zM10 4h4v3M15 4h3v5M10 11h4M10 18h4M5 9c-2 2-2 5 0 7M19 9c2 2 2 5 0 7"/>'
    }[kindOf(kind)] || '<circle cx="12" cy="12" r="7"/>';
    return `<svg class="utility-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">${shape}</svg>`;
  }
  function disc(ctx, x, y, radius, stops) {
    if (!(radius > 0)) return;
    const gradient = ctx.createRadialGradient(x-radius*.18, y-radius*.22, radius*.02, x, y, radius);
    for (const [at, color] of stops) gradient.addColorStop(at, color);
    ctx.fillStyle = gradient;
    ctx.beginPath(); ctx.arc(x, y, radius, 0, TAU); ctx.fill();
  }
  function drawSmoke(ctx, effect, project, worldScale, time) {
    const p = project(effect), phase = seed(effect);
    const radius = footprint("smoke", worldScale);
    const growth = effect.effect_age === null || effect.effect_age === undefined ? 1 : clamp(effect.effect_age / .65, .25, 1);
    const r = radius * growth;
    ctx.save();
    disc(ctx, p.x, p.y, r*1.14, [[0,"#313a40bb"],[.65,"#65707770"],[1,"#77818b00"]]);
    for (let i=0;i<9;i++) {
      const angle = phase + i*TAU/9 + Math.sin(time*.33+i)*.04;
      const distance = i === 8 ? 0 : r*(.39+.05*Math.sin(i*3+phase));
      const puff = r*(.53+.035*Math.sin(time*.6+phase+i));
      disc(ctx,p.x+Math.cos(angle)*distance,p.y+Math.sin(angle)*distance,puff,
        [[0,"#d1d5d7bc"],[.45,"#a6afb4a3"],[.8,"#7e8a9188"],[1,"#8e999f00"]]);
    }
    ctx.restore();
  }
  function drawFire(ctx, effect, project, worldScale, time) {
    const p=project(effect), r=footprint("fire",worldScale), phase=seed(effect);
    ctx.save();
    disc(ctx,p.x,p.y,r*1.2,[[0,"#ffb03999"],[.58,"#ff59155e"],[1,"#e3390c00"]]);
    for(let i=0;i<8;i++) {
      const a=phase+i*TAU/7, reach=i===7?0:r*(.3+.16*Math.sin(i*7+phase));
      const x=p.x+Math.cos(a)*reach, y=p.y+Math.sin(a)*reach;
      const size=r*(.28+.07*Math.sin(time*6+i+phase));
      disc(ctx,x,y,size*1.8,[[0,"#fff3a6ed"],[.25,"#ffcb43d9"],[.52,"#ff8010b3"],[1,"#ff480000"]]);
      ctx.fillStyle="#ffe891bb";
      ctx.beginPath(); ctx.moveTo(x-size*.35,y+size*.25);
      ctx.bezierCurveTo(x-size,y-size*.2,x+size*.4,y-size*.45,x+size*.2,y-size*1.2);
      ctx.bezierCurveTo(x+size,y-size*.3,x+size*.5,y+size*.6,x-size*.35,y+size*.25); ctx.fill();
    }
    ctx.restore();
  }
  function drawGrenade(ctx, p, kind, angle=0, size=7) {
    const type=kindOf(kind), color=COLORS[type] || "#e1e7ee";
    ctx.save(); ctx.translate(p.x,p.y); ctx.rotate(angle);
    ctx.shadowColor="#000d";ctx.shadowBlur=3;
    ctx.strokeStyle="#10202a";ctx.lineWidth=1.7;ctx.fillStyle=color;
    if(type==="he") {ctx.beginPath();ctx.ellipse(0,1,size*.7,size*.85,0,0,TAU);ctx.fill();ctx.stroke();}
    else {ctx.beginPath();ctx.roundRect(-size*.45,-size*.7,size*.9,size*1.5,2);ctx.fill();ctx.stroke();}
    ctx.shadowBlur=0;ctx.strokeStyle="#14222b";ctx.lineWidth=1.2;
    ctx.beginPath();ctx.moveTo(-size*.42,0);ctx.lineTo(size*.42,0);ctx.moveTo(0,-size*.72);ctx.lineTo(0,-size*1.07);ctx.lineTo(size*.55,-size*1.07);ctx.lineTo(size*.7,-size*.5);ctx.stroke();
    if(type==="fire") {ctx.strokeStyle="#ffc26b";ctx.beginPath();ctx.moveTo(0,-size);ctx.lineTo(-3,-size*1.6);ctx.lineTo(1,-size*1.3);ctx.stroke();}
    if(type==="decoy") {ctx.strokeStyle=color;ctx.beginPath();ctx.arc(0,0,size*1.4,-.65,.65);ctx.stroke();}
    ctx.restore();
  }
  function drawFlashHit(ctx,p,age,duration) {
    const alpha=clamp(1-age/duration,0,1), r=12+age*9;
    ctx.save();ctx.globalAlpha=alpha;
    disc(ctx,p.x,p.y,r*1.7,[[0,"#fffef0ce"],[.3,"#fff4b966"],[1,"#fff2b000"]]);
    ctx.fillStyle="#fff9de";ctx.beginPath();
    for(let i=0;i<16;i++){const a=i*TAU/16,reach=i%2?r*.23:r*(i%4===0?1:.6);const x=p.x+Math.cos(a)*reach,y=p.y+Math.sin(a)*reach;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.closePath();ctx.fill();ctx.restore();
  }
  function drawUtilities(ctx, telemetry, options) {
    const {project,worldScale,time}=options;
    if (!(worldScale>0) || !Number.isFinite(time)) return;
    for(const effect of telemetry.smokes.filter(valid)) drawSmoke(ctx,effect,project,worldScale,time);
    for(const effect of telemetry.fires.filter(valid)) drawFire(ctx,effect,project,worldScale,time);
    for(const effect of telemetry.projectiles.filter(valid)) {
      if(effect.kind==="smoke" && telemetry.smokes.some(s=>Math.hypot(s.x-effect.x,s.y-effect.y,(s.z||0)-(effect.z||0))<2)) continue;
      const points=(effect.trail || []).filter(p=>valid(p)&&Number.isFinite(p.time)&&p.time<=time);
      const p=project(effect);
      ctx.save();ctx.strokeStyle=COLORS[kindOf(effect.kind)] || "#d8e2ed";ctx.lineWidth=1.5;ctx.globalAlpha=.65;
      if(points.length>1) {ctx.beginPath();points.forEach((v,i)=>{const q=project(v);i?ctx.lineTo(q.x,q.y):ctx.moveTo(q.x,q.y);});ctx.stroke();}
      ctx.restore();
      const previous=points.length>1?project(points[points.length-2]):null;
      const angle=previous?Math.atan2(p.y-previous.y,p.x-previous.x)+Math.PI/2:-.3;
      drawGrenade(ctx,p,effect.kind,angle);
    }
    for(const pulse of telemetry.pulses.filter(valid)) {
      if(pulse.age<0 || pulse.time>time) continue;
      const p=project(pulse), duration=pulse.display_duration || 1.15;
      if(pulse.phase==="affected") drawFlashHit(ctx,p,pulse.age,duration);
      else {
        ctx.save();ctx.globalAlpha=clamp(1-pulse.age/duration,0,1);ctx.strokeStyle=COLORS[kindOf(pulse.kind)] || "#fff";ctx.lineWidth=1;
        // The throw origin is an event cue, not a second stationary grenade.
        ctx.beginPath();ctx.arc(p.x,p.y,9+pulse.age*10,0,TAU);ctx.stroke();ctx.restore();
      }
    }
  }
  return {drawUtilities,iconSvg,footprint,SMOKE_RADIUS,FIRE_RADIUS};
});
