# Participant Extraction Redesign

## Overview

The participant extraction logic has been redesigned to prioritize title/date identification and use a conservative, context-aware approach for participant name extraction. This prevents incorrect extraction of common words as participant names.

## Priority Order

The orchestrator now follows this priority order for determining which calendars to search:

1. **Explicit `participant_ids` parameter** - Highest priority, takes precedence over all other methods
2. **Participants from `context_json.participants`** - Agent-supplied names and IDs (RECOMMENDED)
   - The orchestrator matches utterance text against participant names in `context_json`
   - This is the preferred method as it avoids incorrect extraction from natural language
3. **Conservative utterance extraction** - Only used if title/date aren't sufficient
   - Uses a dual-stage process:
     - Stage 1: Find capitalized words (potential names)
     - Stage 2: Check context around those words for signifiers:
       - "with [Name]" (e.g., "meeting with Kate")
       - "[Name] and I" (e.g., "Kate and I")
       - "[Name]'s" (possessive forms, e.g., "Kate's meeting")
       - Patterns like "Kate / Chad", "Kate & Chad", "Kate and Chad"
   - Only extracts names if contextual signifiers are found (increases confidence)
4. **Fallback to `user_id`** - Used only if no other participants can be determined

## Key Changes

### 1. Title/Date Prioritization

The orchestrator now prioritizes identifying events by **title and date** (extracted by DSPy) rather than participant names. Participant extraction is only used when:
- Title/date aren't sufficient for event identification
- Or when explicitly needed for calendar searches

### 2. Context JSON Integration

The orchestrator now actively uses `context_json.participants` to match utterance text against agent-supplied participant names. This is the **recommended approach** for participant identification.

**Example `context_json` structure:**
```json
{
  "timeframe": {"from": "2025-12-08", "to": "2025-12-14", "tz": "America/New_York"},
  "participants": [
    {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "name": "Chad Dorsey"},
    {"id": "kmiller@concord.org", "email": "kmiller@concord.org", "name": "Kate Miller"},
    {"id": "jraiff@concord.org", "email": "jraiff@concord.org", "name": "Judi Raiff"}
  ]
}
```

When the utterance contains "Find me a new time for the check-in with Judi", the orchestrator will:
1. Match "Judi" against `context_json.participants` names
2. Find "Judi Raiff" → use `jraiff@concord.org` for calendar search

### 3. Conservative Utterance Extraction

The new extraction logic:
- **Only** looks at capitalized words (potential proper nouns)
- **Requires** contextual signifiers to confirm a word is a participant name
- Skips common words (sentence starters, days, meeting terms, etc.)
- Prevents false positives like "What", "We", "Timeslot", "Options" being treated as names

### 4. Dual-Stage Process

**Stage 1: Find Capitalized Words**
- Extracts capitalized words from utterance (e.g., "Kate", "Chad", "Grants")
- Filters out common capitalized words (sentence starters, days, meeting terms)

**Stage 2: Check Context for Signifiers**
- For each candidate name, checks surrounding context for signifiers:
  - "with [Name]" pattern
  - "[Name] and I" pattern
  - "[Name]'s" possessive pattern
  - Participant name patterns ("Kate / Chad", "Kate & Chad", "Kate and Chad")
- Only confirms a name if a signifier is found

## Benefits

1. **Reduced False Positives**: Common words like "What", "We", "Timeslot", "Options" are no longer extracted as participant names
2. **Better Accuracy**: Context-aware extraction increases confidence in identified names
3. **Agent Control**: Agents can supply participant names via `context_json`, giving them full control over participant identification
4. **Title/Date Priority**: Prioritizes the most reliable identifiers (title and date) over participant names

## Migration Guide

### For Agents

**RECOMMENDED**: Include participant names and IDs in `context_json.participants`:

```json
{
  "timeframe": {"from": "2025-12-08", "to": "2025-12-14", "tz": "America/New_York"},
  "participants": [
    {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "name": "Chad Dorsey"},
    {"id": "kmiller@concord.org", "email": "kmiller@concord.org", "name": "Kate Miller"}
  ]
}
```

This ensures the orchestrator can correctly identify participants from natural language without relying on utterance extraction.

### For Developers

The new `extract_participants_for_event_search()` function encapsulates all participant extraction logic. It:
- Takes utterance, scheduling_problem, context_json, participant_ids, and user_id as inputs
- Returns a list of participant email addresses to search
- Follows the priority order described above

## Example Workflows

### Example 1: Using context_json.participants (RECOMMENDED)

**Input:**
```json
{
  "utterance": "Find me a new time for the check-in with Judi on Dec. 10th",
  "user_id": "cdorsey@concord.org",
  "context_json": "{\"timeframe\": {...}, \"participants\": [{\"id\": \"jraiff@concord.org\", \"email\": \"jraiff@concord.org\", \"name\": \"Judi Raiff\"}]}"
}
```

**Process:**
1. DSPy extracts: title="check-in", date="Dec. 10th", participant_names=["Judi Raiff"]
2. Orchestrator matches "Judi" against `context_json.participants`
3. Finds "Judi Raiff" → uses `jraiff@concord.org` for calendar search
4. Searches `cdorsey@concord.org` and `jraiff@concord.org` calendars
5. Identifies event by title + date + participants

### Example 2: Conservative Utterance Extraction

**Input:**
```json
{
  "utterance": "What other timeslot options are there for the Grants Team Meeting next Thursday?",
  "user_id": "cdorsey@concord.org",
  "context_json": "{\"timeframe\": {...}}"
}
```

**Process:**
1. DSPy extracts: title="Grants Team Meeting", date="Thursday"
2. No `participant_ids` provided, no `context_json.participants` provided
3. Conservative extraction looks for capitalized words: "What", "Grants", "Team", "Meeting", "Thursday"
4. Filters out common words: "What", "Grants", "Team", "Meeting", "Thursday" (all skipped)
5. No confirmed names found (no contextual signifiers)
6. Falls back to `user_id`: searches `cdorsey@concord.org` calendar
7. Identifies event by title + date

**Result**: No false positives like "What", "Timeslot", "Options" being extracted as participant names.

## Testing

The new approach has been tested with:
- Utterances containing common words that were previously incorrectly extracted
- Utterances with participant names in various formats
- Utterances with and without `context_json.participants`
- Edge cases (no participants, generic meeting titles, etc.)

## Future Improvements

Potential enhancements:
1. Machine learning model for participant name extraction (if needed)
2. Integration with organizational directory for name resolution
3. Support for nicknames and name variations
4. Confidence scoring for extracted names

