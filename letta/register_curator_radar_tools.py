#!/usr/bin/env python3
"""Register Curator Radar tools with Letta."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from letta_client import Letta
from curator_radar_tools import query_curator_radar

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def register():
    client = Letta(base_url=LETTA_BASE_URL)
    tool = client.tools.upsert_from_function(
        func=query_curator_radar,
        tags=["curator-radar", "github", "discovery"],
    )
    print(f"Registered: {tool.name} ({tool.id})")


if __name__ == "__main__":
    register()
