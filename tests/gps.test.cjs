const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../index.html'), 'utf8');
const source = html.slice(html.indexOf('function bestFixSingleTap('), html.indexOf('$("captureBtn").addEventListener("click"'));
function gps(accuracyOverride) {
  let now = 100000, success, error, timeout, cleared = false;
  const field = {value: '5'};
  const context = vm.createContext({
    $: () => field, Date: {now: () => now}, setStatus() {},
    GPS_SAMPLE_MS: 16000, GPS_MIN_SAMPLE_MS: 1500, GPS_SINGLE_FIX_SETTLE_MS: 2700,
    GPS_MIN_FIXES: 2, GPS_FRESHNESS_TOLERANCE_MS: 2000,
    setTimeout(fn) {timeout = fn; return 1;}, clearTimeout() {}, setInterval() {return 2;}, clearInterval() {},
    navigator: {geolocation: {watchPosition(ok, fail) {success = ok; error = fail; return 3;}, clearWatch() {cleared = true;}}},
  });
  vm.runInContext(source, context);
  return {promise: vm.runInContext(`bestFixSingleTap(${accuracyOverride ?? ''})`, context), field,
    fix(accuracy, elapsed, timestamp) {now = 100000 + elapsed; success({timestamp: timestamp ?? now, coords: {latitude: -37, longitude: 144, accuracy}});},
    expire() {now = 116000; timeout();}, settle(elapsed=2700) {now = 100000 + elapsed; timeout();},
    deny() {error({code: 1});}, cleared: () => cleared};
}
test('fresh fixes converge and preserve the threshold selected at capture start', async () => {
  const g = gps(); g.fix(4, 0); g.field.value = '3'; g.fix(3.5, 2000);
  const result = await g.promise;
  assert.equal(result.position.coords.accuracy, 3.5); assert.equal(result.sampleCount, 2);
  assert.equal(result.requiredAccuracy, 5); assert.equal(result.durationMs, 2000); assert.ok(g.cleared());
});
test('stale and invalid readings cannot satisfy the gate', async () => {
  const g = gps(); g.fix(1, 0, 90000); g.fix(0, 1000); g.fix(NaN, 2000); g.expire();
  await assert.rejects(g.promise, /No fresh GPS fix/); assert.ok(g.cleared());
});
test('poor accuracy is rejected at the sampling deadline', async () => {
  const g = gps(); g.fix(15, 1000); g.expire();
  await assert.rejects(g.promise, /does not meet/); assert.ok(g.cleared());
});
test('permission denial rejects even after an acceptable sample', async () => {
  const g = gps(); g.fix(3, 1000); g.deny();
  await assert.rejects(g.promise, /permission was denied/); assert.ok(g.cleared());
});

test('street lookup accepts a 20 m fix without weakening the bay threshold', async () => {
  const street = gps(25); street.fix(20, 0); street.fix(20, 4000); street.fix(20, 8000);
  assert.equal((await street.promise).requiredAccuracy, 25);
  const bay = gps(); bay.fix(20, 1000); bay.expire();
  await assert.rejects(bay.promise, /does not meet/);
});

test('one fresh qualifying fix settles quickly without lowering the accuracy threshold', async () => {
  const g = gps(); g.fix(4.8, 1000); g.settle();
  const result = await g.promise;
  assert.equal(result.requiredAccuracy, 5);
  assert.equal(result.position.coords.accuracy, 4.8);
  assert.equal(result.sampleCount, 1);
  assert.equal(result.durationMs, 2700);
});

test('duplicate timestamps cannot fabricate additional GPS fixes', async () => {
  const g = gps(); g.fix(4.5, 0); g.fix(4.3, 2000, 100000); g.settle();
  assert.equal((await g.promise).sampleCount, 1);
});
