/* Run with: node web/app.test.cjs. No browser or third-party modules required. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const telemetry = require("./telemetry.js");
const effects = require("./effects.js");
const motion = require("./motion.js");

const source = fs.readFileSync(path.join(__dirname, "app.js"), "utf8").replace(/initialize\(\);\s*$/, "");
function createViewer() {
  const context = vm.createContext({ document: { getElementById: () => null }, console, IGLTelemetry: telemetry, IGLEffects: effects, IGLMotion: motion });
  vm.runInContext(source, context);
  return (code) => vm.runInContext(code, context);
}
test("Hammer coordinates project with Y inversion and viewport scaling", () => {
  const run = createViewer();
  run("state.map = {pos_x:-2476,pos_y:3239,scale:4.4}");
  const result = run("project({x:-2036,y:2359},{left:10,top:20,scale:0.5})");
  assert.ok(Math.abs(result.x - 60) < 1e-9);
  assert.ok(Math.abs(result.y - 120) < 1e-9);
});
test("world origin maps exactly to radar origin", () => {
  const run = createViewer();
  run("state.map = {pos_x:-2476,pos_y:3239,scale:4.4}");
  const result = run("project({x:-2476,y:3239},{left:31,top:72,scale:0.8})");
  assert.equal(result.x, 31);
  assert.equal(result.y, 72);
});
test("playback interpolates position and takes the shortest yaw arc", () => {
  const run = createViewer();
  run(`state.match={rounds:[{frames:[
    {time:10,players:[{id:'a',team:'T',x:0,y:0,yaw:350,hp:100,alive:true}]},
    {time:11,players:[{id:'a',team:'T',x:100,y:50,yaw:10,hp:100,alive:true}]}
  ]}]}; state.playing=true; state.playbackTime=10.5;`);
  const result = run("interpolatedPlayers()[0]");
  assert.equal(result.x, 50);
  assert.equal(result.y, 25);
  assert.equal(result.yaw % 360, 0);
});
test("playback does not interpolate across deaths or teleports", () => {
  const run = createViewer();
  run(`state.match={rounds:[{frames:[
    {time:0,players:[{id:'a',x:0,y:0,hp:100}]},
    {time:1,players:[{id:'a',x:100,y:50,hp:0,alive:false}]}
  ]}]}; state.playing=true; state.playbackTime=0.5;`);
  assert.equal(run("interpolatedPlayers()[0].x"), 0);
  run("state.match.rounds[0].frames[1].players[0]={id:'a',x:1000,y:0,hp:100}");
  assert.equal(run("interpolatedPlayers()[0].x"), 0);
});
test("friendly-only perspective excludes opponent markers", () => {
  const run = createViewer();
  run("state.perspective='T'");
  assert.equal(run("visiblePlayer({team:'T'})"), true);
  assert.equal(run("visiblePlayer({team:'CT'})"), false);
  run("state.perspective='all'");
  assert.equal(run("visiblePlayer({team:'CT'})"), true);
});
test("malformed and non-monotonic replays fail explicitly", () => {
  const run = createViewer();
  assert.throws(() => run("validateReplay({rounds:[]})"), /no rounds/);
  assert.throws(() => run("validateReplay({rounds:[{frames:[{time:2,players:[]},{time:1,players:[]}]}]})"), /out of order/);
  assert.throws(() => run("validateReplay({rounds:[{frames:[{time:null,players:[]}]}]})"), /timestamps/);
  assert.throws(() => run("validateReplay({rounds:[{frames:[{time:1,players:null}]}]})"), /player data/);
});
test("clock and HTML escaping handle untrusted demo labels", () => {
  const run = createViewer();
  assert.equal(run("clock(65.25,true)"), "01:05.2");
  assert.equal(run("clock(null)"), "—:—");
  assert.equal(run("clock(-1)"), "00:00");
  assert.equal(run("escapeHtml('<script>\"&')"), "&lt;script&gt;&quot;&amp;");
});

test("roster exposes double flashes and distinguishes unknown inventory from zero", () => {
  const run = createViewer();
  const html = run(`inventoryHtml({hp:100, inventory:[{weaponName:'Flashbang', ammoInMagazine:1, ammoInReserve:1}]})`);
  assert.match(html, /Flash: 2/);
  assert.match(html, /Smoke: 0/);
  assert.match(html, /2 util/);
  assert.match(run("inventoryHtml({hp:100,inventory:null})"), /Utility unknown/);
  run("state.simulated=true");
  assert.match(run("inventoryHtml({hp:100,inventory:[]})"), /not simulated/);
});

function identityFixture(matchId = "identity-match") {
  const players = Array.from({ length: 10 }, (_, index) => ({
    id: String(76561198000000000n + BigInt(index)), name: `Player ${index + 1}`,
    team: index < 5 ? "T" : "CT", hp: 100, alive: true, x: index * 10, y: 0,
  }));
  return { match_id: matchId, rounds: [
    { number: 1, frames: [
      { time: 0, players: players.slice().reverse() },
      { time: 1, players: [players[8], players[2], { ...players[0], hp: 0, alive: false }, players[6], players[4]] },
      { time: 2, players: [...players.slice(3), ...players.slice(0, 3)] },
    ] },
    { number: 16, frames: [{ time: 0, players: players.slice().reverse().map((player) => ({ ...player, team: player.team === "T" ? "CT" : "T" })) }] },
  ] };
}

test("match IDs are unique and stable when player arrays are shuffled", () => {
  const run = createViewer();
  const fixture = identityFixture();
  run(`state.match=${JSON.stringify(fixture)}; setPlayerIdentity(state.match);`);
  const byId = run("JSON.stringify([...state.playerNumbers].sort((a,b)=>a[0]<b[0]?-1:1))");
  assert.deepEqual(JSON.parse(byId).map((entry) => entry[1]), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  fixture.rounds.forEach((round) => round.frames.forEach((frame) => frame.players.reverse()));
  run(`state.match=${JSON.stringify(fixture)}; setPlayerIdentity(state.match);`);
  assert.equal(run("JSON.stringify([...state.playerNumbers].sort((a,b)=>a[0]<b[0]?-1:1))"), byId);
});

test("death, absence, seeking, and side swaps never renumber a player", () => {
  const run = createViewer();
  run(`state.match=${JSON.stringify(identityFixture())}; setPlayerIdentity(state.match);`);
  const firstId = "76561198000000000";
  run("state.frameIndex=1");
  assert.equal(run(`playerOrder(currentFrame().players.find(p=>p.id==='${firstId}'))`), 1);
  assert.equal(run("JSON.stringify(orderedTeamPlayers('T', currentFrame().players).map(playerOrder))"), "[1,3,5]");
  run("state.frameIndex=2");
  assert.equal(run("JSON.stringify(orderedTeamPlayers('CT', currentFrame().players).map(playerOrder))"), "[6,7,8,9,10]");
  run("state.roundIndex=1;state.frameIndex=0");
  assert.equal(run("JSON.stringify(orderedTeamPlayers('CT', currentFrame().players).map(playerOrder))"), "[1,2,3,4,5]");
  assert.equal(run("JSON.stringify(orderedTeamPlayers('T', currentFrame().players).map(playerOrder))"), "[6,7,8,9,10]");
  run("state.roundIndex=0;state.frameIndex=0");
  assert.equal(run(`playerOrder(currentFrame().players.find(p=>p.id==='${firstId}'))`), 1);
});

test("distinct SteamID strings above 2^53 retain distinct identities", () => {
  const run = createViewer();
  assert.equal(Number("76561198000000000"), Number("76561198000000001"));
  run(`state.match=${JSON.stringify(identityFixture())}; setPlayerIdentity(state.match);`);
  assert.equal(run("playerOrder({id:'76561198000000000'})"), 1);
  assert.equal(run("playerOrder({id:'76561198000000001'})"), 2);
  assert.equal(run("state.playerNumbers.size"), 10);
});

test("switching matches resets initial-side numbering without leaking the previous match", () => {
  const run = createViewer();
  const first = identityFixture("match-one");
  const second = identityFixture("match-two");
  second.rounds = second.rounds.slice(1);
  run(`state.match=${JSON.stringify(first)};setPlayerIdentity(state.match);`);
  assert.equal(run("playerOrder({id:'76561198000000005'})"), 6);
  run(`state.match=${JSON.stringify(second)};setPlayerIdentity(state.match);`);
  assert.equal(run("playerOrder({id:'76561198000000005'})"), 1);
  assert.equal(run("playerOrder({id:'76561198000000000'})"), 6);
  run(`state.match=${JSON.stringify(first)};setPlayerIdentity(state.match);`);
  assert.equal(run("playerOrder({id:'76561198000000005'})"), 6);
});

test("subset simulation branches inherit original identities and preserve them on return", () => {
  const run = createViewer();
  const original = identityFixture();
  const survivors = original.rounds[0].frames[0].players.filter((player) => ["76561198000000003", "76561198000000009"].includes(player.id));
  const branch = { match_id: "branch", source: { scenario_match_id: original.match_id }, rounds: [{ number: 8, frames: [{ time: 0, players: survivors }] }] };
  run(`state.match=${JSON.stringify(original)};setPlayerIdentity(state.match);state.recording={match:state.match};`);
  run(`state.match=${JSON.stringify(branch)};state.simulated=true;setPlayerIdentity(state.match,true);`);
  assert.equal(run("playerOrder({id:'76561198000000003'})"), 4);
  assert.equal(run("playerOrder({id:'76561198000000009'})"), 10);
  run("state.match=state.recording.match;state.recording=null;state.simulated=false;setPlayerIdentity(state.match);");
  assert.equal(run("playerOrder({id:'76561198000000003'})"), 4);
  run(`state.match=${JSON.stringify(branch)};state.simulated=true;setPlayerIdentity(state.match,true);`);
  assert.equal(run("playerOrder({id:'76561198000000009'})"), 10);
});

test("roster and dead map markers display the same persistent number", () => {
  const run = createViewer();
  run(`state.match=${JSON.stringify(identityFixture())};setPlayerIdentity(state.match);state.frameIndex=1;
    globalThis.rosterElements={tRoster:{innerHTML:'',querySelectorAll:()=>[]},tHealth:{textContent:''}};
    document.getElementById=(id)=>rosterElements[id];
    inventoryHtml=()=>'';
    renderRoster('T',currentFrame().players);`);
  const html = run("rosterElements.tRoster.innerHTML");
  assert.deepEqual([...html.matchAll(/class="player-number">(\d+)</g)].map((match) => Number(match[1])), [1, 3, 5]);
  assert.match(html, /player-card t dead/);
  assert.match(html, /Inspect player 1, Player 1, dead/);
  run(`globalThis.drawnLabels=[];
    const markerContext={beginPath(){},arc(){},fill(){},stroke(){},fillText(text){drawnLabels.push(text)}};
    state.map={pos_x:0,pos_y:0,scale:1};
    drawPlayer(markerContext,currentFrame().players.find(p=>p.id==='76561198000000000'),{left:0,top:0,scale:1,width:600});`);
  assert.equal(run("JSON.stringify(drawnLabels)"), '["1","×"]');
});

function fractionalPlayback() {
  const run=createViewer();
  run(`state.match={source:{},rounds:[{events:[{type:'weapon_fire',time:10.1,weaponClass:'Rifle',weapon:'AK-47',playerX:0,playerY:0,playerZ:0}],frames:[10,10.5,11].map((time,i)=>({time,tick:time*100,
    players:[{id:'p',team:'T',hp:100,x:i*100,y:0,z:0,yaw:0}],
    bomb:{state:'carried',carrier_id:'p'},
    utility:{smokes:[],fires:[],projectiles:[{entity_id:'g',projectileType:'Flashbang',x:20+i*60,y:0,z:10}]}}))}]};
    globalThis.controls={playBtn:{disabled:false,setAttribute(){}},speedSelect:{value:'2'}};
    document.getElementById=id=>controls[id];setControls=()=>{};
    state.playbackTime=10.25;state.playing=true;`);
  return run;
}
test('pause and resume preserve fractional player, grenade and shot state',()=>{
  const run=fractionalPlayback();
  const before=run('JSON.stringify({time:displayTime(),players:interpolatedPlayers(),telemetry:currentTelemetry()})');
  assert.equal(run('currentTelemetry().projectiles[0].x'),50);
  run('stop()');
  assert.equal(run('JSON.stringify({time:displayTime(),players:interpolatedPlayers(),telemetry:currentTelemetry()})'),before);
  run('togglePlayback()');
  assert.equal(run('state.playbackTime'),10.25);
  assert.equal(run('JSON.stringify({time:displayTime(),players:interpolatedPlayers(),telemetry:currentTelemetry()})'),before);
});
test('playback speed advances the shared clock and end-of-round clamps it',()=>{
  const run=fractionalPlayback();
  run('drawMap=()=>{};renderTimeline=()=>{};renderDetails=()=>{};globalThis.requestAnimationFrame=()=>{};state.previousAnimation=1000;animate(1100)');
  assert.ok(Math.abs(run('displayTime()')-10.45)<1e-9);
  run('state.playbackTime=10.95;state.frameIndex=1;animate(1200)');
  assert.equal(run('displayTime()'),11);
  assert.equal(run('state.playbackTime'),11);
  assert.equal(run('state.playing'),false);
});
test('carried bomb follows its interpolated player while dropped bomb stays recorded',()=>{
  const run=fractionalPlayback();
  run(`state.map={pos_x:0,pos_y:0,scale:1};globalThis.bombTranslations=[];
    globalThis.bombContext={save(){},restore(){},translate(x,y){bombTranslations.push([x,y]);},rotate(){},fillRect(){},strokeRect(){}};
    drawBomb(bombContext,{left:0,top:0,scale:1});`);
  assert.equal(run('JSON.stringify(bombTranslations[0])'),'[61,-10]');
  run(`currentFrame().bomb={state:'dropped',x:7,y:8};drawBomb(bombContext,{left:0,top:0,scale:1});`);
  assert.equal(run('JSON.stringify(bombTranslations[1])'),'[7,-8]');
});
