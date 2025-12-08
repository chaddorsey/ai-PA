# Letta v0.14.0 Migration Plan

**Date Created**: 2025-01-21  
**Current Version**: 0.12.1  
**Target Version**: 0.14.0  
**Reference**: [Letta v0.14.0 Announcement](https://forum.letta.com/t/announcement-letta-v0-14-0/124)

## Executive Summary

Letta v0.14.0 introduces **SDK v1.0** with breaking changes, major performance improvements, and new features. This migration plan outlines the steps to safely upgrade from 0.12.1 to 0.14.0.

## Key Changes in v0.14.0

### Breaking Changes (SDK v1.0)

1. **Property Naming**: snake_case instead of camelCase
   - `llmConfig` → `llm_config`
   - All properties now use snake_case

2. **Method Renames**:
   - `modify()` → `update()`
   - `createStream()` → `stream()`

3. **List Method Pagination**:
   - List methods now return page objects with `.items` property
   - Old: `tools = client.tools.list()` (returns list directly)
   - New: `page = client.tools.list(); tools = page.items`

4. **Tool Calls**:
   - Changed from single object → array for parallel tool calling
   - Affects tools that make internal Letta API calls

### New Features

- **Parallel Tool Calling**: Full support for OpenAI and Gemini (streaming + non-streaming)
- **Webhooks for Step Completions**: Real-time notifications when agent steps complete
- **Archival Memory Enhancements**: Direct passage creation without going through agents
- **Performance Improvements**: 
  - 10× faster streaming for long streams
  - 80% faster message queries (step_id index)
  - Better memory and CPU usage

### Known Issues

⚠️ **Server SDK Version Mismatch**: The server bundles `letta-client>=0.1.319` (old SDK), which may cause compatibility issues for tools using the Letta client internally. This is expected to be fixed in a patch release.

## Impact Analysis

### Files Requiring Updates

#### High Priority (Breaking Changes)

1. **`letta/attach_scheduling_tool_to_agent.py`**
   - **Line 100**: `client.agents.modify()` → `client.agents.update()`
   - **Line 64**: `client.tools.list()` → Handle pagination (`.items`)
   - **Line 88**: `client.agents.retrieve()` - Verify still works

2. **`letta/re_register_scheduling_tool.py`**
   - **Line 47**: `client.tools.list()` → Handle pagination (`.items`)

3. **`letta/register_scheduling_tool.py`**
   - **Line 65**: `client.tools.create_from_function()` - Verify API unchanged

#### Medium Priority (Verify Compatibility)

4. **`letta/proper_cartesia_agent.py`**
   - **Line 162**: `client.agents.messages.create()` - Verify API unchanged
   - Check message response structure

5. **`letta/voice_agent/proper_cartesia_agent.py`**
   - **Line 162**: `client.agents.messages.create()` - Verify API unchanged
   - Check message response structure

6. **`letta/upload_granola_transcripts.py`**
   - **Line 66**: `client.folders.list()` → Handle pagination
   - **Line 81**: `client.embeddingModels.list()` → Handle pagination
   - **Line 88**: `client.folders.create()` - Verify API unchanged
   - **Line 133**: `client.jobs.retrieve()` - Verify API unchanged

7. **`letta/attach_folder_to_agent.py`**
   - **Line 51**: `client.folders.list()` → Handle pagination
   - **Line 72**: `client.agents.retrieve()` - Verify API unchanged

#### Low Priority (No Direct SDK Calls)

8. **`slackbot/ai/providers/letta_stream.py`**
   - Uses direct HTTP/SSE calls, not SDK
   - Verify streaming endpoint compatibility

9. **Other files**: Various files import from `letta_client` but may not use breaking APIs

### Dependencies

- **`letta/requirements.txt`**: Currently `letta-client>=0.1.0`
  - Should update to `letta-client>=0.1.324` (or latest v1.0 compatible version)
  - Note: Server bundles old SDK, but client should use new SDK

## Migration Strategy

### Phase 1: Preparation (Before Upgrade)

1. **Backup Current State**
   ```bash
   # Backup docker-compose.yml
   cp docker-compose.yml docker-compose.yml.backup
   
   # Backup version lock file
   cp config/versions/versions.lock.yml config/versions/versions.lock.yml.backup
   ```

2. **Review Current Code**
   - ✅ Identify all files using Letta SDK (done above)
   - Document current behavior for comparison

3. **Update Dependencies**
   - Update `letta/requirements.txt` to pin compatible SDK version
   - Test SDK v1.0 locally if possible

### Phase 2: Code Updates (Before Server Upgrade)

1. **Update Breaking Changes**
   - Replace `modify()` with `update()`
   - Update list method calls to handle pagination
   - Update property names to snake_case if needed

2. **Test Locally**
   - Run updated scripts against current server (should still work)
   - Verify no syntax errors

### Phase 3: Server Upgrade

1. **Update Docker Image**
   ```bash
   # Update docker-compose.yml
   # Change: image: letta/letta:latest
   # To: image: letta/letta:0.14.0
   ```

2. **Pull and Restart**
   ```bash
   docker compose pull letta
   docker compose up -d letta
   ```

3. **Verify Health**
   ```bash
   curl http://localhost:8283/v1/health/ | jq .version
   # Should show: "0.14.0"
   ```

### Phase 4: Post-Upgrade Validation

1. **Test Core Functionality**
   - [ ] Tool registration works
   - [ ] Tool attachment works
   - [ ] Agent messaging works
   - [ ] Streaming works (Slackbot)
   - [ ] Scheduling orchestrator tool works

2. **Monitor for Issues**
   - Check logs for SDK-related errors
   - Verify tool execution in Letta ADE
   - Test agent conversations

3. **Update Documentation**
   - Update version lock file
   - Update compatibility matrix
   - Document any workarounds needed

### Phase 5: Take Advantage of New Features (Optional)

1. **Parallel Tool Calling**
   - Review scheduling orchestrator for parallel tool call opportunities
   - Update tool implementations if beneficial

2. **Webhooks for Step Completions**
   - Configure `STEP_COMPLETE_WEBHOOK` if needed
   - Set up downstream pipeline triggers

3. **Archival Memory**
   - Consider direct passage creation for knowledge bases
   - Pre-populate shared knowledge bases

## Detailed Code Changes

### Change 1: Update `modify()` to `update()`

**File**: `letta/attach_scheduling_tool_to_agent.py`

**Before**:
```python
client.agents.modify(
    agent_id=LETTA_AGENT_ID,
    tool_ids=updated_tool_ids
)
```

**After**:
```python
client.agents.update(
    agent_id=LETTA_AGENT_ID,
    tool_ids=updated_tool_ids
)
```

### Change 2: Handle List Pagination

**Files**: Multiple files using `.list()` methods

**Before**:
```python
tools = client.tools.list()
for tool in tools:
    # process tool
```

**After**:
```python
tools_page = client.tools.list()
tools = tools_page.items if hasattr(tools_page, 'items') else tools_page
for tool in tools:
    # process tool
```

**Alternative (defensive)**:
```python
def get_list_items(list_result):
    """Handle both old (list) and new (page object) list responses."""
    if hasattr(list_result, 'items'):
        return list_result.items
    elif isinstance(list_result, list):
        return list_result
    else:
        return list(list_result)

tools = get_list_items(client.tools.list())
for tool in tools:
    # process tool
```

### Change 3: Update Property Names (if needed)

Check for any camelCase properties and update to snake_case:
- `llmConfig` → `llm_config`
- `toolIds` → `tool_ids`
- `agentId` → `agent_id`

## Rollback Plan

If issues occur after upgrade:

1. **Revert Docker Image**
   ```bash
   # Edit docker-compose.yml
   # Change: image: letta/letta:0.14.0
   # Back to: image: letta/letta:0.12.1
   
   docker compose pull letta
   docker compose up -d letta
   ```

2. **Revert Code Changes**
   ```bash
   git checkout <previous-commit>
   # Or manually revert the breaking changes
   ```

3. **Restore Backups**
   ```bash
   cp docker-compose.yml.backup docker-compose.yml
   cp config/versions/versions.lock.yml.backup config/versions/versions.lock.yml
   ```

## Testing Checklist

- [ ] Server starts successfully
- [ ] Health endpoint returns 0.14.0
- [ ] Tool registration script works
- [ ] Tool attachment script works
- [ ] Agent can use scheduling orchestrator tool
- [ ] Slackbot streaming works
- [ ] Voice agent (Cartesia) works
- [ ] Folder upload/attachment works
- [ ] No SDK-related errors in logs
- [ ] Performance improvements visible (optional)

## Risk Assessment

### Low Risk
- Server upgrade (Docker image change)
- Health check verification

### Medium Risk
- List pagination changes (may break iteration)
- Method rename (`modify` → `update`)

### High Risk
- Server SDK version mismatch (tools using Letta client may fail)
- Tool execution environment compatibility

## Timeline Estimate

- **Phase 1 (Preparation)**: 30 minutes
- **Phase 2 (Code Updates)**: 1-2 hours
- **Phase 3 (Server Upgrade)**: 15 minutes
- **Phase 4 (Validation)**: 1-2 hours
- **Phase 5 (New Features)**: Optional, ongoing

**Total**: ~3-5 hours for core migration

## Next Steps

1. Review this migration plan
2. Create backup of current state
3. Update code for breaking changes
4. Test locally
5. Schedule upgrade window
6. Execute migration
7. Monitor and validate

## References

- [Letta v0.14.0 Announcement](https://forum.letta.com/t/announcement-letta-v0-14-0/124)
- [SDK v1.0 Migration Guide](https://docs.letta.com/migration/sdk-v1) (referenced in announcement)
- [Letta Docker Image](https://hub.docker.com/r/letta/letta)

## Notes

- The server SDK version mismatch issue is expected to be fixed in a patch release
- Tools using Letta client internally may need to use old SDK syntax temporarily
- Consider waiting for patch release if tool compatibility is critical
- Performance improvements (10× streaming, 80% faster queries) are significant benefits

## Migration Results (2025-01-21)

### Completed Successfully

✅ **Task 23-1**: All breaking SDK changes updated
- `modify()` → `update()` in `attach_scheduling_tool_to_agent.py`
- List pagination handling added to all scripts
- All files compile successfully
- Backward compatible with v0.12.1

✅ **Task 23-2**: Server upgraded to v0.14.0
- Docker image updated from `latest` to `0.14.0`
- Service restarted successfully
- Health check passed
- Version verified: 0.14.0

✅ **Task 23-3**: Functionality validated
- SDK v1.0 compatibility confirmed (50 tools, 12 agents)
- List pagination working correctly
- All scripts compile and work
- No SDK errors in logs
- Service healthy and operational

### Key Findings

1. **List Pagination**: The defensive coding approach works perfectly - handles both old (list) and new (page object) API responses
2. **No Breaking Issues**: All functionality works correctly after upgrade
3. **Performance**: Service starts quickly and runs smoothly
4. **Compatibility**: Code changes maintain backward compatibility

### Files Modified

- `letta/attach_scheduling_tool_to_agent.py` - Updated modify→update, list pagination
- `letta/re_register_scheduling_tool.py` - List pagination
- `letta/upload_granola_transcripts.py` - List pagination (2 locations)
- `letta/attach_folder_to_agent.py` - List pagination
- `docker-compose.yml` - Updated image tag to 0.14.0
- `config/versions/versions.lock.yml` - Updated Letta version
- `config/compatibility/compatibility-matrix.yml` - Updated Letta version

### Migration Status: ✅ COMPLETE

