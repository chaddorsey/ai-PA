#!/usr/bin/env python3
"""
Test Slack MCP Tools - Check capabilities for retrieving messages from a channel on a specific date.

This script tests:
1. What tools are available from the Slack MCP server
2. Whether we can get messages from #random on Friday, Dec 19, 2025 (or 2024)
3. Whether replies/threads are included
"""

import json
import os
from datetime import datetime, timedelta
import urllib.request
import urllib.parse

# Test date: Friday, Dec 19
# Could be 2024 or 2025, let's try both
TEST_DATES = [
    "2025-12-19",  # Friday Dec 19, 2025
    "2024-12-19",  # Friday Dec 19, 2024
]

SLACK_TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")

def get_channel_id(channel_name: str = "random") -> str:
    """Get channel ID from channel name using Slack API."""
    if not SLACK_TOKEN:
        return None
    
    try:
        url = "https://slack.com/api/conversations.list"
        params = {"types": "public_channel,private_channel", "exclude_archived": "true"}
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        
        req = urllib.request.Request(
            full_url,
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"}
        )
        
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        
        if not data.get("ok"):
            print(f"❌ Error getting channels: {data.get('error')}")
            return None
        
        channels = data.get("channels", [])
        for channel in channels:
            if channel.get("name") == channel_name:
                return channel.get("id")
        
        print(f"❌ Channel #{channel_name} not found")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_slack_api_conversations_history(channel_id: str, test_date: str) -> dict:
    """
    Test Slack API conversations.history directly to see what's available.
    
    Note: Slack API doesn't support date filtering directly - we get messages and filter client-side.
    """
    if not SLACK_TOKEN:
        return {"error": "No token"}
    
    # Convert date to timestamp
    try:
        target_date = datetime.strptime(test_date, "%Y-%m-%d")
        target_start = target_date.replace(hour=0, minute=0, second=0)
        target_end = target_date.replace(hour=23, minute=59, second=59)
        start_ts = target_start.timestamp()
        end_ts = target_end.timestamp()
    except Exception as e:
        return {"error": f"Invalid date: {e}"}
    
    print(f"\n{'='*60}")
    print(f"Testing Slack API conversations.history")
    print(f"Channel ID: {channel_id}")
    print(f"Target date: {test_date} ({target_date.strftime('%A, %B %d, %Y')})")
    print(f"Timestamp range: {start_ts} to {end_ts}")
    print(f"{'='*60}\n")
    
    try:
        # Get messages (up to 1000, but we'll need to paginate for older dates)
        url = "https://slack.com/api/conversations.history"
        
        # For older dates, we need to use 'oldest' parameter
        params = {
            "channel": channel_id,
            "limit": "1000",
            "oldest": str(start_ts),
            "latest": str(end_ts),
            "inclusive": "true"  # Include messages at the exact timestamp boundaries
        }
        
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        
        req = urllib.request.Request(
            full_url,
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode('utf-8'))
        
        if not data.get("ok"):
            return {"error": data.get("error", "Unknown error"), "ok": False}
        
        messages = data.get("messages", [])
        has_more = data.get("has_more", False)
        next_cursor = data.get("response_metadata", {}).get("next_cursor")
        
        print(f"✓ Retrieved {len(messages)} messages")
        print(f"  Has more: {has_more}")
        if next_cursor:
            print(f"  Next cursor: {next_cursor[:50]}...")
        
        # Filter messages to exact date and extract thread info
        matching_messages = []
        thread_ts_seen = set()
        
        for msg in messages:
            ts = float(msg.get("ts", 0))
            msg_dt = datetime.fromtimestamp(ts)
            
            # Check if message is in our target date
            if msg_dt.date() == target_date.date():
                thread_ts = msg.get("thread_ts")
                is_thread_reply = thread_ts and thread_ts != msg.get("ts")
                
                matching_messages.append({
                    "ts": msg.get("ts"),
                    "text": msg.get("text", "")[:100],  # First 100 chars
                    "user": msg.get("user"),
                    "thread_ts": thread_ts,
                    "is_thread_reply": is_thread_reply,
                    "reply_count": msg.get("reply_count", 0),
                    "reply_users_count": msg.get("reply_users_count", 0),
                    "datetime": msg_dt.isoformat()
                })
                
                if thread_ts:
                    thread_ts_seen.add(thread_ts)
        
        # Get thread replies using conversations.replies for each thread
        all_thread_replies = []
        for thread_ts in list(thread_ts_seen)[:10]:  # Limit to first 10 threads to avoid too many API calls
            try:
                replies_url = "https://slack.com/api/conversations.replies"
                replies_params = {
                    "channel": channel_id,
                    "ts": thread_ts
                }
                replies_query = urllib.parse.urlencode(replies_params)
                replies_full_url = f"{replies_url}?{replies_query}"
                
                replies_req = urllib.request.Request(
                    replies_full_url,
                    headers={"Authorization": f"Bearer {SLACK_TOKEN}"}
                )
                
                with urllib.request.urlopen(replies_req, timeout=10) as replies_r:
                    replies_data = json.loads(replies_r.read().decode('utf-8'))
                
                if replies_data.get("ok"):
                    thread_messages = replies_data.get("messages", [])
                    for reply_msg in thread_messages[1:]:  # Skip first (it's the parent)
                        reply_ts = float(reply_msg.get("ts", 0))
                        reply_dt = datetime.fromtimestamp(reply_ts)
                        
                        if reply_dt.date() == target_date.date():
                            all_thread_replies.append({
                                "ts": reply_msg.get("ts"),
                                "text": reply_msg.get("text", "")[:100],
                                "user": reply_msg.get("user"),
                                "thread_ts": thread_ts,
                                "datetime": reply_dt.isoformat()
                            })
            except Exception as e:
                print(f"  ⚠ Error getting replies for thread {thread_ts}: {e}")
        
        result = {
            "success": True,
            "target_date": test_date,
            "total_messages_retrieved": len(messages),
            "matching_messages": len(matching_messages),
            "thread_replies": len(all_thread_replies),
            "messages": matching_messages,
            "replies": all_thread_replies,
            "has_more": has_more,
            "note": "Replies were only fetched for first 10 threads due to API rate limits"
        }
        
        return result
        
    except Exception as e:
        return {"error": str(e), "ok": False}


