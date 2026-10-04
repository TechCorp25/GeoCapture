import copy
import unittest

from server import validate_segment_payload


class IdentifierContractTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "schema": "civicmaps.parking_segment.v3",
            "segmentId": "9fb6b566-0012-4f32-a025-37e283ba2394",
            "revision": 6,
            "segment": {
                "street": "TALBOT STREET", "between": ["COWPER STREET", "DEAD END"],
                "side": "NORTH", "numberingMode": "numbered", "paymentRequired": False,
                "parkingAreaNumber": "MCC-TA", "permitNumber": None,
                "paymentProvider": None, "paymentAreaNumber": None,
                "easyParkNumber": None, "payStayNumber": None,
            },
            "capture": {}, "bays": [],
        }

    def test_each_identifier_alone(self):
        for field, value in (("parkingAreaNumber", "MCC-TA"), ("permitNumber", "MCC-TA01"),
                             ("parkingAreaNumber", "02")):
            with self.subTest(field=field, value=value):
                p = copy.deepcopy(self.payload)
                p["segment"]["parkingAreaNumber"] = None
                p["segment"][field] = value
                validate_segment_payload(p)
        for provider, prefix, field in (("EasyPark", "EP", "easyParkNumber"), ("PayStay", "PS", "payStayNumber")):
            with self.subTest(provider=provider):
                p = copy.deepcopy(self.payload)
                p["segment"].update(parkingAreaNumber=None, paymentProvider=provider,
                                    paymentRequired=True, paymentAreaNumber=f"{prefix}-007093")
                p["segment"][field] = f"{prefix}-007093"
                validate_segment_payload(p)

    def test_blank_and_invalid_identifier_types_rejected(self):
        for value in (None, "", "  ", 2, [], {}):
            with self.subTest(value=value):
                self.payload["segment"]["parkingAreaNumber"] = value
                with self.assertRaises(ValueError):
                    validate_segment_payload(self.payload)

    def test_provider_contract_rejected_when_inconsistent(self):
        for update in (
            {"paymentProvider": "other"}, {"paymentProvider": []},
            {"paymentProvider": "EasyPark", "paymentRequired": True},
            {"paymentAreaNumber": "EP-7093"},
            {"paymentRequired": True},
            {"paymentProvider": "PayStay", "paymentRequired": True, "paymentAreaNumber": "EP-7093"},
            {"paymentProvider": "EasyPark", "paymentRequired": True, "paymentAreaNumber": "EP-7093", "payStayNumber": "EP-7093"},
        ):
            with self.subTest(update=update):
                p = copy.deepcopy(self.payload)
                p["segment"].update(update)
                with self.assertRaises(ValueError):
                    validate_segment_payload(p)

    def test_unnumbered_still_needs_identifier(self):
        self.payload["segment"]["numberingMode"] = "unnumbered"
        validate_segment_payload(self.payload)
        self.payload["segment"]["parkingAreaNumber"] = None
        with self.assertRaises(ValueError):
            validate_segment_payload(self.payload)

    def test_legacy_v2_still_accepted(self):
        self.payload["schema"] = "civicmaps.parking_segment.v2"
        self.payload["segment"] = {
            "street": "TALBOT STREET", "between": ["COWPER STREET", "DEAD END"],
            "side": "NORTH", "parkingAreaNumber": "02", "easyParkNumber": "02",
        }
        validate_segment_payload(self.payload)


if __name__ == "__main__":
    unittest.main()
