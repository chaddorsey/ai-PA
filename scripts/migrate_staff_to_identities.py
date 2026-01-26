#!/usr/bin/env python3
"""
Migrate staff directory to Letta Identities.

Reads hardcoded staff/family data (from memory block export) and creates
Letta identities with properties:
- colloquial_name, email, slack_id, calendar_id, working_hours, working_week, imessage

Usage:
    python scripts/migrate_staff_to_identities.py --dry-run
    python scripts/migrate_staff_to_identities.py
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client or letta package not found")
        sys.exit(1)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Staff directory data (from memory block export - actual Concord staff)
STAFF_DIRECTORY: List[Dict[str, Any]] = [
    {"name": "Ethan McElroy", "email": "emcelroy@concord.org", "slack_id": "U02V96MQC", "calendar_id": "emcelroy@concord.org", "colloquial_name": "Ethan"},
    {"name": "Kirk Swenson", "email": "kswenson@concord.org", "slack_id": "U0GQHHS1W", "calendar_id": "kswenson@concord.org", "colloquial_name": "Kirk", "working_hours": "11:30AM-7:30PM"},
    {"name": "Scott Cytacki", "email": "scytacki@concord.org", "slack_id": "U02V82YB9", "calendar_id": "scytacki@concord.org", "colloquial_name": "Scott"},
    {"name": "Paul Horwitz", "email": "phorwitz@concord.org", "slack_id": "U031V0J1M", "calendar_id": "phorwitz@concord.org", "colloquial_name": "Paul"},
    {"name": "Hee-Sun Lee", "email": "hlee@concord.org", "slack_id": "U09M9UU3A", "calendar_id": "hlee@concord.org", "colloquial_name": "Hee-Sun", "working_hours": "12:00PM-5:00PM"},
    {"name": "Trudi Lord", "email": "tlord@concord.org", "slack_id": "U02V941L0", "calendar_id": "tlord@concord.org", "colloquial_name": "Trudi"},
    {"name": "Dan Damelin", "email": "ddamelin@concord.org", "slack_id": "U0303SG91", "calendar_id": "ddamelin@concord.org", "colloquial_name": "Dan"},
    {"name": "Judi Raiff", "email": "jraiff@concord.org", "slack_id": "U48DTGUGJ", "calendar_id": "jraiff@concord.org", "colloquial_name": "Judi"},
    {"name": "Cynthia McIntyre", "email": "cmcintyre@concord.org", "slack_id": "U09DXRLAH", "calendar_id": "cmcintyre@concord.org", "colloquial_name": "Cynthia"},
    {"name": "Bill Finzer", "email": "wfinzer@concord.org", "slack_id": "U02VCM7TL", "calendar_id": "wfinzer@concord.org", "colloquial_name": "Bill", "working_hours": "11:00AM-7:00PM"},
    {"name": "Kiley Brown", "email": "kbrown@concord.org", "slack_id": None, "calendar_id": "kbrown@concord.org", "colloquial_name": "Kiley"},
    {"name": "Leslie Bondaryk", "email": "lbondaryk@concord.org", "slack_id": "UACG5LG3Y", "calendar_id": "lbondaryk@concord.org", "colloquial_name": "Leslie", "working_week": "Monday-Thursday"},
    {"name": "Jie Chao", "email": "jchao@concord.org", "slack_id": "U0AEJSLQJ", "calendar_id": "jchao@concord.org", "colloquial_name": "Jie"},
    {"name": "Amy Pallant", "email": "apallant@concord.org", "slack_id": "U09LTDGKX", "calendar_id": "apallant@concord.org", "colloquial_name": "Amy", "working_week": "Monday-Thursday"},
    {"name": "Chris Lore", "email": "clore@concord.org", "slack_id": "UG8PJCU1L", "calendar_id": "clore@concord.org", "colloquial_name": "Chris", "working_week": "Monday-Thursday"},
    {"name": "Kate Miller", "email": "kmiller@concord.org", "slack_id": "U04DMBL0YAU", "calendar_id": "kmiller@concord.org", "colloquial_name": "Kate"},
    {"name": "Kathy Jessen Eller", "email": "kjesseneller@concord.org", "slack_id": "U0836P6REKF", "calendar_id": "kjesseneller@concord.org", "colloquial_name": "Kathy"},
    {"name": "Rebecca Ellis", "email": "rellis@concord.org", "slack_id": "UK486BUSX", "calendar_id": "rellis@concord.org", "colloquial_name": "Rebecca"},
    {"name": "Teale Fristoe", "email": "tfristoe@concord.org", "slack_id": "U03HRBXLJ12", "calendar_id": "tfristoe@concord.org", "colloquial_name": "Teale"},
    {"name": "Lisa Buoncuore", "email": "lbuoncuore@concord.org", "slack_id": "U09DZHHPT", "calendar_id": "lbuoncuore@concord.org", "colloquial_name": "Lisa"},
    {"name": "Danielle Kehoe", "email": "dkehoe@concord.org", "slack_id": "U09B5JUK2TY", "calendar_id": "dkehoe@concord.org", "colloquial_name": "Danielle"},
    {"name": "Sue Brau", "email": "sbrau@concord.org", "slack_id": "U09C3N5LZ", "calendar_id": "sbrau@concord.org", "colloquial_name": "Sue"},
    {"name": "Doug Martin", "email": "dmartin@concord.org", "slack_id": "U048JG9CU", "calendar_id": "dmartin@concord.org", "colloquial_name": "Doug"},
    {"name": "Lynn Stephens", "email": "lstephens@concord.org", "slack_id": "U7DMA61BN", "calendar_id": "lstephens@concord.org", "colloquial_name": "Lynn"},
    {"name": "Michael Tirenin", "email": "mtirenin@concord.org", "slack_id": "UBRAAE2FM", "calendar_id": "mtirenin@concord.org", "colloquial_name": "Michael"},
    {"name": "Aditi Wagh", "email": "awagh@concord.org", "slack_id": "U096MABDPNF", "calendar_id": "awagh@concord.org", "colloquial_name": "Aditi"},
]

# Family directory data
FAMILY_DIRECTORY: List[Dict[str, Any]] = [
    {"name": "Sophia Dorsey", "email": "sophiadorsey@gmail.com", "calendar_id": "sb06g6b1g2jlkplc1bcd7k4ofk@group.calendar.google.com", "colloquial_name": "Sophia", "imessage": "sophiadorsey@gmail.com"},
    {"name": "Liam Dorsey", "email": "liamdorsey00@gmail.com", "calendar_id": "cr89gktnjrcrtm9j9a48j060hc@group.calendar.google.com", "colloquial_name": "Liam", "imessage": "liamdorsey00@gmail.com"},
    {"name": "Liz Dorsey", "email": "lizdorsey@gmail.com", "calendar_id": "lizdorsey@gmail.com", "colloquial_name": "Liz", "imessage": "lizdorsey@gmail.com"},
    {"name": "Chad Dorsey", "email": "cdorsey@concord.org", "calendar_id": "concord.org_ouqdctthtvfm6bklntoq2rbg9s@group.calendar.google.com", "colloquial_name": "Chad", "imessage": "chaddorsey@gmail.com", "personal_email": "chaddorsey@gmail.com"},
]


def build_properties(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build properties list from staff/family data."""
    properties = []

    # Always include colloquial_name
    if data.get("colloquial_name"):
        properties.append({"key": "colloquial_name", "value": data["colloquial_name"], "type": "string"})

    # Platform IDs (skip None values)
    if data.get("slack_id"):
        properties.append({"key": "slack_id", "value": data["slack_id"], "type": "string"})
    if data.get("calendar_id"):
        properties.append({"key": "calendar_id", "value": data["calendar_id"], "type": "string"})

    # Optional fields
    if data.get("working_hours"):
        properties.append({"key": "working_hours", "value": data["working_hours"], "type": "string"})
    if data.get("working_week"):
        properties.append({"key": "working_week", "value": data["working_week"], "type": "string"})
    if data.get("imessage"):
        properties.append({"key": "imessage", "value": data["imessage"], "type": "string"})
    if data.get("personal_email"):
        properties.append({"key": "personal_email", "value": data["personal_email"], "type": "string"})

    return properties


