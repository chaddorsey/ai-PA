# PBI-26: Consolidate Drive Analytics Tools for LLM-Friendly Activity Search

## Overview

Consolidate the existing 13 Drive analytics tools into a smaller, more powerful toolset following the successful Slack tools consolidation pattern. The new toolset will support user filtering, owner filtering, date ranges, and activity type filtering while preserving existing analytics capabilities.

## Problem Statement

Current Drive tools cannot answer common questions like:
- "What Drive documents did Jie and Rebecca work on on Monday?"
- "What did Cynthia edit the most last week?"
- "Which document owned by Leslie was viewed by the most people last month?"

The existing 13 tools are fragmented, single-date only, and lack user/owner filtering capabilities. The underlying Google APIs support these filters, but they aren't exposed.

## User Stories

1. As a user, I want to search Drive activity by specific users so that I can see what my colleagues worked on.
2. As a user, I want to filter by document owner so that I can see activity on documents owned by specific people.
3. As a user, I want to query date ranges so that I can analyze activity over a week or month without multiple tool calls.
4. As a user, I want to preserve analytics capabilities (top-5 lists, trends) so that high-level summaries remain available.

## Technical Approach

### Proposed 5-Tool Structure

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `search_drive_activity` | Unified activity search | `user`, `owner`, `start_date`, `end_date`, `activity_type`, `channel` (folder), `count`, `sort_by` |
| `get_drive_documents` | Document discovery/listing | `owner`, `name`, `shared`, `type`, `modified_after`, `folder` |
| `get_drive_file_info` | Single file/folder details | `drive_url` or `file_id` (existing, minor refinement) |
| `get_drive_mentions` | @-mentions in comments | `start_date`, `end_date`, `unread_only` (consolidate from existing) |
| `get_drive_analytics_summary` | Analytics/trends | `scope`, `date`, `period` (preserve existing analytics) |

### Implementation Strategy

1. **Phase 1**: Create new consolidated tools alongside existing ones
2. **Phase 2**: Verify new tools cover all existing functionality  
3. **Phase 3**: Register new tools with Letta agent
4. **Phase 4**: Deprecate old tools (mark as deprecated, don't remove yet)
5. **Phase 5**: Remove deprecated tools after validation period

### API Mapping

| Capability | Google API | Parameter |
|------------|-----------|-----------|
| Filter by actor | Admin Reports API | `userKey` |
| Filter by owner | Drive API | `q='email' in owners` |
| Date range | Admin Reports API | `startTime`, `endTime` |
| Activity type | Admin Reports API | Event filtering |

## UX/UI Considerations

- Tool names should be self-explanatory
- Parameters should mirror Slack tool patterns for consistency
- Multi-value parameters (comma-separated) for user/owner lists
- Date parameters in YYYY-MM-DD format

## Acceptance Criteria

1. ✅ New `search_drive_activity` tool supports user, owner, date range, activity type filters
2. ✅ New `get_drive_documents` tool supports owner, name search, folder filtering
3. ✅ Existing `get_drive_file_info` preserved or minimally refined
4. ✅ `get_drive_mentions` consolidated with date range support
5. ✅ Analytics capabilities preserved in `get_drive_analytics_summary`
6. ✅ All three example questions can be answered with the new toolset
7. ✅ New tools registered with Letta agent
8. ✅ Old tools marked deprecated but functional
9. ✅ Documentation updated with new tool specifications

## Dependencies

- Google Admin Reports API access (existing)
- Google Drive API access (existing)
- Drive Activity API access (existing)
- Letta agent for tool registration

## Open Questions

1. Should `get_drive_documents` support full-text search in document content? (Probably not - that's a different API)
2. Should we support Shared Drive filtering as a separate parameter?

## Related Tasks

See [tasks.md](./tasks.md) for implementation breakdown.

[View in Backlog](../backlog.md#user-content-26)
