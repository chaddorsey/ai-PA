#!/usr/bin/env python3
"""
Migrate staff properties to Letta identities.

This script:
1. Fetches all identities from Letta
2. Matches them against staff_data.py by email (identifier_key)
3. Adds properties: title, home_state, home_city, us_region, home_office
4. Adds multi-value properties as JSON: roles, departments, projects

Note: Letta identity API doesn't support tags, so multi-value data is
stored as JSON string properties for querying.

Usage:
    python migrate_staff_properties.py --dry-run  # Preview changes
    python migrate_staff_properties.py            # Apply changes
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests

# Import staff data
from staff_data import STAFF_DATA, VALID_DEPARTMENTS, VALID_ROLES, VALID_US_REGIONS

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")


def fetch_all_identities() -> List[Dict]:
    """Fetch all identities from Letta API."""
    response = requests.get(f"{LETTA_BASE_URL}/v1/identities/", timeout=30)
    response.raise_for_status()
    return response.json()


def get_property(properties: List[Dict], key: str) -> Optional[str]:
    """Get a property value by key."""
    for prop in properties:
        if isinstance(prop, dict) and prop.get("key") == key:
            return prop.get("value")
    return None


def update_identity(identity_id: str, properties: List[Dict]) -> bool:
    """Update an identity's properties via Letta API."""
    response = requests.patch(
        f"{LETTA_BASE_URL}/v1/identities/{identity_id}",
        json={"properties": properties},
        timeout=30
    )
    return response.status_code == 200


def build_projects_json(staff_info: Dict) -> str:
    """Build JSON string of projects with roles."""
    projects = []
    for project in staff_info.get("projects", []):
        proj_entry = {"name": project["name"]}
        if project.get("role"):
            proj_entry["role"] = project["role"]
        projects.append(proj_entry)
    return json.dumps(projects)


def migrate_identity(identity: Dict, dry_run: bool = True) -> Optional[Dict]:
    """
    Migrate a single identity to add staff properties and tags.

    Returns:
        Dict with migration details, or None if no migration needed
    """
    identity_id = identity.get("id")
    name = identity.get("name", "Unknown")
    email = identity.get("identifier_key", "")
    properties = identity.get("properties") or []

    # Skip non-Concord staff
    if not email.endswith("@concord.org"):
        return None

    # Check if we have staff data for this email
    staff_info = STAFF_DATA.get(email)
    if not staff_info:
        return {
            "identity_id": identity_id,
            "name": name,
            "email": email,
            "status": "skipped",
            "reason": "No staff data found",
        }

    # Check if already migrated (has title property)
    existing_title = get_property(properties, "title")
    if existing_title:
        return {
            "identity_id": identity_id,
            "name": name,
            "email": email,
            "status": "skipped",
            "reason": f"Already has title: {existing_title}",
        }

    # Build new properties list (preserve existing)
    new_properties = []
    keys_to_add = {"title", "home_state", "home_city", "us_region", "home_office", "roles", "departments", "projects"}

    for prop in properties:
        if isinstance(prop, dict) and prop.get("key") not in keys_to_add:
            new_properties.append(prop)

    # Add new properties
    new_properties.append({"key": "title", "value": staff_info["title"], "type": "string"})
    new_properties.append({"key": "home_state", "value": staff_info["home_state"], "type": "string"})
    new_properties.append({"key": "us_region", "value": staff_info["us_region"], "type": "string"})
    new_properties.append({"key": "home_office", "value": staff_info["home_office"], "type": "string"})

    if staff_info.get("home_city"):
        new_properties.append({"key": "home_city", "value": staff_info["home_city"], "type": "string"})

    # Add multi-value properties as JSON strings
    if staff_info.get("roles"):
        new_properties.append({"key": "roles", "value": json.dumps(staff_info["roles"]), "type": "string"})
    if staff_info.get("departments"):
        new_properties.append({"key": "departments", "value": json.dumps(staff_info["departments"]), "type": "string"})
    if staff_info.get("projects"):
        new_properties.append({"key": "projects", "value": build_projects_json(staff_info), "type": "string"})

    migration_info = {
        "identity_id": identity_id,
        "name": name,
        "email": email,
        "status": "migrated",
        "title": staff_info["title"],
        "home_state": staff_info["home_state"],
        "home_city": staff_info.get("home_city"),
        "us_region": staff_info["us_region"],
        "home_office": staff_info["home_office"],
        "roles": staff_info.get("roles", []),
        "departments": staff_info.get("departments", []),
        "projects": staff_info.get("projects", []),
    }

    if not dry_run:
        success = update_identity(identity_id, new_properties)
        migration_info["success"] = success

    return migration_info


def main():
    parser = argparse.ArgumentParser(description="Migrate staff properties to identities")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    print(f"Fetching identities from {LETTA_BASE_URL}...")
    identities = fetch_all_identities()
    print(f"Found {len(identities)} identities\n")

    migrations = []
    skipped = []

    for identity in identities:
        result = migrate_identity(identity, dry_run=args.dry_run)
        if result:
            if result.get("status") == "migrated":
                migrations.append(result)
            else:
                skipped.append(result)

    # Report skipped
    if skipped:
        print(f"Skipped ({len(skipped)} identities):\n")
        for s in skipped:
            print(f"  {s['name']} ({s['email']}): {s['reason']}")
        print()

    # Report migrations
    if not migrations:
        print("No migrations needed.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Migrations ({len(migrations)} identities):\n")

    for m in migrations:
        print(f"  {m['name']} ({m['email']})")
        print(f"    title: {m['title']}")
        print(f"    location: {m['home_city'] or m['home_state']}, {m['us_region']}")
        print(f"    home_office: {m['home_office']}")

        # Projects with PI/Co-PI roles
        if m.get('projects'):
            project_names = [p["name"] for p in m["projects"]]
            pi_projects = [p["name"] for p in m["projects"] if p.get("role") == "pi"]
            copi_projects = [p["name"] for p in m["projects"] if p.get("role") == "copi"]

            print(f"    projects: {', '.join(project_names)}")
            if pi_projects:
                print(f"    PI on: {', '.join(pi_projects)}")
            if copi_projects:
                print(f"    Co-PI on: {', '.join(copi_projects)}")

        # Roles and departments
        if m.get('roles'):
            print(f"    roles: {', '.join(m['roles'])}")
        if m.get('departments'):
            print(f"    departments: {', '.join(m['departments'])}")

        if not args.dry_run:
            status = "✓" if m.get('success') else "✗"
            print(f"    {status} {'Updated' if m.get('success') else 'FAILED'}")
        print()

    # Summary
    print(f"Summary: {len(migrations)} staff to migrate, {len(skipped)} skipped")

    # Check for staff in STAFF_DATA not found in identities
    identity_emails = {i.get("identifier_key", "").lower() for i in identities}
    missing_identities = []
    for email in STAFF_DATA.keys():
        if email.lower() not in identity_emails:
            missing_identities.append(email)

    if missing_identities:
        print(f"\nWarning: {len(missing_identities)} staff in data file not found in identities:")
        for email in missing_identities:
            print(f"  - {email}")

    if args.dry_run:
        print("\nRun without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
