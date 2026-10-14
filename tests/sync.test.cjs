const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function fieldApp() {
  const elements = {};
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) {
    elements[id] = {value:'',checked:false,listeners:{},addEventListener(event,fn) {
      (this.listeners[event] ||= []).push(fn);
    }};
  }
  const saved = new Map();
  const writes = [];
  let accuracy = 4;
  const context = vm.createContext({
    document:{getElementById:id => elements[id]},
    localStorage:{getItem:key=>saved.get(key) ?? null,setItem:(key,value)=>saved.set(key,value),
      removeItem:key=>saved.delete(key)},
    crypto:{randomUUID:()=> '9fb6b566-0012-4f32-a025-37e283ba2394'},
    navigator:{onLine:true}, window:{addEventListener(){}}, AbortController,
    setTimeout(fn,ms) {if(ms === 5000) return 999; return setTimeout(fn,ms);},
    clearTimeout(id) {if(id !== 999) clearTimeout(id);},
    fetch:async (url, options={}) => {
      if(url === '/api/segments') {
        return new Promise(resolve => writes.push({payload:JSON.parse(options.body),resolve}));
      }
      if(url === '/health') return {ok:true,json:async()=>({mongoConfigured:true,mongoDatabase:'test',mongoCollection:'road_segments'})};
      return {ok:true,json:async()=>({enabled:true})};
    }
  });
  vm.runInContext(script,context);
  const run = expression => vm.runInContext(expression,context);
  run(`bestFixSingleTap = async () => ({position: {timestamp: Date.now(), coords: {
    latitude:-37.8,longitude:144.9,accuracy:4,altitude:null,altitudeAccuracy:null,heading:null,speed:null
  }},sampleCount:2,durationMs:1600,requiredAccuracy:5})`);
  Object.assign(elements.segment,{value:'TEST STREET'});
  Object.assign(elements.betweenA,{value:'FIRST ROAD'});
  Object.assign(elements.betweenB,{value:'LAST ROAD'});
  Object.assign(elements.side,{value:'NORTH'});
  Object.assign(elements.startBay,{value:'1'});
  Object.assign(elements.direction,{value:'1'});
  Object.assign(elements.requiredAccuracy,{value:'5'});
  return {saved, elements, writes, run,
    async click(id) {for(const fn of elements[id].listeners.click || []) await fn();},
    finishWrite(i,ok=true) {writes[i].resolve({ok,json:async()=> ok
      ? {revision:writes[i].payload.revision,pointCount:writes[i].payload.bays.length}
      : {error:'offline'}});}
  };
}

test('next bay captures while previous MongoDB write is unresolved; latest revision wins', async () => {
  const a = fieldApp();
  await a.click('captureBtn');
  assert.equal(a.run('points.length'),1);
  assert.equal(a.elements.captureBtn.disabled,false);
  assert.equal(a.writes.length,1);
  await a.click('captureBtn');
  assert.equal(a.run('points.length'),2);
  assert.equal(a.elements.captureBtn.disabled,false);
  // Only one network writer at a time; newer revision remains durable locally.
  assert.equal(a.writes.length,1);
  assert.equal(JSON.parse(a.saved.get('civicmaps_pending_segment')).revision,2);
  a.finishWrite(0);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.writes.length,2);
  assert.equal(a.writes[1].payload.bays.length,2);
  a.finishWrite(1);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.saved.has('civicmaps_pending_segment'),false);
});

test('failed database write leaves captured bays and newest pending snapshot intact',async () => {
  const a = fieldApp();
  await a.click('captureBtn');
  a.finishWrite(0,false);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.run('points.length'),1);
  assert.equal(JSON.parse(a.saved.get('civicmaps_pending_segment')).bays.length,1);
  assert.equal(a.elements.captureBtn.disabled,false);
  assert.match(a.elements.storageStatus.textContent,/local copy queued/);
});

test('undoing the last bay queues an empty revision so MongoDB cannot retain it',async () => {
  const a = fieldApp();
  await a.click('captureBtn');
  a.finishWrite(0);
  await new Promise(resolve=>setImmediate(resolve));
  await a.click('undoBtn');
  assert.equal(a.run('points.length'),0);
  assert.equal(a.writes[1].payload.bays.length,0);
  assert.equal(a.writes[1].payload.revision,2);
  a.finishWrite(1);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.saved.has('civicmaps_pending_segment'),false);
});
