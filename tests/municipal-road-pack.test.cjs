const {test} = require("node:test");
const assert = require("node:assert/strict");
require("../local-road-data.js");
require("../municipal-road-pack.js");
const matcher = require("../local-street-lookup.js");

test("reviewed Talbot/Cowper/dead-end block is available offline", () => {
  assert.equal(globalThis.GeoCaptureRoadData.segments.length,147);
  const lat=(-37.80225195908597-37.80188509308594)/2;
  const lng=(144.9039780490001+144.90275580500008)/2;
  const result=matcher.resolve(lat,lng,3,{suburb:"Footscray",postcode:"3011"});
  assert.equal(result.status,"matched");
  assert.equal(result.street,"TALBOT STREET");
  assert.deepEqual(result.between,["COWPER STREET","DEAD END"]);
  assert.equal(result.side,"");
  assert.equal(result.source,"local");
  assert.match(result.attribution.source,/Vicmap/);
});
test("cardinal road side uses independently reviewed Talbot field evidence", () => {
  const lat=(-37.80225195908597-37.80188509308594)/2;
  const lng=(144.9039780490001+144.90275580500008)/2;
  const south=matcher.resolve(lat-0.0000843,lng-0.000040,3,{suburb:"Footscray",postcode:"3011"});
  const north=matcher.resolve(lat+0.0000843,lng+0.000040,3,{suburb:"Footscray",postcode:"3011"});
  assert.equal(south.status,"matched");
  assert.equal(north.status,"matched");
  assert.equal(south.side,"SOUTH");
  assert.equal(north.side,"NORTH");
});
test("recovered geometry does not certify other Footscray road blocks", () => {
  const result=matcher.resolve(-37.8035,144.907,5,{suburb:"Footscray"});
  assert.equal(result.status,"uncovered");
});
test("street-side remains blank for GPS straddling official centreline", () => {
  const result=matcher.resolve(-37.802068526,144.903366927,20);
  assert.equal(result.status,"matched");
  assert.equal(result.side,"");
});

test("a precise fix near the reviewed dead end resolves without inventing junctions", () => {
  const r=matcher.resolve(-37.80190,144.90275,3,{suburb:"Footscray",postcode:"3011"});
  assert.equal(r.status,"matched");
  assert.deepEqual(r.between,["COWPER STREET","DEAD END"]);
  assert.equal(r.side,"");
});
test("a noisy fix at the dead end remains uncertain", () => {
  const r=matcher.resolve(-37.80190,144.90275,22,{suburb:"Footscray",postcode:"3011"});
  assert.equal(r.status,"ambiguous");
});
