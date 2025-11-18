"""
Slot indexer for 15-minute time grid.

Converts UTC datetime ranges to discrete 15-minute slot indices for ASP encoding.
"""

from datetime import datetime, timedelta
from typing import Tuple, List, Optional
import pytz


SLOT_SIZE_MINUTES = 15


class SlotIndexer:
    """Maps UTC datetime to 15-minute slot indices."""
    
    def __init__(self, horizon_start_utc: datetime, horizon_end_utc: datetime):
        """
        Initialize slot indexer for a planning horizon.
        
        Args:
            horizon_start_utc: Start of planning horizon (UTC)
            horizon_end_utc: End of planning horizon (UTC)
        """
        # Round down to nearest 15-minute boundary
        self.horizon_start = self._round_down_to_slot(horizon_start_utc)
        self.horizon_end = horizon_end_utc
        
        # Calculate total number of slots
        duration = self.horizon_end - self.horizon_start
        self.total_slots = int(duration.total_seconds() / 60 / SLOT_SIZE_MINUTES)
    
    @staticmethod
    def _round_down_to_slot(dt: datetime) -> datetime:
        """Round datetime down to nearest 15-minute boundary."""
        # Get minutes and round down
        minutes = dt.minute
        rounded_minutes = (minutes // SLOT_SIZE_MINUTES) * SLOT_SIZE_MINUTES
        
        # Create new datetime with rounded minutes and zero seconds/microseconds
        return dt.replace(minute=rounded_minutes, second=0, microsecond=0)
    
    def datetime_to_slot(self, dt_utc: datetime) -> Optional[int]:
        """
        Convert UTC datetime to slot index.
        
        Args:
            dt_utc: Datetime in UTC
            
        Returns:
            Slot index (0-based) or None if outside horizon
        """
        if dt_utc < self.horizon_start or dt_utc >= self.horizon_end:
            return None
        
        duration = dt_utc - self.horizon_start
        slot = int(duration.total_seconds() / 60 / SLOT_SIZE_MINUTES)
        
        # Ensure slot is within bounds
        if 0 <= slot < self.total_slots:
            return slot
        return None
    
    def slot_to_datetime(self, slot: int) -> Optional[datetime]:
        """
        Convert slot index to UTC datetime.
        
        Args:
            slot: Slot index (0-based)
            
        Returns:
            UTC datetime for start of slot, or None if invalid
        """
        if slot < 0 or slot >= self.total_slots:
            return None
        
        return self.horizon_start + timedelta(minutes=slot * SLOT_SIZE_MINUTES)
    
    def get_slots_in_range(self, start_utc: datetime, end_utc: datetime) -> List[int]:
        """
        Get all slot indices that overlap with a time range.
        
        Args:
            start_utc: Start of range (inclusive)
            end_utc: End of range (exclusive)
            
        Returns:
            List of slot indices that overlap with the range
        """
        slots = []
        
        # Find first slot that overlaps
        first_slot = self.datetime_to_slot(start_utc)
        if first_slot is None:
            # Range starts before horizon, find first slot
            if start_utc < self.horizon_start:
                first_slot = 0
            else:
                # Range starts after horizon
                return []
        
        # Find last slot that overlaps
        last_slot = self.datetime_to_slot(end_utc)
        if last_slot is None:
            # Range extends beyond horizon, use last slot
            if end_utc > self.horizon_end:
                last_slot = self.total_slots - 1
            else:
                # Range ends before horizon
                return []
        
        # Include all slots from first to last (inclusive)
        # Also include slot that contains end_utc if it's not exactly on a boundary
        end_slot = self.datetime_to_slot(end_utc)
        if end_slot is not None and end_utc > self.slot_to_datetime(end_slot):
            last_slot = max(last_slot, end_slot)
        
        for slot in range(first_slot, min(last_slot + 1, self.total_slots)):
            slots.append(slot)
        
        return slots
    
    def get_all_slots(self) -> List[int]:
        """Get all slot indices in the horizon."""
        return list(range(self.total_slots))