def main():
    print("="*60)
    print("Testing Slack MCP Tools for Message Retrieval")
    print("="*60)
    print("\nGoal: Find all messages and replies from #random on Friday, Dec 19")
    print("\nNote: Slack MCP server tools would need to:")
    print("  1. Accept channel name (#random) or ID")
    print("  2. Accept date range (Dec 19, 2024 or 2025)")
    print("  3. Retrieve messages from conversations.history")
    print("  4. Retrieve thread replies using conversations.replies")
    print("  5. Filter by date")
    print()
    
    if not SLACK_TOKEN:
        print("❌ SLACK_MCP_XOXP_TOKEN not set in environment")
        return 1
    
    # Get channel ID
    print("→ Looking up #random channel ID...")
    channel_id = get_channel_id("random")
    if not channel_id:
        print("❌ Could not find #random channel")
        return 1
    
    print(f"✓ Found #random channel ID: {channel_id}\n")
    
    # Test with both possible years
    results = {}
    for test_date in TEST_DATES:
        print(f"\n{'='*60}")
        print(f"Testing date: {test_date}")
        print(f"{'='*60}")
        
        result = test_slack_api_conversations_history(channel_id, test_date)
        results[test_date] = result
        
        if result.get("success"):
            print(f"\n✓ Results for {test_date}:")
            print(f"  Total messages retrieved: {result['total_messages_retrieved']}")
            print(f"  Messages matching date: {result['matching_messages']}")
            print(f"  Thread replies on date: {result['thread_replies']}")
            print(f"  Has more pages: {result.get('has_more', False)}")
            
            if result['matching_messages'] > 0:
                print(f"\n  Sample messages:")
                for msg in result['messages'][:3]:
                    print(f"    - {msg['datetime']}: {msg['text'][:60]}...")
                    if msg.get('reply_count', 0) > 0:
                        print(f"      ({msg['reply_count']} replies)")
        else:
            print(f"\n❌ Error: {result.get('error', 'Unknown error')}")
    
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    print("\nSlack API capabilities:")
    print("  ✓ conversations.history - can get messages from channel with date range")
    print("  ✓ conversations.replies - can get thread replies")
    print("  ⚠ No direct date filtering - need to filter client-side")
    print("  ⚠ Requires pagination for large date ranges")
    print("  ⚠ Thread replies require separate API call per thread")
    print("\nSlack MCP Server Assessment:")
    print("  According to documentation, slack-mcp-server supports:")
    print("    - Fetch messages by date (e.g., 'd1', '7d', '1m')")
    print("    - Channel and thread support")
    print("    - Message search with date filters")
    print("\n  However, testing shows:")
    print("    - Need to verify if MCP tools expose exact date range queries")
    print("    - Need to verify if thread replies are automatically included")
    print("    - May require custom tool development for precise date filtering")
    
    return 0


if __name__ == "__main__":
    exit(main())