def create_identity(client, data: Dict[str, Any], category: str, dry_run: bool = False) -> bool:
    """Create a single identity. Returns True on success."""
    email = data["email"]
    name = data["name"]
    properties = build_properties(data)

    print(f"  {name} ({email})")
    for prop in properties:
        print(f"    - {prop['key']}: {prop['value']}")

    if dry_run:
        print("    [DRY RUN - not created]")
        return True

    try:
        identity = client.identities.create(
            identifier_key=email,
            name=name,
            identity_type="user",
            properties=properties
        )
        print(f"    Created: {identity.id}")
        return True
    except Exception as e:
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str:
            print(f"    Already exists, skipping")
            return True
        else:
            print(f"    ERROR: {e}")
            return False


def main():
    """Run the migration."""
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("Staff Directory Migration to Letta Identities")
    print("=" * 60)
    print(f"\nLetta Base URL: {LETTA_BASE_URL}")
    print(f"Dry Run: {dry_run}\n")

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")
    except Exception as e:
        print(f"Failed to connect to Letta: {e}")
        return 1

    created = 0
    failed = 0

    print(f"Migrating {len(STAFF_DIRECTORY)} staff members...")
    print("-" * 40)
    for staff in STAFF_DIRECTORY:
        if create_identity(client, staff, "staff", dry_run):
            created += 1
        else:
            failed += 1

    print()
    print(f"Migrating {len(FAMILY_DIRECTORY)} family members...")
    print("-" * 40)
    for family in FAMILY_DIRECTORY:
        if create_identity(client, family, "family", dry_run):
            created += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print(f"Migration Complete: {created} created, {failed} failed")
    print("=" * 60)

    if dry_run:
        print("\nThis was a dry run. Run without --dry-run to create identities.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
