# PBI-23: Letta v0.14.0 Migration with SDK v1.0 Compatibility

[View in Backlog](../backlog.md#user-content-23)

## Overview

Migrate Letta from v0.12.1 to v0.14.0, updating all code to be compatible with SDK v1.0 breaking changes, and take advantage of major performance improvements and new features including parallel tool calling, webhooks, and archival memory enhancements.

## Problem Statement

Letta v0.14.0 introduces SDK v1.0 with breaking changes that require code updates:
- Method renames: `modify()` → `update()`, `createStream()` → `stream()`
- List pagination: methods now return page objects with `.items` property
- Property naming: snake_case instead of camelCase
- Tool calls: changed from single object → array for parallel tool calling

Additionally, v0.14.0 provides significant benefits:
- 10× faster streaming for long streams
- 80% faster message queries (step_id index)
- Parallel tool calling support (OpenAI and Gemini)
- Webhooks for step completions
- Enhanced archival memory management

Without migration, the system cannot take advantage of these improvements and may face compatibility issues as legacy APIs are deprecated.

## User Stories

**Primary Actor: System Administrator**
- As a system administrator, I want Letta upgraded to v0.14.0 so that I can benefit from performance improvements and new features
- As a system administrator, I want all SDK breaking changes updated in code so that tools and scripts continue to work correctly
- As a system administrator, I want version lock files updated so that the system state is accurately documented
- As a system administrator, I want rollback procedures documented so that I can quickly revert if issues occur

**Secondary Actors:**
- **Application Developer**: Needs tools and scripts to work with new SDK
- **AI Engineer**: Wants to leverage parallel tool calling and performance improvements
- **DevOps Engineer**: Needs migration procedures and validation testing

## Technical Approach

### Migration Strategy

1. **Code Updates (Before Server Upgrade)**
   - Update all `modify()` calls to `update()`
   - Handle list pagination changes (`.items` property)
   - Update property names to snake_case if needed
   - Test updated code against current server (should still work)

2. **Server Upgrade**
   - Update Docker image from `letta/letta:latest` to `letta/letta:0.14.0`
   - Pull new image and restart service
   - Verify health and version

3. **Post-Upgrade Validation**
   - Test all tools and scripts
   - Verify agent functionality
   - Monitor for SDK-related errors
   - Validate performance improvements

4. **Documentation Updates**
   - Update version lock files
   - Update compatibility matrix
   - Document migration procedures
   - Document rollback procedures

### Files Requiring Updates

**High Priority (Breaking Changes):**
- `letta/attach_scheduling_tool_to_agent.py` - `modify()` → `update()`, list pagination
- `letta/re_register_scheduling_tool.py` - list pagination
- `letta/register_scheduling_tool.py` - verify API compatibility

**Medium Priority (Verify Compatibility):**
- `letta/proper_cartesia_agent.py` - message API compatibility
- `letta/voice_agent/proper_cartesia_agent.py` - message API compatibility
- `letta/upload_granola_transcripts.py` - list pagination
- `letta/attach_folder_to_agent.py` - list pagination

**Dependencies:**
- `letta/requirements.txt` - update `letta-client` version if needed

### Known Issues and Considerations

⚠️ **Server SDK Version Mismatch**: The server bundles `letta-client>=0.1.319` (old SDK), which may cause compatibility issues for tools using the Letta client internally. This is expected to be fixed in a patch release. Tools may need to use old SDK syntax temporarily.

## UX/UI Considerations

- No user-facing UI changes
- Migration is transparent to end users
- Performance improvements should be noticeable in agent response times

## Acceptance Criteria

1. **Code Updates Complete**
   - All `modify()` calls updated to `update()`
   - All list methods handle pagination correctly
   - All property names use snake_case where applicable
   - Code tested against current server (backward compatible)

2. **Server Upgrade Successful**
   - Docker image updated to `letta/letta:0.14.0`
   - Health endpoint returns version 0.14.0
   - Service starts and runs without errors

3. **Functionality Validated**
   - Tool registration works
   - Tool attachment works
   - Agent messaging works
   - Streaming works (Slackbot)
   - Scheduling orchestrator tool works
   - All scripts execute successfully

4. **Documentation Updated**
   - Version lock file updated to 0.14.0
   - Compatibility matrix updated
   - Migration procedures documented
   - Rollback procedures documented

5. **Performance Improvements Verified**
   - Streaming performance improved (optional validation)
   - Query performance improved (optional validation)

## Dependencies

- **PBI 11**: Framework version management provides foundation for upgrade procedures
- Current Letta v0.12.1 must be running and stable
- All tools and scripts must be accessible for updates

## Open Questions

1. Should we wait for patch release to fix server SDK version mismatch?
   - **Decision**: Proceed with migration, monitor for issues, use workarounds if needed

2. Do we need to update `letta-client` Python package version?
   - **Decision**: Verify compatibility, update if necessary

3. Should we enable new features (webhooks, parallel tool calling) immediately?
   - **Decision**: Focus on migration first, enable features in follow-up tasks if desired

## Related Tasks

See [Tasks for PBI 23](./tasks.md) for detailed task breakdown.

## References

- [Letta v0.14.0 Announcement](https://forum.letta.com/t/announcement-letta-v0-14-0/124)
- [SDK v1.0 Migration Guide](https://docs.letta.com/migration/sdk-v1) (referenced in announcement)
- [Migration Plan Document](../letta-v0.14-migration-plan.md)

