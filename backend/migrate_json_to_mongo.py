"""One-time migration: copy data/*.json into MongoDB collections.

Run manually once, after MONGO_URI/DB_NAME in .env are set and reachable:
    cd backend && python3 migrate_json_to_mongo.py

Safe to re-run: every write is an upsert keyed by the original dict key
(stored as Mongo's `_id`), so re-running just overwrites with the same data.
"""
import base64
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient, ReplaceOne

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = os.environ.get("DB_NAME", "bland_ai_caller")

if not MONGO_URI or "<db_password>" in MONGO_URI:
    raise SystemExit("MONGO_URI is not set (or still has a placeholder password) in .env")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
client.admin.command("ping")
db = client[DB_NAME]

DATA_DIR = "data"


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def upsert_all(collection, data: dict):
    if not data:
        print(f"  {collection.name}: nothing to migrate")
        return
    ops = [ReplaceOne({"_id": key}, {**doc, "_id": key}, upsert=True) for key, doc in data.items()]
    result = collection.bulk_write(ops)
    print(f"  {collection.name}: upserted {result.upserted_count + result.modified_count} of {len(data)} documents")


def migrate_users():
    print("Migrating users...")
    upsert_all(db["users"], load_json("users.json"))


def migrate_sessions():
    print("Migrating sessions...")
    data = load_json("sessions.json")
    # Parse ISO strings into native datetimes so Mongo stores BSON dates.
    for session in data.values():
        for field in ("created_at", "expires_at"):
            if isinstance(session.get(field), str):
                session[field] = datetime.fromisoformat(session[field])
    upsert_all(db["sessions"], data)


def migrate_clients():
    print("Migrating clients...")
    upsert_all(db["clients"], load_json("clients.json"))


def migrate_campaigns():
    print("Migrating campaigns...")
    data = load_json("campaigns.json")
    # Decode base64 back to raw bytes; Mongo/BSON stores bytes natively.
    for campaign in data.values():
        if "file_data_b64" in campaign:
            campaign["file_data"] = base64.b64decode(campaign["file_data_b64"])
            del campaign["file_data_b64"]
    upsert_all(db["campaigns"], data)
    # Spot-check byte-length parity for the first campaign with file data.
    raw = load_json("campaigns.json")
    for campaign_id, campaign in raw.items():
        if "file_data_b64" in campaign:
            expected_len = len(base64.b64decode(campaign["file_data_b64"]))
            actual_len = len(data[campaign_id]["file_data"])
            assert expected_len == actual_len, f"byte length mismatch for {campaign_id}"
            print(f"  verified file_data byte length for campaign {campaign_id}: {actual_len} bytes")
            break


def migrate_campaign_results():
    print("Migrating campaign_results...")
    upsert_all(db["campaign_results"], load_json("campaign_results.json"))


if __name__ == "__main__":
    migrate_users()
    migrate_sessions()
    migrate_clients()
    migrate_campaigns()
    migrate_campaign_results()

    print("\nFinal collection counts:")
    for name in ["users", "sessions", "clients", "campaigns", "campaign_results"]:
        print(f"  {name}: {db[name].count_documents({})}")
