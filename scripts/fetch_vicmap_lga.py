#!/usr/bin/env python3
"""Fetch official property-aligned City of Maribyrnong polygon (Vicmap Admin layer 9).

Used exclusively at offline source-review build time, never by mobile users.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

LAYER = 'https://vicmap.land.vic.gov.au/agsgis/rest/services/vicmap/Vicmap_Admin/MapServer/9'
URL = LAYER + '/query'


def acquire(fetch=None):
    params = {'where': "LGA_NAME = 'MARIBYRNONG'", 'outFields': '*',
              'returnGeometry': 'true', 'outSR': 4326, 'f': 'geojson'}
    url = URL + '?' + urllib.parse.urlencode(params)
    if fetch is None:
        def fetch(u):
            req = urllib.request.Request(u, headers={
                'User-Agent': 'GeoCapture offline municipal source review/1.0',
                'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read(8_000_001)
            if len(body) > 8_000_000:
                raise ValueError('Unexpectedly large council boundary response')
            return body
    data = fetch(url)
    doc = json.loads(data)
    if doc.get('error') or doc.get('type') != 'FeatureCollection' or len(doc.get('features', [])) != 1:
        raise ValueError('Official layer did not return exactly one Maribyrnong polygon')
    feature = doc['features'][0]
    if (feature.get('geometry') or {}).get('type') not in ('Polygon', 'MultiPolygon'):
        raise ValueError('Expected polygon or multipolygon')
    props = feature.get('properties') or {}
    if not any(str(value).upper().strip() == 'MARIBYRNONG'
               for key, value in props.items() if 'name' in key.lower()):
        raise ValueError('Unexpected municipality name from Vicmap Admin')
    payload = (json.dumps(doc, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    manifest = {'source': 'Vicmap Admin LGA_POLYGON — State of Victoria',
                'serviceUrl': LAYER, 'licence': 'CC BY 4.0',
                'licenceUrl': 'https://creativecommons.org/licenses/by/4.0/',
                'retrievedUTC': dt.datetime.now(dt.timezone.utc).isoformat(),
                'lgaName': 'MARIBYRNONG', 'featureCount': 1,
                'sha256': hashlib.sha256(payload).hexdigest(),
                'reviewStatus': 'OFFICIAL_BOUNDARY_NOT_A_FIELD_SURVEY',
                'note': 'Property-aligned council boundary; road acquisition must retain its separate buffer.'}
    return payload, manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--manifest', required=True)
    args = p.parse_args()
    payload, manifest = acquire()
    for path in (args.output, args.manifest):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_bytes(payload)
    Path(args.manifest).write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('VICMAP LGA', json.dumps(manifest))


if __name__ == '__main__':
    main()
