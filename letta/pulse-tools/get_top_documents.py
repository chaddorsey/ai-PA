def get_top_documents(category: str = "edited", count: int = 5, include_links: bool = True, date: Optional[str] = None) -> str:
    """
    Get top documents by category with links for a specific date or most recent.

    Reads from the drive_analytics_workspace memory block to get top documents.

    Args:
        category: Category - "edited", "shared", "commented", or "viewed" (default: "edited")
        count: Number of documents to return (default: 5)
        include_links: Whether to include Drive document links (default: True)
        date: Optional date in YYYY-MM-DD format. If not provided, uses most recent entry.

    Returns:
        str: JSON string with instructions for the agent
    """
    date_instruction = ""
    if date:
        date_instruction = (
            f"Look for the specific date '{date}' (YYYY-MM-DD format) in the block. "
            f"If that date is not found, inform the user that no data is available for {date} "
            f"and offer to collect it using collect_daily_workspace_activity(date='{date}'). "
            f"CRITICAL: You must pass the date parameter explicitly: date='{date}', not just '{date}'. "
        )
    else:
        date_instruction = (
            "If the user specified a date in their request (e.g., 'Thursday, November 13' or 'November 10, 2025'), "
            "parse it to YYYY-MM-DD format (e.g., '2025-11-13' or '2025-11-10') and look for that specific date. "
            "If the user didn't specify a date, use the most recent entry (latest date key). "
            "If a specific date is requested but not found, inform the user and offer to collect it. "
            "IMPORTANT: When calling collect_daily_workspace_activity() to collect data, you MUST pass the date parameter. "
            "For example, if the user asks for November 10, 2025, you must call: collect_daily_workspace_activity(date='2025-11-10'). "
            "Do NOT call collect_daily_workspace_activity() without the date parameter, as it will default to the last workday "
            "and may not match what the user requested. "
        )

    return json.dumps({
        "message": (
            f"To get top {count} {category} documents, "
            "read the 'drive_analytics_workspace' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no analytics data is available yet and explicitly offer "
            "to collect it using collect_daily_workspace_activity(). Do NOT make up or assume data exists. "
            f"{date_instruction}"
            f"If data exists for the requested date, extract the top_five.most_{category} list "
            f"and return the top {count} items. "
            f"For each document, use the 'display_title' field if available (it shows accessibility status like 'Not shared' or 'Deleted'), "
            f"otherwise use 'title'. "
            f"Only include links for documents where 'is_accessible' is true. "
            f"Format shared documents as: '[Title](link)'. "
            f"Format non-shared documents as: 'Title - Not shared' (no link). "
            f"Format deleted documents as: 'Title - Deleted' (no link)."
        ),
        "block_name": "drive_analytics_workspace",
        "category": category,
        "count": count,
        "include_links": include_links,
        "date": date,
    })
