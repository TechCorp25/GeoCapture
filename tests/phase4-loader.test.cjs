const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createHash, webcrypto} = require("node:crypto");
const loader = require("../municipal-road-loader.js");
const local = require("../local-street-lookup.js");

const sha = text => createHash("sha256").update(text).digest("hex");
const road = {
  id:"maribyrnong:vicmap-98765432:0",
  street:"TEST AVENUE",from:"FIRST STREET",to:"SECOND STREET",
  a:[-37.79,144.85],b:[-37.7905,144.85],
  positive:"EAST",negative:"WEST",suburbs:["BRAYBROOK"],postcode:"",
  reviewState:"OFFICIAL_SOURCE_TOPOLOGY_VERIFIED_HANDSET_QA_PENDING",
  attribution:{source:"State of Victoria — Vicmap Transport TR_ROAD",
    licence:"CC BY 4.0",
    snapshotSHA256:"3f5a4ee47b7e86cff22df5e82efde6afa866eacf42f07ad8b87fce2a944412bb"}
};
const packJSON = JSON.stringify({version:"maribyrnong-phase4-20261015-v2",segments:[road]});
const packRaw = Buffer.from(packJSON);
const packageNames = ["braybrook","footscray","kingsville","maidstone","maribyrnong",
  "seddon","shared-localities","tottenham","west-footscray","yarraville"];
const manifest = {
  schema:"geocapture.municipal_road_packs.v1",version:"maribyrnong-phase4-20261015-v2",
  sourceRoadSHA256:"3f5a4ee47b7e86cff22df5e82efde6afa866eacf42f07ad8b87fce2a944412bb",
  councilPolygonSHA256:"d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb",
  publicationReviewState:"OFFICIAL_SOURCE_TOPOLOGY_VERIFIED_HANDSET_QA_PENDING",
  packages:Object.fromEntries(packageNames.map(n=>[n,{
    file:"./municipal-data/"+n+".json",
    sha256:sha(packRaw),
    roadBlocks:1,
    boundsWGS84:n==="braybrook" ? [144.84,-37.795,144.86,-37.785] :
      [144.9,-37.82,144.91,-37.81]
  }]))
};
const digest = async bytes => createHash("sha256").update(Buffer.from(bytes)).digest("hex");
function mock(badDigest=false) {
  let fetchCalls = [];
  let current = {version:"historic",segments:[]};
  const fetcher=async url=>{
    fetchCalls.push(url);
    return url.endsWith("manifest.json") ? {ok:true,json:async()=>manifest}
      : {ok:true,arrayBuffer:async()=>badDigest ?
        Buffer.from("tampered").buffer.slice(Buffer.from("tampered").byteOffset,Buffer.from("tampered").byteOffset+8)
        : packRaw};
  };
  const api = loader.createLoader(fetcher, ()=>current, x=>current=x, digest);
  return {api,fetchCalls, get data(){return current}};
}
test("full Melbourne CBD remains local without fetching municipal resources", async()=>{
  const m=mock();
  assert.deepEqual(await m.api.ensureFor(-37.81,144.96),{loaded:0,available:false});
  assert.equal(m.fetchCalls.length,0);
});
test("GPS selects only required municipal package, checks checksum and matches street",async()=>{
  const m=mock();
  const first=await m.api.ensureFor(-37.79025,144.85);
  assert.equal(first.loaded,1);
  assert.equal(m.data.segments.length,1);
  assert.deepEqual(m.api.loadedPackages,["braybrook"]);
  assert.equal(m.fetchCalls.length,2);
  const result=local.createResolver(m.data).resolve(-37.79025,144.85,3,{suburb:"BRAYBROOK"});
  assert.equal(result.status,"matched",JSON.stringify(result));
  assert.deepEqual(result.between,["FIRST STREET","SECOND STREET"]);
  assert.equal(result.side,"");
  const again=await m.api.ensureFor(-37.79025,144.85);
  assert.equal(again.loaded,1);
  assert.equal(m.fetchCalls.length,2);
});
test("concurrent GPS queries deduplicate package fetch and preserve road identity",async()=>{
  const m=mock();
  await Promise.all([m.api.ensureFor(-37.79025,144.85),m.api.ensureFor(-37.79025,144.85)]);
  assert.equal(m.data.segments.length,1);
  assert.equal(m.fetchCalls.length,2);
});
test("integrity mismatch refuses data injection",async()=>{
  const m=mock(true);
  await assert.rejects(m.api.ensureFor(-37.79025,144.85),/integrity failed/);
  assert.equal(m.data.segments.length,0);
});
test("invalid GPS cannot initiate municipal lookup",async()=>{
  const m=mock();
  await m.api.ensureFor(Infinity,0);
  await m.api.ensureFor(-120,144.85);
  assert.equal(m.fetchCalls.length,0);
});
