"""Schema registry for Slack API methods.

Maps Slack API method names to metadata including parameters,
token requirements, and OAuth scopes.
"""

SCHEMAS: dict[str, dict] = {
    # ── conversations ────────────────────────────────────────────────
    "conversations.list": {
        "method": "conversations.list",
        "description": "List all channels in a Slack team.",
        "token_type": "bot",
        "scopes": ["channels:read", "groups:read", "im:read", "mpim:read"],
        "params": {
            "types": {
                "type": "str",
                "required": False,
                "description": "Comma-separated list of channel types (public_channel, private_channel, mpim, im).",
            },
            "limit": {
                "type": "int",
                "required": False,
                "description": "Maximum number of items to return (default 100, max 1000).",
            },
            "exclude_archived": {
                "type": "bool",
                "required": False,
                "description": "Set to true to exclude archived channels.",
            },
            "cursor": {
                "type": "str",
                "required": False,
                "description": "Pagination cursor for next page of results.",
            },
        },
    },
    "conversations.info": {
        "method": "conversations.info",
        "description": "Retrieve information about a conversation.",
        "token_type": "bot",
        "scopes": ["channels:read", "groups:read", "im:read", "mpim:read"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to get info on.",
                "semantic_type": "slack_id",
            },
        },
    },
    "conversations.history": {
        "method": "conversations.history",
        "description": "Fetch message history of a conversation.",
        "token_type": "bot",
        "scopes": ["channels:history", "groups:history", "im:history", "mpim:history"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to fetch history for.",
                "semantic_type": "slack_id",
            },
            "oldest": {
                "type": "str",
                "required": False,
                "description": "Only messages after this Unix timestamp.",
                "semantic_type": "timestamp",
            },
            "latest": {
                "type": "str",
                "required": False,
                "description": "Only messages before this Unix timestamp.",
                "semantic_type": "timestamp",
            },
            "limit": {
                "type": "int",
                "required": False,
                "description": "Maximum number of items to return (default 100, max 1000).",
            },
            "inclusive": {
                "type": "bool",
                "required": False,
                "description": "Include messages with oldest or latest timestamps.",
            },
            "cursor": {
                "type": "str",
                "required": False,
                "description": "Pagination cursor for next page of results.",
            },
        },
    },
    "conversations.create": {
        "method": "conversations.create",
        "description": "Create a new channel.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "name": {
                "type": "str",
                "required": True,
                "description": "Name of the channel to create.",
            },
            "is_private": {
                "type": "bool",
                "required": False,
                "description": "Set to true to create a private channel.",
            },
        },
    },
    "conversations.archive": {
        "method": "conversations.archive",
        "description": "Archive a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to archive.",
                "semantic_type": "slack_id",
            },
        },
    },
    "conversations.unarchive": {
        "method": "conversations.unarchive",
        "description": "Unarchive a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to unarchive.",
                "semantic_type": "slack_id",
            },
        },
    },
    "conversations.invite": {
        "method": "conversations.invite",
        "description": "Invite users to a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to invite users to.",
                "semantic_type": "slack_id",
            },
            "users": {
                "type": "str",
                "required": True,
                "description": "Comma-separated list of user IDs to invite.",
            },
        },
    },
    "conversations.kick": {
        "method": "conversations.kick",
        "description": "Remove a user from a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to remove user from.",
                "semantic_type": "slack_id",
            },
            "user": {
                "type": "str",
                "required": True,
                "description": "User ID to remove.",
                "semantic_type": "slack_id",
            },
        },
    },
    "conversations.join": {
        "method": "conversations.join",
        "description": "Join an existing conversation.",
        "token_type": "bot",
        "scopes": ["channels:join"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to join.",
                "semantic_type": "slack_id",
            },
        },
    },
    "conversations.leave": {
        "method": "conversations.leave",
        "description": "Leave a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to leave.",
                "semantic_type": "slack_id",
            },
        },
    },
    "conversations.open": {
        "method": "conversations.open",
        "description": "Open or resume a direct message or multi-person direct message.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": False,
                "description": "Resume a conversation by its channel ID.",
                "semantic_type": "slack_id",
            },
            "users": {
                "type": "str",
                "required": False,
                "description": "Comma-separated list of user IDs to open a DM with.",
            },
        },
    },
    "conversations.close": {
        "method": "conversations.close",
        "description": "Close a direct message or multi-person direct message.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to close.",
                "semantic_type": "slack_id",
            },
        },
    },
    "conversations.members": {
        "method": "conversations.members",
        "description": "List members of a conversation.",
        "token_type": "bot",
        "scopes": ["channels:read", "groups:read", "im:read", "mpim:read"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to fetch members for.",
                "semantic_type": "slack_id",
            },
            "limit": {
                "type": "int",
                "required": False,
                "description": "Maximum number of members to return (default 100, max 1000).",
            },
            "cursor": {
                "type": "str",
                "required": False,
                "description": "Pagination cursor for next page of results.",
            },
        },
    },
    "conversations.rename": {
        "method": "conversations.rename",
        "description": "Rename a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to rename.",
                "semantic_type": "slack_id",
            },
            "name": {
                "type": "str",
                "required": True,
                "description": "New name for the conversation.",
            },
        },
    },
    "conversations.setPurpose": {
        "method": "conversations.setPurpose",
        "description": "Set the purpose for a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to set purpose for.",
                "semantic_type": "slack_id",
            },
            "purpose": {
                "type": "str",
                "required": True,
                "description": "The new purpose for the conversation.",
            },
        },
    },
    "conversations.setTopic": {
        "method": "conversations.setTopic",
        "description": "Set the topic for a conversation.",
        "token_type": "bot",
        "scopes": ["channels:manage", "groups:write", "im:write", "mpim:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID to set topic for.",
                "semantic_type": "slack_id",
            },
            "topic": {
                "type": "str",
                "required": True,
                "description": "The new topic for the conversation.",
            },
        },
    },
    # ── chat ─────────────────────────────────────────────────────────
    "chat.postMessage": {
        "method": "chat.postMessage",
        "description": "Send a message to a channel.",
        "token_type": "either",
        "scopes": ["chat:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel, private group, or IM channel to send message to.",
                "semantic_type": "slack_id",
            },
            "text": {
                "type": "str",
                "required": False,
                "description": "Text of the message to send (required if blocks is not provided).",
            },
            "blocks": {
                "type": "str",
                "required": False,
                "description": "JSON array of Block Kit blocks.",
            },
            "thread_ts": {
                "type": "str",
                "required": False,
                "description": "Timestamp of another message to reply to as a thread.",
                "semantic_type": "timestamp",
            },
            "unfurl_links": {
                "type": "bool",
                "required": False,
                "description": "Pass true to enable unfurling of primarily text-based content.",
            },
            "unfurl_media": {
                "type": "bool",
                "required": False,
                "description": "Pass false to disable unfurling of media content.",
            },
        },
    },
    "chat.update": {
        "method": "chat.update",
        "description": "Update an existing message.",
        "token_type": "bot",
        "scopes": ["chat:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel containing the message to update.",
                "semantic_type": "slack_id",
            },
            "ts": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to update.",
                "semantic_type": "timestamp",
            },
            "text": {
                "type": "str",
                "required": False,
                "description": "New text for the message.",
            },
            "blocks": {
                "type": "str",
                "required": False,
                "description": "JSON array of Block Kit blocks.",
            },
        },
    },
    "chat.delete": {
        "method": "chat.delete",
        "description": "Delete a message.",
        "token_type": "bot",
        "scopes": ["chat:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel containing the message to delete.",
                "semantic_type": "slack_id",
            },
            "ts": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to delete.",
                "semantic_type": "timestamp",
            },
        },
    },
    "chat.postEphemeral": {
        "method": "chat.postEphemeral",
        "description": "Send an ephemeral message visible only to a specific user.",
        "token_type": "bot",
        "scopes": ["chat:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel to send the ephemeral message in.",
                "semantic_type": "slack_id",
            },
            "user": {
                "type": "str",
                "required": True,
                "description": "User ID who will see the ephemeral message.",
                "semantic_type": "slack_id",
            },
            "text": {
                "type": "str",
                "required": False,
                "description": "Text of the message (required if blocks is not provided).",
            },
            "blocks": {
                "type": "str",
                "required": False,
                "description": "JSON array of Block Kit blocks.",
            },
        },
    },
    "chat.scheduleMessage": {
        "method": "chat.scheduleMessage",
        "description": "Schedule a message to be sent at a specific time.",
        "token_type": "bot",
        "scopes": ["chat:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel to send the scheduled message to.",
                "semantic_type": "slack_id",
            },
            "text": {
                "type": "str",
                "required": True,
                "description": "Text of the message to send.",
            },
            "post_at": {
                "type": "int",
                "required": True,
                "description": "Unix timestamp for when the message should be sent.",
                "semantic_type": "timestamp",
            },
        },
    },
    "chat.unfurl": {
        "method": "chat.unfurl",
        "description": "Provide custom unfurl behavior for URLs in messages.",
        "token_type": "bot",
        "scopes": ["links:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel ID of the message.",
                "semantic_type": "slack_id",
            },
            "ts": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to add unfurl to.",
                "semantic_type": "timestamp",
            },
            "unfurls": {
                "type": "str",
                "required": True,
                "description": "JSON map of URL to unfurl Block Kit attachment.",
            },
        },
    },
    # ── users ────────────────────────────────────────────────────────
    "users.list": {
        "method": "users.list",
        "description": "List all users in a Slack team.",
        "token_type": "bot",
        "scopes": ["users:read"],
        "params": {
            "limit": {
                "type": "int",
                "required": False,
                "description": "Maximum number of users to return per page.",
            },
            "cursor": {
                "type": "str",
                "required": False,
                "description": "Pagination cursor for next page of results.",
            },
        },
    },
    "users.info": {
        "method": "users.info",
        "description": "Get information about a user.",
        "token_type": "bot",
        "scopes": ["users:read"],
        "params": {
            "user": {
                "type": "str",
                "required": True,
                "description": "User ID to get info on.",
                "semantic_type": "slack_id",
            },
        },
    },
    "users.lookupByEmail": {
        "method": "users.lookupByEmail",
        "description": "Find a user by their email address.",
        "token_type": "bot",
        "scopes": ["users:read.email"],
        "params": {
            "email": {
                "type": "str",
                "required": True,
                "description": "Email address to look up.",
            },
        },
    },
    "users.getPresence": {
        "method": "users.getPresence",
        "description": "Get a user's current presence status.",
        "token_type": "bot",
        "scopes": ["users:read"],
        "params": {
            "user": {
                "type": "str",
                "required": True,
                "description": "User ID to get presence for.",
                "semantic_type": "slack_id",
            },
        },
    },
    "users.setPresence": {
        "method": "users.setPresence",
        "description": "Manually set the user's presence.",
        "token_type": "bot",
        "scopes": ["users:write"],
        "params": {
            "presence": {
                "type": "str",
                "required": True,
                "description": "Either 'auto' or 'away'.",
            },
        },
    },
    # ── reactions ────────────────────────────────────────────────────
    "reactions.add": {
        "method": "reactions.add",
        "description": "Add a reaction emoji to a message.",
        "token_type": "bot",
        "scopes": ["reactions:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel where the message to react to was posted.",
                "semantic_type": "slack_id",
            },
            "timestamp": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to react to.",
                "semantic_type": "timestamp",
            },
            "name": {
                "type": "str",
                "required": True,
                "description": "Reaction emoji name (without colons).",
            },
        },
    },
    "reactions.remove": {
        "method": "reactions.remove",
        "description": "Remove a reaction emoji from a message.",
        "token_type": "bot",
        "scopes": ["reactions:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel where the message was posted.",
                "semantic_type": "slack_id",
            },
            "timestamp": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to remove reaction from.",
                "semantic_type": "timestamp",
            },
            "name": {
                "type": "str",
                "required": True,
                "description": "Reaction emoji name to remove (without colons).",
            },
        },
    },
    "reactions.get": {
        "method": "reactions.get",
        "description": "Get reactions for a message.",
        "token_type": "either",
        "scopes": ["reactions:read"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel where the message was posted.",
                "semantic_type": "slack_id",
            },
            "timestamp": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to get reactions for.",
                "semantic_type": "timestamp",
            },
        },
    },
    "reactions.list": {
        "method": "reactions.list",
        "description": "List reactions made by a user.",
        "token_type": "either",
        "scopes": ["reactions:read"],
        "params": {
            "user": {
                "type": "str",
                "required": False,
                "description": "User ID to show reactions for (defaults to authed user).",
                "semantic_type": "slack_id",
            },
            "limit": {
                "type": "int",
                "required": False,
                "description": "Maximum number of items to return.",
            },
            "cursor": {
                "type": "str",
                "required": False,
                "description": "Pagination cursor for next page of results.",
            },
        },
    },
    # ── files ────────────────────────────────────────────────────────
    "files.list": {
        "method": "files.list",
        "description": "List files shared in a team.",
        "token_type": "bot",
        "scopes": ["files:read"],
        "params": {
            "channel": {
                "type": "str",
                "required": False,
                "description": "Filter files appearing in this channel.",
                "semantic_type": "slack_id",
            },
            "user": {
                "type": "str",
                "required": False,
                "description": "Filter files uploaded by this user.",
                "semantic_type": "slack_id",
            },
            "types": {
                "type": "str",
                "required": False,
                "description": "Filter by file types (e.g. 'images', 'pdfs').",
            },
            "count": {
                "type": "int",
                "required": False,
                "description": "Number of items to return per page.",
            },
        },
    },
    "files.upload": {
        "method": "files.upload",
        "description": "Upload a file to Slack.",
        "token_type": "bot",
        "scopes": ["files:write"],
        "params": {
            "channels": {
                "type": "str",
                "required": False,
                "description": "Comma-separated list of channel IDs to share the file in.",
            },
            "content": {
                "type": "str",
                "required": False,
                "description": "File contents via a POST variable.",
            },
            "file": {
                "type": "str",
                "required": False,
                "description": "Path to file data to upload.",
            },
            "filename": {
                "type": "str",
                "required": False,
                "description": "Filename of the file.",
            },
            "title": {
                "type": "str",
                "required": False,
                "description": "Title of the file.",
            },
        },
    },
    "files.info": {
        "method": "files.info",
        "description": "Get information about a file.",
        "token_type": "bot",
        "scopes": ["files:read"],
        "params": {
            "file": {
                "type": "str",
                "required": True,
                "description": "File ID to get info for.",
                "semantic_type": "slack_id",
            },
        },
    },
    "files.delete": {
        "method": "files.delete",
        "description": "Delete a file.",
        "token_type": "bot",
        "scopes": ["files:write"],
        "params": {
            "file": {
                "type": "str",
                "required": True,
                "description": "File ID to delete.",
                "semantic_type": "slack_id",
            },
        },
    },
    # ── search ───────────────────────────────────────────────────────
    "search.messages": {
        "method": "search.messages",
        "description": "Search for messages matching a query.",
        "token_type": "user",
        "scopes": ["search:read"],
        "params": {
            "query": {
                "type": "str",
                "required": True,
                "description": "Search query text.",
            },
            "sort": {
                "type": "str",
                "required": False,
                "description": "Sort results by 'score' or 'timestamp'.",
            },
            "sort_dir": {
                "type": "str",
                "required": False,
                "description": "Sort direction: 'asc' or 'desc'.",
            },
            "count": {
                "type": "int",
                "required": False,
                "description": "Number of items to return per page.",
            },
            "page": {
                "type": "int",
                "required": False,
                "description": "Page number of results to return.",
            },
        },
    },
    "search.files": {
        "method": "search.files",
        "description": "Search for files matching a query.",
        "token_type": "user",
        "scopes": ["search:read"],
        "params": {
            "query": {
                "type": "str",
                "required": True,
                "description": "Search query text.",
            },
            "sort": {
                "type": "str",
                "required": False,
                "description": "Sort results by 'score' or 'timestamp'.",
            },
            "sort_dir": {
                "type": "str",
                "required": False,
                "description": "Sort direction: 'asc' or 'desc'.",
            },
            "count": {
                "type": "int",
                "required": False,
                "description": "Number of items to return per page.",
            },
            "page": {
                "type": "int",
                "required": False,
                "description": "Page number of results to return.",
            },
        },
    },
    # ── pins ─────────────────────────────────────────────────────────
    "pins.add": {
        "method": "pins.add",
        "description": "Pin a message to a channel.",
        "token_type": "bot",
        "scopes": ["pins:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel to pin the message in.",
                "semantic_type": "slack_id",
            },
            "timestamp": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to pin.",
                "semantic_type": "timestamp",
            },
        },
    },
    "pins.remove": {
        "method": "pins.remove",
        "description": "Unpin a message from a channel.",
        "token_type": "bot",
        "scopes": ["pins:write"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel to unpin the message from.",
                "semantic_type": "slack_id",
            },
            "timestamp": {
                "type": "str",
                "required": True,
                "description": "Timestamp of the message to unpin.",
                "semantic_type": "timestamp",
            },
        },
    },
    "pins.list": {
        "method": "pins.list",
        "description": "List pinned items in a channel.",
        "token_type": "bot",
        "scopes": ["pins:read"],
        "params": {
            "channel": {
                "type": "str",
                "required": True,
                "description": "Channel to list pins for.",
                "semantic_type": "slack_id",
            },
        },
    },
    # ── bookmarks ────────────────────────────────────────────────────
    "bookmarks.add": {
        "method": "bookmarks.add",
        "description": "Add a bookmark to a channel.",
        "token_type": "bot",
        "scopes": ["bookmarks:write"],
        "params": {
            "channel_id": {
                "type": "str",
                "required": True,
                "description": "Channel ID to add the bookmark to.",
                "semantic_type": "slack_id",
            },
            "title": {
                "type": "str",
                "required": True,
                "description": "Title for the bookmark.",
            },
            "type": {
                "type": "str",
                "required": True,
                "description": "Type of bookmark (e.g. 'link').",
            },
            "link": {
                "type": "str",
                "required": False,
                "description": "URL for the bookmark (required when type is 'link').",
            },
        },
    },
    "bookmarks.edit": {
        "method": "bookmarks.edit",
        "description": "Edit a bookmark in a channel.",
        "token_type": "bot",
        "scopes": ["bookmarks:write"],
        "params": {
            "bookmark_id": {
                "type": "str",
                "required": True,
                "description": "Bookmark ID to edit.",
                "semantic_type": "slack_id",
            },
            "channel_id": {
                "type": "str",
                "required": True,
                "description": "Channel ID containing the bookmark.",
                "semantic_type": "slack_id",
            },
            "title": {
                "type": "str",
                "required": False,
                "description": "New title for the bookmark.",
            },
            "link": {
                "type": "str",
                "required": False,
                "description": "New URL for the bookmark.",
            },
        },
    },
    "bookmarks.remove": {
        "method": "bookmarks.remove",
        "description": "Remove a bookmark from a channel.",
        "token_type": "bot",
        "scopes": ["bookmarks:write"],
        "params": {
            "bookmark_id": {
                "type": "str",
                "required": True,
                "description": "Bookmark ID to remove.",
                "semantic_type": "slack_id",
            },
            "channel_id": {
                "type": "str",
                "required": True,
                "description": "Channel ID containing the bookmark.",
                "semantic_type": "slack_id",
            },
        },
    },
    "bookmarks.list": {
        "method": "bookmarks.list",
        "description": "List bookmarks in a channel.",
        "token_type": "bot",
        "scopes": ["bookmarks:read"],
        "params": {
            "channel_id": {
                "type": "str",
                "required": True,
                "description": "Channel ID to list bookmarks for.",
                "semantic_type": "slack_id",
            },
        },
    },
    # ── reminders ────────────────────────────────────────────────────
    "reminders.add": {
        "method": "reminders.add",
        "description": "Create a reminder.",
        "token_type": "bot",
        "scopes": ["reminders:write"],
        "params": {
            "text": {
                "type": "str",
                "required": True,
                "description": "Content of the reminder.",
            },
            "time": {
                "type": "str",
                "required": True,
                "description": "When the reminder should fire (Unix timestamp or natural language).",
            },
            "user": {
                "type": "str",
                "required": False,
                "description": "User ID to receive the reminder (defaults to authed user).",
                "semantic_type": "slack_id",
            },
        },
    },
    "reminders.complete": {
        "method": "reminders.complete",
        "description": "Mark a reminder as complete.",
        "token_type": "bot",
        "scopes": ["reminders:write"],
        "params": {
            "reminder": {
                "type": "str",
                "required": True,
                "description": "Reminder ID to mark complete.",
                "semantic_type": "slack_id",
            },
        },
    },
    "reminders.delete": {
        "method": "reminders.delete",
        "description": "Delete a reminder.",
        "token_type": "bot",
        "scopes": ["reminders:write"],
        "params": {
            "reminder": {
                "type": "str",
                "required": True,
                "description": "Reminder ID to delete.",
                "semantic_type": "slack_id",
            },
        },
    },
    "reminders.info": {
        "method": "reminders.info",
        "description": "Get information about a reminder.",
        "token_type": "bot",
        "scopes": ["reminders:read"],
        "params": {
            "reminder": {
                "type": "str",
                "required": True,
                "description": "Reminder ID to get info for.",
                "semantic_type": "slack_id",
            },
        },
    },
    "reminders.list": {
        "method": "reminders.list",
        "description": "List all reminders for the authenticated user.",
        "token_type": "bot",
        "scopes": ["reminders:read"],
        "params": {},
    },
    # ── team ─────────────────────────────────────────────────────────
    "team.info": {
        "method": "team.info",
        "description": "Get information about the current team.",
        "token_type": "bot",
        "scopes": ["team:read"],
        "params": {},
    },
    "team.accessLogs": {
        "method": "team.accessLogs",
        "description": "Get the access logs for the current team.",
        "token_type": "bot",
        "scopes": ["admin"],
        "params": {
            "count": {
                "type": "int",
                "required": False,
                "description": "Number of items to return per page.",
            },
            "page": {
                "type": "int",
                "required": False,
                "description": "Page number of results to return.",
            },
            "before": {
                "type": "int",
                "required": False,
                "description": "Unix timestamp to filter logs before this time.",
                "semantic_type": "timestamp",
            },
        },
    },
    "team.billableInfo": {
        "method": "team.billableInfo",
        "description": "Get billable users information for the current team.",
        "token_type": "bot",
        "scopes": ["admin"],
        "params": {
            "user": {
                "type": "str",
                "required": False,
                "description": "User ID to get billable info for.",
                "semantic_type": "slack_id",
            },
        },
    },
}


def get_schema(method: str) -> dict | None:
    """Get schema for a specific method."""
    return SCHEMAS.get(method)


def list_schemas() -> list[str]:
    """List all available method names."""
    return sorted(SCHEMAS.keys())


def list_groups() -> list[str]:
    """List all available command groups."""
    return sorted({key.split(".")[0] for key in SCHEMAS})


def get_group_methods(group: str) -> list[str]:
    """List methods in a specific group."""
    return sorted(k for k in SCHEMAS if k.startswith(f"{group}."))
