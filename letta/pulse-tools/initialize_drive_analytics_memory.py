def initialize_drive_analytics_memory() -> str:
    """
    Initialize Drive analytics memory blocks if they don't exist.

    Creates the consolidated memory blocks with empty JSON objects.
    The agent should call this once to set up the memory structure.

    Returns:
        str: JSON string with instructions for the agent
    """
    _my_email = os.getenv("MY_EMAIL", "cdorsey@concord.org")
    return json.dumps({
        "message": (
            "Initialize Drive analytics memory blocks. For each block name below, "
            "check if it exists using memory_read. If it doesn't exist, create it using "
            "memory_create with an empty JSON object {} as the initial content. "
            "Blocks to create: drive_analytics_workspace, drive_analytics_personal, "
            "drive_analytics_mentions, drive_analytics_averages, drive_analytics_config. "
            "For the config block, you can initialize it with: "
            '{"my_email": "cdorsey@concord.org", "max_days": 50}.'
        ),
        "blocks_to_create": [
            "drive_analytics_workspace",
            "drive_analytics_personal",
            "drive_analytics_mentions",
            "drive_analytics_averages",
            "drive_analytics_config"
        ],
        "initial_content": {
            "drive_analytics_workspace": "{}",
            "drive_analytics_personal": "{}",
            "drive_analytics_mentions": "{}",
            "drive_analytics_averages": "{}",
            "drive_analytics_config": json.dumps({
                "my_email": _my_email,
                "max_days": 50
            }, indent=2)
        }
    })
