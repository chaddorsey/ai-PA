#!/usr/bin/env python3
"""
Test script to inspect MCP responses and troubleshoot missing summaries.

This script:
1. Fetches events from MCP for a specific calendar and date range
2. Displays the raw MCP response structure
3. Shows summary field values for all events
4. Helps identify why summaries might be empty
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add parent directory to path to import scheduling_orchestrator
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from letta.scheduling_orchestrator.mcp_client import MCPCalendarClient, MCPError


async def test_mcp_event_fetching():
    """Test MCP event fetching and inspect summary fields."""
    
    # Get MCP server URL from environment or use default
    # For local testing, use localhost instead of n8n
    default_url = os.getenv(
        "MCP_CALENDAR_SERVER_URL",
        "http://localhost:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
    )
    mcp_base_url = os.getenv("MCP_CALENDAR_SERVER_URL", default_url)
    
    # Test parameters - adjust these based on your test case
    calendar_id = os.getenv("TEST_CALENDAR_ID", "cdorsey@concord.org")
    event_id = os.getenv("TEST_EVENT_ID", "6uhtevmd3ri7n5i5rv1pge7rin")
    
    print("=" * 80)
    print("MCP Event Summary Troubleshooting Test")
    print("=" * 80)
    print(f"MCP Server URL: {mcp_base_url}")
    print(f"Calendar ID: {calendar_id}")
    print(f"Event ID to find: {event_id}")
    print()
    
    try:
        # Initialize MCP client
        client = MCPCalendarClient(base_url=mcp_base_url)
        await client.initialize()
        print("✓ MCP client initialized")
        print()
        
        # Calculate date range (today to 30 days forward)
        now = datetime.now()
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now + timedelta(days=30)
        
        after_date_iso = start_date.strftime("%Y-%m-%dT00:00:00Z")
        before_date_iso = end_date.strftime("%Y-%m-%dT23:59:59Z")
        
        print(f"Fetching events from {after_date_iso} to {before_date_iso}")
        print()
        
        # Fetch events using get_core_event_data
        events = await client.get_core_event_data(
            calendar_id=calendar_id,
            before=before_date_iso,  # END date
            after=after_date_iso     # START date
        )
        
        print(f"✓ Fetched {len(events)} events")
        print()
        
        # Find the specific event if event_id is provided
        target_event = None
        if event_id:
            for event in events:
                if event.get("id") == event_id:
                    target_event = event
                    break
        
        # Analyze all events for summary field issues
        print("=" * 80)
        print("Summary Field Analysis")
        print("=" * 80)
        print()
        
        events_with_summary = 0
        events_without_summary = 0
        events_with_empty_summary = 0
        
        summary_examples = []
        
        for i, event in enumerate(events, 1):
            event_id_val = event.get("id", "unknown")
            summary = event.get("summary", None)
            
            if summary is None:
                events_without_summary += 1
                status = "MISSING (None)"
            elif summary == "":
                events_with_empty_summary += 1
                status = "EMPTY STRING"
            else:
                events_with_summary += 1
                status = f"PRESENT: '{summary[:50]}...'"
                if len(summary_examples) < 5:
                    summary_examples.append((event_id_val, summary))
            
            # Show details for target event or first few events
            if event == target_event or (i <= 5 and not target_event):
                print(f"Event {i}: {event_id_val[:50]}...")
                print(f"  Summary: {status}")
                print(f"  Summary type: {type(summary).__name__}")
                print(f"  Summary value (repr): {repr(summary)}")
                
                # Show all fields in the event
                print(f"  All fields: {list(event.keys())}")
                
                # Show key fields
                if "start" in event:
                    print(f"  Start: {event.get('start')} (type: {type(event.get('start')).__name__})")
                if "end" in event:
                    print(f"  End: {event.get('end')} (type: {type(event.get('end')).__name__})")
                if "attendees_list" in event:
                    attendees = event.get("attendees_list", [])
                    print(f"  Attendees list: {attendees} (count: {len(attendees) if isinstance(attendees, list) else 0})")
                if "attendees_details" in event:
                    attendees_details = event.get("attendees_details", [])
                    print(f"  Attendees details: {attendees_details} (count: {len(attendees_details) if isinstance(attendees_details, list) else 0})")
                    if isinstance(attendees_details, list):
                        for attendee in attendees_details[:3]:
                            if isinstance(attendee, dict):
                                print(f"    - {attendee.get('email', 'no email')}: name='{attendee.get('name', '')}'")
                
                print()
        
        # Summary statistics
        print("=" * 80)
        print("Summary Statistics")
        print("=" * 80)
        print(f"Total events: {len(events)}")
        print(f"Events with summary: {events_with_summary}")
        print(f"Events with empty summary (''): {events_with_empty_summary}")
        print(f"Events without summary field (None): {events_without_summary}")
        print()
        
        if summary_examples:
            print("Example summaries found:")
            for eid, summary in summary_examples:
                print(f"  - {eid[:30]}...: '{summary[:60]}...'")
            print()
        
        # Detailed analysis of target event
        if target_event:
            print("=" * 80)
            print(f"Target Event Analysis: {event_id}")
            print("=" * 80)
            print()
            print("Full event structure:")
            print(json.dumps(target_event, indent=2, default=str))
            print()
            
            # Check if summary exists in different locations
            print("Summary field check:")
            print(f"  event.get('summary'): {repr(target_event.get('summary'))}")
            print(f"  'summary' in event: {'summary' in target_event}")
            print(f"  event.keys(): {list(target_event.keys())}")
            print()
            
            # Check for alternative field names
            alternative_fields = ['title', 'name', 'subject', 'eventTitle', 'event_title']
            for field in alternative_fields:
                if field in target_event:
                    print(f"  Found alternative field '{field}': {repr(target_event.get(field))}")
        
        # Test fetch_event_by_id specifically
        if event_id:
            print()
            print("=" * 80)
            print(f"Testing fetch_event_by_id for: {event_id}")
            print("=" * 80)
            print()
            
            fetched_event = await client.fetch_event_by_id(
                calendar_id=calendar_id,
                event_id=event_id,
                days_forward=30
            )
            
            if fetched_event:
                print("✓ Event found via fetch_event_by_id")
                print(f"Summary: {repr(fetched_event.get('summary'))}")
                print(f"Summary type: {type(fetched_event.get('summary')).__name__}")
                print()
                print("Full event from fetch_event_by_id:")
                print(json.dumps(fetched_event, indent=2, default=str))
            else:
                print("✗ Event NOT found via fetch_event_by_id")
                print("  (This might be because the event is outside the date range)")
        
    except MCPError as e:
        print(f"✗ MCP Error: {e.code} - {e.message}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_mcp_event_fetching())

