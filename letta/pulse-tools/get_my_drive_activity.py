from typing import Dict, Any, Optional, List

def get_my_drive_activity(days: int = 7, include_links: bool = True, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    Get your personal Drive activity with document links for a date range or lookback period.

    Reads from the drive_analytics_personal memory block to get documents you've engaged with.

    Args:
        days: Number of workdays to look back (default: 7, ignored if start_date/end_date provided)
        include_links: Whether to include Drive document links (default: True)
        start_date: Optional start date in YYYY-MM-DD format (overrides days)
        end_date: Optional end date in YYYY-MM-DD format (defaults to today if start_date provided)

    Returns:
        str: JSON string with instructions for the agent
    """
    if start_date:
        date_instruction = (
            f"Extract entries from '{start_date}' to '{end_date or start_date}' (inclusive). "
            f"If any dates in this range are missing, inform the user which dates are missing "
            f"and offer to collect them using collect_daily_personal_activity() with the specific dates. "
        )
    else:
        date_instruction = (
            f"If the user specified a date range in their request, parse the dates to YYYY-MM-DD format "
            f"and extract entries for that range. Otherwise, extract entries for the past {days} workdays. "
            f"If specific dates are requested but not found, inform the user and offer to collect them. "
        )

    return json.dumps({
        "message": (
            f"To get your Drive activity, read the 'drive_analytics_personal' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no analytics data is available yet and explicitly offer "
            "to collect it using collect_daily_personal_activity(). Do NOT make up or assume data exists. "
            f"{date_instruction}"
            f"Aggregate the top_documents from each day in the range. "
            f"For each document, use the 'display_title' field if available (it shows accessibility status), "
            f"otherwise use 'title'. "
            f"Only include links for documents where 'is_accessible' is true. "
            f"Format shared documents as: '[Title](link)'. "
            f"Format non-shared documents as: 'Title - Not shared' (no link)."
        ),
        "block_name": "drive_analytics_personal",
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "include_links": include_links,
    })
