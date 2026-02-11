"""
Slack Custom Tools for Letta

Four optimized tools for Slack monitoring and information extraction:
1. get_slack_channels - Channel discovery and information
2. get_slack_messages - Messages from channels with complete context
3. search_slack_messages - Workspace-wide message search
4. get_slack_users - User discovery and information

All tools follow Letta compliance requirements:
- Return Dict[str, Any] (not JSON strings)
- Imports inside functions at the beginning
- No nested def statements (all logic inlined)
- Comprehensive try-except wrappers
"""

from typing import Dict, Any, Optional, List


def get_slack_channels(
    channel: Optional[str] = None,
    types: Optional[str] = None,
    exclude_archived: Optional[bool] = True,
    include_members: Optional[bool] = False,
    limit: Optional[int] = 500
) -> Dict[str, Any]:
    """
    Get Slack channel information - list all channels, get specific channel details, or resolve channel names.

    When channel parameter is provided, returns single channel (or multiple if comma-separated).
    When channel parameter is omitted, returns list of all channels.

    Args:
        channel: Channel ID(s) or name(s) (e.g., "C1234567890", "#random", or "#general,#random").
                 Can be a single channel or comma-separated list. If omitted, returns list of all channels.
        types: Filter channel types when listing. Comma-separated: "public_channel,private_channel,mpim,im".
               Default: all types.
        exclude_archived: Exclude archived channels when listing. Default: True.
        include_members: Include member list for single channel. Default: False.
        limit: Maximum number of channels to return when listing. Default: 500.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - data: Channel data (single channel object, list of channels, or array for multiple channels)
        - error_message: Error message if status is "error"
    """
    # Imports inside function at the very beginning
    import os
    import traceback
    import json
    import urllib.request
    import urllib.parse
    from datetime import datetime
    
    # Wrap entire function in try-except
    try:
        # Get token
        TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
        if not TOKEN:
            return {
                "status": "error",
                "data": {},
                "error_message": "SLACK_MCP_XOXP_TOKEN not set in environment"
            }
        
        # Normalize channel parameter - handle both single value and list
        channel_list = []
        is_single = False
        is_multiple = False
        
        if channel is not None:
            if isinstance(channel, str):
                channel_list = [channel]
                is_single = True
            elif isinstance(channel, list):
                channel_list = channel
                is_multiple = len(channel) > 1
                is_single = len(channel) == 1
            else:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"channel parameter must be string or list, got {type(channel)}"
                }
        
        # Set defaults
        if limit is None:
            limit = 500
        if exclude_archived is None:
            exclude_archived = True
        if include_members is None:
            include_members = False
        
        # If channel(s) specified, get specific channel(s)
        if channel_list:
            resolved_channels = []
            for ch in channel_list:
                # Inline channel resolution logic
                resolved_id = ch
                if not ch.startswith(("C", "G", "D", "mpdm-")):
                    # Need to resolve name to ID
                    channel_name = ch.lstrip("#")
                    try:
                        url = "https://slack.com/api/conversations.list"
                        params = {"limit": "1000", "exclude_archived": "true"}
                        query_string = urllib.parse.urlencode(params)
                        req = urllib.request.Request(
                            f"{url}?{query_string}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        with urllib.request.urlopen(req, timeout=30) as r:
                            data = json.loads(r.read().decode('utf-8'))
                            if data.get("ok"):
                                found = False
                                for ch_item in data.get("channels", []):
                                    if ch_item.get("name") == channel_name:
                                        resolved_id = ch_item.get("id")
                                        found = True
                                        break
                                if not found:
                                    resolved_id = ch
                    except Exception:
                        resolved_id = ch
                else:
                    resolved_id = ch.lstrip("#")
                
                # Get channel info (inline)
                try:
                    url = "https://slack.com/api/conversations.info"
                    params = {"channel": resolved_id}
                    if include_members:
                        params["include_num_members"] = "true"
                    query_string = urllib.parse.urlencode(params)
                    req = urllib.request.Request(
                        f"{url}?{query_string}",
                        headers={"Authorization": f"Bearer {TOKEN}"}
                    )
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        if not data.get("ok"):
                            if is_single:
                                return {
                                    "status": "error",
                                    "data": {},
                                    "error_message": f"Error getting channel {ch}: {data.get('error', 'Unknown error')}"
                                }
                            continue
                        
                        channel_data = data.get("channel", {})
                        
                        # Format response (inline)
                        ch_info = {
                            "id": channel_data.get("id"),
                            "name": channel_data.get("name"),
                            "is_channel": channel_data.get("is_channel", False),
                            "is_group": channel_data.get("is_group", False),
                            "is_im": channel_data.get("is_im", False),
                            "is_mpim": channel_data.get("is_mpim", False),
                            "is_private": channel_data.get("is_private", False),
                            "is_archived": channel_data.get("is_archived", False),
                            "created": channel_data.get("created"),
                            "creator": channel_data.get("creator"),
                            "topic": channel_data.get("topic", {}).get("value", ""),
                            "purpose": channel_data.get("purpose", {}).get("value", ""),
                            "num_members": channel_data.get("num_members")
                        }
                        
                        # Get members if requested (inline)
                        if include_members:
                            members = []
                            try:
                                members_url = "https://slack.com/api/conversations.members"
                                members_params = {"channel": resolved_id, "limit": "1000"}
                                members_query = urllib.parse.urlencode(members_params)
                                members_req = urllib.request.Request(
                                    f"{members_url}?{members_query}",
                                    headers={"Authorization": f"Bearer {TOKEN}"}
                                )
                                with urllib.request.urlopen(members_req, timeout=30) as mr:
                                    members_data = json.loads(mr.read().decode('utf-8'))
                                    if members_data.get("ok"):
                                        members = members_data.get("members", [])
                            except Exception:
                                pass
                            ch_info["members"] = members
                        
                        resolved_channels.append(ch_info)
                except Exception as e:
                    if is_single:
                        return {
                            "status": "error",
                            "data": {},
                            "error_message": f"Error getting channel {ch}: {str(e)}"
                        }
                    continue
            
            # Return appropriate structure
            if is_single:
                return {
                    "status": "ok",
                    "data": {
                        "channel": resolved_channels[0] if resolved_channels else {}
                    }
                }
            else:
                return {
                    "status": "ok",
                    "data": {
                        "channels": resolved_channels
                    }
                }
        
        # Otherwise, list all channels
        url = "https://slack.com/api/conversations.list"
        params = {"limit": str(limit)}
        if exclude_archived:
            params["exclude_archived"] = "true"
        
        # Handle types filter
        if types:
            type_list = [t.strip() for t in types.split(",")]
            params["types"] = ",".join(type_list)
        
        query_string = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{url}?{query_string}",
            headers={"Authorization": f"Bearer {TOKEN}"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode('utf-8'))
            
            if not data.get("ok"):
                return {
                    "status": "error",
                    "data": {},
                    "error_message": data.get("error", "Unknown Slack API error")
                }
            
            channels = data.get("channels", [])
            
            # Format channels (inline)
            formatted_channels = []
            for ch in channels:
                formatted_channels.append({
                    "id": ch.get("id"),
                    "name": ch.get("name"),
                    "is_channel": ch.get("is_channel", False),
                    "is_group": ch.get("is_group", False),
                    "is_im": ch.get("is_im", False),
                    "is_mpim": ch.get("is_mpim", False),
                    "is_private": ch.get("is_private", False),
                    "is_archived": ch.get("is_archived", False),
                    "created": ch.get("created"),
                    "creator": ch.get("creator"),
                    "topic": ch.get("topic", {}).get("value", ""),
                    "purpose": ch.get("purpose", {}).get("value", ""),
                    "num_members": ch.get("num_members")
                })
            
            return {
                "status": "ok",
                "data": {
                    "channels": formatted_channels,
                    "total": len(formatted_channels)
                }
            }
    
    except Exception as e:
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_slack_messages(
    channel: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    message_ts: Optional[str] = None,
    limit: Optional[int] = 100,
    include_thread_replies: Optional[bool] = True,
    include_context: Optional[bool] = False,
    context_count: Optional[int] = 5,
    only_thread_parents: Optional[bool] = False,
    min_reply_count: Optional[int] = None,
    sort_by: Optional[str] = "timestamp",
    sort_order: Optional[str] = "desc",
    min_reactions: Optional[int] = None,
    has_reactions: Optional[bool] = False
) -> Dict[str, Any]:
    """
    Get messages from Slack channel(s) with complete context including threads, files, links, and reactions.
    
    Supports both single channel and multiple channels. When multiple channels provided,
    returns messages grouped by channel.
    
    Args:
        channel: Channel ID(s) or name(s) (e.g., "C1234567890", "#random", or "#general,#random").
                 Can be a single channel or comma-separated list of channels.
        start_date: Start date in YYYY-MM-DD format or ISO 8601 datetime. Default: None (no start limit).
        end_date: End date in YYYY-MM-DD format or ISO 8601 datetime. Default: None (no end limit).
        message_ts: Specific message timestamp to retrieve (e.g., "1703001234.567890"). When provided, returns single message with optional context. Default: None.
        limit: Maximum messages to return per channel. Default: 100, max: 1000.
        include_thread_replies: Fetch all thread replies. Default: True.
        include_context: Include surrounding messages when message_ts provided. Default: False.
        context_count: Number of messages before/after to include. Default: 5.
        only_thread_parents: Return only messages that have replies. Default: False.
        min_reply_count: Filter messages with at least N replies (thread parents only). Default: None.
        sort_by: Sort order: "timestamp" (default), "reactions", "reply_count", "user".
        sort_order: "asc" or "desc". Default: "desc" for timestamp, "desc" for reactions/reply_count.
        min_reactions: Filter messages with at least N reactions. Default: None.
        has_reactions: Return only messages with reactions. Default: False.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - data: Message data (varies based on single vs multiple channels, see specification)
        - error_message: Error message if status is "error"
    """
    # Imports inside function at the very beginning
    import os
    import traceback
    import json
    import urllib.request
    import urllib.parse
    from datetime import datetime, timezone
    import re

    # Wrap entire function in try-except
    try:
        # Get token
        TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
        if not TOKEN:
            return {
                "status": "error",
                "data": {},
                "error_message": "SLACK_MCP_XOXP_TOKEN not set in environment"
            }
        
        # Normalize channel parameter - handle single value, comma-separated, or list (for backward compatibility)
        if isinstance(channel, str):
            # Single channel or comma-separated
            if ',' in channel:
                channel_list = [ch.strip() for ch in channel.split(',')]
            else:
                channel_list = [channel]
        elif isinstance(channel, list):
            # Support list for backward compatibility (though Letta schema only allows str)
            channel_list = channel
        else:
            return {
                "status": "error",
                "data": {},
                "error_message": f"channel parameter must be string or list, got {type(channel)}"
            }
        
        # Set defaults
        if limit is None:
            limit = 100
        if include_thread_replies is None:
            include_thread_replies = True
        if include_context is None:
            include_context = False
        if context_count is None:
            context_count = 5
        if only_thread_parents is None:
            only_thread_parents = False
        if sort_by is None:
            sort_by = "timestamp"
        if sort_order is None:
            sort_order = "desc"
        if has_reactions is None:
            has_reactions = False
        
        # Limit max
        if limit > 1000:
            limit = 1000
        
        # Date parsing (inline logic)
        oldest_ts = None
        latest_ts = None
        if start_date:
            try:
                if 'T' in start_date or start_date.endswith('Z'):
                    dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    oldest_ts = dt.timestamp()
                else:
                    dt = datetime.strptime(start_date, "%Y-%m-%d")
                    dt = dt.replace(tzinfo=timezone.utc)
                    oldest_ts = dt.timestamp()
            except Exception:
                pass
        
        if end_date:
            try:
                if 'T' in end_date or end_date.endswith('Z'):
                    dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    latest_ts = dt.timestamp()
                else:
                    dt = datetime.strptime(end_date, "%Y-%m-%d")
                    dt = dt.replace(tzinfo=timezone.utc)
                    # End of day
                    dt = dt.replace(hour=23, minute=59, second=59)
                    latest_ts = dt.timestamp()
            except Exception:
                pass
        
        # Get workspace URL and team ID for permalinks (inline)
        workspace_url = "https://concord-consortium.slack.com"
        team_id = None
        try:
            auth_url = "https://slack.com/api/auth.test"
            auth_req = urllib.request.Request(auth_url, headers={"Authorization": f"Bearer {TOKEN}"})
            with urllib.request.urlopen(auth_req, timeout=10) as ar:
                auth_data = json.loads(ar.read().decode('utf-8'))
                if auth_data.get("ok"):
                    url_value = auth_data.get("url", "")
                    if url_value:
                        # Normalize workspace URL - remove any existing https:// prefix and trailing slash
                        url_value = url_value.rstrip('/').replace('https://', '').replace('http://', '')
                        workspace_url = f"https://{url_value}"
                    # Get team ID for desktop deep links
                    team_id = auth_data.get("team_id") or (auth_data.get("team", {}).get("id") if isinstance(auth_data.get("team"), dict) else None)
        except Exception:
            pass
        
        # Normalize workspace_url to ensure it's clean (no double prefixes, no trailing slash)
        workspace_url = workspace_url.rstrip('/')
        if workspace_url.startswith('https://https://') or workspace_url.startswith('http://https://'):
            workspace_url = 'https://' + workspace_url.split('://', 1)[-1].split('://', 1)[-1]
        elif not workspace_url.startswith('https://'):
            workspace_url = f"https://{workspace_url}"
        
        # User cache for efficient lookups (inline, stored in dict)
        user_cache = {}
        
        # Resolve channel names to IDs (inline, similar to get_slack_channels)
        resolved_channels = []
        channel_name_map = {}
        for ch in channel_list:
            resolved_id = ch
            if not ch.startswith(("C", "G", "D", "mpdm-")):
                channel_name = ch.lstrip("#")
                try:
                    url = "https://slack.com/api/conversations.list"
                    params = {"limit": "1000", "exclude_archived": "true"}
                    query_string = urllib.parse.urlencode(params)
                    req = urllib.request.Request(
                        f"{url}?{query_string}",
                        headers={"Authorization": f"Bearer {TOKEN}"}
                    )
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        if data.get("ok"):
                            found = False
                            for ch_item in data.get("channels", []):
                                if ch_item.get("name") == channel_name:
                                    resolved_id = ch_item.get("id")
                                    channel_name_map[resolved_id] = channel_name
                                    found = True
                                    break
                            if not found:
                                resolved_id = ch
                except Exception:
                    resolved_id = ch
            else:
                resolved_id = ch.lstrip("#")
                channel_name_map[resolved_id] = ch.lstrip("#")
            resolved_channels.append((resolved_id, channel_name_map.get(resolved_id, ch.lstrip("#"))))
        
        # Normalize message_ts - handle empty strings as None
        if message_ts == "":
            message_ts = None
        
        # Handle single message mode
        if message_ts and len(channel_list) == 1:
            channel_id, channel_name = resolved_channels[0]
            # INLINED: Process single message (all logic inlined for Letta compliance)
            url = "https://slack.com/api/conversations.history"
            params = {"channel": channel_id, "limit": "1", "latest": message_ts, "inclusive": "true"}
            
            query_string = urllib.parse.urlencode(params)
            req = urllib.request.Request(
                f"{url}?{query_string}",
                headers={"Authorization": f"Bearer {TOKEN}"}
            )
            
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode('utf-8'))
                    
                    if not data.get("ok"):
                        return {
                            "status": "error",
                            "data": {},
                            "error_message": data.get("error", "Unknown error")
                        }
                    
                    messages = data.get("messages", [])
                    if not messages:
                        return {
                            "status": "error",
                            "data": {},
                            "error_message": f"Message {message_ts} not found in channel {channel_name}"
                        }
                    
                    # Process the single message (inline logic)
                    msg = messages[0]
                    ts = msg.get("ts", "")
                    user_id = msg.get("user", "")
                    text = msg.get("text", "")
                    
                    # Get user info (inline, with cache)
                    user_info = {"id": "", "username": "", "real_name": "", "display_name": ""}
                    if user_id:
                        if user_id in user_cache:
                            user_info = user_cache[user_id]
                        else:
                            try:
                                user_url = "https://slack.com/api/users.info"
                                user_params = {"user": user_id}
                                user_query = urllib.parse.urlencode(user_params)
                                user_req = urllib.request.Request(
                                    f"{user_url}?{user_query}",
                                    headers={"Authorization": f"Bearer {TOKEN}"}
                                )
                                with urllib.request.urlopen(user_req, timeout=30) as ur:
                                    user_data = json.loads(ur.read().decode('utf-8'))
                                    if user_data.get("ok"):
                                        u_data = user_data.get("user", {})
                                        profile = u_data.get("profile", {})
                                        user_info = {
                                            "id": user_id,
                                            "username": u_data.get("name", ""),
                                            "real_name": profile.get("real_name", ""),
                                            "display_name": profile.get("display_name", "")
                                        }
                                        user_cache[user_id] = user_info
                            except Exception:
                                pass
                    
                    # Convert timestamp
                    dt = datetime.fromtimestamp(float(ts)) if ts else datetime.now()
                    dt_iso = dt.isoformat() + "Z"
                    
                    # Build permalink (HTTPS) and desktop deep link (slack://)
                    permalink_ts = ts.replace('.', '')
                    permalink = f"{workspace_url}/archives/{channel_id}/p{permalink_ts}"
                    # Build app_redirect deep link for better browser compatibility
                    desktop_link = None
                    if team_id and channel_id:
                        # Use app_redirect with the permalink URL for consistent browser behavior
                        encoded_permalink = urllib.parse.quote(permalink, safe='')
                        desktop_link = f"https://slack.com/app_redirect?team={team_id}&url={encoded_permalink}"
                    
                    # Extract files (inline)
                    files = []
                    for file_data in msg.get("files", []):
                        files.append({
                            "id": file_data.get("id"),
                            "name": file_data.get("name"),
                            "title": file_data.get("title"),
                            "mimetype": file_data.get("mimetype"),
                            "filetype": file_data.get("filetype"),
                            "size": file_data.get("size"),
                            "url_private_download": file_data.get("url_private_download"),
                            "created": file_data.get("created")
                        })
                    
                    # Extract links from text (inline regex)
                    links = []
                    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
                    matches = re.finditer(url_pattern, text)
                    for match in matches:
                        url = match.group(0).rstrip('.,;:)!?')
                        links.append({
                            "url": url,
                            "display_text": url,
                            "type": "link"
                        })
                    
                    # Extract reactions (inline)
                    reactions = []
                    for reaction_data in msg.get("reactions", []):
                        reactions.append({
                            "name": reaction_data.get("name"),
                            "count": reaction_data.get("count"),
                            "users": reaction_data.get("users", [])
                        })
                    
                    reply_count = msg.get("reply_count", 0)
                    is_thread_parent = reply_count > 0
                    
                    processed_message = {
                        "ts": ts,
                        "text": text,
                        "user": user_id,
                        "username": user_info.get("username", ""),
                        "real_name": user_info.get("real_name", ""),
                        "datetime": dt_iso,
                        "permalink": permalink,
                        "desktop_link": desktop_link,
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "thread_ts": msg.get("thread_ts"),
                        "is_thread_parent": is_thread_parent,
                        "reply_count": reply_count,
                        "reply_users_count": msg.get("reply_users_count", 0),
                        "reactions": reactions,
                        "files": files,
                        "links": links,
                        "thread_replies": []
                    }
                    
                    # Get thread replies if requested (inline)
                    if include_thread_replies and is_thread_parent:
                        thread_ts = ts
                        replies_url = "https://slack.com/api/conversations.replies"
                        replies_params = {"channel": channel_id, "ts": thread_ts, "limit": "1000"}
                        replies_query = urllib.parse.urlencode(replies_params)
                        replies_req = urllib.request.Request(
                            f"{replies_url}?{replies_query}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        
                        try:
                            with urllib.request.urlopen(replies_req, timeout=30) as rr:
                                replies_data = json.loads(rr.read().decode('utf-8'))
                                if replies_data.get("ok"):
                                    replies = replies_data.get("messages", [])
                                    # Process replies (skip first - it's the parent)
                                    for reply in replies[1:]:
                                        reply_ts = reply.get("ts", "")
                                        reply_user_id = reply.get("user", "")
                                        reply_text = reply.get("text", "")
                                        
                                        # Get user info for reply
                                        reply_user_info = {"id": "", "username": "", "real_name": ""}
                                        if reply_user_id:
                                            if reply_user_id in user_cache:
                                                reply_user_info = user_cache[reply_user_id]
                                            else:
                                                try:
                                                    user_url = "https://slack.com/api/users.info"
                                                    user_params = {"user": reply_user_id}
                                                    user_query = urllib.parse.urlencode(user_params)
                                                    user_req = urllib.request.Request(
                                                        f"{user_url}?{user_query}",
                                                        headers={"Authorization": f"Bearer {TOKEN}"}
                                                    )
                                                    with urllib.request.urlopen(user_req, timeout=30) as ur:
                                                        user_data = json.loads(ur.read().decode('utf-8'))
                                                        if user_data.get("ok"):
                                                            u_data = user_data.get("user", {})
                                                            profile = u_data.get("profile", {})
                                                            reply_user_info = {
                                                                "id": reply_user_id,
                                                                "username": u_data.get("name", ""),
                                                                "real_name": profile.get("real_name", "")
                                                            }
                                                            user_cache[reply_user_id] = reply_user_info
                                                except Exception:
                                                    pass
                                        
                                        reply_dt = datetime.fromtimestamp(float(reply_ts)) if reply_ts else datetime.now()
                                        # Thread reply permalink format: path uses reply timestamp WITHOUT decimal, query uses thread_ts WITH decimal
                                        reply_permalink_ts = reply_ts.replace('.', '')
                                        reply_permalink = f"{workspace_url}/archives/{channel_id}/p{reply_permalink_ts}?thread_ts={thread_ts}&cid={channel_id}"
                                        # Build app_redirect deep link for better browser compatibility
                                        reply_desktop_link = None
                                        if team_id and channel_id and thread_ts:
                                            # Use app_redirect with the permalink URL for consistent browser behavior
                                            encoded_reply_permalink = urllib.parse.quote(reply_permalink, safe='')
                                            reply_desktop_link = f"https://slack.com/app_redirect?team={team_id}&url={encoded_reply_permalink}"
                                        
                                        # Extract files for reply
                                        reply_files = []
                                        for file_data in reply.get("files", []):
                                            reply_files.append({
                                                "id": file_data.get("id"),
                                                "name": file_data.get("name"),
                                                "title": file_data.get("title"),
                                                "mimetype": file_data.get("mimetype"),
                                                "filetype": file_data.get("filetype"),
                                                "size": file_data.get("size"),
                                                "url_private_download": file_data.get("url_private_download"),
                                                "created": file_data.get("created")
                                            })
                                        
                                        # Extract links for reply
                                        reply_links = []
                                        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
                                        reply_matches = re.finditer(url_pattern, reply_text)
                                        for match in reply_matches:
                                            url = match.group(0).rstrip('.,;:)!?')
                                            reply_links.append({
                                                "url": url,
                                                "display_text": url,
                                                "type": "link"
                                            })
                                        
                                        # Extract reactions for reply
                                        reply_reactions = []
                                        for reaction_data in reply.get("reactions", []):
                                            reply_reactions.append({
                                                "name": reaction_data.get("name"),
                                                "count": reaction_data.get("count"),
                                                "users": reaction_data.get("users", [])
                                            })
                                        
                                        processed_reply = {
                                            "ts": reply_ts,
                                            "text": reply_text,
                                            "user": reply_user_id,
                                            "username": reply_user_info.get("username", ""),
                                            "real_name": reply_user_info.get("real_name", ""),
                                            "datetime": reply_dt.isoformat() + "Z",
                                            "permalink": reply_permalink,
                                            "desktop_link": reply_desktop_link,
                                            "channel_id": channel_id,
                                            "channel_name": channel_name,
                                            "thread_ts": thread_ts,
                                            "reactions": reply_reactions,
                                            "files": reply_files,
                                            "links": reply_links
                                        }
                                        
                                        processed_message["thread_replies"].append(processed_reply)
                        except Exception:
                            pass
                    
                    # Get context if requested (inline, simplified - fetch before/after messages)
                    context_before = []
                    context_after = []
                    if include_context:
                        # Get messages before (simplified implementation)
                        try:
                            before_url = "https://slack.com/api/conversations.history"
                            before_params = {"channel": channel_id, "limit": str(context_count), "latest": message_ts}
                            before_query = urllib.parse.urlencode(before_params)
                            before_req = urllib.request.Request(
                                f"{before_url}?{before_query}",
                                headers={"Authorization": f"Bearer {TOKEN}"}
                            )
                            with urllib.request.urlopen(before_req, timeout=30) as br:
                                before_data = json.loads(br.read().decode('utf-8'))
                                if before_data.get("ok"):
                                    before_messages = before_data.get("messages", [])
                                    # Skip the current message and get previous ones
                                    for bmsg in before_messages[1:context_count+1]:
                                        # Simplified processing for context messages
                                        context_before.append({
                                            "ts": bmsg.get("ts"),
                                            "text": bmsg.get("text", "")[:200],  # Truncate for context
                                            "user": bmsg.get("user")
                                        })
                        except Exception:
                            pass
                    
                    return {
                        "status": "ok",
                        "data": {
                            "message": processed_message,
                            "context": {
                                "before": context_before,
                                "after": context_after
                            }
                        }
                    }
            except Exception as e:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"Error retrieving message: {str(e)}"
                }
        
        # Get messages for all channels
        all_channel_results = []
        for channel_id, channel_name in resolved_channels:
            # INLINED: Process messages from channel (all logic inlined for Letta compliance)
            # Get messages from channel
            url = "https://slack.com/api/conversations.history"
            params = {"channel": channel_id, "limit": str(min(limit, 1000))}
            if oldest_ts:
                params["oldest"] = str(int(oldest_ts))
            if latest_ts:
                params["latest"] = str(int(latest_ts))
            if oldest_ts or latest_ts:
                params["inclusive"] = "true"
            
            query_string = urllib.parse.urlencode(params)
            req = urllib.request.Request(
                f"{url}?{query_string}",
                headers={"Authorization": f"Bearer {TOKEN}"}
            )
            
            channel_error = None
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode('utf-8'))
                    
                    if not data.get("ok"):
                        channel_error = data.get("error", "Unknown error")
                    else:
                        messages = data.get("messages", [])
                        has_more = data.get("has_more", False)
                        
                        # Process each message (inline logic)
                        processed_messages = []
                        thread_ts_set = set()
                        
                        for msg in messages:
                            ts = msg.get("ts", "")
                            user_id = msg.get("user", "")
                            text = msg.get("text", "")
                            
                            # Get user info (inline, with cache)
                            user_info = {"id": "", "username": "", "real_name": "", "display_name": ""}
                            if user_id:
                                if user_id in user_cache:
                                    user_info = user_cache[user_id]
                                else:
                                    try:
                                        user_url = "https://slack.com/api/users.info"
                                        user_params = {"user": user_id}
                                        user_query = urllib.parse.urlencode(user_params)
                                        user_req = urllib.request.Request(
                                            f"{user_url}?{user_query}",
                                            headers={"Authorization": f"Bearer {TOKEN}"}
                                        )
                                        with urllib.request.urlopen(user_req, timeout=30) as ur:
                                            user_data = json.loads(ur.read().decode('utf-8'))
                                            if user_data.get("ok"):
                                                u_data = user_data.get("user", {})
                                                profile = u_data.get("profile", {})
                                                user_info = {
                                                    "id": user_id,
                                                    "username": u_data.get("name", ""),
                                                    "real_name": profile.get("real_name", ""),
                                                    "display_name": profile.get("display_name", "")
                                                }
                                                user_cache[user_id] = user_info
                                    except Exception:
                                        pass
                            
                            # Convert timestamp
                            dt = datetime.fromtimestamp(float(ts)) if ts else datetime.now()
                            dt_iso = dt.isoformat() + "Z"
                            
                            # Build permalink (HTTPS) and desktop deep link (slack://)
                            permalink_ts = ts.replace('.', '')
                            permalink = f"{workspace_url}/archives/{channel_id}/p{permalink_ts}"
                            # Build app_redirect deep link for better browser compatibility
                            desktop_link = None
                            if team_id and channel_id:
                                # Use app_redirect with the permalink URL for consistent browser behavior
                                encoded_permalink = urllib.parse.quote(permalink, safe='')
                                desktop_link = f"https://slack.com/app_redirect?team={team_id}&url={encoded_permalink}"
                            
                            # Extract files (inline)
                            files = []
                            for file_data in msg.get("files", []):
                                files.append({
                                    "id": file_data.get("id"),
                                    "name": file_data.get("name"),
                                    "title": file_data.get("title"),
                                    "mimetype": file_data.get("mimetype"),
                                    "filetype": file_data.get("filetype"),
                                    "size": file_data.get("size"),
                                    "url_private_download": file_data.get("url_private_download"),
                                    "created": file_data.get("created")
                                })
                            
                            # Extract links from text (inline regex)
                            links = []
                            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
                            matches = re.finditer(url_pattern, text)
                            for match in matches:
                                url = match.group(0).rstrip('.,;:)!?')
                                links.append({
                                    "url": url,
                                    "display_text": url,
                                    "type": "link"
                                })
                            
                            # Extract reactions (inline)
                            reactions = []
                            for reaction_data in msg.get("reactions", []):
                                reactions.append({
                                    "name": reaction_data.get("name"),
                                    "count": reaction_data.get("count"),
                                    "users": reaction_data.get("users", [])
                                })
                            
                            reply_count = msg.get("reply_count", 0)
                            is_thread_parent = reply_count > 0
                            
                            processed_msg = {
                                "ts": ts,
                                "text": text,
                                "user": user_id,
                                "username": user_info.get("username", ""),
                                "real_name": user_info.get("real_name", ""),
                                "datetime": dt_iso,
                                "permalink": permalink,
                                "desktop_link": desktop_link,
                                "channel_id": channel_id,
                                "channel_name": channel_name,
                                "thread_ts": msg.get("thread_ts"),
                                "is_thread_parent": is_thread_parent,
                                "reply_count": reply_count,
                                "reply_users_count": msg.get("reply_users_count", 0),
                                "reactions": reactions,
                                "files": files,
                                "links": links,
                                "thread_replies": []
                            }
                            
                            # Apply filters (inline)
                            if only_thread_parents and not is_thread_parent:
                                continue
                            
                            if min_reply_count is not None and reply_count < min_reply_count:
                                continue
                            
                            reaction_count = sum(r.get("count", 0) for r in reactions)
                            if min_reactions is not None and reaction_count < min_reactions:
                                continue
                            
                            if has_reactions and len(reactions) == 0:
                                continue
                            
                            processed_messages.append(processed_msg)
                            
                            if is_thread_parent:
                                thread_ts_set.add(ts)
                        
                        # Get thread replies if requested (inline)
                        if include_thread_replies and thread_ts_set:
                            for thread_ts in thread_ts_set:
                                # Find parent message
                                parent_msg = None
                                for pmsg in processed_messages:
                                    if pmsg["ts"] == thread_ts:
                                        parent_msg = pmsg
                                        break
                                
                                if parent_msg:
                                    # Get replies
                                    replies_url = "https://slack.com/api/conversations.replies"
                                    replies_params = {"channel": channel_id, "ts": thread_ts, "limit": "1000"}
                                    replies_query = urllib.parse.urlencode(replies_params)
                                    replies_req = urllib.request.Request(
                                        f"{replies_url}?{replies_query}",
                                        headers={"Authorization": f"Bearer {TOKEN}"}
                                    )
                                    
                                    try:
                                        with urllib.request.urlopen(replies_req, timeout=30) as rr:
                                            replies_data = json.loads(rr.read().decode('utf-8'))
                                            if replies_data.get("ok"):
                                                replies = replies_data.get("messages", [])
                                                # Process replies (skip first - it's the parent)
                                                for reply in replies[1:]:
                                                    reply_ts = reply.get("ts", "")
                                                    reply_user_id = reply.get("user", "")
                                                    reply_text = reply.get("text", "")
                                                    
                                                    # Get user info for reply
                                                    reply_user_info = {"id": "", "username": "", "real_name": ""}
                                                    if reply_user_id:
                                                        if reply_user_id in user_cache:
                                                            reply_user_info = user_cache[reply_user_id]
                                                        else:
                                                            try:
                                                                user_url = "https://slack.com/api/users.info"
                                                                user_params = {"user": reply_user_id}
                                                                user_query = urllib.parse.urlencode(user_params)
                                                                user_req = urllib.request.Request(
                                                                    f"{user_url}?{user_query}",
                                                                    headers={"Authorization": f"Bearer {TOKEN}"}
                                                                )
                                                                with urllib.request.urlopen(user_req, timeout=30) as ur:
                                                                    user_data = json.loads(ur.read().decode('utf-8'))
                                                                    if user_data.get("ok"):
                                                                        u_data = user_data.get("user", {})
                                                                        profile = u_data.get("profile", {})
                                                                        reply_user_info = {
                                                                            "id": reply_user_id,
                                                                            "username": u_data.get("name", ""),
                                                                            "real_name": profile.get("real_name", "")
                                                                        }
                                                                        user_cache[reply_user_id] = reply_user_info
                                                            except Exception:
                                                                pass
                                                    
                                                    reply_dt = datetime.fromtimestamp(float(reply_ts)) if reply_ts else datetime.now()
                                                    # Thread reply permalink format: path uses reply timestamp WITHOUT decimal, query uses thread_ts WITH decimal
                                                    reply_permalink_ts = reply_ts.replace('.', '')
                                                    reply_permalink = f"{workspace_url}/archives/{channel_id}/p{reply_permalink_ts}?thread_ts={thread_ts}&cid={channel_id}"
                                                    # Build app_redirect deep link for better browser compatibility
                                                    reply_desktop_link = None
                                                    if team_id and channel_id and thread_ts:
                                                        # Use app_redirect with the permalink URL for consistent browser behavior
                                                        encoded_reply_permalink = urllib.parse.quote(reply_permalink, safe='')
                                                        reply_desktop_link = f"https://slack.com/app_redirect?team={team_id}&url={encoded_reply_permalink}"
                                                    
                                                    # Extract files for reply
                                                    reply_files = []
                                                    for file_data in reply.get("files", []):
                                                        reply_files.append({
                                                            "id": file_data.get("id"),
                                                            "name": file_data.get("name"),
                                                            "title": file_data.get("title"),
                                                            "mimetype": file_data.get("mimetype"),
                                                            "filetype": file_data.get("filetype"),
                                                            "size": file_data.get("size"),
                                                            "url_private_download": file_data.get("url_private_download"),
                                                            "created": file_data.get("created")
                                                        })
                                                    
                                                    # Extract links for reply
                                                    reply_links = []
                                                    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
                                                    reply_matches = re.finditer(url_pattern, reply_text)
                                                    for match in reply_matches:
                                                        url = match.group(0).rstrip('.,;:)!?')
                                                        reply_links.append({
                                                            "url": url,
                                                            "display_text": url,
                                                            "type": "link"
                                                        })
                                                    
                                                    # Extract reactions for reply
                                                    reply_reactions = []
                                                    for reaction_data in reply.get("reactions", []):
                                                        reply_reactions.append({
                                                            "name": reaction_data.get("name"),
                                                            "count": reaction_data.get("count"),
                                                            "users": reaction_data.get("users", [])
                                                        })
                                                    
                                                    processed_reply = {
                                                        "ts": reply_ts,
                                                        "text": reply_text,
                                                        "user": reply_user_id,
                                                        "username": reply_user_info.get("username", ""),
                                                        "real_name": reply_user_info.get("real_name", ""),
                                                        "datetime": reply_dt.isoformat() + "Z",
                                                        "permalink": reply_permalink,
                                                        "desktop_link": reply_desktop_link,
                                                        "channel_id": channel_id,
                                                        "channel_name": channel_name,
                                                        "thread_ts": thread_ts,
                                                        "reactions": reply_reactions,
                                                        "files": reply_files,
                                                        "links": reply_links
                                                    }
                                                    
                                                    parent_msg["thread_replies"].append(processed_reply)
                                    except Exception:
                                        pass
                        
                        # Sort messages (inline)
                        if sort_by == "timestamp":
                            reverse = (sort_order == "desc")
                            processed_messages.sort(key=lambda m: float(m.get("ts", 0)), reverse=reverse)
                        elif sort_by == "reactions":
                            reverse = (sort_order == "desc")
                            processed_messages.sort(key=lambda m: sum(r.get("count", 0) for r in m.get("reactions", [])), reverse=reverse)
                        elif sort_by == "reply_count":
                            reverse = (sort_order == "desc")
                            processed_messages.sort(key=lambda m: m.get("reply_count", 0), reverse=reverse)
                        elif sort_by == "user":
                            reverse = (sort_order == "desc")
                            processed_messages.sort(key=lambda m: m.get("username", ""), reverse=reverse)
                        
                        # Add to results
                        all_channel_results.append({
                            "channel_id": channel_id,
                            "channel_name": channel_name,
                            "messages": processed_messages,
                            "has_more": has_more
                        })
            except Exception as e:
                channel_error = str(e)
            
            # Skip channel if error occurred
            if channel_error:
                continue
        
        # Return structure based on single vs multiple channels
        if len(channel_list) == 1:
            if all_channel_results:
                ch_result = all_channel_results[0]
                return {
                    "status": "ok",
                    "data": {
                        "channel_id": ch_result["channel_id"],
                        "channel_name": ch_result["channel_name"],
                        "messages": ch_result["messages"],
                        "has_more": ch_result["has_more"],
                        "total_returned": len(ch_result["messages"]),
                        "date_range": {
                            "start": datetime.fromtimestamp(oldest_ts).isoformat() + "Z" if oldest_ts else None,
                            "end": datetime.fromtimestamp(latest_ts).isoformat() + "Z" if latest_ts else None
                        }
                    }
                }
            else:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": "Failed to retrieve messages from channel"
                }
        else:
            return {
                "status": "ok",
                "data": {
                    "channels": all_channel_results,
                    "total_channels": len(all_channel_results)
                }
            }
    
    except Exception as e:
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def search_slack_messages(
    query: Optional[str] = None,
    user: Optional[str] = None,
    channel: Optional[str] = None,
    saved_only: Optional[bool] = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    count: Optional[int] = 20,
    sort: Optional[str] = "score",
    sort_by: Optional[str] = None,
    min_reactions: Optional[str] = None,
    min_reply_count: Optional[str] = None,
    only_thread_parents: Optional[str] = None,
    has_reactions: Optional[str] = None,
    is_dm: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for messages across the entire Slack workspace, or retrieve saved/bookmarked items.

    When saved_only=True, returns items you've saved for later (starred/bookmarked).
    When query is omitted or empty, returns recent messages across workspace.
    Supports filtering by user(s) and/or channel(s) using Slack's query syntax.

    Query Syntax: "term1 term2" (AND), "term1 OR term2", "NOT term", '"exact phrase"', "prefix*" (wildcard), "@username" (mentions).

    @-Mentions: Use "@username" in query to find messages mentioning a user. Combine with filters as needed.

    Automatic Handling: OR queries with user/channel filters are automatically split into separate
    searches and combined (Slack API treats OR as AND when filters present).

    Known Limitation: Prefix wildcards "*term" match literal, not wildcard. Use "term*" instead.

    Args:
        query: Search query string. Supports @username for mentions. When saved_only=True, filters saved items by query. Default: None.
        user: User ID(s) or username(s) (e.g., "sue" or "sue,dan"). Use usernames for efficiency. Default: None.
        channel: Channel ID(s) or name(s) (e.g., "#random" or "#general,#random"). Use names for efficiency. Default: None.
        saved_only: When True, returns only saved/bookmarked items instead of searching all messages. Default: False.
        start_date: Start date in YYYY-MM-DD format or ISO 8601 datetime. Default: None.
        end_date: End date in YYYY-MM-DD format or ISO 8601 datetime. Default: None.
        count: Maximum number of messages to return. Default: 20, max: 100.
        sort: Sort order: "score" (default) or "timestamp".
        sort_by: Additional sort criteria. Default: None.
        min_reactions: Filter messages with at least N reactions. Default: None.
        min_reply_count: Filter messages with at least N replies. Default: None.
        only_thread_parents: Return only messages that have replies. Default: False.
        has_reactions: Return only messages with reactions. Default: False.
        is_dm: Search only in direct messages. Default: False. Use with user filter for specific DM conversations.

    Returns:
        Dictionary with status, data (messages array and metadata), and error_message if applicable.
    """
    # Imports inside function at the very beginning
    import os
    import traceback
    import json
    import urllib.request
    import urllib.parse
    from datetime import datetime, timezone
    import re

    # Wrap entire function in try-except
    try:
        # Get token
        TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
        if not TOKEN:
            return {
                "status": "error",
                "data": {},
                "error_message": "SLACK_MCP_XOXP_TOKEN not set in environment"
            }
        
        # Set defaults and handle type conversions (Letta passes null as string "None" or actual None)
        if count is None:
            count = 20
        if sort is None:
            sort = "score"

        # Convert string bool params (workaround for Letta Optional[bool] null handling)
        # Inline conversion - no nested def allowed by Letta
        if only_thread_parents is None or only_thread_parents == "":
            only_thread_parents = False
        elif isinstance(only_thread_parents, bool):
            pass  # Already bool
        elif isinstance(only_thread_parents, str):
            only_thread_parents = only_thread_parents.lower() in ("true", "1", "yes")
        else:
            only_thread_parents = False

        if has_reactions is None or has_reactions == "":
            has_reactions = False
        elif isinstance(has_reactions, bool):
            pass  # Already bool
        elif isinstance(has_reactions, str):
            has_reactions = has_reactions.lower() in ("true", "1", "yes")
        else:
            has_reactions = False

        if is_dm is None or is_dm == "":
            is_dm = False
        elif isinstance(is_dm, bool):
            pass  # Already bool
        elif isinstance(is_dm, str):
            is_dm = is_dm.lower() in ("true", "1", "yes")
        else:
            is_dm = False

        # Convert string int params (workaround for Letta Optional[int] null handling)
        if min_reactions is None or min_reactions == "":
            min_reactions = None
        else:
            try:
                min_reactions = int(min_reactions)
            except (ValueError, TypeError):
                min_reactions = None

        if min_reply_count is None or min_reply_count == "":
            min_reply_count = None
        else:
            try:
                min_reply_count = int(min_reply_count)
            except (ValueError, TypeError):
                min_reply_count = None

        # Limit max
        if count > 100:
            count = 100

        # Handle saved_only parameter conversion (same pattern as other booleans)
        if saved_only is None or saved_only == "":
            saved_only = False
        elif isinstance(saved_only, bool):
            pass  # Already bool
        elif isinstance(saved_only, str):
            saved_only = saved_only.lower() in ("true", "1", "yes")
        else:
            saved_only = False

        # SAVED ITEMS PATH: Use stars.list API instead of search.messages
        if saved_only:
            try:
                url = "https://slack.com/api/stars.list"
                params = {"count": str(count)}

                query_string = urllib.parse.urlencode(params)
                req = urllib.request.Request(
                    f"{url}?{query_string}",
                    headers={"Authorization": f"Bearer {TOKEN}"}
                )

                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode('utf-8'))

                    if not data.get("ok"):
                        return {
                            "status": "error",
                            "data": {},
                            "error_message": data.get("error", "Unknown Slack API error")
                        }

                    items = data.get("items", [])

                    # Build channel ID to name cache for saved items
                    channel_ids_in_saved = set()
                    for item in items:
                        if item.get("type") == "message":
                            ch_id = item.get("channel", "")
                            if ch_id:
                                channel_ids_in_saved.add(ch_id)

                    # Fetch channel info for all channels in saved items
                    saved_channel_cache = {}
                    if channel_ids_in_saved:
                        try:
                            ch_url = "https://slack.com/api/conversations.list"
                            ch_params = {"limit": "1000", "exclude_archived": "false"}
                            ch_query = urllib.parse.urlencode(ch_params)
                            ch_req = urllib.request.Request(
                                f"{ch_url}?{ch_query}",
                                headers={"Authorization": f"Bearer {TOKEN}"}
                            )
                            with urllib.request.urlopen(ch_req, timeout=30) as chr:
                                ch_data = json.loads(chr.read().decode('utf-8'))
                                if ch_data.get("ok"):
                                    for ch_item in ch_data.get("channels", []):
                                        ch_id = ch_item.get("id")
                                        if ch_id in channel_ids_in_saved:
                                            saved_channel_cache[ch_id] = ch_item.get("name", "")

                            # Also try individual lookups for any missing (private channels, DMs)
                            for ch_id in channel_ids_in_saved:
                                if ch_id not in saved_channel_cache:
                                    try:
                                        info_url = "https://slack.com/api/conversations.info"
                                        info_params = {"channel": ch_id}
                                        info_query = urllib.parse.urlencode(info_params)
                                        info_req = urllib.request.Request(
                                            f"{info_url}?{info_query}",
                                            headers={"Authorization": f"Bearer {TOKEN}"}
                                        )
                                        with urllib.request.urlopen(info_req, timeout=30) as ir:
                                            info_data = json.loads(ir.read().decode('utf-8'))
                                            if info_data.get("ok"):
                                                ch_info = info_data.get("channel", {})
                                                saved_channel_cache[ch_id] = ch_info.get("name", "") or ch_id
                                    except Exception:
                                        saved_channel_cache[ch_id] = ch_id  # Fallback to ID
                        except Exception:
                            pass

                    # Transform stars.list format to match search.messages format
                    # stars.list returns {type: "message", message: {...}, channel: "C123"}
                    # search.messages returns matches array with message data at top level
                    matches = []
                    for item in items:
                        if item.get("type") == "message":
                            msg = item.get("message", {})
                            ch_id = item.get("channel", "")
                            # Add channel info to message (stars.list has it at item level)
                            msg["channel"] = {
                                "id": ch_id,
                                "name": saved_channel_cache.get(ch_id, ch_id)
                            }
                            matches.append(msg)

                    # Apply client-side filtering for saved items (query, user, channel)
                    # The common processing path handles dates/reactions/replies
                    filtered_matches = []

                    # Parse filter values
                    user_list = []
                    if user:
                        if isinstance(user, str):
                            user_list = [u.strip() for u in user.split(',')] if ',' in user else [user]
                        elif isinstance(user, list):
                            user_list = user

                    channel_list = []
                    if channel:
                        if isinstance(channel, str):
                            channel_list = [ch.strip().lstrip('#') for ch in channel.split(',')] if ',' in channel else [channel.lstrip('#')]
                        elif isinstance(channel, list):
                            channel_list = [ch.lstrip('#') for ch in channel]

                    # Filter matches
                    for match in matches:
                        # Filter by user if specified
                        if user_list:
                            msg_user = match.get("user", "")
                            user_match = any(
                                (u.startswith("U") and msg_user == u) or  # Match by ID
                                (not u.startswith("U") and msg_user == u)  # Username would need resolution, skip for now
                                for u in user_list
                            )
                            if not user_match:
                                continue

                        # Filter by channel if specified
                        if channel_list:
                            msg_channel_id = match.get("channel", {}).get("id", "")
                            msg_channel_name = match.get("channel", {}).get("name", "")
                            channel_match = any(
                                msg_channel_id == ch or msg_channel_name == ch
                                for ch in channel_list
                            )
                            if not channel_match:
                                continue

                        # Filter by query if specified (simple text match)
                        if query:
                            msg_text = match.get("text", "").lower()
                            # Simple AND logic: all terms must appear
                            query_terms = query.lower().split()
                            query_match = all(term in msg_text for term in query_terms)
                            if not query_match:
                                continue

                        filtered_matches.append(match)

                    # Update matches with filtered results
                    matches = filtered_matches

                    # Set total and pagination for consistency with search path
                    total = len(matches)
                    pagination = {"total_count": total, "page": 1, "per_page": count}

                    # Build final_query string
                    filter_parts = []
                    if query:
                        filter_parts.append(f"query='{query}'")
                    if user:
                        filter_parts.append(f"user={user}")
                    if channel:
                        filter_parts.append(f"channel={channel}")
                    filter_str = ", ".join(filter_parts) if filter_parts else "all"
                    final_query = f"saved items ({filter_str}, count={len(matches)})"

                    # Continue to common processing path below
                    # (matches, total, pagination, final_query are now set)

            except Exception as e_stars:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"Error fetching saved items: {str(e_stars)}"
                }
        else:
            # NORMAL SEARCH PATH: Build search query with user/channel filters (inline logic)
            search_query_parts = []

            # NOTE: We'll add the query text AFTER building filters
            # Only use "*" fallback if there are NO filters at all
            # (The "*" can interfere with filter-only searches)

            # Handle user filter (support multiple users with OR syntax) - inline
            if user:
                if isinstance(user, str):
                    # Single user or comma-separated
                    if ',' in user:
                        user_list = [u.strip() for u in user.split(',')]
                    else:
                        user_list = [user]
                elif isinstance(user, list):
                    # Support list for backward compatibility (though Letta schema only allows str)
                    user_list = user
                else:
                    return {
                        "status": "error",
                        "data": {},
                        "error_message": f"user parameter must be string or list, got {type(user)}"
                    }
            
                # Build user filters (use OR syntax for multiple)
                # Resolve user IDs to usernames for search queries (Slack search works better with usernames)
                user_filters = []
                user_cache_for_search = {}
            
                # First pass: collect all user IDs that need resolution
                user_ids_to_resolve = []
                for u in user_list:
                    if u.startswith("U"):
                        user_ids_to_resolve.append(u)
            
                # Resolve user IDs to usernames
                if user_ids_to_resolve:
                    try:
                        url = "https://slack.com/api/users.list"
                        params = {"limit": "1000"}
                        query_string = urllib.parse.urlencode(params)
                        req = urllib.request.Request(
                            f"{url}?{query_string}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        with urllib.request.urlopen(req, timeout=30) as ur:
                            user_data = json.loads(ur.read().decode('utf-8'))
                            if user_data.get("ok"):
                                for user_item in user_data.get("members", []):
                                    user_id = user_item.get("id")
                                    if user_id in user_ids_to_resolve:
                                        user_cache_for_search[user_id] = user_item.get("name", "")
                    except Exception:
                        pass
            
                # Build filters using usernames when available, otherwise use the provided value
                for u in user_list:
                    if u.startswith("U") and u in user_cache_for_search:
                        # Use resolved username
                        user_filters.append(f"from:{user_cache_for_search[u]}")
                    else:
                        # Use as-is (username or unresolved ID)
                        user_filters.append(f"from:{u}")
            
                if len(user_filters) == 1:
                    search_query_parts.insert(0, user_filters[0])
                else:
                    # Slack search API doesn't support parentheses around OR clauses
                    # Use "from:user1 OR from:user2" instead of "(from:user1 OR from:user2)"
                    user_query = " OR ".join(user_filters)
                    search_query_parts.insert(0, user_query)
        
            # Handle channel filter (support multiple channels with OR syntax) - inline
            if channel:
                if isinstance(channel, str):
                    # Single channel or comma-separated
                    if ',' in channel:
                        channel_list = [ch.strip() for ch in channel.split(',')]
                    else:
                        channel_list = [channel]
                elif isinstance(channel, list):
                    # Support list for backward compatibility (though Letta schema only allows str)
                    channel_list = channel
                else:
                    return {
                        "status": "error",
                        "data": {},
                        "error_message": f"channel parameter must be string or list, got {type(channel)}"
                    }
            
                # Build channel filters (resolve IDs to names - Slack search requires channel names, not IDs)
                # DM channels need special handling - use "dm:username" syntax instead of "in:channel"
                channel_filters = []
                channel_id_to_name_cache = {}
                dm_channel_to_username_cache = {}  # For DM channels: channel_id -> username

                # First pass: separate DM channels from regular channels
                regular_channel_ids = []
                dm_channel_ids = []
                for ch in channel_list:
                    channel_name = ch.lstrip("#")
                    if channel_name.startswith("D"):
                        # DM channel - needs special handling
                        dm_channel_ids.append(channel_name)
                    elif channel_name.startswith(("C", "G", "mpdm-")):
                        regular_channel_ids.append(channel_name)

                # Resolve regular channel IDs to names
                if regular_channel_ids:
                    try:
                        url = "https://slack.com/api/conversations.list"
                        params = {"limit": "1000", "exclude_archived": "false"}
                        query_string = urllib.parse.urlencode(params)
                        req = urllib.request.Request(
                            f"{url}?{query_string}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        with urllib.request.urlopen(req, timeout=30) as cr:
                            channel_data = json.loads(cr.read().decode('utf-8'))
                            if channel_data.get("ok"):
                                for ch_item in channel_data.get("channels", []):
                                    ch_id = ch_item.get("id")
                                    ch_name = ch_item.get("name", "")
                                    if ch_id in regular_channel_ids and ch_name:
                                        channel_id_to_name_cache[ch_id] = ch_name

                        # Also try conversations.info for each ID individually (in case it's a private channel not in list)
                        for ch_id in regular_channel_ids:
                            if ch_id not in channel_id_to_name_cache:
                                try:
                                    info_url = "https://slack.com/api/conversations.info"
                                    info_params = {"channel": ch_id}
                                    info_query = urllib.parse.urlencode(info_params)
                                    info_req = urllib.request.Request(
                                        f"{info_url}?{info_query}",
                                        headers={"Authorization": f"Bearer {TOKEN}"}
                                    )
                                    with urllib.request.urlopen(info_req, timeout=30) as ir:
                                        info_data = json.loads(ir.read().decode('utf-8'))
                                        if info_data.get("ok"):
                                            ch_info = info_data.get("channel", {})
                                            ch_name = ch_info.get("name", "")
                                            if ch_name:
                                                channel_id_to_name_cache[ch_id] = ch_name
                                except Exception:
                                    pass
                    except Exception:
                        pass

                # Resolve DM channel IDs to usernames (for dm:username syntax)
                if dm_channel_ids:
                    # First get user info for resolving user IDs to usernames
                    user_id_to_name = {}
                    try:
                        url = "https://slack.com/api/users.list"
                        params = {"limit": "1000"}
                        query_string = urllib.parse.urlencode(params)
                        req = urllib.request.Request(
                            f"{url}?{query_string}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        with urllib.request.urlopen(req, timeout=30) as ur:
                            user_data = json.loads(ur.read().decode('utf-8'))
                            if user_data.get("ok"):
                                for user_item in user_data.get("members", []):
                                    user_id_to_name[user_item.get("id")] = user_item.get("name", "")
                    except Exception:
                        pass

                    # Get user ID for each DM channel
                    for dm_id in dm_channel_ids:
                        try:
                            info_url = "https://slack.com/api/conversations.info"
                            info_params = {"channel": dm_id}
                            info_query = urllib.parse.urlencode(info_params)
                            info_req = urllib.request.Request(
                                f"{info_url}?{info_query}",
                                headers={"Authorization": f"Bearer {TOKEN}"}
                            )
                            with urllib.request.urlopen(info_req, timeout=30) as ir:
                                info_data = json.loads(ir.read().decode('utf-8'))
                                if info_data.get("ok"):
                                    ch_info = info_data.get("channel", {})
                                    # DM channels have a "user" field with the other user's ID
                                    dm_user_id = ch_info.get("user", "")
                                    if dm_user_id and dm_user_id in user_id_to_name:
                                        dm_channel_to_username_cache[dm_id] = user_id_to_name[dm_user_id]
                                    elif dm_user_id:
                                        # Fallback: use user ID if we can't resolve to name
                                        dm_channel_to_username_cache[dm_id] = dm_user_id
                        except Exception:
                            pass

                # Build filters using channel names (Slack search requires names, not IDs)
                for ch in channel_list:
                    channel_name = ch.lstrip("#")
                    if channel_name.startswith("D"):
                        # DM channel - use dm:username syntax
                        if channel_name in dm_channel_to_username_cache:
                            channel_filters.append(f"dm:{dm_channel_to_username_cache[channel_name]}")
                        else:
                            # Fallback: use is:dm (searches all DMs, less specific)
                            channel_filters.append("is:dm")
                    elif channel_name.startswith(("C", "G", "mpdm-")):
                        # Regular channel - use in:channel_name syntax
                        if channel_name in channel_id_to_name_cache:
                            channel_filters.append(f"in:{channel_id_to_name_cache[channel_name]}")
                        else:
                            # Fallback: try using ID anyway (might work for some cases)
                            channel_filters.append(f"in:{channel_name}")
                    else:
                        # It's already a channel name - use directly
                        channel_filters.append(f"in:{channel_name}")
            
                if len(channel_filters) == 1:
                    search_query_parts.insert(0, channel_filters[0])
                else:
                    # Slack search API doesn't support parentheses around OR clauses
                    # Use "in:chan1 OR in:chan2" instead of "(in:chan1 OR in:chan2)"
                    channel_query = " OR ".join(channel_filters)
                    search_query_parts.insert(0, channel_query)

            # Add is:dm filter if requested (search only in direct messages)
            if is_dm:
                search_query_parts.insert(0, "is:dm")

            # Add date filters using Slack's native syntax (more accurate than post-filtering)
            if start_date:
                # Convert to YYYY-MM-DD format for after: syntax
                try:
                    if 'T' in start_date:
                        date_part = start_date.split('T')[0]
                    else:
                        date_part = start_date
                    search_query_parts.append(f"after:{date_part}")
                except Exception:
                    pass
        
            if end_date:
                # Convert to YYYY-MM-DD format for before: syntax
                # Add 1 day because before: is exclusive
                try:
                    if 'T' in end_date:
                        date_part = end_date.split('T')[0]
                    else:
                        date_part = end_date
                    # Parse and add 1 day for inclusive end date
                    from datetime import timedelta
                    end_dt_temp = datetime.strptime(date_part, "%Y-%m-%d")
                    end_dt_plus_one = end_dt_temp + timedelta(days=1)
                    search_query_parts.append(f"before:{end_dt_plus_one.strftime('%Y-%m-%d')}")
                except Exception:
                    pass

            # Now add the query text (after filters are built)
            # Only use "*" fallback if there are NO filters at all
            has_filters = bool(search_query_parts)  # True if we have any from:/in:/is:dm/after:/before: filters
            if query:
                # User provided a query - add it
                search_query_parts.append(query)
            elif not has_filters:
                # No query AND no filters - need "*" to avoid Slack API error
                search_query_parts.append("*")
            # else: we have filters but no query - that's fine, filters alone work

            # Combine query parts
            final_query = " ".join(search_query_parts) if search_query_parts else ""
        
            # Check if we need to split OR query (workaround for Slack API limitation)
            # Slack treats "OR" as "AND" when from: or in: filters are present.
            # We split OR queries into separate searches and combine results.
            or_pattern = re.compile(r'\s+OR\s+', re.IGNORECASE)
        
            # Check if OR is outside quotes (inline - no nested def allowed by Letta)
            has_unquoted_or = False
            if query:
                in_quote = False
                cleaned_query = []
                for char in query:
                    if char == '"':
                        in_quote = not in_quote
                    elif not in_quote:
                        cleaned_query.append(char)
                has_unquoted_or = bool(or_pattern.search(''.join(cleaned_query)))
        
            # Split if: query has unquoted OR AND any filter is present
            needs_or_split = query and has_unquoted_or and (user or channel)
        
            if needs_or_split:
                # Split query into separate terms and search each
                or_terms = [term.strip() for term in or_pattern.split(query)]
                all_matches = []
                all_total = 0
                seen_message_ids = set()
            
                for or_term in or_terms:
                    # Build query for this single term (reuse the already-built filters)
                    # Extract the filter parts from search_query_parts (user and channel filters)
                    term_query_parts = []
                    for part in search_query_parts:
                        if part == query:
                            term_query_parts.append(or_term)
                        else:
                            term_query_parts.append(part)
                    term_final_query = " ".join(term_query_parts) if term_query_parts else or_term
                
                    # Make API call for this term
                    try:
                        term_url = "https://slack.com/api/search.messages"
                        term_params = {
                            "query": term_final_query,
                            "count": str(count),
                            "sort": sort
                        }
                        term_query_string = urllib.parse.urlencode(term_params)
                        term_req = urllib.request.Request(
                            f"{term_url}?{term_query_string}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        with urllib.request.urlopen(term_req, timeout=30) as tr:
                            term_data = json.loads(tr.read().decode('utf-8'))
                            if term_data.get("ok"):
                                term_matches = term_data.get("messages", {}).get("matches", [])
                                term_total = term_data.get("messages", {}).get("total", 0)
                                all_total += term_total
                            
                                # Deduplicate by channel_id + ts
                                for match in term_matches:
                                    match_id = f"{match.get('channel', {}).get('id', '')}_{match.get('ts', '')}"
                                    if match_id not in seen_message_ids:
                                        seen_message_ids.add(match_id)
                                        all_matches.append(match)
                    except Exception:
                        pass
            
                # Use combined results
                matches = all_matches
                total = len(all_matches)  # Use deduplicated count
                pagination = {"total_count": total, "page": 1, "per_page": count}
                final_query = f"{query} (split into {len(or_terms)} searches)"
            else:
                # Normal path: single API call
                # Build API request
                url = "https://slack.com/api/search.messages"
                params = {
                    "query": final_query,
                    "count": str(count),
                    "sort": sort
                }
            
                query_string = urllib.parse.urlencode(params)
                req = urllib.request.Request(
                    f"{url}?{query_string}",
                    headers={"Authorization": f"Bearer {TOKEN}"}
                )
            
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode('utf-8'))
                
                    if not data.get("ok"):
                        return {
                            "status": "error",
                            "data": {},
                            "error_message": data.get("error", "Unknown Slack API error")
                        }
                
                    matches = data.get("messages", {}).get("matches", [])
                    total = data.get("messages", {}).get("total", 0)
                    pagination = data.get("messages", {}).get("pagination", {})
        
        # Continue processing (both paths have set matches, total, pagination)
        # User cache for efficient lookups
        user_cache = {}
        
        # Parse dates for filtering (inline)
        start_dt = None
        end_dt = None
        if start_date:
            try:
                if 'T' in start_date or start_date.endswith('Z'):
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                else:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        
        if end_date:
            try:
                if 'T' in end_date or end_date.endswith('Z'):
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                else:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                    end_dt = end_dt.replace(hour=23, minute=59, second=59)
            except Exception:
                pass
        
        # Get workspace URL and team ID for permalinks
        workspace_url = "https://concord-consortium.slack.com"
        team_id = None
        try:
            auth_url = "https://slack.com/api/auth.test"
            auth_req = urllib.request.Request(auth_url, headers={"Authorization": f"Bearer {TOKEN}"})
            with urllib.request.urlopen(auth_req, timeout=10) as ar:
                auth_data = json.loads(ar.read().decode('utf-8'))
                if auth_data.get("ok"):
                    url_value = auth_data.get("url", "")
                    if url_value:
                        # Normalize workspace URL - remove any existing https:// prefix and trailing slash
                        url_value = url_value.rstrip('/').replace('https://', '').replace('http://', '')
                        workspace_url = f"https://{url_value}"
                    # Get team ID for desktop deep links
                    team_id = auth_data.get("team_id") or (auth_data.get("team", {}).get("id") if isinstance(auth_data.get("team"), dict) else None)
        except Exception:
            pass
        
        # Normalize workspace_url to ensure it's clean (no double prefixes, no trailing slash)
        workspace_url = workspace_url.rstrip('/')
        if workspace_url.startswith('https://https://') or workspace_url.startswith('http://https://'):
            workspace_url = 'https://' + workspace_url.split('://', 1)[-1].split('://', 1)[-1]
        elif not workspace_url.startswith('https://'):
            workspace_url = f"https://{workspace_url}"
        
        # Process search results (inline)
        processed_messages = []
        for match in matches:
            ts = match.get("ts", "")
            user_id = match.get("user", "")
            text = match.get("text", "")
            
            # Filter by date if provided
            if start_dt or end_dt:
                try:
                    msg_dt = datetime.fromtimestamp(float(ts))
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                    if start_dt and msg_dt < start_dt:
                        continue
                    if end_dt and msg_dt > end_dt:
                        continue
                except Exception:
                    pass
            
            # Get user info (inline with cache)
            user_info = {"id": "", "username": "", "real_name": ""}
            if user_id:
                if user_id in user_cache:
                    user_info = user_cache[user_id]
                else:
                    try:
                        user_url = "https://slack.com/api/users.info"
                        user_params = {"user": user_id}
                        user_query = urllib.parse.urlencode(user_params)
                        user_req = urllib.request.Request(
                            f"{user_url}?{user_query}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        with urllib.request.urlopen(user_req, timeout=30) as ur:
                            user_data = json.loads(ur.read().decode('utf-8'))
                            if user_data.get("ok"):
                                u_data = user_data.get("user", {})
                                profile = u_data.get("profile", {})
                                user_info = {
                                    "id": user_id,
                                    "username": u_data.get("name", ""),
                                    "real_name": profile.get("real_name", "")
                                }
                                user_cache[user_id] = user_info
                    except Exception:
                        pass
            
            # Convert timestamp
            dt = datetime.fromtimestamp(float(ts)) if ts else datetime.now()
            dt_iso = dt.isoformat() + "Z"
            
            # Build permalink (HTTPS) and desktop deep link (slack://)
            channel_id = match.get("channel", {}).get("id", "")
            permalink_ts = ts.replace('.', '')
            permalink = f"{workspace_url}/archives/{channel_id}/p{permalink_ts}"
            # Build app_redirect deep link for better browser compatibility
            desktop_link = None
            if team_id and channel_id:
                # Use app_redirect with the permalink URL for consistent browser behavior
                encoded_permalink = urllib.parse.quote(permalink, safe='')
                desktop_link = f"https://slack.com/app_redirect?team={team_id}&url={encoded_permalink}"
            
            # Extract files (inline)
            files = []
            for file_data in match.get("files", []):
                files.append({
                    "id": file_data.get("id"),
                    "name": file_data.get("name"),
                    "title": file_data.get("title"),
                    "mimetype": file_data.get("mimetype"),
                    "filetype": file_data.get("filetype"),
                    "size": file_data.get("size"),
                    "url_private_download": file_data.get("url_private_download"),
                    "created": file_data.get("created")
                })
            
            # Extract links (inline regex)
            links = []
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            url_matches = re.finditer(url_pattern, text)
            for url_match in url_matches:
                url = url_match.group(0).rstrip('.,;:)!?')
                links.append({
                    "url": url,
                    "display_text": url,
                    "type": "link"
                })
            
            # Extract reactions (inline)
            reactions = []
            for reaction_data in match.get("reactions", []):
                reactions.append({
                    "name": reaction_data.get("name"),
                    "count": reaction_data.get("count"),
                    "users": reaction_data.get("users", [])
                })
            
            # Check thread info
            reply_count = match.get("reply_count", 0)
            is_thread_parent = reply_count > 0
            
            # Apply filters (inline)
            if only_thread_parents and not is_thread_parent:
                continue
            
            if min_reply_count is not None and reply_count < min_reply_count:
                continue
            
            reaction_count = sum(r.get("count", 0) for r in reactions)
            if min_reactions is not None and reaction_count < min_reactions:
                continue
            
            if has_reactions and len(reactions) == 0:
                continue
            
            processed_msg = {
                "ts": ts,
                "text": text,
                "user": user_id,
                "username": user_info.get("username", ""),
                "real_name": user_info.get("real_name", ""),
                "datetime": dt_iso,
                "permalink": permalink,
                "desktop_link": desktop_link,
                "channel_id": channel_id,
                "channel_name": match.get("channel", {}).get("name", ""),
                "thread_ts": match.get("thread_ts"),
                "is_thread_parent": is_thread_parent,
                "reply_count": reply_count,
                "reply_users_count": match.get("reply_users_count", 0),
                "reactions": reactions,
                "files": files,
                "links": links
            }
            
            # Add highlight if present
            if "highlight" in match:
                processed_msg["highlight"] = match["highlight"]
            
            processed_messages.append(processed_msg)
        
        # Apply post-search sort if requested (inline)
        if sort_by:
            if sort_by == "timestamp":
                processed_messages.sort(key=lambda m: float(m.get("ts", 0)), reverse=True)
            elif sort_by == "reactions":
                processed_messages.sort(key=lambda m: sum(r.get("count", 0) for r in m.get("reactions", [])), reverse=True)
            elif sort_by == "reply_count":
                processed_messages.sort(key=lambda m: m.get("reply_count", 0), reverse=True)
        
        return {
                "status": "ok",
                "data": {
                    "query": final_query,
                    "total_results": total,
                    "messages": processed_messages,
                    "pagination": pagination
                }
            }
    
    except Exception as e:
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_slack_users(
    user: Optional[str] = None,
    include_deleted: Optional[bool] = False,
    limit: Optional[int] = 1000
) -> Dict[str, Any]:
    """
    Get Slack user information - list all users, get specific user details, or resolve usernames.

    When user parameter is provided, returns single user (or multiple if comma-separated).
    When user parameter is omitted, returns list of all users.

    Args:
        user: User ID(s) or username(s) (e.g., "U1234567890", "sue", or "sue,dan").
              Can be a single user or comma-separated list. If omitted, returns list of all users.
        include_deleted: Include deleted users when listing. Default: False.
        limit: Maximum number of users to return when listing. Default: 1000.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - data: User data (single user object, list of users, or array for multiple users)
        - error_message: Error message if status is "error"
    """
    # Imports inside function at the very beginning
    import os
    import traceback
    import json
    import urllib.request
    import urllib.parse
    from datetime import datetime
    
    # Wrap entire function in try-except
    try:
        # Get token
        TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
        if not TOKEN:
            return {
                "status": "error",
                "data": {},
                "error_message": "SLACK_MCP_XOXP_TOKEN not set in environment"
            }
        
        # Normalize user parameter - handle single value, comma-separated, or list (for backward compatibility)
        user_list = []
        is_single = False
        is_multiple = False

        if user is not None:
            if isinstance(user, str):
                # Single user or comma-separated
                if ',' in user:
                    user_list = [u.strip() for u in user.split(',')]
                    is_multiple = True
                else:
                    user_list = [user]
                    is_single = True
            elif isinstance(user, list):
                # Support list for backward compatibility (though Letta schema only allows str)
                user_list = user
                is_multiple = len(user) > 1
                is_single = len(user) == 1
            else:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"user parameter must be string or list, got {type(user)}"
                }
        
        # Set defaults
        if limit is None:
            limit = 1000
        if include_deleted is None:
            include_deleted = False
        
        # If user(s) specified, get specific user(s)
        if user_list:
            resolved_users = []
            # Get full user list once to resolve usernames/emails to IDs (more efficient)
            all_users_map = {}  # Map username -> user_data
            all_users_by_email = {}  # Map email -> user_data
            try:
                url = "https://slack.com/api/users.list"
                params = {"limit": "1000"}
                query_string = urllib.parse.urlencode(params)
                req = urllib.request.Request(
                    f"{url}?{query_string}",
                    headers={"Authorization": f"Bearer {TOKEN}"}
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode('utf-8'))
                    if data.get("ok"):
                        for user_item in data.get("members", []):
                            user_id = user_item.get("id")
                            username = user_item.get("name", "")
                            profile = user_item.get("profile", {})
                            email = profile.get("email", "")
                            
                            if username:
                                all_users_map[username] = user_item
                            if user_id:
                                all_users_map[user_id] = user_item
                            if email:
                                all_users_by_email[email] = user_item
            except Exception:
                pass
            
            for u in user_list:
                # Resolve username/email/userID to user item
                user_item = None
                if u.startswith("U"):
                    # It's a user ID
                    if u in all_users_map:
                        user_item = all_users_map[u]
                elif "@" in u:
                    # It's an email address
                    if u in all_users_by_email:
                        user_item = all_users_by_email[u]
                else:
                    # It's a username
                    if u in all_users_map:
                        user_item = all_users_map[u]
                
                # If not found in cache, try users.info API (for user IDs only)
                if not user_item and u.startswith("U"):
                    try:
                        url = "https://slack.com/api/users.info"
                        params = {"user": u}
                        query_string = urllib.parse.urlencode(params)
                        req = urllib.request.Request(
                            f"{url}?{query_string}",
                            headers={"Authorization": f"Bearer {TOKEN}"}
                        )
                        with urllib.request.urlopen(req, timeout=30) as r:
                            data = json.loads(r.read().decode('utf-8'))
                            if data.get("ok"):
                                user_item = data.get("user")
                    except Exception:
                        pass
                
                if not user_item:
                    if is_single:
                        return {
                            "status": "error",
                            "data": {},
                            "error_message": f"User not found: {u}"
                        }
                    continue
                
                # Process user data
                user_data = user_item
                profile = user_data.get("profile", {})
                
                # Format response (inline)
                user_info = {
                    "id": user_data.get("id"),
                    "name": user_data.get("name"),
                    "username": user_data.get("name"),
                    "real_name": profile.get("real_name", ""),
                    "display_name": profile.get("display_name", ""),
                    "email": profile.get("email", ""),
                    "image_24": profile.get("image_24", ""),
                    "image_32": profile.get("image_32", ""),
                    "image_48": profile.get("image_48", ""),
                    "image_72": profile.get("image_72", ""),
                    "image_192": profile.get("image_192", ""),
                    "image_512": profile.get("image_512", ""),
                    "status_text": profile.get("status_text", ""),
                    "status_emoji": profile.get("status_emoji", ""),
                    "is_admin": user_data.get("is_admin", False),
                    "is_owner": user_data.get("is_owner", False),
                    "is_bot": user_data.get("is_bot", False),
                    "deleted": user_data.get("deleted", False),
                    "tz": user_data.get("tz"),
                    "tz_label": user_data.get("tz_label"),
                    "tz_offset": user_data.get("tz_offset")
                }
                
                resolved_users.append(user_info)
            
            # Return appropriate structure
            if is_single:
                return {
                    "status": "ok",
                    "data": {
                        "user": resolved_users[0] if resolved_users else {}
                    }
                }
            else:
                return {
                    "status": "ok",
                    "data": {
                        "users": resolved_users
                    }
                }
        
        # Otherwise, list all users
        url = "https://slack.com/api/users.list"
        params = {"limit": str(limit)}
        if include_deleted:
            params["include_deleted"] = "true"
        
        query_string = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{url}?{query_string}",
            headers={"Authorization": f"Bearer {TOKEN}"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode('utf-8'))
            
            if not data.get("ok"):
                return {
                    "status": "error",
                    "data": {},
                    "error_message": data.get("error", "Unknown Slack API error")
                }
            
            members = data.get("members", [])
            
            # Filter deleted if not requested
            if not include_deleted:
                members = [m for m in members if not m.get("deleted", False)]
            
            # Format users (inline)
            formatted_users = []
            for member in members:
                profile = member.get("profile", {})
                formatted_users.append({
                    "id": member.get("id"),
                    "name": member.get("name"),
                    "username": member.get("name"),
                    "real_name": profile.get("real_name", ""),
                    "display_name": profile.get("display_name", ""),
                    "email": profile.get("email", ""),
                    "image_24": profile.get("image_24", ""),
                    "image_32": profile.get("image_32", ""),
                    "image_48": profile.get("image_48", ""),
                    "image_72": profile.get("image_72", ""),
                    "image_192": profile.get("image_192", ""),
                    "image_512": profile.get("image_512", ""),
                    "status_text": profile.get("status_text", ""),
                    "status_emoji": profile.get("status_emoji", ""),
                    "is_admin": member.get("is_admin", False),
                    "is_owner": member.get("is_owner", False),
                    "is_bot": member.get("is_bot", False),
                    "deleted": member.get("deleted", False),
                    "tz": member.get("tz"),
                    "tz_label": member.get("tz_label"),
                    "tz_offset": member.get("tz_offset")
                })
            
            return {
                "status": "ok",
                "data": {
                    "users": formatted_users,
                    "total": len(formatted_users)
                }
            }
    
    except Exception as e:
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error: {str(e)}\n{traceback.format_exc()}"
        }

