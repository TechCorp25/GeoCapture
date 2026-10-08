const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const suggestion = {street:'TALBOT STREET', between:['COWPER STREET','DEAD END'], warnings:[], candidates:[],
  attribution:{source:'OpenStreetMap', license:'ODbL-1.0'}, googleReference:'Google test street'};

function app() {
  const elements = {};
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) {
    elements[id] = {value:'', checked:false, listeners:{}, addEventListener(event, fn) {
      (this.listeners[event] ||= []).push(fn);
    }};
  }
  const saved = new Map();
  let answer = async () => suggestion;
  let requested = 0;
  const context = vm.createContext({
    document:{getElementById:id => elements[id]},
    localStorage:{getItem:key => saved.get(key) ?? null, setItem:(key,val) => saved.set(key,val), removeItem:key => saved.delete(key)},
    crypto:{randomUUID:() => '9fb6b566-0012-4f32-a025-37e283ba2394'},
    navigator:{onLine:true}, window:{addEventListener() {}},
    setTimeout, clearTimeout, AbortController,
    fetch:async url => {
      if (url === '/api/location/suggest') {
        requested++;
        return {ok:true, json:answer};
      }
      return {ok:true, json:async () => ({enabled:true, mongoConfigured:false})};
    },
  });
  vm.runInContext(script, context);
  const run = code => vm.runInContext(code, context);
  run('bestFixSingleTap = async () => ({position:{timestamp:Date.now(),coords:{latitude:-37.8,longitude:144.9,accuracy:4}}})');
  return {elements, saved, run, requested:() => requested,
    answer(fn) {answer = fn;},
    async fire(id, event) {for (const fn of elements[id].listeners[event] || []) await fn();},
    lookup:() => run('autoFillLocation()'),
    async input(id, value) {elements[id].value = value; for (const fn of elements[id].listeners.input || []) await fn();},
  };
}

test('one tap fills street and boundaries, all remain editable, Google never persists', async () => {
  const a = app(); await a.lookup();
  assert.equal(a.elements.segment.value, 'TALBOT STREET');
  assert.equal(a.elements.betweenA.value, 'COWPER STREET');
  assert.equal(a.elements.betweenB.value, 'DEAD END');
  assert.equal(a.elements.segment.disabled, undefined);
  assert.equal(a.elements.googleReference.hidden, false);
  assert.ok(!a.saved.get('civicmaps_form').includes('Google test street'));
  await a.input('betweenB', 'FOOTSCRAY ROAD');
  assert.equal(JSON.parse(a.saved.get('civicmaps_form')).betweenB, 'FOOTSCRAY ROAD');
  a.elements.side.value = 'SOUTH'; a.elements.area.value = 'TA'; a.elements.startBay.value = '1';
  const payload = a.run('JSON.stringify(buildPayload())');
  assert.ok(payload.includes('OpenStreetMap'));
  assert.ok(!payload.includes('Google test street'));
});

test('manual existing fields are kept and boundary order aligns with retained A', async () => {
  const a = app(); a.elements.segment.value = 'Talbot Street'; a.elements.betweenA.value = 'DEAD END';
  await a.lookup();
  assert.equal(a.elements.segment.value, 'Talbot Street');
  assert.equal(a.elements.betweenA.value, 'DEAD END');
  assert.equal(a.elements.betweenB.value, 'COWPER STREET');
});

test('a conflicting retained boundary prevents inserting an unrelated second boundary', async () => {
  const a = app(); a.elements.betweenA.value = 'OTHER ROAD'; await a.lookup();
  assert.equal(a.elements.betweenA.value, 'OTHER ROAD');
  assert.equal(a.elements.betweenB.value, '');
  assert.match(a.elements.locationStatus.textContent, /differ/);
});

test('changing the street clears automatic boundaries but keeps manual overrides', async () => {
  const a = app(); await a.lookup();
  await a.input('betweenB', 'CUSTOM BOUNDARY');
  await a.input('segment', 'NEW STREET');
  assert.equal(a.elements.betweenA.value, '');
  assert.equal(a.elements.betweenB.value, 'CUSTOM BOUNDARY');
});

test('street change looks up blank boundaries using the recent GPS fix', async () => {
  const a = app(); await a.lookup();
  a.run('bestFixSingleTap = async () => {throw new Error("must reuse recent fix")};');
  a.answer(async () => ({...suggestion, street:'NEW STREET', between:['FIRST ROAD','LAST ROAD']}));
  await a.input('segment', 'NEW STREET');
  await a.fire('segment', 'change');
  // The event deliberately starts asynchronous work without blocking UI input.
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(a.elements.betweenA.value, 'FIRST ROAD');
  assert.equal(a.requested(), 2);
});

test('edits during delayed provider response are never overwritten, including a cleared field', async () => {
  const a = app(); let resolve, started;
  const pending = new Promise(r => started = r);
  a.answer(() => {started(); return new Promise(r => resolve = r);});
  const lookup = a.lookup(); await pending;
  await a.input('betweenA', 'MY STREET'); await a.input('betweenA', '');
  resolve(suggestion); await lookup;
  assert.equal(a.elements.segment.value, '');
  assert.equal(a.elements.betweenA.value, '');
  assert.match(a.elements.locationStatus.textContent, /Fields changed/);
});

test('new segment identity discards a late response', async () => {
  const a = app(); let resolve, started;
  const pending = new Promise(r => started = r);
  a.answer(() => {started(); return new Promise(r => resolve = r);});
  const lookup = a.lookup(); await pending;
  a.run('segmentId = "another-segment"');
  resolve(suggestion); await lookup;
  assert.equal(a.elements.segment.value, '');
});

test('offline, GPS denial and network failure retain entries and restore buttons', async () => {
  for (const mode of ['offline','denied','network']) {
    const a = app(); a.elements.segment.value = 'RETAIN ME';
    if (mode === 'offline') a.run('navigator.onLine = false');
    if (mode === 'denied') a.run('bestFixSingleTap = async () => {throw new Error("Location permission denied")};');
    if (mode === 'network') a.answer(async () => {throw new Error('Provider unavailable');});
    await a.lookup();
    assert.equal(a.elements.segment.value, 'RETAIN ME');
    assert.ok(!a.elements.captureBtn.disabled);
    assert.ok(!a.elements.locateStreetBtn.disabled);
    assert.equal(a.run('points.length'), 0);
  }
});

test('active segments and ambiguous lookups do not acquire metadata accidentally', async () => {
  const a = app(); a.run('points = [{latitude:1}]'); await a.lookup();
  assert.equal(a.requested(), 0);
  a.run('points = []');
  a.answer(async () => ({...suggestion, street:null, between:[null,null], candidates:['FIRST ROAD','SECOND ROAD'], warnings:['Ambiguous']}));
  await a.lookup();
  assert.equal(a.elements.segment.value, '');
  assert.equal(a.elements.betweenB.value, '');
  assert.match(a.elements.locationStatus.textContent, /Nearby streets/);
});
