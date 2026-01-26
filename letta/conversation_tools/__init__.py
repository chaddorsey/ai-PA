"""
Letta Conversation Tools for multi-user agent access.

These tools enable user-scoped memory block discovery and creation
using naming conventions for permission enforcement.

Architecture Note (2026-01-26):
- `tool_variables` does not exist in Letta 0.16.3 API
- `isolated_block_labels` creates copies but memory tools operate at agent level
- Permission enforcement is "soft" via naming conventions and system prompt instructions
"""

from .find_user_blocks import find_user_blocks
from .create_user_memory_block import create_user_memory_block
from .lookup_staff import lookup_staff

__all__ = ["find_user_blocks", "create_user_memory_block", "lookup_staff"]
