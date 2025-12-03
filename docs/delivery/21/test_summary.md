# Test Setup Summary for Scheduling Orchestrator

## What We've Set Up

1. **Test Input Data** (`example_event_data.md`)
   - Real calendar event data for three participants (Chad, Sue, Danielle)
   - Timeframe: December 1-12, 2025
   - Contains ~40 events per participant with various types (meetings, holds, vacation blocks)

2. **Test Script** (`test_orchestrator_sue_danielle.py`)
   - Automated test that loads events and calls the orchestrator
   - Parses the markdown-formatted event data
   - Converts event format (nested dateTime → flat strings, summary → title)
   - Prints human-readable results and saves JSON output

3. **Formatted Input** (`test_input_sue_danielle.json`)
   - JSON file with properly formatted input for the orchestrator
   - Can be used for manual testing or reference

4. **Documentation** (`TEST_SETUP.md`)
   - Instructions for running the test
   - Expected output format
   - Troubleshooting guide

## Test Scenario Details

**Request**: "Provide me options for a 45-minute meeting with Sue and Danielle between December 1 and December 12."

**Participants**:
- cdorsey@concord.org (Chad - the requester)
- sbrau@concord.org (Sue)
- dkehoe@concord.org (Danielle)

**Constraints**:
- Work hours: Monday-Friday 09:00-17:30 ET
- Minimum gap: 15 minutes between meetings
- Duration: 45 minutes (3 slots of 15 minutes each)

## Key Calendar Constraints in the Data

### Sue's Calendar
- **VACATION Dec 5-9**: Full-day vacation blocks (should exclude these days)
- Multiple accounting/budget meetings
- Several shared meetings with Chad and Danielle

### Chad's Calendar  
- Many "Hold" blocks (flexible, could be moved if needed)
- Several recurring meetings (weekly reviews, grants team meetings)
- One protected meeting: "Concord Tech Capabilities Development Discussion" (Dec 4, Dec 11)

### Danielle's Calendar
- Various individual commitments (piano, athletics, appointments)
- Several shared meetings with Chad and Sue
- All-hands meeting on Dec 11

### Shared Meetings
These meetings involve all three participants, so those times are definitely blocked:
- Grants Team Meeting (Dec 4, Dec 11) - 11:00-12:00 ET
- Core Support (Dec 3) - 15:00-15:45 ET
- Concord Finance / AAFCPA Meeting (Dec 12) - 12:00-12:50 ET
- Concord Audit Drafts (Dec 8) - 16:00-16:50 ET
- Development Weekly Check In (Dec 8) - 11:00-12:00 ET
- 2025 End of Year Potluck (Dec 11) - 12:15-13:15 ET

## What to Check When Running Tests

### 1. Correct Slot Detection
- Does the orchestrator find slots where all three participants are free?
- Are the suggested times actually free (not conflicting with any events)?

### 2. Constraint Enforcement
- ✅ Work hours only (09:00-17:30 ET, Mon-Fri)
- ✅ Time window respected (Dec 1-12)
- ✅ Duration exactly 45 minutes
- ✅ Minimum gap of 15 minutes after existing meetings

### 3. Sue's Vacation
- **Critical**: No slots should be suggested during Dec 5-9 (Sue's vacation)

### 4. Protected Events
- "Concord Tech Capabilities Development Discussion" should NOT be moved (it's protected)

### 5. Performance
- Should complete in < 5 seconds for this dataset
- Check `debug.solve_time_ms` in output

### 6. Explanation Quality
- Explanation should be clear and mention which free slot was found
- If no solution, should explain why (e.g., "Sue is on vacation during the requested period")

## Expected Behavior

### If Free Slots Exist
- Status: `ok`
- At least one proposal with valid start/end times
- `moved_events` should be empty (free slot)
- Explanation should describe the slot

### If No Free Slots
- Status: `unsat`
- Empty proposals array
- Relaxations should suggest ways to find a slot
- Explanation should describe why no slot exists

### Potential Issues to Watch For

1. **Work Hours Too Restrictive**: If work hours are enforced strictly, Sue's vacation + work hours might leave very few slots. Consider if off-hours should be allowed.

2. **Min Gap Too Large**: 15-minute gap might eliminate slots that are otherwise free.

3. **Timezone Handling**: All times should be in ET (America/New_York) or converted correctly to UTC.

4. **DSPy Extraction**: The utterance might not be correctly parsed. Check if participants are identified as email addresses vs. names "Sue" and "Danielle".

## Next Steps After Running

1. **Review Output**: Check `test_output_sue_danielle.json` for detailed results
2. **Validate Slots**: Manually verify proposed slots don't conflict with calendar events
3. **Performance Tuning**: If slow, check debug info and optimize horizon reduction
4. **Edge Cases**: Test with more constrained scenarios (e.g., very busy calendars)
5. **DSPy Accuracy**: Verify that "Sue" and "Danielle" are correctly mapped to email addresses

## Important Note: Participant Name Mapping

The utterance uses names "Sue" and "Danielle", but the orchestrator needs email addresses (participant IDs). The DSPy extraction should use the `context_json.participants` list to map:
- "Sue" → sbrau@concord.org
- "Danielle" → dkehoe@concord.org

**If DSPy fails to map correctly**, you may need to:
1. Enhance the utterance to include email addresses: "Provide me options for a 45-minute meeting with sbrau@concord.org and dkehoe@concord.org..."
2. Or enhance the context_json to include a name-to-email mapping
3. Or improve the DSPy prompt to explicitly use the participants list from context

The fallback parser is basic and might not handle name-to-email mapping well, so DSPy extraction should be working.

## Questions to Answer

1. Does the orchestrator correctly identify "Sue" as sbrau@concord.org and "Danielle" as dkehoe@concord.org?
2. How many free slots exist in this 12-day period?
3. What's the performance (solve_time_ms)?
4. If no solution found, what are the blocking constraints?
5. Are the proposed slots optimal (considering focus blocks, disruption minimization)?

