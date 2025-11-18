#!/usr/bin/env python3
"""
Helper functions for managing Drive Analytics memory blocks in Letta.

This module provides utilities for working with the consolidated memory block structure:
- drive_analytics_workspace: JSON object with date-indexed workspace activity
- drive_analytics_personal: JSON object with date-indexed personal activity
- drive_analytics_mentions: JSON object with date-indexed mentions
- drive_analytics_averages: Running averages and trends
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


def merge_daily_data_into_block(
    existing_block_content: str,
    new_data: Dict[str, Any],
    date: str,
    max_days: int = 50
) -> str:
    """
    Merge new daily data into an existing memory block.
    
    Args:
        existing_block_content: Current content of the memory block (JSON string or empty)
        new_data: New data to add (dict with 'type' and 'data' keys)
        date: Date string in YYYY-MM-DD format
        max_days: Maximum number of days to keep (default: 50)
    
    Returns:
        Updated JSON string for the memory block
    """
    # Parse existing data or start fresh
    if existing_block_content and existing_block_content.strip():
        try:
            data = json.loads(existing_block_content)
        except json.JSONDecodeError:
            # If invalid JSON, start fresh
            data = {}
    else:
        data = {}
    
    # Ensure it's a dict with date-indexed entries
    if not isinstance(data, dict):
        data = {}
    
    # Add or update the date entry
    data[date] = new_data
    
    # Remove entries older than max_days
    if max_days > 0:
        cutoff_date = datetime.now() - timedelta(days=max_days)
        dates_to_remove = []
        for date_key in data.keys():
            try:
                entry_date = datetime.strptime(date_key, "%Y-%m-%d")
                if entry_date < cutoff_date:
                    dates_to_remove.append(date_key)
            except ValueError:
                # Invalid date format, keep it for now
                pass
        
        for date_key in dates_to_remove:
            del data[date]
    
    # Return formatted JSON
    return json.dumps(data, indent=2)


def get_data_for_date(block_content: str, date: str) -> Optional[Dict[str, Any]]:
    """
    Extract data for a specific date from a memory block.
    
    Args:
        block_content: Memory block content (JSON string)
        date: Date string in YYYY-MM-DD format
    
    Returns:
        Data dict for the date, or None if not found
    """
    if not block_content or not block_content.strip():
        return None
    
    try:
        data = json.loads(block_content)
        return data.get(date)
    except json.JSONDecodeError:
        return None


def get_data_for_date_range(
    block_content: str,
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """
    Extract data for a date range from a memory block.
    
    Args:
        block_content: Memory block content (JSON string)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        Dict with date keys and their data
    """
    if not block_content or not block_content.strip():
        return {}
    
    try:
        all_data = json.loads(block_content)
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        result = {}
        for date_str, date_data in all_data.items():
            try:
                entry_date = datetime.strptime(date_str, "%Y-%m-%d")
                if start <= entry_date <= end:
                    result[date_str] = date_data
            except ValueError:
                continue
        
        return result
    except json.JSONDecodeError:
        return {}


def get_latest_entry(block_content: str) -> Optional[tuple[str, Dict[str, Any]]]:
    """
    Get the most recent entry from a memory block.
    
    Args:
        block_content: Memory block content (JSON string)
    
    Returns:
        Tuple of (date, data) for the latest entry, or None
    """
    if not block_content or not block_content.strip():
        return None
    
    try:
        data = json.loads(block_content)
        if not data:
            return None
        
        # Find the latest date
        dates = []
        for date_str in data.keys():
            try:
                dates.append((datetime.strptime(date_str, "%Y-%m-%d"), date_str))
            except ValueError:
                continue
        
        if not dates:
            return None
        
        latest_date_str = max(dates, key=lambda x: x[0])[1]
        return (latest_date_str, data[latest_date_str])
    except json.JSONDecodeError:
        return None

