import unittest
from scripts.verify_phase3_footscray import validate_static, ROAD_SHA, LGA_SHA


class Phase3FootscrayPublishedTests(unittest.TestCase):
    def test_exact_official_geometry_cardinal_orientation_licence_and_checksum(self):
        reviewed = validate_static()
        self.assertEqual(len(reviewed), 32)
        self.assertEqual(len({f["properties"]["vicmapPFI"] for f in reviewed}), 32)

    def test_no_private_location_metadata_in_public_geojson(self):
        reviewed = validate_static()
        for feat in reviewed:
            text = str(feat).lower()
            for sensitive in ("capturedat", "deviceid", "baynumber",
                              "baynumber", "gpssamples", "parkingrestriction"):
                self.assertNotIn(sensitive, text)


if __name__ == "__main__":
    unittest.main()
