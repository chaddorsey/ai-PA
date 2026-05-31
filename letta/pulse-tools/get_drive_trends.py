from typing import Dict, Any, Optional, List

def get_drive_trends(metric: str = "document", comparison_period: str = "10_day") -> str:
    """
    Compare current activity to historical averages.

    Reads from memory blocks and compares current period to running averages.

    Args:
        metric: What to analyze - "activity_type", "document", or "user"
        comparison_period: Period for comparison - "3_day", "10_day", or "50_day"

    Returns:
        str: JSON string with trends (or instruction to read from memory)
    """
    return json.dumps({
        "message": (
            f"To get Drive trends for {metric} compared to {comparison_period} average, "
            "read from drive_analytics_averages memory block and compare with recent daily logs. "
            "Use memory blocks to access stored data."
        ),
        "metric": metric,
        "comparison_period": comparison_period,
    })
