"""One-time migration: import the legacy clinic CSV location data into the
client_locations collection, matched to existing clients by name prefix.

Run manually once, after MONGO_URI/DB_NAME in .env are set and reachable:
    cd backend && python3 migrate_clinic_csv_to_client_locations.py

Safe to re-run: skips any (client_id, location_name) pair that already
exists in client_locations before inserting.
"""
import csv
import os
import uuid

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = os.environ.get("DB_NAME", "bland_ai_caller")

if not MONGO_URI or "<db_password>" in MONGO_URI:
    raise SystemExit("MONGO_URI is not set (or still has a placeholder password) in .env")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
client.admin.command("ping")
db = client[DB_NAME]

SOURCE_DIR = "clinic_source_data"
CSV_FILES = [
    ("PHPC_clinic_data_1757918909480.csv", True),   # (filename, has_phone_column)
    ("hillside_clinic_data - Clinic Locations_1756207573609.csv", False),
]


def load_clients():
    """Return list of {id, name} for every existing client."""
    return [{"id": doc["_id"], "name": doc.get("name", "")} for doc in db["clients"].find()]


def match_client(office_location: str, clients: list):
    """Return the client whose name is the longest case-insensitive prefix
    of office_location, or None if no client's name is a prefix at all."""
    location_lower = office_location.strip().lower()
    candidates = [
        c for c in clients
        if c["name"] and location_lower.startswith(c["name"].strip().lower())
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda c: len(c["name"]), reverse=True)
    return candidates[0]


def location_exists(client_id: str, location_name: str) -> bool:
    name_lower = location_name.strip().lower()
    return db["client_locations"].find_one({
        "client_id": client_id,
        "location_name": {"$regex": f"^{name_lower}$", "$options": "i"},
    }) is not None


def migrate():
    clients = load_clients()
    if not clients:
        raise SystemExit("No clients found in the clients collection - add clients before running this migration.")

    unmatched = []
    inserted = 0
    skipped = 0

    for filename, has_phone in CSV_FILES:
        path = os.path.join(SOURCE_DIR, filename)
        if not os.path.exists(path):
            print(f"WARNING: {path} not found, skipping")
            continue

        print(f"\nProcessing {filename}...")
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                office_location = (row.get("office_location") or "").strip()
                address = (row.get("Address") or "").strip()
                phone_number = (row.get("Phone_number") or "").strip() if has_phone else ""

                if not office_location:
                    continue

                matched_client = match_client(office_location, clients)
                if matched_client is None:
                    unmatched.append(office_location)
                    continue

                if location_exists(matched_client["id"], office_location):
                    print(f"  SKIP (already exists): {office_location}")
                    skipped += 1
                    continue

                location_id = str(uuid.uuid4())
                db["client_locations"].insert_one({
                    "_id": location_id,
                    "id": location_id,
                    "client_id": matched_client["id"],
                    "location_name": office_location,
                    "address": address,
                    "phone_number": phone_number,
                    "email": "",
                })
                print(f"  Inserted: '{office_location}' -> client '{matched_client['name']}'")
                inserted += 1

    print(f"\nDone. Inserted {inserted}, skipped {skipped} already-existing, {len(unmatched)} unmatched.")
    if unmatched:
        print("\nUnmatched office_location rows (no existing client name is a prefix - needs manual follow-up):")
        for name in unmatched:
            print(f"  - {name}")


if __name__ == "__main__":
    migrate()
    print(f"\nFinal client_locations count: {db['client_locations'].count_documents({})}")
