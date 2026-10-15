/* Reviewed Vicmap Transport / GeoCapture field-verified Talbot Street, Footscray.
 * CC BY 4.0 State of Victoria, source:
 * https://discover.data.vic.gov.au/en_AU/dataset/vicmap-transport-road-line
 * Review date 2026-10-15; PFI 5669272. Scope: one street block ONLY.
 * No individual parking-bay GPS coordinates are stored in this source bundle.
 */
(function(root) {
  "use strict";
  const previous = root.GeoCaptureRoadData;
  if (!previous) throw new Error("Historical local road dataset missing");
  root.GeoCaptureRoadData = Object.freeze({
    ...previous,
    version: previous.version + "+maribyrnong-vicmap-20261015",
    segments: previous.segments.concat([{"id":"maribyrnong:vicmap-pfi-5669272:0","street":"TALBOT STREET","from":"COWPER STREET","to":"DEAD END","a":[-37.80225195908597,144.9039780490001],"b":[-37.80188509308594,144.90275580500008],"positive":"NORTH","negative":"SOUTH","suburbs":["FOOTSCRAY"],"postcode":"3011","startBoundary":true,"endBoundary":true,"attribution":{"source":"Vicmap Transport TR_ROAD — State of Victoria","licence":"CC BY 4.0","url":"https://discover.data.vic.gov.au/en_AU/dataset/vicmap-transport-road-line","jurisdiction":"maribyrnong"}}])
  });
})(typeof globalThis === "object" ? globalThis : this);
