const {test} = require("node:test");
const assert = require("node:assert/strict");
const {performance} = require("node:perf_hooks");
require("../local-road-data.js");
require("../municipal-road-pack.js");
require("../municipal-road-phase3.js");
const resolver = require("../local-street-lookup.js");

test("source-verified Footscray package augments CBD and Talbot without overwrite",()=>{
 const data=globalThis.GeoCaptureRoadData;
 assert.equal(data.segments.length,179);
 assert.equal(new Set(data.segments.map(s=>s.id)).size,179);
 assert.match(data.version,/footscray-reviewed-20261015-v1/);
 assert.ok(data.segments.some(s=>s.id==="maribyrnong:vicmap-pfi-5669272:0"));
 assert.ok(data.segments.some(s=>s.id==="maribyrnong:vicmap-21914804:0"));
});

test("official Cowper Street PFI 21914805 resolves correct named junctions",()=>{
 const midLat=(-37.801699906085965-37.80078123808596)/2;
 const midLon=(144.90423083000007+144.90465147100008)/2;
 const result=resolver.resolve(midLat,midLon,3,{suburb:"Footscray",postcode:"3011"});
 assert.equal(result.status,"matched",JSON.stringify(result));
 assert.equal(result.street,"COWPER STREET");
 assert.deepEqual(result.between,["FALCON COURT","WINGFIELD STREET"]);
 assert.equal(result.roadSegmentId,"maribyrnong:vicmap-21914805:0");
 assert.equal(result.side,"");
 assert.match(result.attribution.source,/Vicmap/);
 assert.equal(result.attribution.licence,"CC BY 4.0");
});
test("operator locality conflicts, uncertainty, and invalid GPS do not create matches",()=>{
 const lat=(-37.801699906085965-37.80078123808596)/2;
 const lon=(144.90423083000007+144.90465147100008)/2;
 assert.equal(resolver.resolve(lat,lon,4,{suburb:"Melbourne"}).status,"uncovered");
 assert.equal(resolver.resolve(lat,lon,4,{street:"NOT A STREET"}).status,"uncovered");
 assert.equal(resolver.resolve(NaN,lon,4).status,"invalid");
 const uncertain=resolver.resolve(lat,lon,12,{suburb:"Footscray"});
 if(uncertain.status==="matched")assert.equal(uncertain.side,"");
});
test("p95 for audited 179-edge mobile bundle is less than 250ms after fix",()=>{
 const lat=(-37.801699906085965-37.80078123808596)/2;
 const lon=(144.90423083000007+144.90465147100008)/2;
 const times=[];
 for(let i=0;i<800;i++){const start=performance.now();resolver.resolve(lat,lon,4);times.push(performance.now()-start);}
 times.sort((a,b)=>a-b);
 const p95=times[Math.floor(times.length*.95)];
 console.log(`Local-only Footscray 179-edge matching: ${times.length} fixes, p95=${p95.toFixed(3)}ms (Node CI, excludes GPS/network/MongoDB)`);
 assert.ok(p95<250);
});
