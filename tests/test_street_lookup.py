import json
import math
import os
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import street_lookup as streets
from server import Handler


def node(i, x, y=0):
    return {"type": "node", "id": i, "lat": y / 111320, "lon": x / 111320}


def way(i, nodes, name="Test Street", **tags):
    return {"type": "way", "id": i, "nodes": nodes,
            "tags": {"highway": "residential", "name": name, **tags}}


def block():
    return [node(1, -100), node(2, 100), node(3, -100, 100), node(4, 100, 100),
            way(10, [1, 2]), way(11, [1, 3], "First Road"), way(12, [2, 4], "Last Road")]


class NetworkTests(unittest.TestCase):
    def resolve(self, elements, **kwargs):
        return streets.resolve_network(elements, 0, 0, 5, **kwargs)

    def test_two_connected_cross_streets(self):
        r = self.resolve(block())
        self.assertEqual(r["street"], "TEST STREET")
        self.assertEqual(r["between"], ["FIRST ROAD", "LAST ROAD"])

    def test_split_way_is_not_dead_end(self):
        data = block()
        data[4] = way(10, [1, 5])
        data += [node(5, 20), way(13, [5, 2])]
        self.assertEqual(self.resolve(data)["between"], ["FIRST ROAD", "LAST ROAD"])

    def test_dead_end_and_private_driveway(self):
        data = [node(1, -100), node(2, 100), node(3, -100, 100), node(4, 20), node(5, 20, 40),
                way(10, [1, 4, 2]), way(11, [1, 3], "Cowper Street"),
                way(12, [4, 5], "", highway="service", service="driveway")]
        r = self.resolve(data)
        self.assertEqual(r["between"], ["COWPER STREET", "DEAD END"])
        self.assertTrue(any("on site" in w for w in r["warnings"]))

    def test_overpass_road_crossing_without_shared_node_is_not_intersection(self):
        data = block() + [node(5, 50, -50), node(6, 50, 50), way(13, [5, 6], "Overpass", bridge="yes")]
        self.assertEqual(self.resolve(data)["between"], ["FIRST ROAD", "LAST ROAD"])

    def test_nearby_parallel_streets_require_selection(self):
        data = block() + [node(5, -100, 6), node(6, 100, 6), way(13, [5, 6], "Parallel Road")]
        self.assertIsNone(self.resolve(data)["street"])
        self.assertEqual(self.resolve(data, street="TEST ST")["between"], ["FIRST ROAD", "LAST ROAD"])

    def test_parallel_same_name_is_ambiguous(self):
        data = block() + [node(5, -100, 6), node(6, 100, 6), way(13, [5, 6])]
        self.assertEqual(self.resolve(data)["between"], [None, None])

    def test_outside_search_radius_does_not_become_dead_end(self):
        r = self.resolve([node(1, -900), node(2, 900), way(10, [1, 2])])
        self.assertEqual(r["between"], [None, None])

    def test_incomplete_geometry_rejected(self):
        with self.assertRaises(streets.LookupUnavailable):
            self.resolve([node(1, -100), way(10, [1, 2])])

    def test_unnamed_junction_and_roundabout_not_guessed(self):
        for tags in ({"name": ""}, {"name": "Round Road", "junction": "roundabout"}):
            data = block()
            data[5] = way(11, [1, 3], **tags)
            self.assertIsNone(self.resolve(data)["between"][0])

    def test_street_mismatch_and_no_network(self):
        self.assertIsNone(self.resolve(block(), street="Different Street")["street"])
        self.assertEqual(self.resolve([])["between"], [None, None])

    def test_near_intersection_does_not_pick_wrong_block(self):
        data = block()
        data[0] = node(1, -4)
        self.assertIsNone(self.resolve(data, street="Test Street")["between"][0])

    def test_invalid_request_values(self):
        good = {"latitude": -37.8, "longitude": 144.9, "accuracy": 5}
        for key, value in (("latitude", True), ("latitude", math.nan), ("latitude", 91),
                           ("longitude", 181), ("accuracy", 0), ("accuracy", 26),
                           ("street", []), ("street", "A" * 151)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                streets.validate_request({**good, key: value})

    def test_google_reference_never_changes_osm_suggestions(self):
        streets._requests.clear()
        with patch.dict(os.environ, {"STREET_LOOKUP_ENABLED": "true"}), \
             patch.object(streets, "road_network", return_value=block()), \
             patch.object(streets, "google_reference", return_value="Google-only Road"):
            r = streets.lookup({"latitude": 0, "longitude": 0, "accuracy": 5})
        self.assertEqual(r["street"], "TEST STREET")
        self.assertEqual(r["googleReference"], "Google-only Road")

    def test_provider_partial_response_and_key_redaction(self):
        with patch.object(streets, "fetch_json", return_value={"remark": "timed out", "elements": block()}):
            with self.assertRaises(streets.LookupUnavailable):
                streets.road_network(0, 0)
        with patch.object(streets, "urlopen", side_effect=RuntimeError("SECRET-KEY")):
            with self.assertRaises(streets.LookupUnavailable) as caught:
                streets.fetch_json("https://example.invalid")
            self.assertNotIn("SECRET", str(caught.exception))

    def test_rate_limit_and_disabled_feature(self):
        streets._requests.clear()
        with patch.dict(os.environ, {"STREET_LOOKUP_ENABLED": "false"}):
            with self.assertRaises(streets.LookupUnavailable):
                streets.lookup({"latitude": 0, "longitude": 0, "accuracy": 5})
        streets._requests.extend([streets.time.monotonic()] * 30)
        try:
            with patch.dict(os.environ, {"STREET_LOOKUP_ENABLED": "true"}), self.assertRaises(streets.LookupBusy):
                streets.lookup({"latitude": 0, "longitude": 0, "accuracy": 5})
        finally:
            streets._requests.clear()


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, content_type="application/json"):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(method, path, body=body, headers={"Content-Type": content_type})
        response = conn.getresponse()
        result = response.status, response.getheader("Cache-Control"), json.loads(response.read())
        conn.close()
        return result

    def test_config_has_no_key_and_is_not_cacheable(self):
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "SECRET"}):
            status, cache, body = self.request("GET", "/api/location/config")
        self.assertEqual(status, 200)
        self.assertEqual(cache, "no-store")
        self.assertNotIn("SECRET", json.dumps(body))

    def test_lookup_success_and_failure_codes(self):
        with patch("server.lookup", return_value={"street": "TEST STREET"}):
            status, cache, body = self.request("POST", "/api/location/suggest", "{}")
        self.assertEqual((status, cache, body["street"]), (200, "no-store", "TEST STREET"))
        for error, code in ((ValueError("invalid"), 400), (streets.LookupUnavailable("unavailable"), 503),
                            (streets.LookupBusy("busy"), 429)):
            with patch("server.lookup", side_effect=error):
                self.assertEqual(self.request("POST", "/api/location/suggest", "{}")[0], code)

    def test_non_json_oversized_and_malformed_requests(self):
        self.assertEqual(self.request("POST", "/api/location/suggest", "{}", "text/plain")[0], 415)
        self.assertEqual(self.request("POST", "/api/location/suggest", " " * 2049)[0], 413)
        self.assertEqual(self.request("POST", "/api/location/suggest", "{")[0], 400)


if __name__ == "__main__":
    unittest.main()
