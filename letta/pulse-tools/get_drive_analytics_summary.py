from typing import Dict, Any, Optional, List

def get_drive_analytics_summary(period: str = "yesterday", scope: str = "workspace", date: Optional[str] = None) -> str:
    """
    Get summary of Drive activity for a period or specific date from memory blocks.

    Reads from stored memory blocks to provide a summary of Drive activity.
    The agent should read from the consolidated memory blocks:
    - drive_analytics_workspace (for workspace data)
    - drive_analytics_personal (for personal data)

    Args:
        period: Time period - "today", "yesterday", "last_7_workdays", "last_10_workdays" (ignored if date is provided)
        scope: Scope of data - "workspace" or "personal"
        date: Optional specific date in YYYY-MM-DD format. If provided, overrides period.

    Returns:
        str: JSON string with instructions for the agent
    """
    block_name = "drive_analytics_workspace" if scope == "workspace" else "drive_analytics_personal"

    if date:
        date_instruction = (
            f"Look for the specific date '{date}' (YYYY-MM-DD format) in the block. "
            f"If that date is not found, inform the user that no data is available for {date} "
            f"and offer to collect it using collect_daily_workspace_activity('{date}') "
            f"or collect_daily_personal_activity('{date}'). "
        )
    else:
        date_instruction = (
            f"If the user specified a date in their request, parse it to YYYY-MM-DD format "
            f"and look for that specific date. Otherwise, interpret the period '{period}' "
            f"(e.g., 'yesterday' = most recent workday, 'today' = today if it's a workday). "
            f"If a specific date is requested but not found, inform the user and offer to collect it. "
        )

    return json.dumps({
        "message": (
            f"To get Drive analytics summary for {period if not date else date} ({scope}), "
            f"read the '{block_name}' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no analytics data is available yet and explicitly offer "
            "to collect it using collect_daily_workspace_activity() or collect_daily_personal_activity(). "
            "Do NOT make up or assume data exists. "
            f"{date_instruction}"
            "If data exists for the requested date/period, extract it and provide a summary."
        ),
        "block_name": block_name,
        "period": period,
        "scope": scope,
        "date": date,
    })
