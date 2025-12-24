#!/usr/bin/env python3
"""
Test script for Slack custom tools

This script allows direct testing of Slack tools without going through Letta.
Set SLACK_MCP_XOXP_TOKEN environment variable before running.
"""

import os
import sys
import json
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slack_custom_tools import (
    get_slack_channels,
    get_slack_messages,
    search_slack_messages,
    get_slack_users
)


def print_result(tool_name, result):
    """Pretty print test result"""
    print(f"\n{'='*60}")
    print(f"{tool_name} RESULT:")
    print(f"{'='*60}")
    print(f"Status: {result.get('status')}")
    
    if result.get('status') == 'ok':
        data = result.get('data', {})
        
        # Print query for search
        if 'query' in data:
            print(f"Query used: {data.get('query')}")
        
        # Print counts
        if 'total_results' in data:
            print(f"Total results: {data.get('total_results')}")
        if 'messages' in data:
            print(f"Messages returned: {len(data.get('messages', []))}")
        if 'users' in data:
            print(f"Users returned: {len(data.get('users', []))}")
        if 'channels' in data:
            print(f"Channels returned: {len(data.get('channels', []))}")
        if 'channel' in data:
            print(f"Channel: {data.get('channel', {}).get('name', 'N/A')}")
        if 'user' in data:
            print(f"User: {data.get('user', {}).get('name', 'N/A')}")
        
        # Print first item preview if available
        for key in ['messages', 'users', 'channels']:
            items = data.get(key, [])
            if items:
                first = items[0]
                print(f"\nFirst {key[:-1]} preview:")
                if key == 'messages':
                    print(f"  User: {first.get('username')} ({first.get('user')})")
                    print(f"  Channel: {first.get('channel_name')} ({first.get('channel_id')})")
                    print(f"  Text: {first.get('text', '')[:100]}...")
                elif key == 'users':
                    print(f"  Name: {first.get('name')} ({first.get('id')})")
                    print(f"  Email: {first.get('email', 'N/A')}")
                elif key == 'channels':
                    print(f"  Name: {first.get('name')} ({first.get('id')})")
                    print(f"  Purpose: {first.get('purpose', {}).get('value', 'N/A')[:50]}...")
                break
        
        # Print full JSON if small enough
        result_str = json.dumps(result, indent=2)
        if len(result_str) < 2000:
            print(f"\nFull result:\n{result_str}")
        else:
            print(f"\n(Result too large to display - {len(result_str)} chars)")
    else:
        print(f"Error: {result.get('error_message', 'Unknown error')}")
    
    print(f"{'='*60}\n")


def test_search_slack_messages():
    """Test search_slack_messages with the problematic case"""
    print("\n" + "="*60)
    print("TEST: search_slack_messages")
    print("="*60)
    
    result = search_slack_messages(
        query="http",
        user="U048JG9CU,U02V82YB9",
        channel="C04V4FP7F5F",
        start_date="2025-12-19",
        end_date="2025-12-19",
        count=40,
        sort="timestamp",
        sort_by="",
        min_reactions=0,
        min_reply_count=0,
        only_thread_parents=False,
        has_reactions=False
    )
    
    print_result("search_slack_messages", result)
    return result


def test_get_slack_users():
    """Test get_slack_users with email addresses"""
    print("\n" + "="*60)
    print("TEST: get_slack_users (email addresses)")
    print("="*60)
    
    result = get_slack_users(
        user="dmartin@concord.org,scytacki@concord.org",
        include_deleted=False,
        limit=10
    )
    
    print_result("get_slack_users", result)
    return result


def test_get_slack_messages():
    """Test get_slack_messages with date range"""
    print("\n" + "="*60)
    print("TEST: get_slack_messages")
    print("="*60)
    
    result = get_slack_messages(
        channel="C04V4FP7F5F",
        start_date="2025-12-19",
        end_date="2025-12-19",
        message_ts="",
        limit=100,
        include_thread_replies=True,
        include_context=False,
        context_count=5,
        only_thread_parents=False,
        min_reply_count=None,
        sort_by="timestamp",
        sort_order="asc",
        min_reactions=0,
        has_reactions=False
    )
    
    print_result("get_slack_messages", result)
    return result


def main():
    """Run all tests"""
    token = os.getenv("SLACK_MCP_XOXP_TOKEN")
    if not token:
        print("ERROR: SLACK_MCP_XOXP_TOKEN environment variable not set")
        print("Set it before running: export SLACK_MCP_XOXP_TOKEN='your-token'")
        sys.exit(1)
    
    print(f"Token found (length: {len(token)})")
    
    # Run tests
    test_search_slack_messages()
    # Uncomment to test other tools:
    # test_get_slack_users()
    # test_get_slack_messages()


if __name__ == "__main__":
    main()

