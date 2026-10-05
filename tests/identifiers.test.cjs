const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function app(form) {
  const elements = {};
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) {
    elements[id] = {value: '', checked: false, listeners: {}, addEventListener(event, callback) {
      this.listeners[event] = callback;
    }};
  }
  const saved = new Map(form ? [['civicmaps_form', JSON.stringify(form)]] : []);
  const context = vm.createContext({
    document: {getElementById: id => elements[id]},
    localStorage: {getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value), removeItem: key => saved.delete(key)},
    crypto: {randomUUID: () => '9fb6b566-0012-4f32-a025-37e283ba2394'},
    navigator: {}, window: {addEventListener() {}}, setTimeout() {}, clearTimeout() {},
    fetch: async () => ({json: async () => ({mongoConfigured: false})}),
  });
  vm.runInContext(script, context);
  for (const [id, value] of Object.entries({segment: 'TALBOT STREET', betweenA: 'COWPER STREET', betweenB: 'DEAD END', side: 'NORTH', startBay: '1', direction: '1'})) {
    elements[id].value = value;
  }
  return {
    elements, saved,
    run: code => vm.runInContext(code, context),
    payload: () => JSON.parse(vm.runInContext('JSON.stringify(buildPayload())', context)),
    toggle(id, checked) {elements[id].checked = checked; elements[id].listeners.change();},
  };
}

test('area or permit alone accepts alphabetic identifiers and leading zeroes', () => {
  for (const [id, key, value] of [['area', 'parkingAreaNumber', 'MCC-TA'], ['permit', 'permitNumber', 'MCC-TA01'], ['area', 'parkingAreaNumber', '02']]) {
    const a = app(); a.elements[id].value = value;
    const p = a.payload();
    assert.equal(p.segment[key], value);
    assert.equal(p.segment.paymentRequired, false);
    assert.equal(p.segment.easyParkNumber, null);
  }
});

test('no identifiers, including whitespace, block capture and export', async () => {
  const a = app(); a.elements.area.value = '  '; a.elements.permit.value = ' ';
  assert.throws(a.payload, /at least one/);
  await a.elements.captureBtn.listeners.click();
  assert.match(a.elements.status.textContent, /at least one/);
  await a.elements.copyBtn.listeners.click();
  assert.match(a.elements.status.textContent, /at least one/);
  a.elements.downloadBtn.listeners.click();
  assert.match(a.elements.status.textContent, /at least one/);
});

test('payment-only prefixes and provider switching are consistent', () => {
  const a = app(); a.elements.easypark.value = '7093';
  a.toggle('easyparkEnabled', true);
  assert.equal(a.payload().segment.easyParkNumber, 'EP-7093');
  a.toggle('paystayEnabled', true);
  assert.equal(a.elements.easyparkEnabled.checked, false);
  assert.equal(a.payload().segment.payStayNumber, 'PS-7093');
  assert.equal(a.payload().segment.easyParkNumber, null);
  a.elements.easypark.value = 'EP-007093';
  assert.equal(a.payload().segment.paymentAreaNumber, 'PS-007093');
  a.elements.easypark.value = 'EP-EP-7093';
  assert.throws(a.payload, /numeric/);
});

test('both off omit retained payment draft and remain off after reload', () => {
  const a = app(); a.elements.area.value = 'MCC-TA'; a.elements.easypark.value = 'EP-7093';
  a.toggle('easyparkEnabled', true); a.toggle('easyparkEnabled', false);
  assert.equal(a.payload().segment.paymentProvider, null);
  const b = app(JSON.parse(a.saved.get('civicmaps_form')));
  assert.equal(b.payload().segment.paymentAreaNumber, null);
  assert.equal(b.elements.easypark.disabled, true);
  assert.equal(b.elements.easypark.value, 'EP-7093');
});

test('empty optional payment field does not block an area-only record', () => {
  const a = app(); a.elements.area.value = 'MCC-TA'; a.toggle('easyparkEnabled', true);
  assert.equal(a.payload().segment.paymentAreaNumber, null);
});

test('unnumbered permits work without disabling identifiers', () => {
  const a = app(); a.elements.permit.value = 'MCC-TA'; a.toggle('unnumbered', true);
  assert.equal(a.payload().segment.numberingMode, 'unnumbered');
  assert.equal(a.elements.area.disabled, undefined);
  assert.equal(a.elements.startBay.disabled, true);
});

test('legacy shared number is preserved until provider reviewed', () => {
  const a = app({area: '02', easypark: '02'});
  assert.throws(a.payload, /saved payment number/);
  a.run('saveForm()');
  const b = app(JSON.parse(a.saved.get('civicmaps_form')));
  assert.throws(b.payload, /saved payment number/);
  b.elements.confirmNoProvider.listeners.click();
  b.elements.area.value = 'MCC-TA';
  assert.equal(b.payload().segment.parkingAreaNumber, 'MCC-TA');
  assert.equal(b.payload().segment.paymentAreaNumber, null);
  a.toggle('paystayEnabled', true);
  assert.equal(a.payload().segment.payStayNumber, 'PS-02');
});

test('form round trip retains permit and provider', () => {
  const a = app(); a.elements.permit.value = 'MCC-TA'; a.elements.easypark.value = '7093';
  a.toggle('easyparkEnabled', true);
  const b = app(JSON.parse(a.saved.get('civicmaps_form')));
  assert.equal(b.payload().segment.permitNumber, 'MCC-TA');
  assert.equal(b.payload().segment.paymentAreaNumber, 'EP-7093');
});
