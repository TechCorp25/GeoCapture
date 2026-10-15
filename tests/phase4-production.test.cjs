/* Production integration checks against the actually emitted, source-verified
 * Maribyrnong locality packages. No external requests or private bay data.
 */
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {createHash} = require("node:crypto");
const {performance} = require("node:perf_hooks");
require("../local-road-data.js");
require("../municipal-road-pack.js");
require("../municipal-road-phase3.js");
const {createLoader} = require("../municipal-road-loader.js");
const local = require("../local-street-lookup.js");
const root = path.join(__dirname,"..","municipal-data");
const manifest = JSON.parse(fs.readFileSync(path.join(root,"manifest.json"),"utf8"));
const seed = globalThis.GeoCaptureRoadData;
const sha = bytes => createHash("sha256").update(Buffer.from(bytes)).digest("hex");

function harness() {
  let content = seed;
  const seen=[];
  const fetcher=async uri=>{
    seen.push(uri);
    if(uri.endsWith("/manifest.json")) return {ok:true,json:async()=>manifest};
    const filename = path.basename(uri);
    const buffer = fs.readFileSync(path.join(root,filename));
    const bytes = Uint8Array.from(buffer).buffer;
    return {ok:true,arrayBuffer:async()=>bytes};
  };
  const packLoader=createLoader(fetcher,()=>content,c=>content=c,async bytes=>sha(bytes));
  return {packLoader, seen, get content(){return content}};
}

test("static municipal source and all 10 package checksums agree with pinned release",()=>{
  assert.ok(manifest.newSourceQualifiedRoadBlocks>=1454);
  assert.ok(manifest.newGeometryEdges>=manifest.newSourceQualifiedRoadBlocks);
  assert.equal(manifest.publishedExistingRoadBlocks,33);
  assert.equal(Object.keys(manifest.packages).length,10);
  assert.equal(manifest.operationalCoverageComplete,false);
  let seen=new Set(),blocks=0,edges=0;
  for (const [key,item] of Object.entries(manifest.packages)) {
    const raw=fs.readFileSync(path.join(root,key+".json"));
    assert.equal(sha(raw),item.sha256);
    const doc=JSON.parse(raw);
    edges+=doc.segments.length;
    blocks+=item.roadBlocks;
    for (const s of doc.segments) {
      assert.ok(!seen.has(s.id),"duplicate edge identity "+s.id);
      seen.add(s.id);
      assert.equal(s.postcode,"","postcode not invented");
      assert.equal(s.attribution.licence,"CC BY 4.0");
      assert.equal(s.reviewState,"OFFICIAL_SOURCE_TOPOLOGY_VERIFIED_HANDSET_QA_PENDING");
      if(s.vicmapClassCodes?.includes(2)){assert.equal(s.positive,"");assert.equal(s.negative,"");}
    }
  }
  assert.equal(blocks,manifest.newSourceQualifiedRoadBlocks);
  assert.equal(edges,manifest.newGeometryEdges);
});
test("GPS selects required locality data without remote lookup and rebuilds spatial index",async()=>{
  const h=harness();
  assert.equal(seed.segments.length,179);
  assert.equal((await h.packLoader.ensureFor(-37.81,144.96)).available,false);
  assert.equal(h.seen.length,0);
  for(const key of Object.keys(manifest.packages)){
    const pack = JSON.parse(fs.readFileSync(path.join(root,key+".json")));
    const sample=pack.segments[0].a;
    await h.packLoader.ensureFor(sample[0],sample[1]);
  }
  assert.equal(h.packLoader.loadedPackages.length,10);
  assert.equal(h.content.segments.length,179+manifest.newGeometryEdges);
  assert.equal(new Set(h.content.segments.map(s=>s.id)).size,179+manifest.newGeometryEdges);
  const engine=local.createResolver(h.content);
  assert.equal(engine.segmentCount,179+manifest.newGeometryEdges);
  // Use mid-block points: genuine ambiguities are permitted but should not
  // erase every correct match within a locality.
  let matched=0;
  for (const key of Object.keys(manifest.packages)) {
    const pack=JSON.parse(fs.readFileSync(path.join(root,key+".json")));
    let hits=0;
    for(const road of pack.segments.slice(0,40)){
      const lat=(road.a[0]+road.b[0])/2,lon=(road.a[1]+road.b[1])/2;
      const result=engine.resolve(lat,lon,3,{street:road.street});
      if(result.status==="matched" && result.street===road.street) hits++;
    }
    assert.ok(hits>0,"no viable GPS street match for "+key);
    matched+=hits;
  }
  assert.ok(matched>30,"insufficient municipal GPS samples matched");
});
test("full municipal graph maintains low local matching p95 excluding receiver/database",async()=>{
  const h=harness();
  for(const key of Object.keys(manifest.packages)){
    const pack=JSON.parse(fs.readFileSync(path.join(root,key+".json")));
    await h.packLoader.ensureFor(...pack.segments[0].a);
  }
  const engine=local.createResolver(h.content);
  const roads=h.content.segments.filter(s=>s.id.startsWith("maribyrnong:"));
  const samples=[];
  for(let i=0;i<500;i++){
    const s=roads[(i*23)%roads.length];
    const start=performance.now();
    engine.resolve((s.a[0]+s.b[0])/2,(s.a[1]+s.b[1])/2,5);
    samples.push(performance.now()-start);
  }
  samples.sort((a,b)=>a-b);
  const p95=samples[Math.floor(samples.length*.95)];
  console.log("Phase 4 local graph",179+manifest.newGeometryEdges,"geometry edges; p95 =",p95.toFixed(3),"ms; excludes GPS/MongoDB");
  assert.ok(p95<250);
});
