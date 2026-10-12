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
    GPS_SAMPLE_MS: 30000, GPS_MIN_SAMPLE_MS: 8000, GPS_MIN_FIXES: 3, GPS_FRESHNESS_TOLERANCE_MS: 2000,
    setTimeout(fn) {timeout = fn; return 1;}, clearTimeout() {}, setInterval() {return 2;}, clearInterval() {},
    navigator: {geolocation: {watchPosition(ok, fail) {success = ok; error = fail; return 3;}, clearWatch() {cleared = true;}}},
  });
  vm.runInContext(source, context);
  return {promise: vm.runInContext(`bestFixSingleTap(${accuracyOverride ?? ''})`, context), field,
    fix(accuracy, elapsed, timestamp) {now = 100000 + elapsed; success({timestamp: timestamp ?? now, coords: {latitude: -37, longitude: 144, accuracy}});},
    expire() {now = 130000; timeout();}, deny() {error({code: 1});}, cleared: () => cleared};
}
test('fresh fixes converge and preserve the threshold selected at capture start', async () => {
  const g = gps(); g.fix(4, 0); g.field.value = '3'; g.fix(3.5, 4000); g.fix(4.5, 8000);
  const result = await g.promise;
  assert.equal(result.position.coords.accuracy, 3.5); assert.equal(result.sampleCount, 3);
  assert.equal(result.requiredAccuracy, 5); assert.equal(result.durationMs, 8000); assert.ok(g.cleared());
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
