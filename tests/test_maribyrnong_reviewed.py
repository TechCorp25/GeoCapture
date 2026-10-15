import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
GEO=ROOT/"data/reviewed/maribyrnong-talbot-cowper-dead-end.geojson"
PACK=ROOT/"municipal-road-pack.js"

class ReviewedMaribyrnongPilotTests(unittest.TestCase):
    def test_pack_geometry_and_verified_scope_exactly_match_reviewed_source(self):
        geo=json.loads(GEO.read_text())["features"]
        self.assertEqual(len(geo),1)
        g=geo[0]
        p=g["properties"]
        self.assertTrue(p["boundaryEndpointsVerified"])
        self.assertEqual(p["vicmapPFI"],5669272)
        self.assertEqual((p["street"],p["from"],p["to"]),
                         ("TALBOT STREET","COWPER STREET","DEAD END"))
        source=PACK.read_text()
        match=re.search(r"segments: previous\.segments\.concat\((\[.*?\])\)",source)
        self.assertIsNotNone(match)
        rows=json.loads(match.group(1))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["a"],list(reversed(g["geometry"]["coordinates"][0])))
        self.assertEqual(rows[0]["b"],list(reversed(g["geometry"]["coordinates"][-1])))
        self.assertEqual(rows[0]["suburbs"],["FOOTSCRAY"])
        self.assertEqual(rows[0]["attribution"]["licence"],"CC BY 4.0")
    def test_no_private_capture_points_embedded(self):
        geo=GEO.read_text().lower()
        for secret in ["2458","2457","2456","2455","2454","2453","2452",
                       "capturedat","sampl ecount","dev ice_geolocation"]:
            self.assertNotIn(secret.replace(" ",""),geo)
if __name__=="__main__":unittest.main()
