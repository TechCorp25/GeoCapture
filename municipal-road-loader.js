/* GeoCapture municipality-scoped lazy local road pack loader.
 * Sources: independently audited Vicmap Transport TR_ROAD; State of Victoria CC BY 4.0.
 * Loads signed-by-manifest same-origin static data only; never sends GPS off device.
 */
(function(root) {
  "use strict";
  const ROAD_SHA = "3f5a4ee47b7e86cff22df5e82efde6afa866eacf42f07ad8b87fce2a944412bb";
  const LGA_SHA = "d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb";
  const MANIFEST_URL = "./municipal-data/manifest.json";
  const VERSION = "maribyrnong-phase4-20261015-v2";

  function bboxContains(bbox, lat, lon, metres = 100) {
    if (!Array.isArray(bbox) || bbox.length !== 4) return false;
    const dy = metres / 111000;
    const dx = metres / (111000 * Math.max(.1, Math.cos(lat * Math.PI / 180)));
    return lon >= bbox[0] - dx && lon <= bbox[2] + dx
      && lat >= bbox[1] - dy && lat <= bbox[3] + dy;
  }

  async function digestHex(buffer) {
    if (!root.crypto?.subtle) throw new Error("Package SHA-256 verification requires a secure browser context");
    const hash = await root.crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, "0")).join("");
  }

  function createLoader(fetcher, readData, writeData, verifyDigest = digestHex) {
    if (typeof fetcher !== "function") throw new TypeError("fetch required");
    const completed = new Set();
    const inflight = new Map();
    let manifestPromise = null;
    async function manifest() {
      if (manifestPromise) return manifestPromise;
      manifestPromise = (async () => {
        const response = await fetcher(MANIFEST_URL);
        if (!response.ok) throw new Error("Municipal package manifest unavailable");
        const doc = await response.json();
        if (doc.schema !== "geocapture.municipal_road_packs.v1" ||
            doc.version !== VERSION || doc.sourceRoadSHA256 !== ROAD_SHA ||
            doc.councilPolygonSHA256 !== LGA_SHA ||
            doc.publicationReviewState !== "OFFICIAL_SOURCE_TOPOLOGY_VERIFIED_HANDSET_QA_PENDING" ||
            !doc.packages || typeof doc.packages !== "object" ||
            Object.keys(doc.packages).length !== 10) {
          throw new Error("Municipal road package manifest is unverified or unexpected");
        }
        return doc;
      })();
      try { return await manifestPromise; }
      catch(error) { manifestPromise = null; throw error; }
    }

    async function loadOne(key, item) {
      if (completed.has(key)) return;
      if (inflight.has(key)) return inflight.get(key);
      const promise = (async() => {
        if (!/^[-a-z]+$/.test(key) || item.file !== "./municipal-data/" + key + ".json" ||
            !/^[0-9a-f]{64}$/.test(item.sha256)) {
          throw new Error("Invalid municipal package identity");
        }
        const response = await fetcher(item.file);
        if (!response.ok) throw new Error("Municipal package unavailable: " + key);
        const bytes = await response.arrayBuffer();
        if (await verifyDigest(bytes) !== item.sha256) {
          throw new Error("Municipal road package integrity failed: " + key);
        }
        const doc = JSON.parse(new TextDecoder().decode(bytes));
        if (doc.version !== VERSION || !Array.isArray(doc.segments) ||
            doc.segments.length < item.roadBlocks) {
          throw new Error("Municipal package structure invalid: " + key);
        }
        const original = readData();
        if (!original || !Array.isArray(original.segments)) throw new Error("Historic road seed unavailable");
        const known = new Set(original.segments.map(s => s.id));
        const incoming = new Set();
        for (const segment of doc.segments) {
          if (!segment || !segment.id?.startsWith("maribyrnong:vicmap-") ||
              !segment.street || !segment.from || !segment.to ||
              !Array.isArray(segment.a) || !Array.isArray(segment.b) ||
              segment.a.length !== 2 || segment.b.length !== 2 ||
              !segment.a.every(Number.isFinite) || !segment.b.every(Number.isFinite) ||
              !["", "NORTH", "SOUTH", "EAST", "WEST"].includes(segment.positive) ||
              !["", "NORTH", "SOUTH", "EAST", "WEST"].includes(segment.negative) ||
              segment.reviewState !== "OFFICIAL_SOURCE_TOPOLOGY_VERIFIED_HANDSET_QA_PENDING" ||
              segment.attribution?.snapshotSHA256 !== ROAD_SHA ||
              known.has(segment.id) || incoming.has(segment.id)) {
            throw new Error("Unreviewed or duplicate municipal segment in package: " + key);
          }
          incoming.add(segment.id);
        }
        writeData(Object.freeze({...original,
          version: original.version + "+" + VERSION + ":" + key,
          segments: original.segments.concat(doc.segments)
        }));
        completed.add(key);
      })();
      inflight.set(key, promise);
      try { await promise; }
      finally { inflight.delete(key); }
    }
    async function ensureFor(lat, lon) {
      if (![lat, lon].every(Number.isFinite) ||
          lat < -90 || lat > 90 || lon < -180 || lon > 180) return {loaded:0, available:false};
      // Outside municipal bounds: no network requests. The historic CBD loader remains ready.
      if (!bboxContains([144.83232328049982, -37.8323474585149,
                         144.92335033374718, -37.75040609666159], lat, lon, 0)) {
        return {loaded:0, available:false};
      }
      const doc = await manifest();
      const selected = Object.entries(doc.packages).filter(([,item]) =>
        bboxContains(item.boundsWGS84, lat, lon, 150));
      await Promise.all(selected.map(([key, item]) => loadOne(key, item)));
      return {loaded:selected.length, available:true, version:doc.version};
    }
    return {ensureFor, manifest, get loadedPackages(){return [...completed];}};
  }
  const local = typeof root.fetch === "function" ? createLoader(
    (...args) => root.fetch(...args),
    () => root.GeoCaptureRoadData,
    data => { root.GeoCaptureRoadData = data; }
  ) : null;
  const API = {createLoader, bboxContains, manifestURL:MANIFEST_URL,
    ensureFor: (...args) => local ? local.ensureFor(...args) : Promise.resolve({loaded:0, available:false})};
  if (typeof module === "object" && module.exports) module.exports = API;
  root.GeoCaptureMunicipalPacks = API;
})(typeof globalThis === "object" ? globalThis : this);
