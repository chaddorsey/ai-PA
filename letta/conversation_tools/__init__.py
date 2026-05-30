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

# lookup_staff removed 2026-05-30 as part of the Letta identities strip-out
# (Phase 4 of docs/followups/2026-05-30-strip-letta-identities.md). It read
# from /v1/identities/, which we no longer use. People lookups now go
# through canonical (agents-canonical Gitea repo) via Bash + curl per the
# canonical_reference_protocol — see archived source at
# archived/letta-conversation-tools/lookup_staff.py.

__all__ = ["find_user_blocks", "create_user_memory_block"]
