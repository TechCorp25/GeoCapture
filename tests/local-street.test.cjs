const {test} = require("node:test");
const assert = require("node:assert/strict");
const {performance} = require("node:perf_hooks");
require("../local-road-data.js");
const local = require("../local-street-lookup.js");
const cbd = globalThis.GeoCaptureRoadData;
const resolve = (lat,lng,accuracy=5,opts={}) => local.resolve(lat,lng,accuracy,opts);

test("historical April CBD geometry packaged with named between streets", () => {
  const match = local.createResolver(cbd);
  assert.equal(match.segmentCount, 146);
  const a = resolve(-37.810807, 144.961586, 5, {suburb:"Melbourne",postcode:"3000"});
  assert.equal(a.status,"matched");
  assert.equal(a.street,"ELIZABETH STREET");
  assert.deepEqual(a.between,["LITTLE LONSDALE STREET","LA TROBE STREET"]);
  assert.equal(a.side,""); // close to GPS centreline: do not invent side
  assert.equal(a.source,"local");
  assert.equal(a.distance < 3,true);
});
test("side of street follows historic cardinal direction when offset is decisive", () => {
  const west = resolve(-37.810807,144.961386,5);
  const east = resolve(-37.810807,144.961786,5);
  assert.equal(west.status,"matched");
  assert.equal(east.status,"matched");
  assert.equal(west.side,"WEST");
  assert.equal(east.side,"EAST");
});
test("near junction ambiguity is not silently assigned a block", () => {
  const result = resolve(-37.8103112,144.9613574,5);
  assert.equal(result.status,"ambiguous");
});
test("never hallucinate unknown Footscray boundaries from CBD data", () => {
  assert.equal(resolve(-37.80205275,144.90327245,5,{suburb:"Footscray", postcode:"3011"}).status,"uncovered");
});
test("wrong entered street, locality, postcode and bad GPS cannot create a local match", () => {
  const lat=-37.810807, lon=144.961586;
  assert.equal(resolve(lat,lon,5,{street:"TALBOT STREET"}).status,"uncovered");
  assert.equal(resolve(lat,lon,5,{suburb:"FOOTSCRAY"}).status,"uncovered");
  assert.equal(resolve(lat,lon,5,{postcode:"3011"}).status,"uncovered");
  assert.equal(resolve(NaN,lon,5).status,"invalid");
  assert.equal(resolve(lat,lon,0).status,"invalid");
});
test("synthetic intersecting roads within GPS ambiguity must not pick nearest arbitrarily", () => {
  const data={version:"test",segments:[
    {id:"A",street:"ALPHA STREET",from:"FIRST",to:"SECOND",a:[-.001,0],b:[.001,0],positive:"WEST",negative:"EAST"},
    {id:"B",street:"BRAVO STREET",from:"THIRD",to:"FOURTH",a:[0,-.001],b:[0,.001],positive:"SOUTH",negative:"NORTH"}
  ]};
  assert.equal(local.createResolver(data).resolve(0,0,5).status,"ambiguous");
});
test("benchmark on-device matching against preindexed municipal-scale synthetic data", () => {
  const large=[];
  for(let i=0;i<5000;i++){
    const y=-38+Math.floor(i/100)*.003, x=144+(i%100)*.003;
    large.push({id:i,street:"ROAD "+i,from:"A",to:"B",a:[y,x],b:[y+.001,x],
      positive:"WEST",negative:"EAST"});
  }
  const engine=local.createResolver({version:"bench",segments:large});
  const times=[];
  for(let i=0;i<500;i++){
    const t=performance.now();
    engine.resolve(-37.9975,144.003,5);
    times.push(performance.now()-t);
  }
  times.sort((a,b)=>a-b);
  assert.ok(times[Math.floor(times.length*.95)] < 250,"local matcher p95 must remain under 250 ms");
});
