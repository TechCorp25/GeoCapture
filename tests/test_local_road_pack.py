import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts.build_municipal_road_pack import build, sides_for

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "build_municipal_road_pack.py"


def feature(street="Talbot Street", boundaries=True):
    return {
        "type": "Feature",
        "properties": {
            "roadSegmentId": 101,
            "street": street,
            "from": "Cowper Street",
            "to": "Dead End",
            "suburb": "Footscray",
            "postcode": "3011",
            "boundaryEndpointsVerified": boundaries,
        },
        "geometry": {"type": "LineString", "coordinates": [
            [144.904, -37.802], [144.904, -37.803], [144.904, -37.804]
        ]}
    }


class MunicipalRoadBuildTests(unittest.TestCase):
    def test_unverified_intersections_never_generate_local_matches(self):
        data, skipped = build({"type":"FeatureCollection", "features":[feature(boundaries=False)]},
                              "maribyrnong", "Reviewed geometry", "CC BY", "https://example.org")
        self.assertEqual(data, [])
        self.assertEqual(len(skipped), 1)

    def test_verified_polylines_split_without_false_internal_intersections(self):
        data, skipped = build({"type":"FeatureCollection", "features":[feature()]},
                              "maribyrnong", "Reviewed geometry", "CC BY", "https://example.org")
        self.assertEqual(skipped, [])
        self.assertEqual(len(data), 2)
        self.assertEqual([row["startBoundary"] for row in data], [True, False])
        self.assertEqual([row["endBoundary"] for row in data], [False, True])
        self.assertEqual(data[0]["suburbs"], ["FOOTSCRAY"])
        self.assertEqual(data[0]["positive"], "WEST")
        self.assertEqual(data[0]["negative"], "EAST")
        self.assertEqual(data[0]["attribution"]["jurisdiction"], "maribyrnong")

    def test_diagonal_side_is_not_fabricated(self):
        pos, neg = sides_for([-37.8, 144.9],[-37.799, 144.901])
        self.assertEqual((pos, neg), ("", ""))

    @unittest.skipUnless(shutil.which("node"), "Node.js required for packaged JS smoke test")
    def test_compiler_emits_runnable_offline_road_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            in_file = pathlib.Path(tmp) / "source.json"
            out_file = pathlib.Path(tmp) / "municipal-road-pack.js"
            in_file.write_text(json.dumps({"type":"FeatureCollection","features":[feature()]}))
            proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(in_file),
                "--output", str(out_file), "--jurisdiction", "maribyrnong",
                "--source", "Reviewed geometry", "--licence", "CC BY",
                "--source-url", "https://example.org"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            code = ("globalThis.GeoCaptureRoadData={version:'cbd',segments:[]};"
                    "require(process.argv[1]);"
                    "if(globalThis.GeoCaptureRoadData.segments.length!==2)process.exit(2);")
            smoke = subprocess.run(["node", "-e", code, str(out_file)],
                                    capture_output=True, text=True)
            self.assertEqual(smoke.returncode, 0, smoke.stderr)


if __name__ == "__main__":
    unittest.main()
