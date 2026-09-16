import json
import os
import uuid
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

PORT = int(os.environ.get("PORT", "8080"))
ROOT = os.path.dirname(os.path.abspath(__file__))

MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "geocapture").strip() or "geocapture"
MONGODB_COLLECTION = os.environ.get("MONGODB_COLLECTION", "road_segments").strip() or "road_segments"

_mongo_client = None


def utc_now():
    return datetime.now(timezone.utc)


def json_safe(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    return value


def get_collection():
    global _mongo_client
    if not MONGODB_URI:
        raise RuntimeError("MongoDB is not configured.")
    if _mongo_client is None:
        # One process-wide client: PyMongo manages and reuses its connection pool.
        _mongo_client = MongoClient(MONGODB_URI, appname="GeoCapture")
    return _mongo_client[MONGODB_DATABASE][MONGODB_COLLECTION]


def validate_segment_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")

    segment_id = payload.get("segmentId")
    if not isinstance(segment_id, str):
        raise ValueError("segmentId is required.")
    try:
        uuid.UUID(segment_id)
    except ValueError as exc:
        raise ValueError("segmentId must be a UUID.") from exc

    revision = payload.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise ValueError("revision must be a positive integer.")

    segment = payload.get("segment")
    capture = payload.get("capture")
    bays = payload.get("bays")

    if not isinstance(segment, dict):
        raise ValueError("segment must be an object.")
    if not isinstance(capture, dict):
        raise ValueError("capture must be an object.")
    if not isinstance(bays, list):
        raise ValueError("bays must be an array.")
    if len(bays) > 2000:
        raise ValueError("A road segment cannot contain more than 2000 capture points.")

    street = segment.get("street")
    between = segment.get("between")
    side = segment.get("side")
    if not isinstance(street, str) or not street.strip():
        raise ValueError("segment.street is required.")
    if not isinstance(between, list) or len(between) != 2 or not all(isinstance(v, str) and v.strip() for v in between):
        raise ValueError("segment.between must contain two street names.")
    if side not in {"NORTH", "SOUTH", "EAST", "WEST"}:
        raise ValueError("segment.side is invalid.")

    for index, bay in enumerate(bays):
        if not isinstance(bay, dict):
            raise ValueError(f"bays[{index}] must be an object.")
        for field in ("latitude", "longitude", "accuracy"):
            value = bay.get(field)
            if not isinstance(value, (int, float)):
                raise ValueError(f"bays[{index}].{field} must be numeric.")

    return segment_id, revision


def save_segment(payload):
    segment_id, revision = validate_segment_payload(payload)
    collection = get_collection()
    now = utc_now()

    stored_fields = {
        "schema": payload.get("schema", "civicmaps.parking_segment.v2"),
        "revision": revision,
        "segment": payload["segment"],
        "capture": payload["capture"],
        "bays": payload["bays"],
        "storage": {
            "sourceApplication": "GeoCapture",
            "state": payload.get("storageState", "active"),
            "savedReason": payload.get("savedReason", "autosave"),
        },
        "updatedAt": now,
    }

    try:
        document = collection.find_one_and_update(
            {
                "_id": segment_id,
                "$or": [
                    {"revision": {"$lt": revision}},
                    {"revision": {"$exists": False}},
                ],
            },
            {
                "$set": stored_fields,
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return document, False
    except DuplicateKeyError:
        existing = collection.find_one({"_id": segment_id})
        if existing and existing.get("revision") == revision:
            return existing, True
        stored_revision = existing.get("revision") if existing else None
        raise ValueError(f"Stale segment revision. Server revision is {stored_revision}.") from None


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(json_safe(payload), separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self.send_json(
                200,
                {
                    "status": "ok",
                    "service": "civicmaps-gps-capture",
                    "mongoConfigured": bool(MONGODB_URI),
                    "mongoDatabase": MONGODB_DATABASE,
                    "mongoCollection": MONGODB_COLLECTION,
                },
            )
            return

        if path.startswith("/api/segments/"):
            segment_id = path.removeprefix("/api/segments/")
            try:
                uuid.UUID(segment_id)
                document = get_collection().find_one({"_id": segment_id})
                if not document:
                    self.send_json(404, {"error": "Segment not found."})
                    return
                self.send_json(200, document)
            except (ValueError, RuntimeError) as exc:
                self.send_json(400 if isinstance(exc, ValueError) else 503, {"error": str(exc)})
            except PyMongoError:
                self.send_json(503, {"error": "MongoDB is temporarily unavailable."})
            return

        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/segments":
            self.send_json(404, {"error": "Not found."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        if length <= 0:
            self.send_json(400, {"error": "JSON body is required."})
            return
        if length > 2_000_000:
            self.send_json(413, {"error": "Segment payload is too large."})
            return

        try:
            payload = json.loads(self.rfile.read(length))
            document, idempotent = save_segment(payload)
            self.send_json(
                200,
                {
                    "saved": True,
                    "idempotent": idempotent,
                    "segmentId": document["_id"],
                    "revision": document["revision"],
                    "pointCount": len(document.get("bays", [])),
                    "updatedAt": document["updatedAt"],
                },
            )
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON."})
        except ValueError as exc:
            status = 409 if str(exc).startswith("Stale segment revision") else 400
            self.send_json(status, {"error": str(exc)})
        except RuntimeError as exc:
            self.send_json(503, {"error": str(exc)})
        except PyMongoError:
            self.send_json(503, {"error": "MongoDB is temporarily unavailable."})

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"CivicMAPS GPS Capture listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()
