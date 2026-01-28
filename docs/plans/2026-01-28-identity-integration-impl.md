# Identity Service Integration for Participant Attribution

**Goal:** Use Letta identity service to display colloquial names (first names) instead of email prefixes in scheduling conflict summaries.

**Example transformation:**
- Before: "dkehoe's 2:00-3:00 *Hold* event"
- After: "Dan's 2:00-3:00 *Hold* event"

---

## Tasks

### Task 1: Create Identity Lookup Helper
**File:** `letta/scheduling_orchestrator/identity_lookup.py` (new)

Create a simple function to fetch participant names from Letta identity API.

### Task 2: Update format_refined_user_display Signature
**File:** `letta/scheduling_orchestrator/formatting.py`

Add `participant_names: Optional[Dict[str, str]] = None` parameter.

### Task 3: Create Display Name Helper
**File:** `letta/scheduling_orchestrator/formatting.py`

Add `_get_owner_display_name()` helper that:
- Returns "your" if owner == user_id
- Looks up colloquial name from participant_names dict
- Falls back to email prefix

### Task 4: Update All Owner Name Lookups
**File:** `letta/scheduling_orchestrator/formatting.py`

Replace all 4 instances of `owner.split("@")[0]` with the new helper:
- Line 587 (override section - other participants)
- Line 611 (override descriptions fallback)
- Line 698 (move proposals)
- Line 1055 (transparent event notes)

### Task 5: Integrate in Orchestrator
**File:** `letta/scheduling_orchestrator/orchestrate_scheduling.py`

Call identity lookup early, pass names to format_refined_user_display().

### Task 6: Test
Verify the integration works end-to-end.

---

## Design Decisions

- **Name preference:** colloquial_name (first name like "Dan")
- **Fallback:** email prefix if identity not found
- **Caching:** None in orchestrator (identity service caches internally)
- **API:** Direct HTTP call to `http://letta:8283/v1/identities/`
