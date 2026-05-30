def get_drive_mentions(days: int = 7, unread_only: bool = False, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    Get comments that mention you from memory for a date range or lookback period.

    Reads from the drive_analytics_mentions memory block to get comments mentioning you.

    Args:
        days: Number of days to look back (default: 7, ignored if start_date/end_date provided)
        unread_only: Filter to only unread mentions (default: False)
        start_date: Optional start date in YYYY-MM-DD format (overrides days)
        end_date: Optional end date in YYYY-MM-DD format (defaults to today if start_date provided)

    Returns:
        str: JSON string with instructions for the agent
    """
    if start_date:
        date_instruction = (
            f"Extract entries from '{start_date}' to '{end_date or start_date}' (inclusive). "
            f"If any dates in this range are missing, inform the user which dates are missing "
            f"and offer to collect them using collect_daily_mentions() with the specific dates. "
        )
    else:
        date_instruction = (
            f"If the user specified a date range in their request, parse the dates to YYYY-MM-DD format "
            f"and extract entries for that range. Otherwise, extract entries for the past {days} days. "
            f"If specific dates are requested but not found, inform the user and offer to collect them. "
        )

    return json.dumps({
        "message": (
            f"To get Drive mentions, read the 'drive_analytics_mentions' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no mentions data is available yet and explicitly offer "
            "to collect it using collect_daily_mentions(). Do NOT make up or assume data exists. "
            f"{date_instruction}"
            f"Filter by is_new if unread_only is True ({unread_only}). "
            "For each mention, only include document links if the file is accessible. "
            "If a file is not accessible, note it in the response (e.g., 'File not accessible'). "
            "Provide a list with document links (when accessible), comment text, and timestamps."
        ),
        "block_name": "drive_analytics_mentions",
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "unread_only": unread_only,
    })
