# Test Setup for Scheduling Orchestrator

This directory contains test files for validating the scheduling orchestrator with real calendar data.

## Test Scenario

**Goal**: Find a 45-minute meeting slot for:
- Chad (cdorsey@concord.org)
- Sue (sbrau@concord.org)  
- Danielle (dkehoe@concord.org)

**Timeframe**: December 1-12, 2025

**Duration**: 45 minutes

## Files

### Input Files

1. **`example_event_data.md`** - Raw calendar event data exported from the calendar system
   - Contains events for all three participants
   - Format: JSON arrays with event details including start/end times, locked/protected/flexible flags

2. **`test_input_sue_danielle.json`** - Formatted input for orchestrator tool
   - Contains utterance, events_by_participant, and context_json
   - Can be used for manual testing or as a reference format

### Test Scripts

1. **`test_orchestrator_sue_danielle.py`** - Python test script
   - Loads events from `example_event_data.md`
   - Calls `orchestrate_scheduling()` with proper parameters
   - Prints results and saves output to JSON file
   - Exit code: 0 if solution found, 1 if unsat/bad_input

### Output Files (Generated)

1. **`test_output_sue_danielle.json`** - Orchestrator response
   - Contains status, proposals, explanation, debug info
   - Generated when test script runs

## Running the Test

### Prerequisites

1. Ensure the orchestrator dependencies are installed:
   ```bash
   cd letta
   pip install -r requirements.txt
   ```

2. Ensure DSPy and other dependencies are available (see `letta/requirements.txt`)

### Run the Test

```bash
cd docs/delivery/21
python test_orchestrator_sue_danielle.py
```

Or make it executable and run directly:
```bash
chmod +x test_orchestrator_sue_danielle.py
./test_orchestrator_sue_danielle.py
```

### Expected Output

The script will:
1. Load events from `example_event_data.md`
2. Print summary of loaded events per participant
3. Call the orchestrator
4. Display results:
   - Status (ok/unsat/bad_input)
   - Proposals (if found)
   - Explanation
   - Debug information
5. Save full results to `test_output_sue_danielle.json`

### Example Successful Output

```
Status: ok

Found 1 proposal(s):

Proposal 1:
  Title: Meeting with Sue and Danielle
  Start: 2025-12-03T14:00:00Z
  End: 2025-12-03T14:45:00Z
  Participants: cdorsey@concord.org, sbrau@concord.org, dkehoe@concord.org
  Moved Events: None (free slot)

Explanation:
Found a free 45-minute slot on December 3 at 2:00 PM ET...
```

## Key Test Validation Points

When running this test, verify:

1. **Free Slot Detection**: Does the orchestrator correctly identify time slots where all three participants are free?

2. **Work Hours Enforcement**: Are slots only suggested during work hours (M-F 09:00-17:30 ET)?

3. **Time Window**: Are slots only within the requested timeframe (Dec 1-12)?

4. **Duration**: Is the meeting exactly 45 minutes?

5. **Min Gap**: Is there at least a 15-minute gap after existing meetings?

6. **Performance**: Does the orchestrator complete in a reasonable time (< 5 seconds)?

7. **Protected Events**: Are protected events (like "Concord Tech Capabilities Development Discussion") not moved?

## Known Calendar Constraints

From the event data, some constraints to be aware of:

- **Sue has VACATION Dec 5-9**: Should not suggest slots during this time
- **Chad has many "Hold" blocks**: These are flexible and could theoretically be moved if needed
- **Several shared meetings**: 
  - Grants Team Meeting (Dec 4, Dec 11) - 3 participants
  - Core Support (Dec 3) - 3 participants  
  - Concord Finance / AAFCPA Meeting (Dec 12) - 3 participants

## Troubleshooting

### Import Errors

If you get import errors, ensure you're running from the correct directory or that the Python path includes the `letta` directory:

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/.."
```

### No Solutions Found

If status is `unsat`, check:
1. Are there any free slots in the time window?
2. Are work hours too restrictive?
3. Is the min_gap too large?
4. Are there too many locked/protected events blocking all slots?

### Performance Issues

If the orchestrator is slow:
1. Check debug info for solve_time_ms
2. Verify horizon reducer is working (should reduce large horizons)
3. Check if too many events are being processed

## Next Steps

After running the test:
1. Review `test_output_sue_danielle.json` for detailed results
2. Manually verify proposed slots make sense given the calendar
3. Test edge cases (e.g., no free slots, very constrained calendars)
4. Optimize based on performance metrics in debug info

