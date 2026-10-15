/* GeoCapture local street matcher.
 * Adapted from the April 2026 CivicMAPS shared street-position algorithm:
 * nearest finite segment projection; cardinal side via cross product;
 * suppress side when uncertainty overlaps the road centreline.
 * Matching uses only packaged data and device GPS; never fetches.
 */
(function (root) {
  "use strict";
  const CELL_DEGREES = 0.002;
  const LAT_M = 111000;
  const MAX_DISTANCE_M = 30;
  const SIDE_MIN_DISTANCE_M = 4;
  const normal = name => String(name || "").toUpperCase().replace(/[’']/g, "").replace(/[^A-Z0-9]/g, "");
  const cell = (lat, lng) => Math.floor(lat / CELL_DEGREES) + ":" + Math.floor(lng / CELL_DEGREES);

  function validPoint(point) {
    return Array.isArray(point) && point.length === 2
      && Number.isFinite(point[0]) && Number.isFinite(point[1])
      && Math.abs(point[0]) <= 90 && Math.abs(point[1]) <= 180;
  }
  function project(lat, lng, seg) {
    const latToMetres = LAT_M;
    const lonToMetres = LAT_M * Math.cos(lat * Math.PI / 180);
    // Preserve the historical cross-product convention: latitude first.
    const dx = (seg.b[0] - seg.a[0]) * latToMetres;
    const dy = (seg.b[1] - seg.a[1]) * lonToMetres;
    const px = (lat - seg.a[0]) * latToMetres;
    const py = (lng - seg.a[1]) * lonToMetres;
    const lenSq = dx * dx + dy * dy;
    if (lenSq < 0.0001) return null;
    const t = Math.max(0, Math.min(1, (px * dx + py * dy) / lenSq));
    const distance = Math.hypot(px - t * dx, py - t * dy);
    return {
      distance, t, cross: dx * py - dy * px,
      nearestEndpoint: Math.min(seg.startBoundary === false ? Infinity : t * Math.sqrt(lenSq),
        seg.endBoundary === false ? Infinity : (1 - t) * Math.sqrt(lenSq))
    };
  }

  function createResolver(bundle) {
    if (!bundle || !Array.isArray(bundle.segments)) throw new TypeError("Missing municipal road data");
    const bins = new Map();
    const filtered = [];
    for (const seg of bundle.segments) {
      if (!seg || !seg.street || !validPoint(seg.a) || !validPoint(seg.b)) continue;
      if (!seg.from || !seg.to) continue;
      // Boundary metadata may be available even where the road's cardinal
      // side is not safely known (e.g. curves and diagonal streets).
      const validSides = ["NORTH","SOUTH","EAST","WEST"];
      if ((seg.positive || seg.negative) &&
          (!validSides.includes(seg.positive) || !validSides.includes(seg.negative))) continue;
      const i = filtered.push(seg) - 1;
      // Expand each segment bbox by ~45 m so nearby street geometry is considered.
      const padding = 0.00055;
      const minLat = Math.floor((Math.min(seg.a[0], seg.b[0]) - padding) / CELL_DEGREES);
      const maxLat = Math.floor((Math.max(seg.a[0], seg.b[0]) + padding) / CELL_DEGREES);
      const minLng = Math.floor((Math.min(seg.a[1], seg.b[1]) - padding) / CELL_DEGREES);
      const maxLng = Math.floor((Math.max(seg.a[1], seg.b[1]) + padding) / CELL_DEGREES);
      // Bounds guard prevents corrupt data from allocating an unbounded grid.
      if ((maxLat - minLat + 1) * (maxLng - minLng + 1) > 2000) continue;
      for (let y = minLat; y <= maxLat; y++) for (let x = minLng; x <= maxLng; x++) {
        const key = y + ":" + x;
        if (!bins.has(key)) bins.set(key, []);
        bins.get(key).push(i);
      }
    }
    function resolve(lat, lng, accuracy, options = {}) {
      if (![lat, lng, accuracy].every(Number.isFinite) || accuracy <= 0 ||
          Math.abs(lat) > 90 || Math.abs(lng) > 180) {
        return {status:"invalid", warnings:["Invalid GPS fix."]};
      }
      const indices = bins.get(cell(lat, lng)) || [];
      if (!indices.length) return {status:"uncovered", warnings:["No locally indexed roads at this position."]};
      const candidates = indices.map(id => {
        const seg = filtered[id];
        const point = project(lat, lng, seg);
        return point && {...point, seg};
      }).filter(Boolean).sort((a,b) => a.distance - b.distance);
      const gate = accuracy <= 15 ? MAX_DISTANCE_M : Math.min(MAX_DISTANCE_M, Math.max(15, accuracy * 0.5));
      const close = candidates.filter(c => c.distance <= gate);
      if (!close.length) return {status:"uncovered", warnings:["No indexed road is sufficiently close to GPS."]};
      const requestedName = normal(options.street);
      const constrained = requestedName ? close.filter(c => normal(c.seg.street) === requestedName) : close;
      if (!constrained.length) {
        return {status:"uncovered", warnings:["The entered street is not matched by local geometry."],
          candidates:[...new Set(close.slice(0,6).map(c=>c.seg.street))]};
      }
      const best = constrained[0];
      if (options.suburb && best.seg.suburbs?.length &&
          !best.seg.suburbs.some(s => normal(s) === normal(options.suburb))) {
        return {status:"uncovered", warnings:["Local road data differs from entered suburb."]};
      }
      if (options.postcode && best.seg.postcode && String(best.seg.postcode) !== String(options.postcode)) {
        return {status:"uncovered", warnings:["Local road data differs from entered postcode."]};
      }
      const competing = close.find(c => c.seg.id !== best.seg.id && (
        normal(c.seg.street) !== normal(best.seg.street) ||
        (normal(c.seg.from) !== normal(best.seg.from) || normal(c.seg.to) !== normal(best.seg.to))
      ) && c.distance <= best.distance + Math.max(3, Math.min(12, accuracy * 0.6)));
      if (competing && (!requestedName || competing.distance + Math.max(3, accuracy * 0.5) < best.distance
          || normal(competing.seg.street) === requestedName)) {
        return {status:"ambiguous",warnings:["Multiple nearby road segments; confirm the street and boundaries manually."],
          candidates:[...new Set(close.slice(0,6).map(c=>c.seg.street))]};
      }
      if (best.nearestEndpoint <= Math.max(5, Math.min(15, accuracy))) {
        return {status:"ambiguous",warnings:["Close to an intersection; confirm the segment boundaries manually."],
          candidates:[best.seg.street]};
      }
      const threshold = Math.max(SIDE_MIN_DISTANCE_M, accuracy * 0.7);
      // A GPS fix straddling the centreline cannot support a cardinal side.
      const side = best.distance < threshold || !best.seg.positive || !best.seg.negative
        ? "" : best.cross > 0 ? best.seg.positive : best.seg.negative;
      return {
        status:"matched",
        source:"local",
        street:best.seg.street,
        between:[best.seg.from,best.seg.to],
        side,
        distance:Math.round(best.distance * 10) / 10,
        roadSegmentId:best.seg.id,
        attribution:bundle.attribution || {source:bundle.source || "Municipal road geometry"},
        warnings:side ? [] : ["Street side not reliable at reported GPS accuracy; select manually."]
      };
    }
    return {resolve, segmentCount:filtered.length, version:bundle.version || "unknown"};
  }
  const API = {
    createResolver,
    resolve(lat,lng,accuracy,options) {
      const bundle = root.GeoCaptureRoadData;
      if (!bundle) return {status:"uncovered",warnings:["Municipal road dataset unavailable."]};
      if (!this._resolver || this._source !== bundle) {
        this._resolver = createResolver(bundle);
        this._source = bundle;
      }
      return this._resolver.resolve(lat,lng,accuracy,options);
    }
  };
  if (typeof module === "object" && module.exports) module.exports = API;
  root.GeoCaptureLocalLookup = API;
})(typeof globalThis === "object" ? globalThis : this);
