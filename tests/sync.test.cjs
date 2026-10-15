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
  let idSequence = 0;
  let accuracy = 4;
  const context = vm.createContext({
    document:{getElementById:id => elements[id]},
    localStorage:{getItem:key=>saved.get(key) ?? null,setItem:(key,value)=>saved.set(key,value),
      removeItem:key=>saved.delete(key)},
    crypto:{randomUUID:()=> '9fb6b566-0012-4f32-a025-' + String(++idSequence).padStart(12, '0')},
    confirm:()=>true,
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


test('segment completion locally preserves the previous revision while the next street is captured', async () => {
  const a=fieldApp();
  await a.click('captureBtn');
  assert.equal(a.writes.length,1);
  const firstId=a.writes[0].payload.segmentId;
  // MongoDB deliberately does not answer before completing the street.
  await a.click('clearBtn');
  assert.equal(a.run('points.length'),0);
  assert.equal(a.elements.clearBtn.disabled,false);
  const firstQueue=JSON.parse(a.saved.get('civicmaps_pending_segments_v1'));
  assert.equal(JSON.parse(firstQueue[firstId]).storageState,'complete');
  assert.equal(JSON.parse(firstQueue[firstId]).revision,2);

  a.elements.segment.value='SECOND STREET';
  a.elements.betweenA.value='THIRD ROAD';
  a.elements.betweenB.value='FOURTH ROAD';
  a.elements.side.value='SOUTH';
  await a.click('captureBtn');
  assert.equal(a.run('points.length'),1);
  assert.equal(a.elements.captureBtn.disabled,false);
  const queued=JSON.parse(a.saved.get('civicmaps_pending_segments_v1'));
  const ids=Object.keys(queued);
  assert.equal(ids.length,2,'completed street must remain queued alongside new street');
  const secondId=ids.find(id=>id!==firstId);
  assert.ok(secondId);
  assert.equal(JSON.parse(queued[secondId]).bays.length,1);
  assert.equal(a.writes.length,1,'MongoDB cannot block the second bay');

  a.finishWrite(0);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.writes[1].payload.segmentId,firstId);
  assert.equal(a.writes[1].payload.storageState,'complete');
  a.finishWrite(1);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.writes[2].payload.segmentId,secondId);
  a.finishWrite(2);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.saved.has('civicmaps_pending_segments_v1'),false);
  assert.equal(a.saved.has('civicmaps_pending_segment'),false);
});

test('offline completed street and next street both survive and resynchronise after reconnect', async () => {
  const a=fieldApp();
  a.run('navigator.onLine = false');
  await a.click('captureBtn');
  await a.click('clearBtn');
  a.elements.segment.value='NEXT STREET';
  a.elements.betweenA.value='THIRD ROAD';
  a.elements.betweenB.value='FOURTH ROAD';
  a.elements.side.value='WEST';
  await a.click('captureBtn');
  assert.equal(a.writes.length,0,'offline captures must not issue MongoDB requests');
  assert.equal(Object.keys(JSON.parse(a.saved.get('civicmaps_pending_segments_v1'))).length,2);
  a.run('navigator.onLine = true; void flushSegmentQueue()');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.writes.length,1);
  a.finishWrite(0);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.writes.length,2);
  a.finishWrite(1);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.saved.has('civicmaps_pending_segments_v1'),false);
});

test('localStorage quota failure does not accept or number an uncommitted bay', async () => {
  const a=fieldApp();
  a.run(`(() => {
    const original = localStorage.setItem;
    let failOnce = true;
    localStorage.setItem = function(key, value) {
      if (key === 'civicmaps_points' && JSON.parse(value).length === 1 && failOnce) {
        failOnce = false;
        throw new Error('QuotaExceededError');
      }
      return original.call(this,key,value);
    };
  })()`);
  await a.click('captureBtn');
  assert.equal(a.run('points.length'),0,'failed write must roll back in-memory bay');
  assert.equal(a.elements.count.textContent,0,'failed capture must not update visible count');
  assert.match(a.elements.status.textContent,/Bay not saved/);
  assert.equal(a.writes.length,0,'failed local commit must not post to MongoDB');
  assert.equal(a.elements.captureBtn.disabled,false);
  await a.click('captureBtn');
  assert.equal(a.run('points.length'),1,'retry can commit same bay after quota pressure lifts');
  assert.equal(a.writes[0].payload.bays[0].bay,1,'bay numbering must not skip failed attempt');
  a.finishWrite(0);
  await new Promise(resolve=>setImmediate(resolve));
});

test('failed local undo preserves the last bay and prevents destructive sync', async () => {
  const a=fieldApp();
  await a.click('captureBtn');
  const saved = a.saved.get('civicmaps_points');
  a.run(`(() => {
    const original = localStorage.setItem;
    let failOnce = true;
    localStorage.setItem = function(key, value) {
      if (key === 'civicmaps_points' && JSON.parse(value).length === 0 && failOnce) {
        failOnce = false;
        throw new Error('QuotaExceededError');
      }
      return original.call(this,key,value);
    };
  })()`);
  await a.click('undoBtn');
  assert.equal(a.run('points.length'),1,'failed undo must restore the in-memory bay');
  assert.equal(a.saved.get('civicmaps_points'),saved,'durable bay data must remain unchanged');
  assert.match(a.elements.status.textContent,/Undo not saved/);
  assert.equal(a.writes.length,1,'no uncommitted destructive revision may be sent');
  a.finishWrite(0);
  await new Promise(resolve=>setImmediate(resolve));
});
