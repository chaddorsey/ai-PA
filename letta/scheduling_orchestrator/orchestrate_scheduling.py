"""
Scheduling Orchestration Tool for Letta

This tool takes natural language scheduling requests plus calendar events and returns
ready-to-schedule meeting proposals that satisfy hard constraints and optimize soft preferences.

The tool uses:
- DSPy for robust natural language → structured JSON extraction
- clingo ASP for constraint-based optimization on a 15-minute grid
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import sys

# Type alias for schema generator compatibility
if False:  # Never executes, but satisfies type checkers
    DictType = Dict[str, Any]
    ObjectType = object

# Lazy imports to avoid dependency issues during Letta schema generation
# These will be imported when the function is actually called


def _is_internal_participant(participant_id: str, internal_domains: Optional[List[str]] = None) -> bool:
    """
    Determine if a participant is internal (e.g., @concord.org) or external.
    
    Args:
        participant_id: Email address of the participant
        internal_domains: List of internal domain suffixes (default: ["@concord.org"])
    
    Returns:
        True if participant is internal, False if external
    """
    if internal_domains is None:
        internal_domains = ["@concord.org"]
    
    if not participant_id or "@" not in participant_id:
        return False
    
    participant_lower = participant_id.lower()
    return any(participant_lower.endswith(domain.lower()) for domain in internal_domains)


def _separate_internal_external_participants(participants: List[str], internal_domains: Optional[List[str]] = None) -> tuple[List[str], List[str]]:
    """
    Separate participants into internal and external lists.

    Args:
        participants: List of participant email addresses
        internal_domains: List of internal domain suffixes (default: ["@concord.org"])

    Returns:
        Tuple of (internal_participants, external_participants)
    """
    internal = []
    external = []

    for p in participants:
        if _is_internal_participant(p, internal_domains):
            internal.append(p)
        else:
            external.append(p)

    return internal, external


def _calculate_work_slots_for_horizon(
    work_hours: List[tuple],
    participant_tz: Any,
    slot_indexer: Any,
    horizon_start: datetime,
    horizon_end: datetime
) -> set:
    """
    Calculate work hours slots for a participant over a given horizon.

    This helper function consolidates the repeated work hours slot calculation
    logic that was duplicated 3+ times in orchestrate_scheduling (Issue #16 fix).

    Args:
        work_hours: Parsed work hours list of tuples (day_of_week, start_hhmm, end_hhmm)
                   e.g., [(0, 900, 1700), (1, 900, 1700), ...]  # Mon-Fri 9am-5pm
        participant_tz: pytz timezone object for the participant
        slot_indexer: SlotIndexer instance for converting datetimes to slots
        horizon_start: Start of the scheduling horizon (UTC datetime)
        horizon_end: End of the scheduling horizon (UTC datetime)

    Returns:
        Set of slot indices representing work hours within the horizon
    """
    import pytz
    from datetime import timedelta

    work_slots = set()
    current_date = horizon_start.replace(hour=0, minute=0, second=0, microsecond=0)

    while current_date < horizon_end:
        current_date_local = current_date.astimezone(participant_tz)
        day_of_week = current_date_local.weekday()

        for day, start_hm, end_hm in work_hours:
            if day_of_week == day:
                start_hour = start_hm // 100
                start_min = start_hm % 100
                end_hour = end_hm // 100
                end_min = end_hm % 100

                work_start = current_date_local.replace(
                    hour=start_hour, minute=start_min, second=0, microsecond=0
                )
                work_end = current_date_local.replace(
                    hour=end_hour, minute=end_min, second=0, microsecond=0
                )

                # Convert to UTC
                work_start_utc = work_start.astimezone(pytz.UTC)
                work_end_utc = work_end.astimezone(pytz.UTC)

                # Get slots in the indexer
                work_period_slots = slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                work_slots.update(work_period_slots)

        current_date += timedelta(days=1)

    return work_slots


def orchestrate_scheduling(
    utterance: str,
        participant_ids: Optional[List[str]] = None,  # NEW: List of participant email addresses for automatic event fetching (optional for rescheduling when event_id is provided)
        user_id: Optional[str] = None,  # NEW: User's own email address (REQUIRED for rescheduling - assumed to be an attendee)
        context_json: Optional[str] = None,  # JSON string: Optional[Dict[str, Any]] - optional scheduling context and preferences (REQUIRED when using participant_ids or for rescheduling)
        events_by_participant: Optional[str] = None,  # JSON string: Dict[str, List[Dict[str, Any]]] - LEGACY: Pre-fetched events (use participant_ids instead)
        event_id: Optional[str] = None,  # NEW: Explicit event ID for rescheduling (when provided by agent)
        event_participant_id: Optional[str] = None  # NEW: ID of one of the event participants (optional when event_id is provided - defaults to user_id for rescheduling)
) -> dict:
    """
    Orchestrate scheduling by finding optimal meeting times that satisfy constraints and preferences.
    
    This tool supports two primary use cases:
    
    1. **New Meeting Scheduling**: Find optimal time slots for a new meeting with specified participants.
    
    2. **Rescheduling Existing Meetings**: Find alternative time options for an existing meeting, either by:
       - Providing explicit event_id and event_owner_id (agent-generated requests)
       - Using natural language to identify the meeting (e.g., "Find me a new time for the check-in with Judi on Dec. 10th")
    
    This tool can operate in two modes for event retrieval:
    
    1. **RECOMMENDED - Direct Event Retrieval**: Provide participant_ids and the tool will automatically
       fetch calendar events via MCP. This is more reliable and avoids message size limits.
       No need to call Get_Events or Core_Event_Data first.
    
    2. **LEGACY - Pre-fetched Events**: Provide events_by_participant if you've already fetched events.
       Use this only for testing or custom calendar sources.
    
    This function includes comprehensive error handling and logging. Errors are captured
    with full tracebacks and returned in the response for debugging.
    
    The tool uses Answer Set Programming (ASP) to find optimal solutions that:
    - Satisfy hard constraints (no double bookings, work hours, minimum gaps)
    - Optimize soft preferences (minimize disruption, maximize focus blocks, respect timing preferences)
    
    Args:
        utterance: Natural language scheduling request (e.g., "Find 45 minutes with Alex & Priya Tue–Thu mornings. Minimize disruption.")
                   For rescheduling, can be a simple request like "Find new time options" when event_id is provided,
                   or can identify the meeting: "Find me a new time for the check-in with Judi on Dec. 10th"
        
        participant_ids: (Optional for rescheduling) List of participant email addresses. The tool will automatically fetch
                        their calendar events via MCP Core_Event_Data. For rescheduling with event_id, if not provided,
                        participants will be derived from the event after it's fetched. For new meeting scheduling,
                        this is required. Example: ["cdorsey@concord.org", "alex@example.com"]
                        If provided, context_json must include timeframe.
        
        user_id: (REQUIRED for rescheduling) User's own email address. For rescheduling requests, the tool will
                 use this as a fallback to search the requester's calendar if participants cannot be determined
                 from the utterance (e.g., "When else this week can we hold Friday's Grants Team Meeting?").
                 However, if participants are explicitly provided via participant_ids or can be inferred from the
                 utterance (e.g., "Can Leslie and Kirk's check-in meeting..."), those will be used instead.
                 If not provided for rescheduling, the tool will return an error.
        
        context_json: (REQUIRED when using participant_ids) JSON string containing:
                      - timeframe: {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "tz": "America/New_York"} (REQUIRED for participant_ids mode)
                      - participants: [{"id": "exec", "email": "me@acme.com", "name": "John Doe", "work_hours": "M-F 09:00-17:30"}, ...]
                         **RECOMMENDED**: Include participant names and IDs in this list. The orchestrator will match utterance
                         text against these names to identify participants for event searches. This is the preferred method
                         for participant identification, as it avoids incorrect extraction from natural language.
                      - policy: {
                          "hard": {"min_gap_min": 10},
                          "soft": {
                            "maximize_focus_blocks": {"block_min": 90, "weight": 10},
                            "minimize_moves_of_existing": {"weight_per_min_shift": 2, "tier": "protected"},
                            "respect_others_prefs_weight": 3
                          },
                          "lexicographic_levels": ["feasibility", "protected_events", "move_costs", "focus_blocks"]
                        }
                      - slot_size_minutes: 15 (fixed for now)
        
        events_by_participant: (LEGACY) JSON string representing a dictionary mapping participant IDs to lists of calendar events.
                              Each event should be a dict with keys: id, title, start, end, locked, protected, flexible.
                              Only use this if you've already fetched events. Otherwise, use participant_ids.
                              Example JSON: '{"exec": [{"id": "evt1", "title": "Meeting", "start": "2025-11-25T10:00:00Z", "end": "2025-11-25T11:00:00Z", "locked": false}], "alex": []}'
        
        event_id: (Optional) Explicit event ID for rescheduling. When provided, the tool will fetch the specific event
                  via MCP Core_Event_Data and extract its details (participants, duration, title, location) to use
                  as the base for finding alternative time slots. Use this when the agent has already identified the
                  event to reschedule. If provided, event_participant_id must also be provided.
                  The tool searches for the event in the calendar of the specified participant, looking from today
                  forward up to 14 days. Example: "evt_abc123xyz"
        
        event_participant_id: (Optional) Email address or calendar ID of one of the event participants. This is used
                              to fetch the event via MCP Core_Event_Data. The event will be searched in this
                              participant's calendar from today forward up to 14 days. For rescheduling, if not provided
                              when event_id is provided, defaults to user_id (assuming requester is an attendee).
                              Can be any participant of the event, not necessarily the owner.
                              Example: "cdorsey@concord.org"
    
    Returns:
        Dictionary with keys:
        - status: "ok" | "unsat" | "bad_input"
        - proposals: List of Proposal objects (backward compatibility)
        - explanation: Human-readable explanation (backward compatibility)
        - relaxations: List of Relaxation suggestions (if status is "unsat")
        - debug: DebugInfo with timing and statistics
        - error_message: Error message (if status is "bad_input")
        - user_display: Optional[UserDisplay] - Pre-formatted content for end users
        - agent_data: Optional[AgentData] - Structured metadata for agent reasoning
        - mapping: Optional[CrossReferenceMapping] - Links between user_display and agent_data
    
    Examples:
        New meeting scheduling:
        >>> result = orchestrate_scheduling(
        ...     utterance="Find 45 minutes with Alex & Priya Tue–Thu mornings",
        ...     participant_ids=["cdorsey@concord.org", "alex@example.com", "priya@example.com"],
        ...     context_json='{"timeframe": {"from": "2025-11-24", "to": "2025-11-28", "tz": "America/New_York"}}'
        ... )
        
        Rescheduling with explicit event ID (participants derived from event):
        >>> result = orchestrate_scheduling(
        ...     utterance="Find new time options",
        ...     event_id="evt_abc123xyz",
        ...     user_id="cdorsey@concord.org",  # Required - assumed to be attendee
        ...     context_json='{"timeframe": {"from": "2025-12-01", "to": "2025-12-15", "tz": "America/New_York"}}'
        ...     # participant_ids not needed - will be derived from event
        ...     # event_participant_id not needed - defaults to user_id
        ... )
        
        Rescheduling with natural language (searches requester's calendar first):
        >>> result = orchestrate_scheduling(
        ...     utterance="Find me a new time for the check-in with Judi on Dec. 10th",
        ...     user_id="cdorsey@concord.org",  # Required - searches this calendar first
        ...     context_json='{"timeframe": {"from": "2025-12-01", "to": "2025-12-15", "tz": "America/New_York"}}'
        ...     # participant_ids optional - will search user_id calendar first, then expand if needed
        ... )
    """
    # Import traceback, json, time, datetime, and pytz (ensure they're available)
    import traceback
    import json
    import time
    from datetime import datetime
    import pytz
    
    # Helper functions will be defined inline where used to avoid schema generator issues
    
    # Wrap entire function in try-except to catch any unexpected errors
    try:
        # Log function entry for debugging (stderr goes to Docker logs)
        import sys
        try:
            print(f"[orchestrate_scheduling] Function called", file=sys.stderr, flush=True)
        except:
            pass  # Don't fail if logging fails
        
        # Lazy imports - only import when function is called, not during schema generation
        # Try relative imports first (when run as package), then absolute imports (when run standalone)
        try:
            # Try relative imports (when run as package)
            from .schemas import (
                ResponseEnvelope,
                Proposal,
                Event,
                FreeBlockStats,
                SchedulingProblem,
                Relaxation,
                DebugInfo,
                UserDisplay,
                AgentData,
                CrossReferenceMapping,
                FormattedProposal,
                CategoryInfo,
                OptimizationSummary,
                ConstraintsApplied,
                MovedEvent,
                ObjectiveScores,
            )
            from .dspy_extraction import extract_with_fallback
            from .normalizer import normalize_events
            from .fact_generator import generate_asp_program
            from .clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
            from .unsat_analyzer import explain_unsat
            from .formatting import format_proposal_for_display, generate_proposal_id
            from .agent_data_builder import (
                build_event_registry,
                generate_ranking_rationale,
                build_optimization_summary,
                build_constraints_applied
            )
        except (ImportError, ValueError):
            # Fallback to absolute imports (when run standalone or in Letta)
            import sys
            import os
            
            # Find the letta directory and add it to path
            # __file__ might be the .pyc file, so get the real path
            current_file = os.path.abspath(__file__)
            if current_file.endswith('.pyc'):
                current_file = current_file[:-1]  # Remove .pyc to get .py
            
            # Get letta directory (parent of scheduling_orchestrator)
            letta_dir = os.path.dirname(os.path.dirname(current_file))
            if letta_dir not in sys.path:
                sys.path.insert(0, letta_dir)
            
            # Also try adding the scheduling_orchestrator directory itself
            orchestrator_dir = os.path.dirname(current_file)
            if orchestrator_dir not in sys.path:
                sys.path.insert(0, orchestrator_dir)
            
            # Now try absolute imports
            try:
                from scheduling_orchestrator.schemas import (
                    ResponseEnvelope,
                    Proposal,
                    Event,
                    SchedulingProblem,
                    Relaxation,
                    DebugInfo,
                    MovedEvent,
                    ObjectiveScores,
                    UserDisplay,
                    AgentData,
                    CrossReferenceMapping,
                    FormattedProposal,
                    CategoryInfo,
                    OptimizationSummary,
                    ConstraintsApplied,
                )
                from scheduling_orchestrator.dspy_extraction import extract_with_fallback
                from scheduling_orchestrator.normalizer import normalize_events
                from scheduling_orchestrator.fact_generator import generate_asp_program
                from scheduling_orchestrator.clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                from scheduling_orchestrator.unsat_analyzer import explain_unsat
                from scheduling_orchestrator.formatting import format_proposal_for_display, generate_proposal_id
                from scheduling_orchestrator.agent_data_builder import (
                    build_event_registry,
                    generate_ranking_rationale,
                    build_optimization_summary,
                    build_constraints_applied
                )
            except ImportError:
                # Last resort: try direct imports from orchestrator_dir
                from schemas import (
                    ResponseEnvelope,
                    Proposal,
                    Event,
                    SchedulingProblem,
                    Relaxation,
                    DebugInfo,
                    MovedEvent,
                    ObjectiveScores,
                    UserDisplay,
                    AgentData,
                    CrossReferenceMapping,
                    FormattedProposal,
                    CategoryInfo,
                    OptimizationSummary,
                    ConstraintsApplied,
                )
                from dspy_extraction import extract_with_fallback
                from normalizer import normalize_events
                from fact_generator import generate_asp_program
                from clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                from unsat_analyzer import explain_unsat
                from formatting import format_proposal_for_display, generate_proposal_id
                from agent_data_builder import (
                    build_event_registry,
                    generate_ranking_rationale,
                    build_optimization_summary,
                    build_constraints_applied
                )
        except ImportError as e:
            # If dependencies are missing, return a helpful error with traceback
            error_traceback = traceback.format_exc()
            return {
                "status": "bad_input",
                "explanation": f"Tool dependencies not available: {str(e)}. Please ensure clingo and dspy-ai are installed.",
                "proposals": [],
                "error_message": f"Missing dependencies: {str(e)}",
                "error_traceback": error_traceback,
                "debug": {
                    "error_type": "ImportError",
                    "missing_module": str(e)
                }
            }
        
        # Parse JSON string inputs
        try:
            if isinstance(events_by_participant, str):
                # Handle empty string - treat as None (no events provided)
                if events_by_participant.strip() == "":
                    events_by_participant = None
                else:
                    events_by_participant = json.loads(events_by_participant)
            if context_json is not None and isinstance(context_json, str):
                # Handle empty string - treat as None
                if context_json.strip() == "":
                    context_json = None
                else:
                    context_json = json.loads(context_json)
        except json.JSONDecodeError as e:
            return {
                "status": "bad_input",
                "explanation": f"Invalid JSON in input parameters: {str(e)}",
                "proposals": [],
                "error_message": f"JSON decode error: {str(e)}",
                "debug": {}
            }
        
        # Early extraction to check for rescheduling intent
        # We need to know if this is rescheduling to determine parameter requirements
        scheduling_problem_preview = None
        try:
            scheduling_problem_preview = extract_with_fallback(utterance, context_json)
        except:
            pass  # Will extract again later, this is just for early validation
        
        # Check if this is a rescheduling request
        # CRITICAL: Rescheduling requires reference to an EXISTING meeting
        # Primary indicators:
        # 1. Explicit event_id provided
        # 2. Event identifiers (titles, specific dates/times for existing event) present
        # 3. Explicit rescheduling keywords (reschedule, move meeting, new time for, etc.)
        
        # First, check for phrases that explicitly indicate a NEW meeting (not rescheduling)
        utterance_lower = utterance.lower()
        new_meeting_phrases = [
            "schedule a new",
            "create a new",
            "set up a new",
            "book a new",
            "arrange a new",
            "plan a new",
            "organize a new",
            "schedule new",
            "create new",
            "set up new",
            "book new",
            "arrange new",
            "plan new",
            "organize new"
        ]
        is_new_meeting_by_phrase = any(phrase in utterance_lower for phrase in new_meeting_phrases)
        
        # Check for event identifiers in the preview extraction
        has_event_identifiers = False
        if scheduling_problem_preview and scheduling_problem_preview.event_identifiers:
            event_identifiers = scheduling_problem_preview.event_identifiers
            # Handle both dict and string formats
            if isinstance(event_identifiers, str):
                try:
                    import json
                    event_identifiers = json.loads(event_identifiers)
                except:
                    event_identifiers = {}
            
            if isinstance(event_identifiers, dict):
                # Check if there are any meaningful event identifiers
                titles = event_identifiers.get("titles", []) or []
                dates = event_identifiers.get("dates", []) or []
                times = event_identifiers.get("times", []) or []
                participant_names = event_identifiers.get("participant_names", []) or []
                
                # Has event identifiers if there are titles, specific dates, or times
                # (participant names alone don't indicate an existing meeting - they could be for a new meeting)
                has_event_identifiers = bool(titles or (dates and len(dates) > 0) or (times and len(times) > 0))
        
        # Check for explicit rescheduling keywords (only if NOT a new meeting phrase)
        has_rescheduling_keyword = False
        if not is_new_meeting_by_phrase:
            import re
            rescheduling_patterns = [
                r'\breschedule\b',
                r'\bmove\b.*\bmeeting\b',
                r'\bnew time\b.*\bfor\b',  # "new time for" indicates rescheduling
                r'\balternative time\b.*\bfor\b',  # "alternative time for" indicates rescheduling
                r'\bdifferent time\b.*\bfor\b',  # "different time for" indicates rescheduling
                r'\bfind.*new time\b.*\bfor\b',  # "find new time for" indicates rescheduling
                r'\bchange.*time\b.*\bfor\b',  # "change time for" indicates rescheduling
                r'\bfind.*alternative\b.*\bfor\b',  # "find alternative for" indicates rescheduling
                r'\bfind.*different\b.*\bfor\b',  # "find different for" indicates rescheduling
                r'\breschedule.*meeting\b',
                r'\bmove.*meeting\b',
                r'\bthe meeting\b',  # "the meeting" suggests an existing meeting
                r'\bthat meeting\b',  # "that meeting" suggests an existing meeting
                r'\bthis meeting\b'  # "this meeting" suggests an existing meeting
            ]
            has_rescheduling_keyword = any(re.search(pattern, utterance_lower) for pattern in rescheduling_patterns)
        
        # Determine if this is rescheduling
        # Rescheduling requires: event_id OR (event identifiers AND rescheduling keyword) OR explicit rescheduling keyword
        # If no event identifiers and no explicit rescheduling keywords → it's a NEW meeting
        is_rescheduling = False
        if event_id:
            # Explicit event_id always means rescheduling
            is_rescheduling = True
        elif is_new_meeting_by_phrase:
            # Explicit new meeting phrases override everything
            is_rescheduling = False
        elif has_event_identifiers and has_rescheduling_keyword:
            # Both event identifiers AND rescheduling keywords → rescheduling
            is_rescheduling = True
        elif has_rescheduling_keyword:
            # Explicit rescheduling keywords → rescheduling
            is_rescheduling = True
        elif has_event_identifiers:
            # Event identifiers alone might be rescheduling, but check DSPy's detection
            if scheduling_problem_preview and scheduling_problem_preview.is_rescheduling:
                is_rescheduling = True
            else:
                # Event identifiers but no rescheduling keywords and DSPy didn't detect it → likely new meeting
                is_rescheduling = False
        else:
            # No event identifiers, no rescheduling keywords → NEW meeting (default)
            is_rescheduling = False
        
        # Log the detection result
        try:
            if is_new_meeting_by_phrase:
                print(f"[orchestrate_scheduling] Detected NEW meeting request (not rescheduling) - phrases like 'schedule a new' found", file=sys.stderr, flush=True)
            elif is_rescheduling:
                reason = []
                if event_id:
                    reason.append("event_id provided")
                if has_event_identifiers:
                    reason.append("event identifiers found")
                if has_rescheduling_keyword:
                    reason.append("rescheduling keywords found")
                print(f"[orchestrate_scheduling] Detected rescheduling request - {', '.join(reason)}", file=sys.stderr, flush=True)
            else:
                print(f"[orchestrate_scheduling] Detected NEW meeting request (default) - no event identifiers or rescheduling keywords", file=sys.stderr, flush=True)
        except:
            pass
        
        # For rescheduling, require user_id (used as fallback if no other participants can be determined)
        if is_rescheduling and not user_id:
            return {
                "status": "bad_input",
                "explanation": "user_id is required for rescheduling requests. It will be used as a fallback to search the requester's calendar if participants cannot be determined from the utterance or event. Please provide the requester's email address.",
                "proposals": [],
                "error_message": "user_id is required for rescheduling",
                "debug": {}
            }
        
        # For rescheduling with event_id, default event_participant_id to user_id if not provided (as fallback)
        if event_id is not None and event_participant_id is None:
            if user_id:
                event_participant_id = user_id
                try:
                    print(f"[orchestrate_scheduling] Using user_id ({user_id}) as fallback event_participant_id for rescheduling", file=sys.stderr, flush=True)
                except:
                    pass
            else:
                return {
                    "status": "bad_input",
                    "explanation": "event_participant_id or user_id is required when event_id is provided. For rescheduling, provide user_id and it will be used as a fallback to fetch the event from the requester's calendar.",
                    "proposals": [],
                    "error_message": "event_participant_id or user_id required when event_id is provided",
                    "debug": {}
                }
        
        start_time = time.time()
        debug_info = DebugInfo()
        
        # Initialize variable for fetched event (used for rescheduling)
        fetched_event_by_id = None
        
        # Handle participant_ids - fetch events via MCP if provided
        if participant_ids:
            # Parse if it's a JSON string
            if isinstance(participant_ids, str):
                try:
                    participant_ids = json.loads(participant_ids)
                except json.JSONDecodeError:
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Invalid JSON in participant_ids: {participant_ids}",
                        proposals=[],
                        error_message="Invalid participant_ids JSON",
                        debug=debug_info
                    ).model_dump()
            
            # Ensure it's a list
            if not isinstance(participant_ids, list):
                return ResponseEnvelope(
                    status="bad_input",
                    explanation="participant_ids must be a list of email addresses",
                    proposals=[],
                    error_message="participant_ids must be a list",
                    debug=debug_info
                ).model_dump()
        
        # For rescheduling with event_id but no participant_ids, fetch event first to derive participants
        derived_participant_ids = None
        if is_rescheduling and event_id and not participant_ids:
            # We'll fetch the event first, extract participants, then fetch calendars
            # This will be handled after we initialize the MCP client
            derived_participant_ids = []  # Will be populated after event fetch
        
        # Determine which mode to use: participant_ids (automatic fetching) or events_by_participant (legacy)
        # For rescheduling, we may need to fetch event first to get participant_ids, or fetch user's calendar for natural language identification
        if participant_ids or (is_rescheduling and (event_id or user_id)):
            # Mode 1: Fetch events automatically via MCP
            if not context_json:
                # For natural language rescheduling (title-based, no event_id), default to 2 weeks forward
                if is_rescheduling and not event_id and user_id and scheduling_problem_preview:
                    event_identifiers_dict = scheduling_problem_preview.event_identifiers if hasattr(scheduling_problem_preview, 'event_identifiers') and scheduling_problem_preview.event_identifiers else {}
                    titles = event_identifiers_dict.get("titles", []) if isinstance(event_identifiers_dict, dict) else []
                    # If we have a title, default to 2 weeks forward for natural language rescheduling
                    if titles:
                        from datetime import timedelta
                        tz = pytz.timezone("America/New_York")  # Default timezone
                        now = datetime.now(tz)
                        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)  # Start of today
                        end_dt = now + timedelta(days=14)  # 14 days forward
                        context_json = {
                            "timeframe": {
                                "from": start_dt.strftime("%Y-%m-%d"),
                                "to": end_dt.strftime("%Y-%m-%d"),
                                "tz": "America/New_York"
                            }
                        }
                        try:
                            print(f"[orchestrate_scheduling] Defaulting to 2-week forward timeframe for natural language rescheduling: {context_json['timeframe']}", file=sys.stderr, flush=True)
                        except:
                            pass
                    else:
                        # No title, require context_json
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation="context_json with timeframe is required for rescheduling. Provide timeframe with 'from', 'to', and 'tz' fields to search for the meeting and find alternative times.",
                            proposals=[],
                            error_message="Missing context_json with timeframe",
                            debug=debug_info
                        ).model_dump()
                elif is_rescheduling:
                    # Rescheduling with event_id but no context_json - require it
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation="context_json with timeframe is required for rescheduling. Provide timeframe with 'from', 'to', and 'tz' fields to search for the meeting and find alternative times.",
                        proposals=[],
                        error_message="Missing context_json with timeframe",
                        debug=debug_info
                    ).model_dump()
                else:
                    # Not rescheduling, require context_json
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation="context_json with timeframe is required when using participant_ids. Provide timeframe with 'from', 'to', and 'tz' fields.",
                        proposals=[],
                        error_message="Missing context_json with timeframe",
                        debug=debug_info
                    ).model_dump()
            
            if "timeframe" not in context_json:
                if is_rescheduling:
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation="timeframe is required in context_json for rescheduling. Provide timeframe with 'from', 'to', and 'tz' fields to search for the meeting and find alternative times.",
                        proposals=[],
                        error_message="Missing timeframe in context_json",
                        debug=debug_info
                    ).model_dump()
                else:
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation="timeframe is required in context_json when using participant_ids. Provide timeframe with 'from', 'to', and 'tz' fields.",
                        proposals=[],
                        error_message="Missing timeframe in context_json",
                        debug=debug_info
                    ).model_dump()
            
            # Fetch events from MCP
            import os
            import asyncio
            try:
                # Try relative import first (when run as package)
                from .mcp_client import MCPCalendarClient, MCPError
            except (ImportError, ValueError):
                try:
                    # Try absolute import (when run standalone or in Letta)
                    from scheduling_orchestrator.mcp_client import MCPCalendarClient, MCPError
                except ImportError:
                    # Last resort: try direct import
                    from mcp_client import MCPCalendarClient, MCPError
            
            # Get MCP server URL from environment or use default
            mcp_url = os.getenv(
                "MCP_CALENDAR_SERVER_URL",
                "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
            )
            
            # Create MCP client
            mcp_client = MCPCalendarClient(
                base_url=mcp_url,
                timeout=int(os.getenv("MCP_CALENDAR_TIMEOUT", "30")),
                max_retries=int(os.getenv("MCP_CALENDAR_RETRY_ATTEMPTS", "3"))
            )
            
            # For rescheduling with event_id but no participant_ids, fetch event first to derive participants
            if is_rescheduling and event_id and event_participant_id and not participant_ids:
                try:
                    async def fetch_specific_event():
                        await mcp_client.initialize()
                        return await mcp_client.fetch_event_by_id(
                            calendar_id=event_participant_id,
                            event_id=event_id
                        )
                    
                    fetched_event_by_id = asyncio.run(fetch_specific_event())
                    
                    if fetched_event_by_id is None:
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=f"Event with ID '{event_id}' not found in calendar '{event_participant_id}'. The event may not exist, may be outside the search range (today to 14 days in the future), or you may not have access to it. Please provide participant_ids if you know them, or check that the event_id and event_participant_id are correct.",
                            proposals=[],
                            error_message=f"Event {event_id} not found in calendar {event_participant_id}",
                            debug=debug_info
                        ).model_dump()
                    
                    # Extract participants from the event
                    try:
                        from .event_extractor import extract_event_details_for_rescheduling
                    except (ImportError, ValueError):
                        try:
                            from scheduling_orchestrator.event_extractor import extract_event_details_for_rescheduling
                        except ImportError:
                            from event_extractor import extract_event_details_for_rescheduling
                    
                    # Use event_participant_id as the owner for extraction
                    extracted_details = extract_event_details_for_rescheduling(
                        event=fetched_event_by_id,
                        event_owner_id=event_participant_id
                    )
                    
                    # Derive participant_ids from extracted event details
                    participant_ids = extracted_details.get("participants", [])
                    
                    if not participant_ids:
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=f"Could not extract participants from event '{event_id}'. The event may be missing attendee information. Please provide participant_ids explicitly.",
                            proposals=[],
                            error_message="Could not extract participants from event",
                            debug=debug_info
                        ).model_dump()
                    
                    # Log successful derivation
                    try:
                        print(f"[orchestrate_scheduling] Derived participant_ids from event: {participant_ids}", file=sys.stderr, flush=True)
                    except:
                        pass
                        
                except MCPError as e:
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Error fetching event '{event_id}' from calendar '{event_participant_id}': {e.message}. The event may be inaccessible or there may be a connection issue.",
                        proposals=[],
                        error_message=f"MCP error fetching event: {e.message}",
                        debug=debug_info
                    ).model_dump()
                except Exception as e:
                    error_traceback = traceback.format_exc()
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Unexpected error fetching or processing event '{event_id}': {str(e)}",
                        proposals=[],
                        error_message=f"Error processing event by ID: {str(e)}",
                        error_traceback=error_traceback,
                        debug=debug_info
                    ).model_dump()
            
            # Fetch specific event by ID if provided (for rescheduling with participant_ids already known)
            elif event_id and event_participant_id:
                try:
                    async def fetch_specific_event():
                        await mcp_client.initialize()
                        return await mcp_client.fetch_event_by_id(
                            calendar_id=event_participant_id,
                            event_id=event_id
                        )
                    
                    fetched_event_by_id = asyncio.run(fetch_specific_event())
                    
                    if fetched_event_by_id is None:
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=f"Event with ID '{event_id}' not found in calendar '{event_participant_id}'. The event may not exist, may be outside the search range (today to 14 days in the future), or you may not have access to it.",
                            proposals=[],
                            error_message=f"Event {event_id} not found in calendar {event_participant_id}",
                            debug=debug_info
                        ).model_dump()
                    
                    # Log successful fetch
                    try:
                        print(f"[orchestrate_scheduling] Successfully fetched event {event_id} from calendar {event_participant_id}", file=sys.stderr, flush=True)
                    except:
                        pass
                        
                except MCPError as e:
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Error fetching event '{event_id}' from calendar '{event_participant_id}': {e.message}. The event may be inaccessible or there may be a connection issue.",
                        proposals=[],
                        error_message=f"MCP error fetching event: {e.message}",
                        debug=debug_info
                    ).model_dump()
                except Exception as e:
                    error_traceback = traceback.format_exc()
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Unexpected error fetching event '{event_id}': {str(e)}",
                        proposals=[],
                        error_message=f"Error fetching event by ID: {str(e)}",
                        error_traceback=error_traceback,
                        debug=debug_info
                    ).model_dump()
            
            # Fetch events asynchronously
            try:
                # Import the fetch_calendar_events function (defined below or inline)
                # For now, define it inline
                async def fetch_calendar_events(
                    participant_ids: List[str],
                    user_id: Optional[str],
                    timeframe: Dict[str, str],
                    mcp_client
                ) -> Dict[str, List[Dict[str, Any]]]:
                    """Fetch calendar events for all participants via MCP Core_Event_Data tool."""
                    import pytz
                    from datetime import datetime
                    
                    events_by_participant = {}
                    
                    # Convert date strings to format expected by Core_Event_Data
                    # ⚠️ IMPORTANT: Parameter names are REVERSED!
                    # "Before" = END date, "After" = START date
                    tz = pytz.timezone(timeframe.get("tz", "America/New_York"))
                    
                    # Parse start date (handles both date-only and ISO 8601 datetime formats)
                    try:
                        start_dt = datetime.fromisoformat(timeframe["from"].replace('Z', '+00:00'))
                        if start_dt.tzinfo:
                            start_dt = start_dt.replace(tzinfo=None)
                    except (ValueError, AttributeError):
                        start_dt = datetime.strptime(timeframe["from"], "%Y-%m-%d")
                    # If the input was a datetime, extract just the date part; otherwise use start of day
                    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    start_dt = tz.localize(start_dt)
                    after_date_iso = start_dt.strftime("%Y-%m-%dT00:00:00Z")
                    
                    # Parse end date (handles both date-only and ISO 8601 datetime formats)
                    try:
                        end_dt = datetime.fromisoformat(timeframe["to"].replace('Z', '+00:00'))
                        if end_dt.tzinfo:
                            end_dt = end_dt.replace(tzinfo=None)
                    except (ValueError, AttributeError):
                        end_dt = datetime.strptime(timeframe["to"], "%Y-%m-%d")
                    # If the input was a datetime, extract just the date part; otherwise use end of day
                    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
                    end_dt = tz.localize(end_dt)
                    before_date_iso = end_dt.strftime("%Y-%m-%dT23:59:59Z")
                    
                    # Fetch events for each participant concurrently
                    async def fetch_participant_events(participant_id: str):
                        try:
                            # Core_Event_Data accepts one calendar at a time
                            # ⚠️ IMPORTANT: Parameter names are REVERSED - Before=end, After=start
                            result = await mcp_client.get_core_event_data(
                                calendar_id=participant_id,
                                before=before_date_iso,  # END date
                                after=after_date_iso      # START date
                            )
                            
                            # The result is a JSON array of events (already parsed from text field)
                            if isinstance(result, list):
                                events = result
                            elif isinstance(result, dict):
                                # If wrapped in a dict, try to extract
                                if "events" in result:
                                    events = result["events"]
                                elif "items" in result:
                                    events = result["items"]
                                elif "data" in result:
                                    events = result["data"]
                                else:
                                    events = []
                            else:
                                events = []
                            
                            # Normalize to orchestrator's expected format
                            # Core_Event_Data provides: summary, id, start.dateTime, end.dateTime, locked, protected, flexible, attendees_list
                            # Orchestrator expects: id, title, start, end, locked, protected, flexible, attendees
                            normalized_events = []
                            for evt in events:
                                # Skip all-day events if present
                                if evt.get("start", {}).get("date"):  # All-day events have "date" not "dateTime"
                                    continue
                                
                                # Extract start/end from nested structure
                                start_dt = evt.get("start", {}).get("dateTime") or evt.get("start", {}).get("date")
                                end_dt = evt.get("end", {}).get("dateTime") or evt.get("end", {}).get("date")
                                
                                if not start_dt or not end_dt:
                                    continue  # Skip events without valid start/end
                                
                                # Extract attendees_list (for backward compatibility)
                                attendees_list = evt.get("attendees_list", [])
                                if isinstance(attendees_list, str):
                                    try:
                                        import ast
                                        attendees_list = ast.literal_eval(attendees_list)
                                    except:
                                        attendees_list = []
                                elif not isinstance(attendees_list, list):
                                    attendees_list = []
                                
                                # Extract attendees_details (new field with names)
                                attendees_details = evt.get("attendees_details", [])
                                if not isinstance(attendees_details, list):
                                    attendees_details = []
                                
                                # If attendees_details not available, construct from attendees_list
                                if not attendees_details and attendees_list:
                                    attendees_details = [
                                        {"email": email, "name": email.split("@")[0]}  # Use email prefix as name fallback
                                        for email in attendees_list
                                        if isinstance(email, str)
                                    ]
                                
                                # Normalize to orchestrator format
                                # Preserve both 'summary' (raw MCP) and 'title' (normalized) fields
                                # This ensures summary is available for event extraction later
                                evt_summary = evt.get("summary", "")
                                normalized_events.append({
                                    "id": evt.get("id", ""),
                                    "title": evt_summary,  # Use summary as title for normalized format
                                    "summary": evt_summary,  # Preserve original summary field
                                    "start": start_dt,
                                    "end": end_dt,
                                    "locked": evt.get("locked", False),
                                    "protected": evt.get("protected", False),
                                    "flexible": evt.get("flexible", True),
                                    "transparent": evt.get("transparent", False),  # True = "show as free"
                                    "description": evt.get("description", ""),  # For description-based protection detection
                                    "attendees": attendees_list,  # Keep for backward compatibility
                                    "attendees_details": attendees_details  # New field with names
                                })

                            return participant_id, normalized_events
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.error(f"Failed to fetch events for {participant_id}: {e}")
                            import traceback
                            logger.error(traceback.format_exc())
                            return participant_id, []
                    
                    # Fetch all calendars concurrently
                    tasks = [fetch_participant_events(pid) for pid in participant_ids]
                    results = await asyncio.gather(*tasks)
                    
                    # Build result dictionary
                    for participant_id, events in results:
                        events_by_participant[participant_id] = events
                    
                    return events_by_participant
                
                # Initialize MCP client and fetch events
                # Use asyncio.run() since this function is not async
                async def fetch_all():
                    await mcp_client.initialize()
                    
                    # For rescheduling with title + ambiguous dates, expand date range for initial fetch
                    # This ensures the event is included in the search results
                    timeframe_to_use = context_json["timeframe"].copy()
                    if is_rescheduling and scheduling_problem_preview:
                        event_identifiers_dict = scheduling_problem_preview.event_identifiers if hasattr(scheduling_problem_preview, 'event_identifiers') and scheduling_problem_preview.event_identifiers else {}
                        titles = event_identifiers_dict.get("titles", []) if isinstance(event_identifiers_dict, dict) else []
                        dates = event_identifiers_dict.get("dates", []) if isinstance(event_identifiers_dict, dict) else []
                        participant_names = event_identifiers_dict.get("participant_names", []) if isinstance(event_identifiers_dict, dict) else []
                        
                        has_title = bool(titles)
                        has_specific_dates = bool(dates)
                        has_participants = bool(participant_names)
                        dates_are_ambiguous = len(dates) > 1
                        
                        import pytz
                        from datetime import datetime, timedelta
                        tz = pytz.timezone(context_json["timeframe"].get("tz", "America/New_York"))
                        
                        # CRITICAL: If we have a single specific date (e.g., "Dec. 11"), use it to expand/narrow the search
                        # This ensures we find the meeting even if it's outside the context_json timeframe
                        use_date_specific_range = False
                        if dates and len(dates) == 1 and not dates_are_ambiguous:
                            # Single date provided - parse it and use it to expand/narrow the search window
                            try:
                                try:
                                    from .event_matcher import parse_date_reference
                                except (ImportError, ValueError):
                                    try:
                                        from scheduling_orchestrator.event_matcher import parse_date_reference
                                    except ImportError:
                                        from event_matcher import parse_date_reference
                                
                                target_date_dt = parse_date_reference(dates[0], datetime.now(tz))
                                if target_date_dt:
                                    # Use the target date ± 1 day for safety (in case of timezone issues or edge cases)
                                    use_date_specific_range = True
                                    start_dt = target_date_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                                    end_dt = target_date_dt.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=1)
                                    
                                    # CRITICAL: If the target date is outside the context_json timeframe, expand the range
                                    # to include both the target date AND the context timeframe
                                    # Parse context start date (handles both date-only and ISO 8601 datetime formats)
                                    try:
                                        context_start = datetime.fromisoformat(context_json["timeframe"]["from"].replace('Z', '+00:00'))
                                        if context_start.tzinfo:
                                            context_start = context_start.replace(tzinfo=None)
                                    except (ValueError, AttributeError):
                                        context_start = datetime.strptime(context_json["timeframe"]["from"], "%Y-%m-%d")
                                    context_start = context_start.replace(hour=0, minute=0, second=0, microsecond=0)
                                    context_start = tz.localize(context_start)
                                    # Parse context end date (handles both date-only and ISO 8601 datetime formats)
                                    try:
                                        context_end = datetime.fromisoformat(context_json["timeframe"]["to"].replace('Z', '+00:00'))
                                        if context_end.tzinfo:
                                            context_end = context_end.replace(tzinfo=None)
                                    except (ValueError, AttributeError):
                                        context_end = datetime.strptime(context_json["timeframe"]["to"], "%Y-%m-%d")
                                    context_end = context_end.replace(hour=23, minute=59, second=59, microsecond=0)
                                    context_end = tz.localize(context_end)
                                    
                                    # Expand to include both ranges
                                    start_dt = min(start_dt, context_start)
                                    end_dt = max(end_dt, context_end)
                                    
                                    timeframe_to_use = {
                                        "from": start_dt.strftime("%Y-%m-%d"),
                                        "to": end_dt.strftime("%Y-%m-%d"),
                                        "tz": context_json["timeframe"].get("tz", "America/New_York")
                                    }
                                    try:
                                        print(f"[orchestrate_scheduling] Using date-specific range for event fetch: '{dates[0]}' -> {timeframe_to_use['from']} to {timeframe_to_use['to']}", file=sys.stderr, flush=True)
                                    except:
                                        pass
                            except Exception as e:
                                # If date parsing fails, fall through to other logic
                                try:
                                    print(f"[orchestrate_scheduling] Failed to parse date '{dates[0]}' for expanding search: {e}", file=sys.stderr, flush=True)
                                except:
                                    pass
                        
                        # Use broad range if title + multiple dates (likely search window, not event date)
                        # Only if we didn't already set a date-specific range
                        if not use_date_specific_range:
                            use_broad_range = has_title and (
                                not has_specific_dates or 
                                dates_are_ambiguous or 
                                (has_specific_dates and not has_participants) or
                                (has_title and len(dates) > 1)
                            )
                            
                            if use_broad_range:
                                now = datetime.now(tz)
                                # Use 14 days forward from today for event identification
                                # Only look forward since it's unusual to reschedule past meetings
                                start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)  # Start of today
                                end_dt = now + timedelta(days=14)  # 14 days forward
                                timeframe_to_use = {
                                    "from": start_dt.strftime("%Y-%m-%d"),
                                    "to": end_dt.strftime("%Y-%m-%d"),
                                    "tz": context_json["timeframe"].get("tz", "America/New_York")
                                }
                                try:
                                    print(f"[orchestrate_scheduling] Expanded date range for initial event fetch: {timeframe_to_use['from']} to {timeframe_to_use['to']} (14 days forward, title: {titles}, dates: {dates})", file=sys.stderr, flush=True)
                                except:
                                    pass
                    
                    return await fetch_calendar_events(
                        participant_ids, user_id, timeframe_to_use, mcp_client
                    )
                
                fetched_events = asyncio.run(fetch_all())
                # Merge fetched events with any provided events_by_participant (if both are used)
                if events_by_participant:
                    for pid, events in fetched_events.items():
                        if pid in events_by_participant:
                            events_by_participant[pid].extend(events)
                        else:
                            events_by_participant[pid] = events
                else:
                    events_by_participant = fetched_events
            except MCPError as e:
                error_traceback = traceback.format_exc()
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Failed to fetch calendar events from MCP server: {e.message}",
                    proposals=[],
                    error_message=f"MCP error: {e.message}",
                    debug=debug_info
                ).model_dump() | {"error_traceback": error_traceback}
            except Exception as e:
                error_traceback = traceback.format_exc()
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Failed to fetch calendar events: {str(e)}",
                    proposals=[],
                    error_message=str(e),
                    debug=debug_info
                ).model_dump() | {"error_traceback": error_traceback}
        
        # Log input summary for debugging
        input_summary = {
            "utterance": utterance[:200] + ("..." if len(utterance) > 200 else ""),  # Truncate long utterances
            "num_participants": len(events_by_participant) if events_by_participant else 0,
            "events_per_participant": {pid: len(events) for pid, events in events_by_participant.items()} if events_by_participant else {},
            "total_events": sum(len(events) for events in events_by_participant.values()) if events_by_participant else 0,
            "has_context": context_json is not None,
            "context_keys": list(context_json.keys()) if context_json else []
        }
        debug_info.input_summary = input_summary
        
        # 1. Validate inputs
        # For rescheduling with user_id but no participant_ids, we may need to fetch events
        # for natural language identification, so don't fail here - let the rescheduling logic handle it
        # Use scheduling_problem_preview (extracted earlier) or is_rescheduling flag
        is_rescheduling_with_natural_language = (
            is_rescheduling and 
            not event_id and 
            scheduling_problem_preview and 
            scheduling_problem_preview.event_identifiers and
            user_id and
            not participant_ids
        )
        
        if not events_by_participant and not is_rescheduling_with_natural_language:
            return ResponseEnvelope(
                status="bad_input",
                explanation="No events provided or fetched. Please provide events_by_participant or participant_ids with a valid timeframe in context.",
                proposals=[],
                relaxations=[
                    Relaxation(
                        description="Provide participant_ids and a timeframe in context_json to enable automatic event fetching.",
                        expected_impact="high",
                        policy_change={},
                        rank=1
                    )
                ],
                error_message="No events to schedule",
                debug=debug_info
            ).model_dump()
        
        # Bounds checking
        MAX_PARTICIPANTS = 10
        MAX_EVENTS_PER_PARTICIPANT = 100
        MAX_HORIZON_DAYS = 28  # 4 weeks
        
        if context_json and "timeframe" in context_json:
            try:
                from_dt = datetime.fromisoformat(context_json["timeframe"]["from"])
                to_dt = datetime.fromisoformat(context_json["timeframe"]["to"])
                horizon_days = (to_dt - from_dt).days
                if horizon_days > MAX_HORIZON_DAYS:
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Planning horizon ({horizon_days} days) exceeds maximum ({MAX_HORIZON_DAYS} days).",
                        proposals=[],
                        error_message=f"Horizon too large: {horizon_days} days",
                        debug=debug_info
                    ).model_dump()
            except Exception:
                pass
        
        if len(events_by_participant) > MAX_PARTICIPANTS:
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Number of participants ({len(events_by_participant)}) exceeds maximum ({MAX_PARTICIPANTS}).",
                proposals=[],
                error_message=f"Too many participants: {len(events_by_participant)}",
                debug=debug_info
            ).model_dump()
        
        # Track if we used expanded date range for event identification
        # If so, we'll filter events to the narrower timeframe after identification
        used_expanded_range_for_identification = False
        
        # For rescheduling with expanded range, defer limit check until after filtering
        # Check if this is rescheduling with title + ambiguous dates (would use expanded range)
        should_defer_limit_check = False
        if is_rescheduling and scheduling_problem_preview:
            event_identifiers_dict = scheduling_problem_preview.event_identifiers if hasattr(scheduling_problem_preview, 'event_identifiers') and scheduling_problem_preview.event_identifiers else {}
            titles = event_identifiers_dict.get("titles", []) if isinstance(event_identifiers_dict, dict) else []
            dates = event_identifiers_dict.get("dates", []) if isinstance(event_identifiers_dict, dict) else []
            if titles and len(dates) > 1:
                should_defer_limit_check = True
                used_expanded_range_for_identification = True
        
        # Only check limit now if we're NOT deferring (i.e., not using expanded range for identification)
        if not should_defer_limit_check:
            for participant_id, events in events_by_participant.items():
                if len(events) > MAX_EVENTS_PER_PARTICIPANT:
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Participant {participant_id} has {len(events)} events, exceeding maximum ({MAX_EVENTS_PER_PARTICIPANT}).",
                        proposals=[],
                        error_message=f"Too many events for {participant_id}: {len(events)}",
                        debug=debug_info
                    ).model_dump()
        
        # 2. Extract scheduling problem from utterance using DSPy
        # ISSUE #11 FIX: Reuse scheduling_problem_preview if available (500-2000ms savings)
        # The preview extraction was done earlier to check for rescheduling intent
        extraction_start = time.time()
        try:
            if scheduling_problem_preview is not None:
                # Reuse cached extraction result
                scheduling_problem = scheduling_problem_preview
                extraction_time_ms = 0  # Already extracted
                print(f"[orchestrate_scheduling] Reusing cached DSPy extraction (Issue #11 fix)", file=sys.stderr, flush=True)
            else:
                # Fallback to fresh extraction if preview failed
                scheduling_problem = extract_with_fallback(utterance, context_json)
                extraction_time_ms = int((time.time() - extraction_start) * 1000)
            debug_info.extraction_time_ms = extraction_time_ms
            # Note: extraction_time_ms == 0 is expected when reusing cached preview (Issue #11 fix)
            # Only warn if preview was NOT used and extraction still took 0ms
            if extraction_time_ms == 0 and scheduling_problem_preview is None:
                print(f"[orchestrate_scheduling] WARNING: Extraction time is 0ms - DSPy may not have been used", file=sys.stderr, flush=True)
            
            # Ensure is_rescheduling is set correctly if event_id is provided or local is_rescheduling is True
            # DSPy might not detect rescheduling from utterance alone, but we know it's rescheduling if event_id is provided
            # CRITICAL: If this is a NEW meeting request, override any rescheduling detection
            # Re-check for new meeting phrases and event identifiers (variables from earlier scope may not be accessible here)
            utterance_lower_check = utterance.lower()
            new_meeting_phrases_check = [
                "schedule a new", "create a new", "set up a new", "book a new",
                "arrange a new", "plan a new", "organize a new",
                "schedule new", "create new", "set up new", "book new",
                "arrange new", "plan new", "organize new"
            ]
            is_new_meeting_by_phrase_check = any(phrase in utterance_lower_check for phrase in new_meeting_phrases_check)
            
            # Also check if there are no event identifiers (default to new meeting)
            has_event_identifiers_check = False
            if scheduling_problem.event_identifiers:
                event_identifiers_check = scheduling_problem.event_identifiers
                if isinstance(event_identifiers_check, str):
                    try:
                        import json
                        event_identifiers_check = json.loads(event_identifiers_check)
                    except:
                        event_identifiers_check = {}
                if isinstance(event_identifiers_check, dict):
                    titles = event_identifiers_check.get("titles", []) or []
                    dates = event_identifiers_check.get("dates", []) or []
                    times = event_identifiers_check.get("times", []) or []
                    has_event_identifiers_check = bool(titles or (dates and len(dates) > 0) or (times and len(times) > 0))
            
            # Override rescheduling if it's a new meeting by phrase OR no event identifiers and no explicit rescheduling
            if is_new_meeting_by_phrase_check or (not has_event_identifiers_check and not scheduling_problem.is_rescheduling):
                scheduling_problem.is_rescheduling = False
                try:
                    print(f"[orchestrate_scheduling] Overriding rescheduling detection - this is a NEW meeting request", file=sys.stderr, flush=True)
                except:
                    pass
            elif is_rescheduling and not scheduling_problem.is_rescheduling:
                scheduling_problem.is_rescheduling = True
                print(f"[orchestrate_scheduling] Set is_rescheduling=True because event_id is provided or rescheduling keywords detected", file=sys.stderr, flush=True)
            
            # Post-process event_identifiers to fix common DSPy extraction errors
            # Sometimes DSPy extracts meeting titles as participant names (e.g., "Concord Audit Drafts")
            if scheduling_problem.event_identifiers and isinstance(scheduling_problem.event_identifiers, dict):
                participant_names = scheduling_problem.event_identifiers.get("participant_names", [])
                titles = scheduling_problem.event_identifiers.get("titles", [])
                
                # Heuristic: If participant_names contains phrases that look like meeting titles,
                # and titles is empty or only contains generic words, move them to titles
                if participant_names and (not titles or all(t.lower() in ["meeting", "meetings"] for t in titles)):
                    title_like_phrases = []
                    remaining_participants = []
                    
                    for pn in participant_names:
                        pn_lower = pn.lower()
                        # Check if this looks like a meeting title:
                        # - Contains multiple capitalized words (e.g., "Concord Audit Drafts")
                        # - Contains organization names or project names
                        # - Contains words like "Audit", "Drafts", "Team", "Review", etc.
                        # - Does NOT look like a personal name (e.g., "Judi", "Chad", "Kate")
                        is_title_like = False
                        
                        # Multiple words with capitals suggests a title
                        words = pn.split()
                        if len(words) >= 2:
                            # Check if most words start with capital letters
                            capitalized_words = sum(1 for w in words if w and w[0].isupper())
                            if capitalized_words >= 2:
                                is_title_like = True
                        
                        # Check for title-like keywords
                        title_keywords = ["audit", "drafts", "team", "review", "meeting", "standup", "sync", "check-in", "planning", "design", "development", "finance", "grants", "consortium"]
                        if any(keyword in pn_lower for keyword in title_keywords):
                            is_title_like = True
                        
                        # Check if it's clearly NOT a personal name
                        # Personal names are typically 1-2 words, don't contain organization terms
                        personal_name_indicators = ["with", "and", "&", "/"]
                        if not any(indicator in pn_lower for indicator in personal_name_indicators):
                            # If it's 2+ words and doesn't contain personal name indicators, likely a title
                            if len(words) >= 2:
                                is_title_like = True
                        
                        if is_title_like:
                            title_like_phrases.append(pn)
                        else:
                            remaining_participants.append(pn)
                    
                    # If we found title-like phrases, move them to titles
                    if title_like_phrases:
                        if not titles:
                            scheduling_problem.event_identifiers["titles"] = title_like_phrases
                        else:
                            # Merge with existing titles
                            scheduling_problem.event_identifiers["titles"] = titles + title_like_phrases
                        scheduling_problem.event_identifiers["participant_names"] = remaining_participants
                        try:
                            print(f"[orchestrate_scheduling] Post-processed event_identifiers: moved {title_like_phrases} from participant_names to titles", file=sys.stderr, flush=True)
                        except:
                            pass
        except Exception as e:
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to extract scheduling problem from utterance: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
        # 3. Identify event from natural language if rescheduling and event_id not provided
        # Determine which calendar(s) to search based on priority:
        # 1. Explicit participant_ids parameter
        # 2. Participants from context_json (agent-supplied names and IDs)
        # 3. Conservative utterance extraction (only if title/date aren't sufficient)
        # 4. Fallback to user_id if no other participants can be determined
        if (scheduling_problem.is_rescheduling and 
            not event_id and 
            scheduling_problem.event_identifiers):
            
            # Determine participants to search from (priority order)
            # Check for possessive pronoun "my" or "mine" to prioritize user_id calendar
            utterance_lower = utterance.lower() if utterance else ""
            has_possessive = user_id and (" my " in utterance_lower or " mine " in utterance_lower or utterance_lower.startswith("my ") or utterance_lower.startswith("mine "))
            
            # If "my" is detected, prioritize user_id calendar for rescheduling
            if has_possessive and user_id and scheduling_problem.is_rescheduling:
                calendars_to_search = [user_id]
                try:
                    print(f"[orchestrate_scheduling] Detected possessive pronoun 'my' - prioritizing user_id calendar: {calendars_to_search}", file=sys.stderr, flush=True)
                except:
                    pass
            else:
                # Inline participant extraction logic (no separate function to avoid Letta schema issues)
                import re
                calendars_to_search = []
                
                # Priority 1: Explicit participant_ids parameter
                if participant_ids:
                    calendars_to_search = participant_ids
                    try:
                        print(f"[extract_participants] Using explicit participant_ids: {participant_ids}", file=sys.stderr, flush=True)
                    except:
                        pass
                else:
                    # Priority 2: Match utterance against context_json.participants
                    context_dict = context_json
                    if isinstance(context_json, str):
                        try:
                            context_dict = json.loads(context_json)
                        except:
                            context_dict = {}
                    
                    matched_emails = []
                    if isinstance(context_dict, dict) and "participants" in context_dict:
                        participants_list = context_dict.get("participants", [])
                        utterance_lower_check = utterance.lower() if utterance else ""
                        
                        for p in participants_list:
                            if isinstance(p, dict):
                                p_name = p.get("name", "")
                                p_email = p.get("email", "")
                                p_id = p.get("id", "")
                                
                                if p_name:
                                    name_parts = p_name.split()
                                    first_name = name_parts[0] if name_parts else ""
                                    
                                    name_patterns = [
                                        rf'\b{re.escape(first_name)}\b',
                                        rf'\b{re.escape(p_name)}\b',
                                    ]
                                    
                                    for pattern in name_patterns:
                                        if re.search(pattern, utterance, re.IGNORECASE):
                                            email_to_use = p_email or p_id
                                            if email_to_use and email_to_use not in matched_emails:
                                                matched_emails.append(email_to_use)
                                                try:
                                                    print(f"[extract_participants] Matched '{p_name}' from context_json to {email_to_use}", file=sys.stderr, flush=True)
                                                except:
                                                    pass
                                            break
                    
                    if matched_emails:
                        calendars_to_search = matched_emails
                    else:
                        # Priority 3: Conservative utterance extraction
                        proper_noun_pattern = r'\b([A-Z][a-z]{2,15})\b'
                        capitalized_words = re.findall(proper_noun_pattern, utterance)
                        
                        skip_capitalized = {
                            'What', 'We', 'The', 'There', 'This', 'That', 'These', 'Those', 'They', 'It',
                            'When', 'Where', 'Why', 'How', 'Which', 'Who', 'Whose', 'Whom',
                            'But', 'And', 'Or', 'For', 'With', 'From', 'To', 'Of', 'In', 'On', 'At', 'By',
                            'Friday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday', 'Sunday',
                            'Grants', 'Team', 'Meeting', 'Week', 'Next', 'Time', 'New', 'Alternative', 'Different',
                            'Check', 'Hold', 'Block', 'Review', 'Planning', 'Standup', 'Sync', 'Retro', 'All-hands',
                            'Weekly', 'Daily', 'Monthly', 'Quarterly', 'Annual', 'Finance', 'Engineering', 'Product',
                            'Design', 'Marketing', 'Sales', 'Support', 'HR', 'IT',
                            'Need', 'Have', 'Are', 'Other', 'Options', 'Timeslot', 'Timeslots'
                        }
                        
                        candidate_names = [w for w in capitalized_words if w not in skip_capitalized]
                        confirmed_names = []
                        utterance_lower_check = utterance.lower()
                        
                        for name in candidate_names:
                            name_lower = name.lower()
                            name_pos = utterance_lower_check.find(name_lower)
                            if name_pos == -1:
                                continue
                            
                            context_before = utterance_lower_check[max(0, name_pos - 20):name_pos]
                            context_after = utterance_lower_check[name_pos + len(name_lower):name_pos + len(name_lower) + 20]
                            
                            has_signifier = (
                                re.search(r'\bwith\s+' + re.escape(name_lower) + r'\b', context_before + ' ' + name_lower + ' ' + context_after) or
                                re.search(r'\b' + re.escape(name_lower) + r'\s+and\s+i\b', context_before + ' ' + name_lower + ' ' + context_after) or
                                re.search(r'\b' + re.escape(name_lower) + r"'s\b", utterance_lower_check) or
                                any(re.search(p, utterance) for p in [
                                    rf'\b{re.escape(name)}\s*[/&]\s*([A-Z][a-z]+)\b',
                                    rf'\b([A-Z][a-z]+)\s*[/&]\s*{re.escape(name)}\b',
                                    rf'\b{re.escape(name)}\s+and\s+([A-Z][a-z]+)\b',
                                    rf'\b([A-Z][a-z]+)\s+and\s+{re.escape(name)}\b',
                                ])
                            )
                            
                            if has_signifier:
                                confirmed_names.append(name)
                                try:
                                    print(f"[extract_participants] Confirmed participant name from utterance: {name} (context signifier found)", file=sys.stderr, flush=True)
                                except:
                                    pass
                        
                        # Map confirmed names to emails
                        if confirmed_names:
                            try:
                                from .event_matcher import map_participant_names_to_emails
                            except (ImportError, ValueError):
                                try:
                                    from scheduling_orchestrator.event_matcher import map_participant_names_to_emails
                                except ImportError:
                                    from event_matcher import map_participant_names_to_emails
                            
                            mapped_emails = map_participant_names_to_emails(
                                confirmed_names,
                                context_dict,
                                participant_ids
                            )
                            
                            if mapped_emails:
                                valid_emails = []
                                invalid_patterns = [
                                    'grants@', 'team@', 'meeting@', 'find@', 'me@', 'next@', 'week@',
                                    'friday@', 'monday@', 'tuesday@', 'wednesday@', 'thursday@', 'saturday@', 'sunday@'
                                ]
                                for email in mapped_emails:
                                    if '@' in email and '.' in email.split('@')[1]:
                                        email_lower = email.lower()
                                        if not any(pattern in email_lower for pattern in invalid_patterns):
                                            valid_emails.append(email)
                                
                                if valid_emails:
                                    calendars_to_search = valid_emails
                        
                        # Priority 4: Fallback to user_id
                        if not calendars_to_search and user_id:
                            calendars_to_search = [user_id]
                            try:
                                print(f"[extract_participants] Falling back to user_id: {user_id}", file=sys.stderr, flush=True)
                            except:
                                pass
                
                if not calendars_to_search:
                    # No participants found - this will be handled by the fallback logic below
                    try:
                        print(f"[orchestrate_scheduling] No participants found for event search, will use user_id fallback", file=sys.stderr, flush=True)
                    except:
                        pass
            
            # Fetch calendars for determined participants if not already available
            if calendars_to_search and not events_by_participant:
                # Need to fetch user_id calendar first to search for the event
                if context_json and "timeframe" in context_json:
                    try:
                        import os
                        import asyncio
                        try:
                            from .mcp_client import MCPCalendarClient, MCPError
                        except (ImportError, ValueError):
                            try:
                                from scheduling_orchestrator.mcp_client import MCPCalendarClient, MCPError
                            except ImportError:
                                from mcp_client import MCPCalendarClient, MCPError
                        
                        mcp_url = os.getenv(
                            "MCP_CALENDAR_SERVER_URL",
                            "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
                        )
                        
                        mcp_client = MCPCalendarClient(
                            base_url=mcp_url,
                            timeout=int(os.getenv("MCP_CALENDAR_TIMEOUT", "30")),
                            max_retries=int(os.getenv("MCP_CALENDAR_RETRY_ATTEMPTS", "3"))
                        )
                        
                        # Fetch calendars for determined participants
                        async def fetch_calendars_for_search():
                            await mcp_client.initialize()
                            import pytz
                            from datetime import datetime, timedelta
                            
                            tz = pytz.timezone(context_json["timeframe"].get("tz", "America/New_York"))
                            
                            # Determine date range for event identification
                            # If title is primary identifier (and dates are ambiguous or missing),
                            # use a broader range to find the meeting
                            # NOTE: Use scheduling_problem_preview since scheduling_problem hasn't been created yet
                            event_identifiers_dict = {}
                            if scheduling_problem_preview and hasattr(scheduling_problem_preview, 'event_identifiers') and scheduling_problem_preview.event_identifiers:
                                event_identifiers_dict = scheduling_problem_preview.event_identifiers
                            elif 'scheduling_problem' in locals() and hasattr(scheduling_problem, 'event_identifiers') and scheduling_problem.event_identifiers:
                                event_identifiers_dict = scheduling_problem.event_identifiers
                            
                            titles = event_identifiers_dict.get("titles", []) if isinstance(event_identifiers_dict, dict) else []
                            dates = event_identifiers_dict.get("dates", []) if isinstance(event_identifiers_dict, dict) else []
                            participant_names = event_identifiers_dict.get("participant_names", []) if isinstance(event_identifiers_dict, dict) else []
                            
                            try:
                                print(f"[orchestrate_scheduling] DEBUG: event_identifiers_dict={event_identifiers_dict}, dates={dates}, len(dates)={len(dates) if dates else 0}", file=sys.stderr, flush=True)
                            except:
                                pass
                            
                            # If we have a title but no specific dates (or ambiguous dates like "Wednesday through Friday"
                            # which could be the search window), expand the search range
                            has_title = bool(titles)
                            has_specific_dates = bool(dates)
                            has_participants = bool(participant_names)
                            
                            # Check if dates are ambiguous (multiple days likely means search window, not event date)
                            # Examples: "Wednesday through Friday", "between Monday and Wednesday" → likely search window
                            # Also: "Wednesday" and "Friday" as separate dates likely means search window, not event date
                            dates_are_ambiguous = False
                            if dates and len(dates) > 1:
                                # Multiple dates in event_identifiers likely means search window, not event date
                                dates_are_ambiguous = True
                            
                            try:
                                print(f"[orchestrate_scheduling] DEBUG: dates_are_ambiguous={dates_are_ambiguous}, dates={dates}, len(dates)={len(dates) if dates else 0}", file=sys.stderr, flush=True)
                            except:
                                pass
                            
                            # CRITICAL: If we have a single specific date (e.g., "Dec. 11"), use it to expand/narrow the search
                            # This ensures we find the meeting even if it's outside the context_json timeframe
                            use_date_specific_range = False
                            target_date_dt = None
                            if dates and len(dates) == 1 and not dates_are_ambiguous:
                                try:
                                    print(f"[orchestrate_scheduling] DEBUG: Entering date-specific range logic for date: '{dates[0]}'", file=sys.stderr, flush=True)
                                except:
                                    pass
                                # Single date provided - parse it and use it to expand/narrow the search window
                                try:
                                    try:
                                        from .event_matcher import parse_date_reference
                                    except (ImportError, ValueError):
                                        try:
                                            from scheduling_orchestrator.event_matcher import parse_date_reference
                                        except ImportError:
                                            from event_matcher import parse_date_reference
                                    
                                    target_date_dt = parse_date_reference(dates[0], datetime.now(tz))
                                    if target_date_dt:
                                        # Use the target date ± 1 day for safety (in case of timezone issues or edge cases)
                                        use_date_specific_range = True
                                        start_dt = target_date_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                                        end_dt = target_date_dt.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=1)
                                        
                                        # CRITICAL: If the target date is outside the context_json timeframe, expand the range
                                        # to include both the target date AND the context timeframe
                                        if context_json and "timeframe" in context_json:
                                            # Parse context start date (handles both date-only and ISO 8601 datetime formats)
                                            try:
                                                context_start = datetime.fromisoformat(context_json["timeframe"]["from"].replace('Z', '+00:00'))
                                                if context_start.tzinfo:
                                                    context_start = context_start.replace(tzinfo=None)
                                            except (ValueError, AttributeError):
                                                context_start = datetime.strptime(context_json["timeframe"]["from"], "%Y-%m-%d")
                                            context_start = context_start.replace(hour=0, minute=0, second=0, microsecond=0)
                                            context_start = tz.localize(context_start)
                                            # Parse context end date (handles both date-only and ISO 8601 datetime formats)
                                            try:
                                                context_end = datetime.fromisoformat(context_json["timeframe"]["to"].replace('Z', '+00:00'))
                                                if context_end.tzinfo:
                                                    context_end = context_end.replace(tzinfo=None)
                                            except (ValueError, AttributeError):
                                                context_end = datetime.strptime(context_json["timeframe"]["to"], "%Y-%m-%d")
                                            context_end = context_end.replace(hour=23, minute=59, second=59, microsecond=0)
                                            context_end = tz.localize(context_end)
                                            
                                            # Expand to include both ranges
                                            start_dt = min(start_dt, context_start)
                                            end_dt = max(end_dt, context_end)
                                        
                                        try:
                                            print(f"[orchestrate_scheduling] Using date-specific range for event identification: '{dates[0]}' -> {start_dt.date()} to {end_dt.date()}", file=sys.stderr, flush=True)
                                        except:
                                            pass
                                except Exception as e:
                                    # If date parsing fails, fall through to other logic
                                    try:
                                        print(f"[orchestrate_scheduling] Failed to parse date '{dates[0]}' for narrowing search: {e}", file=sys.stderr, flush=True)
                                    except:
                                        pass
                            
                            # CRITICAL: If no date was extracted but title contains a day-of-week reference,
                            # extract it from the title and use it to narrow the search window
                            # Example: "Tuesday Inquisitive & Concord Consortium meeting" -> search Tuesday
                            if not use_date_specific_range and titles:
                                import re
                                # Day-of-week names (case-insensitive)
                                day_names = {
                                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                    'friday': 4, 'saturday': 5, 'sunday': 6,
                                    'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3,
                                    'fri': 4, 'sat': 5, 'sun': 6
                                }
                                
                                # Search for day names in titles
                                for title in titles:
                                    if not isinstance(title, str):
                                        continue
                                    title_lower = title.lower()
                                    
                                    # Look for day names as whole words (word boundaries)
                                    for day_name, day_num in day_names.items():
                                        # Use word boundary regex to match whole words only
                                        pattern = r'\b' + re.escape(day_name) + r'\b'
                                        if re.search(pattern, title_lower):
                                            # Found a day name - parse it to get the actual date
                                            try:
                                                try:
                                                    from .event_matcher import parse_date_reference
                                                except (ImportError, ValueError):
                                                    try:
                                                        from scheduling_orchestrator.event_matcher import parse_date_reference
                                                    except ImportError:
                                                        from event_matcher import parse_date_reference
                                                
                                                # Parse the day name (e.g., "Tuesday" -> next Tuesday)
                                                target_date_dt = parse_date_reference(day_name.capitalize(), datetime.now(tz))
                                                if target_date_dt:
                                                    # Use the target date ± 1 day for safety
                                                    use_date_specific_range = True
                                                    start_dt = target_date_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                                                    end_dt = target_date_dt.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=1)
                                                    try:
                                                        print(f"[orchestrate_scheduling] Extracted day-of-week '{day_name}' from title '{title}' and using date-specific range: {start_dt.date()} to {end_dt.date()}", file=sys.stderr, flush=True)
                                                    except:
                                                        pass
                                                    break  # Found a day, stop searching
                                            except Exception as e:
                                                # If date parsing fails, continue to next title
                                                try:
                                                    print(f"[orchestrate_scheduling] Failed to parse day-of-week '{day_name}' from title '{title}': {e}", file=sys.stderr, flush=True)
                                                except:
                                                    pass
                                    
                                    if use_date_specific_range:
                                        break  # Found a day in this title, stop searching titles
                            
                            if not use_date_specific_range:
                                # No specific date or ambiguous dates - determine range based on other factors
                                # Use broader range if:
                                # 1. Title is primary identifier (has_title)
                                # 2. AND either:
                                #    - No dates provided, OR
                                #    - Dates are ambiguous (multiple days = likely search window), OR
                                #    - Dates provided but no participant names (title is the main identifier)
                                # CRITICAL: If we have a title and multiple dates, always use broad range
                                # because multiple dates almost certainly means search window, not event date
                                use_broad_range = has_title and (
                                    not has_specific_dates or 
                                    dates_are_ambiguous or 
                                    (has_specific_dates and not has_participants) or
                                    (has_title and len(dates) > 1)  # Title + multiple dates = always broad range
                                )
                                
                                # Debug logging
                                try:
                                    print(f"[orchestrate_scheduling] Date range expansion check: has_title={has_title}, has_specific_dates={has_specific_dates}, dates_are_ambiguous={dates_are_ambiguous}, has_participants={has_participants}, use_broad_range={use_broad_range}", file=sys.stderr, flush=True)
                                except:
                                    pass
                                
                                if use_broad_range:
                                    # Use 14 days forward from today for event identification
                                    # Only look forward since it's unusual to reschedule past meetings
                                    now = datetime.now(tz)
                                    start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)  # Start of today
                                    end_dt = now + timedelta(days=14)  # 14 days forward
                                    try:
                                        print(f"[orchestrate_scheduling] Using expanded date range (14 days forward from today) for event identification with title: {titles}", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                else:
                                    # Use the timeframe from context_json (for rescheduling search window)
                                    # Parse start date (handles both date-only and ISO 8601 datetime formats)
                                    try:
                                        start_dt = datetime.fromisoformat(context_json["timeframe"]["from"].replace('Z', '+00:00'))
                                        if start_dt.tzinfo:
                                            start_dt = start_dt.replace(tzinfo=None)
                                    except (ValueError, AttributeError):
                                        start_dt = datetime.strptime(context_json["timeframe"]["from"], "%Y-%m-%d")
                                    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                                    start_dt = tz.localize(start_dt)
                                    # Parse end date (handles both date-only and ISO 8601 datetime formats)
                                    try:
                                        end_dt = datetime.fromisoformat(context_json["timeframe"]["to"].replace('Z', '+00:00'))
                                        if end_dt.tzinfo:
                                            end_dt = end_dt.replace(tzinfo=None)
                                    except (ValueError, AttributeError):
                                        end_dt = datetime.strptime(context_json["timeframe"]["to"], "%Y-%m-%d")
                                    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
                                    end_dt = tz.localize(end_dt)
                            
                            after_date_iso = start_dt.strftime("%Y-%m-%dT00:00:00Z")
                            before_date_iso = end_dt.strftime("%Y-%m-%dT23:59:59Z")
                            
                            all_events = {}
                            for calendar_id in calendars_to_search:
                                try:
                                    result = await mcp_client.get_core_event_data(
                                        calendar_id=calendar_id,
                                        before=before_date_iso,
                                        after=after_date_iso
                                    )
                                    
                                    if isinstance(result, list):
                                        events = result
                                    elif isinstance(result, dict):
                                        events = result.get("events", result.get("items", result.get("data", [])))
                                    else:
                                        events = []
                                    
                                    all_events[calendar_id] = events
                                except Exception as e:
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.error(f"Failed to fetch events for {calendar_id}: {e}")
                                    all_events[calendar_id] = []
                            
                            return all_events
                        
                        fetched_events_by_calendar = asyncio.run(fetch_calendars_for_search())
                        
                        # Normalize events for all calendars
                        normalized_events_by_participant = {}
                        for calendar_id, events in fetched_events_by_calendar.items():
                            normalized_events = []
                            for evt in events:
                                if evt.get("start", {}).get("date"):
                                    continue
                                start_dt = evt.get("start", {}).get("dateTime")
                                end_dt = evt.get("end", {}).get("dateTime")
                                if not start_dt or not end_dt:
                                    continue
                                
                                attendees_list = evt.get("attendees_list", [])
                                if isinstance(attendees_list, str):
                                    try:
                                        import ast
                                        attendees_list = ast.literal_eval(attendees_list)
                                    except:
                                        attendees_list = []
                                elif not isinstance(attendees_list, list):
                                    attendees_list = []
                                
                                attendees_details = evt.get("attendees_details", [])
                                if not isinstance(attendees_details, list):
                                    attendees_details = []
                                if not attendees_details and attendees_list:
                                    attendees_details = [
                                        {"email": email, "name": email.split("@")[0]}
                                        for email in attendees_list
                                        if isinstance(email, str)
                                    ]
                                
                                # Preserve both 'summary' (raw MCP) and 'title' (normalized) fields
                                # This ensures summary is available for event extraction later
                                evt_summary = evt.get("summary", "")
                                normalized_events.append({
                                    "id": evt.get("id", ""),
                                    "title": evt_summary,  # Use summary as title for normalized format
                                    "summary": evt_summary,  # Preserve original summary field
                                    "start": start_dt,
                                    "end": end_dt,
                                    "locked": evt.get("locked", False),
                                    "protected": evt.get("protected", False),
                                    "flexible": evt.get("flexible", True),
                                    "transparent": evt.get("transparent", False),  # True = "show as free"
                                    "description": evt.get("description", ""),  # For description-based protection detection
                                    "attendees": attendees_list,
                                    "attendees_details": attendees_details
                                })

                            normalized_events_by_participant[calendar_id] = normalized_events

                        # Create events_by_participant with fetched calendars
                        events_by_participant = normalized_events_by_participant
                        
                        try:
                            total_events = sum(len(events) for events in normalized_events_by_participant.values())
                            print(f"[orchestrate_scheduling] Fetched {total_events} events from {len(calendars_to_search)} calendar(s) ({', '.join(calendars_to_search)}) for natural language event identification", file=sys.stderr, flush=True)
                        except:
                            pass
                    except Exception as e:
                        # If fetching fails, we'll try to continue with natural language identification
                        # but may need to ask for more information
                        try:
                            print(f"[orchestrate_scheduling] Warning: Could not fetch requester's calendar for event identification: {str(e)}", file=sys.stderr, flush=True)
                        except:
                            pass
            
            if events_by_participant:
                try:
                    # Import event matcher
                    try:
                        from .event_matcher import identify_event_from_natural_language
                    except (ImportError, ValueError):
                        try:
                            from scheduling_orchestrator.event_matcher import identify_event_from_natural_language
                        except ImportError:
                            from event_matcher import identify_event_from_natural_language
                    
                    # Convert context_json to dict if needed
                    context_dict = context_json
                    if isinstance(context_json, str):
                        context_dict = json.loads(context_json)
                    
                    # Enhance context_dict with participant information from participant_ids and events
                    # This helps with participant name mapping in event identification
                    # Extract names from attendees_details in events if available
                    participant_name_map = {}  # email -> name mapping from events
                    if events_by_participant:
                        for owner_id, events_list in events_by_participant.items():
                            for evt in events_list:
                                attendees_details = evt.get("attendees_details", [])
                                if attendees_details and isinstance(attendees_details, list):
                                    for attendee in attendees_details:
                                        if isinstance(attendee, dict):
                                            email = attendee.get("email", "")
                                            name = attendee.get("name", "")
                                            if email and name and email not in participant_name_map:
                                                participant_name_map[email] = name
                    
                    if participant_ids and ("participants" not in context_dict or not context_dict.get("participants")):
                        if "participants" not in context_dict:
                            context_dict["participants"] = []
                        # Add participant info from participant_ids, using names from events if available
                        for p_id in participant_ids:
                            # Check if this participant is already in the list
                            existing = any(p.get("id") == p_id or p.get("email") == p_id for p in context_dict["participants"])
                            if not existing:
                                # Use name from events if available, otherwise use email prefix
                                participant_name = participant_name_map.get(p_id, p_id.split("@")[0])
                                context_dict["participants"].append({
                                    "id": p_id,
                                    "email": p_id,
                                    "name": participant_name
                                })
                    
                    # Ensure event_identifiers is a dict (not a string)
                    event_identifiers_dict = scheduling_problem.event_identifiers
                    if isinstance(event_identifiers_dict, str):
                        try:
                            event_identifiers_dict = json.loads(event_identifiers_dict)
                        except (json.JSONDecodeError, ValueError):
                            # If parsing fails, try to extract from the string
                            import re
                            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', event_identifiers_dict, re.DOTALL)
                            if json_match:
                                try:
                                    event_identifiers_dict = json.loads(json_match.group(0))
                                except (json.JSONDecodeError, ValueError):
                                    event_identifiers_dict = None
                            else:
                                event_identifiers_dict = None
                    
                    # If event_identifiers is still not a dict, we can't proceed
                    if not isinstance(event_identifiers_dict, dict):
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation="Could not parse event identifiers from the request. Please provide more specific details like: participant names, date, time, or meeting title.",
                            proposals=[],
                            error_message="Event identifiers not in valid format",
                            debug=debug_info
                        ).model_dump()
                    
                    # Log event identifiers for debugging
                    try:
                        print(f"[orchestrate_scheduling] Event identifiers: {event_identifiers_dict}", file=sys.stderr, flush=True)
                    except:
                        pass
                    
                    # Identify event from natural language
                    # Pass participant_ids directly for exact matching
                    match_result = identify_event_from_natural_language(
                        event_identifiers=event_identifiers_dict,
                        events_by_participant=events_by_participant,
                        context_json=context_dict,
                        participant_ids=participant_ids  # Pass participant_ids for exact participant matching
                    )
                    
                    # Debug logging for match result
                    try:
                        print(f"[orchestrate_scheduling] Match result: {match_result is not None}, type: {type(match_result)}", file=sys.stderr, flush=True)
                        if match_result:
                            print(f"[orchestrate_scheduling] Match result details: event_id={match_result[0].get('id', '') if match_result[0] else 'None'}, participant={match_result[1] if len(match_result) > 1 else 'None'}", file=sys.stderr, flush=True)
                    except:
                        pass
                    
                    if match_result:
                        matched_event, matched_participant = match_result
                        fetched_event_by_id = matched_event
                        # Store matched participant for later use in event extraction
                        if not event_participant_id:
                            event_participant_id = matched_participant
                        # Log successful identification with full MCP response details
                        try:
                            event_summary = matched_event.get("summary", "")
                            event_id = matched_event.get("id", "")
                            event_attendees = matched_event.get("attendees_list", [])
                            event_attendees_details = matched_event.get("attendees_details", [])
                            event_start = matched_event.get("start", {})
                            
                            print(f"[orchestrate_scheduling] Identified event '{event_summary}' (ID: {event_id}) from natural language in calendar {matched_participant}", file=sys.stderr, flush=True)
                            print(f"[orchestrate_scheduling] MCP Response Details:", file=sys.stderr, flush=True)
                            print(f"  - summary field: '{event_summary}' (type: {type(event_summary).__name__}, empty: {not event_summary})", file=sys.stderr, flush=True)
                            print(f"  - attendees_list: {event_attendees} (type: {type(event_attendees).__name__}, count: {len(event_attendees) if isinstance(event_attendees, list) else 0})", file=sys.stderr, flush=True)
                            print(f"  - attendees_details: {event_attendees_details} (type: {type(event_attendees_details).__name__}, count: {len(event_attendees_details) if isinstance(event_attendees_details, list) else 0})", file=sys.stderr, flush=True)
                            print(f"  - start: {event_start} (type: {type(event_start).__name__})", file=sys.stderr, flush=True)
                            if participant_ids:
                                print(f"  - participant_ids provided: {participant_ids}", file=sys.stderr, flush=True)
                                # Check if all participant_ids are in attendees
                                all_attendees = set(event_attendees) if isinstance(event_attendees, list) else set()
                                if event_attendees_details and isinstance(event_attendees_details, list):
                                    all_attendees.update([a.get("email", "") for a in event_attendees_details if isinstance(a, dict) and a.get("email")])
                                all_attendees.add(matched_participant)  # Owner is always an attendee
                                matching = set(participant_ids).intersection(all_attendees)
                                print(f"  - participant_ids matching: {list(matching)} / {len(participant_ids)} required", file=sys.stderr, flush=True)
                        except Exception as e:
                            import traceback
                            print(f"[orchestrate_scheduling] Error logging event details: {e}", file=sys.stderr, flush=True)
                            traceback.print_exc(file=sys.stderr)
                        
                        # If we identified the event but don't have participant_ids, extract participants from event
                        # and fetch their calendars (will happen after event extraction)
                        if not participant_ids:
                            # Extract participants from the matched event for later calendar fetching
                            event_attendees = matched_event.get("attendees_list", [])
                            event_attendees_details = matched_event.get("attendees_details", [])
                            
                            # Build participant list from event
                            if event_attendees_details:
                                participant_ids = [attendee.get("email") for attendee in event_attendees_details if isinstance(attendee, dict) and attendee.get("email")]
                            elif event_attendees:
                                participant_ids = [email for email in event_attendees if isinstance(email, str)]
                            
                            # Add the matched participant (owner) if not already in list
                            if matched_participant and matched_participant not in (participant_ids or []):
                                if not participant_ids:
                                    participant_ids = []
                                participant_ids.insert(0, matched_participant)
                            
                            try:
                                print(f"[orchestrate_scheduling] Derived participant_ids from identified event: {participant_ids}", file=sys.stderr, flush=True)
                            except:
                                pass
                    else:
                        # No match found - return helpful error
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=f"Could not identify the meeting to reschedule from your request. Please provide more specific details like: participant names, date, time, or meeting title. Alternatively, you can provide the event ID directly.",
                            proposals=[],
                        error_message="Event not identified from natural language",
                        debug=debug_info
                    ).model_dump()
                except Exception as e:
                    error_traceback = traceback.format_exc()
                    # Log detailed error for debugging
                    try:
                        print(f"[orchestrate_scheduling] Event identification error details:", file=sys.stderr, flush=True)
                        print(f"  - event_identifiers type: {type(scheduling_problem.event_identifiers)}", file=sys.stderr, flush=True)
                        print(f"  - event_identifiers value: {scheduling_problem.event_identifiers}", file=sys.stderr, flush=True)
                        print(f"  - events_by_participant type: {type(events_by_participant)}", file=sys.stderr, flush=True)
                        print(f"  - context_json type: {type(context_json)}", file=sys.stderr, flush=True)
                        print(f"  - Error: {str(e)}", file=sys.stderr, flush=True)
                        print(f"  - Traceback: {error_traceback}", file=sys.stderr, flush=True)
                    except:
                        pass
                    # For rescheduling, if event identification fails, return error
                    # Don't silently continue - user asked to reschedule a specific meeting
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation=f"Error identifying the meeting to reschedule: {str(e)}. Please provide more specific details like: participant names, date, time, or meeting title. Alternatively, you can provide the event ID directly.",
                        proposals=[],
                        error_message=f"Event identification failed: {str(e)}",
                        debug=debug_info
                    ).model_dump()
        
        # 4. Extract event details if event was fetched (for rescheduling)
        extracted_event_details = None
        external_participants_for_display = []  # Store external participants for rescheduling display
        if fetched_event_by_id:
            try:
                # Import event extractor
                try:
                    from .event_extractor import extract_event_details_for_rescheduling
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.event_extractor import extract_event_details_for_rescheduling
                    except ImportError:
                        from event_extractor import extract_event_details_for_rescheduling
                
                # Determine event owner (use event_participant_id if provided, otherwise use first participant from context)
                event_owner = event_participant_id
                if not event_owner and context_json:
                    context_dict = context_json if isinstance(context_json, dict) else json.loads(context_json)
                    if "participants" in context_dict and context_dict["participants"]:
                        event_owner = context_dict["participants"][0].get("id") or context_dict["participants"][0].get("email", "")
                
                if not event_owner:
                    # Fallback: try to get from matched_participant if available from natural language identification
                    # (This is a bit of a hack - we'd need to store matched_participant in a variable)
                    # For now, use first participant from scheduling_problem if available
                    if scheduling_problem.participants:
                        event_owner = scheduling_problem.participants[0]
                
                if event_owner:
                    extracted_event_details = extract_event_details_for_rescheduling(
                        event=fetched_event_by_id,
                        event_owner_id=event_owner
                    )
                    # Log successful extraction
                    try:
                        print(f"[orchestrate_scheduling] Extracted event details: {extracted_event_details.get('title', '')} ({extracted_event_details.get('duration_minutes', 0)} min) with {len(extracted_event_details.get('participants', []))} participants", file=sys.stderr, flush=True)
                    except:
                        pass
                else:
                    # Can't extract without owner - return error for rescheduling
                    return ResponseEnvelope(
                        status="bad_input",
                        explanation="Cannot reschedule: event owner/participant ID is required to extract event details. Please provide event_participant_id when using event_id, or ensure participant information is available in context_json.",
                        proposals=[],
                        error_message="Event owner not available for extraction",
                        debug=debug_info
                    ).model_dump()
                        
            except ValueError as e:
                # Event extraction failed (e.g., all-day event, missing fields)
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Cannot reschedule this event: {str(e)}. The event may be an all-day event or missing required information.",
                    proposals=[],
                    error_message=f"Event extraction failed: {str(e)}",
                    debug=debug_info
                ).model_dump()
            except Exception as e:
                error_traceback = traceback.format_exc()
                # For rescheduling, if event extraction fails, return error
                # Don't silently continue - we need the event details to reschedule
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Error extracting event details: {str(e)}. Cannot proceed with rescheduling without event details.",
                    proposals=[],
                    error_message=f"Event extraction failed: {str(e)}",
                    debug=debug_info
                    ).model_dump()
        
        # Filter events to narrower timeframe if we used expanded range for identification
        if used_expanded_range_for_identification and context_json and "timeframe" in context_json:
            try:
                import pytz
                from datetime import datetime
                tz = pytz.timezone(context_json["timeframe"].get("tz", "America/New_York"))
                # Parse filter start date (handles both date-only and ISO 8601 datetime formats)
                try:
                    filter_start_dt = datetime.fromisoformat(context_json["timeframe"]["from"].replace('Z', '+00:00'))
                    if filter_start_dt.tzinfo:
                        filter_start_dt = filter_start_dt.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    filter_start_dt = datetime.strptime(context_json["timeframe"]["from"], "%Y-%m-%d")
                filter_start_dt = filter_start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                filter_start_dt = tz.localize(filter_start_dt)
                # Parse filter end date (handles both date-only and ISO 8601 datetime formats)
                try:
                    filter_end_dt = datetime.fromisoformat(context_json["timeframe"]["to"].replace('Z', '+00:00'))
                    if filter_end_dt.tzinfo:
                        filter_end_dt = filter_end_dt.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    filter_end_dt = datetime.strptime(context_json["timeframe"]["to"], "%Y-%m-%d")
                filter_end_dt = filter_end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
                filter_end_dt = tz.localize(filter_end_dt)
                
                # Filter events for each participant to only include those within the narrower timeframe
                total_before = sum(len(events) for events in events_by_participant.values())
                filtered_events_by_participant = {}
                for participant_id, events in events_by_participant.items():
                    filtered_events = []
                    for event in events:
                        # Extract event start time
                        event_start = event.get("start", {})
                        if isinstance(event_start, str):
                            try:
                                event_start_dt = datetime.fromisoformat(event_start.replace("Z", "+00:00"))
                            except:
                                continue
                        elif isinstance(event_start, dict):
                            event_start_str = event_start.get("dateTime") or event_start.get("date", "")
                            if not event_start_str:
                                continue
                            try:
                                event_start_dt = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
                            except:
                                continue
                        else:
                            continue
                        
                        # Convert to timezone-aware if needed
                        if event_start_dt.tzinfo is None:
                            event_start_dt = tz.localize(event_start_dt)
                        else:
                            event_start_dt = event_start_dt.astimezone(tz)
                        
                        # Check if event is within the narrower timeframe
                        if filter_start_dt <= event_start_dt <= filter_end_dt:
                            filtered_events.append(event)
                    
                    filtered_events_by_participant[participant_id] = filtered_events
                
                # Ensure the identified event is included in filtered events (even if outside narrower timeframe)
                # This is critical - we need the event to reschedule even if it's outside the search window
                if fetched_event_by_id:
                    event_id = fetched_event_by_id.get("id", "")
                    # Find which participant's calendar contains this event
                    for participant_id, events in events_by_participant.items():
                        # Check if event is already in filtered events
                        event_already_included = any(
                            evt.get("id", "") == event_id for evt in filtered_events_by_participant.get(participant_id, [])
                        )
                        if not event_already_included:
                            # Check if event is in original events for this participant
                            event_in_original = any(
                                evt.get("id", "") == event_id for evt in events
                            )
                            if event_in_original:
                                # Add the identified event to filtered events (even if outside timeframe)
                                if participant_id not in filtered_events_by_participant:
                                    filtered_events_by_participant[participant_id] = []
                                # Find the event in original events
                                for evt in events:
                                    if evt.get("id", "") == event_id:
                                        filtered_events_by_participant[participant_id].append(evt)
                                        try:
                                            print(f"[orchestrate_scheduling] Added identified event '{fetched_event_by_id.get('summary', '')}' to filtered events (outside narrower timeframe but needed for rescheduling)", file=sys.stderr, flush=True)
                                        except:
                                            pass
                                        break
                                break
                
                # Replace events_by_participant with filtered events
                events_by_participant = filtered_events_by_participant
                
                # Now check the limit on filtered events
                for participant_id, events in events_by_participant.items():
                    if len(events) > MAX_EVENTS_PER_PARTICIPANT:
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=f"Participant {participant_id} has {len(events)} events in the specified timeframe, exceeding maximum ({MAX_EVENTS_PER_PARTICIPANT}).",
                            proposals=[],
                            error_message=f"Too many events for {participant_id}: {len(events)}",
                            debug=debug_info
                        ).model_dump()
                
                try:
                    total_after = sum(len(events) for events in filtered_events_by_participant.values())
                    print(f"[orchestrate_scheduling] Filtered events from expanded range: {total_before} -> {total_after} events (timeframe: {context_json['timeframe']['from']} to {context_json['timeframe']['to']})", file=sys.stderr, flush=True)
                except:
                    pass
            except Exception as e:
                # If filtering fails, log but continue (better to have too many events than fail completely)
                try:
                    print(f"[orchestrate_scheduling] Warning: Failed to filter events to narrower timeframe: {e}", file=sys.stderr, flush=True)
                except:
                    pass
        
        # 5. Merge event details with utterance constraints if rescheduling
        # For rescheduling, we MUST have successfully identified and extracted the event
        if scheduling_problem.is_rescheduling:
            # If event identification/extraction failed, we should have already returned an error
            # But double-check here to be safe
            if not extracted_event_details:
                return ResponseEnvelope(
                    status="bad_input",
                    explanation="Cannot reschedule: the meeting to reschedule could not be identified or extracted. Please provide more specific details like: participant names, date, time, or meeting title. Alternatively, you can provide the event ID directly.",
                    proposals=[],
                    error_message="Event not identified or extracted for rescheduling",
                    debug=debug_info
                ).model_dump()
            try:
                # Import merge function
                try:
                    from .event_extractor import merge_event_details_with_utterance
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.event_extractor import merge_event_details_with_utterance
                    except ImportError:
                        from event_extractor import merge_event_details_with_utterance
                
                # Convert context_json to dict if needed
                context_dict = context_json
                if isinstance(context_json, str):
                    context_dict = json.loads(context_json)
                
                # If event was identified and we don't have calendars for all participants,
                # fetch calendars for all participants from the event
                event_participants = extracted_event_details.get("participants", [])
                if event_participants and context_json and "timeframe" in context_json:
                    # Check if we need to fetch calendars for missing participants
                    missing_participants = []
                    if participant_ids:
                        # Check which participants we don't have calendars for
                        for pid in event_participants:
                            if pid not in (events_by_participant or {}):
                                missing_participants.append(pid)
                    else:
                        # No participant_ids provided - use event participants
                        participant_ids = event_participants
                        missing_participants = event_participants
                    
                    # Filter to only internal participants for calendar fetching
                    # External participants' calendars are not accessible, so we only fetch internal ones
                    internal_domains = ["@concord.org"]
                    missing_participants = [
                        p for p in missing_participants 
                        if p and "@" in p and any(p.lower().endswith(domain.lower()) for domain in internal_domains)
                    ]
                    
                    # Fetch calendars for missing participants (only internal ones)
                    if missing_participants:
                        try:
                            import os
                            import asyncio
                            try:
                                from .mcp_client import MCPCalendarClient, MCPError
                            except (ImportError, ValueError):
                                try:
                                    from scheduling_orchestrator.mcp_client import MCPCalendarClient, MCPError
                                except ImportError:
                                    from mcp_client import MCPCalendarClient, MCPError
                            
                            mcp_url = os.getenv(
                                "MCP_CALENDAR_SERVER_URL",
                                "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
                            )
                            
                            mcp_client = MCPCalendarClient(
                                base_url=mcp_url,
                                timeout=int(os.getenv("MCP_CALENDAR_TIMEOUT", "30")),
                                max_retries=int(os.getenv("MCP_CALENDAR_RETRY_ATTEMPTS", "3"))
                            )
                            
                            # Reuse the fetch_calendar_events function logic
                            async def fetch_all_participant_calendars():
                                await mcp_client.initialize()
                                import pytz
                                from datetime import datetime
                                
                                tz = pytz.timezone(context_json["timeframe"].get("tz", "America/New_York"))
                                
                                # Parse start date (handles both date-only and ISO 8601 datetime formats)
                                try:
                                    start_dt = datetime.fromisoformat(context_json["timeframe"]["from"].replace('Z', '+00:00'))
                                    if start_dt.tzinfo:
                                        start_dt = start_dt.replace(tzinfo=None)
                                except (ValueError, AttributeError):
                                    start_dt = datetime.strptime(context_json["timeframe"]["from"], "%Y-%m-%d")
                                start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                                start_dt = tz.localize(start_dt)
                                after_date_iso = start_dt.strftime("%Y-%m-%dT00:00:00Z")
                                
                                # Parse end date (handles both date-only and ISO 8601 datetime formats)
                                try:
                                    end_dt = datetime.fromisoformat(context_json["timeframe"]["to"].replace('Z', '+00:00'))
                                    if end_dt.tzinfo:
                                        end_dt = end_dt.replace(tzinfo=None)
                                except (ValueError, AttributeError):
                                    end_dt = datetime.strptime(context_json["timeframe"]["to"], "%Y-%m-%d")
                                end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
                                end_dt = tz.localize(end_dt)
                                before_date_iso = end_dt.strftime("%Y-%m-%dT23:59:59Z")
                                
                                all_events = {}
                                for pid in participant_ids:
                                    try:
                                        result = await mcp_client.get_core_event_data(
                                            calendar_id=pid,
                                            before=before_date_iso,
                                            after=after_date_iso
                                        )
                                        
                                        if isinstance(result, list):
                                            events = result
                                        elif isinstance(result, dict):
                                            events = result.get("events", result.get("items", result.get("data", [])))
                                        else:
                                            events = []
                                        
                                        normalized_events = []
                                        for evt in events:
                                            if evt.get("start", {}).get("date"):
                                                continue
                                            start_dt = evt.get("start", {}).get("dateTime")
                                            end_dt = evt.get("end", {}).get("dateTime")
                                            if not start_dt or not end_dt:
                                                continue
                                            
                                            attendees_list = evt.get("attendees_list", [])
                                            if isinstance(attendees_list, str):
                                                try:
                                                    import ast
                                                    attendees_list = ast.literal_eval(attendees_list)
                                                except:
                                                    attendees_list = []
                                            elif not isinstance(attendees_list, list):
                                                attendees_list = []
                                            
                                            attendees_details = evt.get("attendees_details", [])
                                            if not isinstance(attendees_details, list):
                                                attendees_details = []
                                            if not attendees_details and attendees_list:
                                                attendees_details = [
                                                    {"email": email, "name": email.split("@")[0]}
                                                    for email in attendees_list
                                                    if isinstance(email, str)
                                                ]
                                            
                                            # Preserve both 'summary' (raw MCP) and 'title' (normalized) fields
                                            evt_summary = evt.get("summary", "")
                                            normalized_events.append({
                                                "id": evt.get("id", ""),
                                                "title": evt_summary,  # Use summary as title for normalized format
                                                "summary": evt_summary,  # Preserve original summary field
                                                "start": start_dt,
                                                "end": end_dt,
                                                "locked": evt.get("locked", False),
                                                "protected": evt.get("protected", False),
                                                "flexible": evt.get("flexible", True),
                                                "transparent": evt.get("transparent", False),  # True = "show as free"
                                                "description": evt.get("description", ""),  # For description-based protection detection
                                                "attendees": attendees_list,
                                                "attendees_details": attendees_details
                                            })

                                        all_events[pid] = normalized_events
                                    except Exception as e:
                                        import logging
                                        logger = logging.getLogger(__name__)
                                        logger.error(f"Failed to fetch events for {pid}: {e}")
                                        all_events[pid] = []

                                return all_events

                            # Fetch calendars only for missing participants
                            async def fetch_missing_calendars():
                                await mcp_client.initialize()
                                import pytz
                                from datetime import datetime
                                
                                tz = pytz.timezone(context_json["timeframe"].get("tz", "America/New_York"))
                                
                                # Parse start date (handles both date-only and ISO 8601 datetime formats)
                                try:
                                    start_dt = datetime.fromisoformat(context_json["timeframe"]["from"].replace('Z', '+00:00'))
                                    if start_dt.tzinfo:
                                        start_dt = start_dt.replace(tzinfo=None)
                                except (ValueError, AttributeError):
                                    start_dt = datetime.strptime(context_json["timeframe"]["from"], "%Y-%m-%d")
                                start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                                start_dt = tz.localize(start_dt)
                                after_date_iso = start_dt.strftime("%Y-%m-%dT00:00:00Z")
                                
                                # Parse end date (handles both date-only and ISO 8601 datetime formats)
                                try:
                                    end_dt = datetime.fromisoformat(context_json["timeframe"]["to"].replace('Z', '+00:00'))
                                    if end_dt.tzinfo:
                                        end_dt = end_dt.replace(tzinfo=None)
                                except (ValueError, AttributeError):
                                    end_dt = datetime.strptime(context_json["timeframe"]["to"], "%Y-%m-%d")
                                end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
                                end_dt = tz.localize(end_dt)
                                before_date_iso = end_dt.strftime("%Y-%m-%dT23:59:59Z")
                                
                                all_events = {}
                                for pid in missing_participants:
                                    try:
                                        result = await mcp_client.get_core_event_data(
                                            calendar_id=pid,
                                            before=before_date_iso,
                                            after=after_date_iso
                                        )
                                        
                                        if isinstance(result, list):
                                            events = result
                                        elif isinstance(result, dict):
                                            events = result.get("events", result.get("items", result.get("data", [])))
                                        else:
                                            events = []
                                        
                                        normalized_events = []
                                        for evt in events:
                                            if evt.get("start", {}).get("date"):
                                                continue
                                            start_dt = evt.get("start", {}).get("dateTime")
                                            end_dt = evt.get("end", {}).get("dateTime")
                                            if not start_dt or not end_dt:
                                                continue
                                            
                                            attendees_list = evt.get("attendees_list", [])
                                            if isinstance(attendees_list, str):
                                                try:
                                                    import ast
                                                    attendees_list = ast.literal_eval(attendees_list)
                                                except:
                                                    attendees_list = []
                                            elif not isinstance(attendees_list, list):
                                                attendees_list = []
                                            
                                            attendees_details = evt.get("attendees_details", [])
                                            if not isinstance(attendees_details, list):
                                                attendees_details = []
                                            if not attendees_details and attendees_list:
                                                attendees_details = [
                                                    {"email": email, "name": email.split("@")[0]}
                                                    for email in attendees_list
                                                    if isinstance(email, str)
                                                ]
                                            
                                            # Preserve both 'summary' (raw MCP) and 'title' (normalized) fields
                                            evt_summary = evt.get("summary", "")
                                            normalized_events.append({
                                                "id": evt.get("id", ""),
                                                "title": evt_summary,  # Use summary as title for normalized format
                                                "summary": evt_summary,  # Preserve original summary field
                                                "start": start_dt,
                                                "end": end_dt,
                                                "locked": evt.get("locked", False),
                                                "protected": evt.get("protected", False),
                                                "flexible": evt.get("flexible", True),
                                                "transparent": evt.get("transparent", False),  # True = "show as free"
                                                "description": evt.get("description", ""),  # For description-based protection detection
                                                "attendees": attendees_list,
                                                "attendees_details": attendees_details
                                            })

                                        all_events[pid] = normalized_events
                                    except Exception as e:
                                        import logging
                                        logger = logging.getLogger(__name__)
                                        logger.error(f"Failed to fetch events for {pid}: {e}")
                                        all_events[pid] = []

                                return all_events

                            # Fetch calendars for missing participants
                            additional_events = asyncio.run(fetch_missing_calendars())
                            
                            # Merge with existing events_by_participant
                            if events_by_participant:
                                for pid, events in additional_events.items():
                                    if pid in events_by_participant:
                                        # Merge, avoiding duplicates
                                        existing_ids = {evt.get("id") for evt in events_by_participant[pid]}
                                        for evt in events:
                                            if evt.get("id") not in existing_ids:
                                                events_by_participant[pid].append(evt)
                                    else:
                                        events_by_participant[pid] = events
                            else:
                                events_by_participant = additional_events
                            
                            try:
                                print(f"[orchestrate_scheduling] Fetched calendars for {len(missing_participants)} missing participants derived from event", file=sys.stderr, flush=True)
                            except:
                                pass
                        except Exception as e:
                            # If fetching fails, log but continue - we at least have the event details
                            try:
                                print(f"[orchestrate_scheduling] Warning: Could not fetch all participant calendars: {str(e)}", file=sys.stderr, flush=True)
                            except:
                                pass
                
                # If event was identified, merge event details with utterance constraints
                # If event identification failed, still expand time window (use None for extracted_event_details)
                print(f"[orchestrate_scheduling] About to call merge_event_details_with_utterance", file=sys.stderr, flush=True)
                print(f"[orchestrate_scheduling] context_dict type: {type(context_dict)}, value: {context_dict}", file=sys.stderr, flush=True)
                print(f"[orchestrate_scheduling] scheduling_problem.time_window_start before merge: {scheduling_problem.time_window_start}", file=sys.stderr, flush=True)
                print(f"[orchestrate_scheduling] scheduling_problem.time_window_end before merge: {scheduling_problem.time_window_end}", file=sys.stderr, flush=True)
                scheduling_problem = merge_event_details_with_utterance(
                    extracted_event_details=extracted_event_details,  # None if identification failed
                    scheduling_problem=scheduling_problem,
                    context_json=context_dict,
                    participant_ids=participant_ids,  # Pass participant_ids for fallback
                    utterance=utterance  # Pass utterance to check for explicit changes
                )
                print(f"[orchestrate_scheduling] After merge_event_details_with_utterance call", file=sys.stderr, flush=True)
                
                # Log successful merge/expansion
                try:
                    if extracted_event_details:
                        print(f"[orchestrate_scheduling] Merged event details: {len(scheduling_problem.participants)} participants, {scheduling_problem.duration_minutes} min, title: '{scheduling_problem.title}'", file=sys.stderr, flush=True)
                        print(f"[orchestrate_scheduling] Time window after merge: start={scheduling_problem.time_window_start}, end={scheduling_problem.time_window_end}", file=sys.stderr, flush=True)
                    else:
                        print(f"[orchestrate_scheduling] Expanded time window for rescheduling (event identification failed): {scheduling_problem.time_window_start} to {scheduling_problem.time_window_end}", file=sys.stderr, flush=True)
                except:
                    pass
                
                # 5a. Handle external participants for rescheduling
                # If the original event has external participants, filter to only internal participants for scheduling
                # but preserve external participant info for display purposes
                external_participants_for_display = []
                if extracted_event_details and scheduling_problem.is_rescheduling:
                    original_participants = extracted_event_details.get("participants", [])
                    if original_participants:
                        # Separate internal and external participants (inline to avoid scoping issues)
                        internal_domains = ["@concord.org"]
                        internal_participants = []
                        external_participants = []
                        for p in original_participants:
                            if p and "@" in p:
                                participant_lower = p.lower()
                                is_internal = any(participant_lower.endswith(domain.lower()) for domain in internal_domains)
                                if is_internal:
                                    internal_participants.append(p)
                                else:
                                    external_participants.append(p)
                            else:
                                # If no @, assume internal (shouldn't happen but be safe)
                                internal_participants.append(p)
                        
                        if external_participants:
                            # Store external participants for display
                            external_participants_for_display = external_participants
                            
                            # Filter scheduling_problem.participants to only internal participants
                            # This allows us to find slots when internal staff are available
                            # even though external participants' calendars aren't accessible
                            original_participant_list = scheduling_problem.participants.copy() if scheduling_problem.participants else []
                            internal_only_participants = []
                            for p in original_participant_list:
                                if p and "@" in p:
                                    participant_lower = p.lower()
                                    is_internal = any(participant_lower.endswith(domain.lower()) for domain in internal_domains)
                                    if is_internal:
                                        internal_only_participants.append(p)
                            
                            # If we have internal participants, use them; otherwise keep original list
                            if internal_only_participants:
                                scheduling_problem.participants = internal_only_participants
                                try:
                                    print(f"[orchestrate_scheduling] External participants detected: {external_participants}. Filtering to internal participants only: {internal_only_participants}", file=sys.stderr, flush=True)
                                except:
                                    pass
                            else:
                                # No internal participants found - this shouldn't happen for rescheduling
                                # but log a warning and continue with original participants
                                try:
                                    print(f"[orchestrate_scheduling] WARNING: No internal participants found in {original_participant_list}. External participants: {external_participants}", file=sys.stderr, flush=True)
                                except:
                                    pass
                    
            except ValueError as e:
                # Merge failed (e.g., missing participants, invalid duration)
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Cannot merge event details with request: {str(e)}",
                    proposals=[],
                    error_message=f"Event merge failed: {str(e)}",
                    debug=debug_info
                ).model_dump()
            except Exception as e:
                error_traceback = traceback.format_exc()
                # Log error but continue with original scheduling_problem
                try:
                    print(f"[orchestrate_scheduling] Error merging event details: {str(e)}", file=sys.stderr, flush=True)
                except:
                    pass
        
        # 6. Add original event to events_by_participant if rescheduling
        # This ensures the original event is included in normalized data and can be moved/overridden
        if extracted_event_details and scheduling_problem.is_rescheduling:
            try:
                original_event_id = extracted_event_details.get("event_id")
                original_participants = extracted_event_details.get("participants", [])
                original_start = extracted_event_details.get("current_start_utc")
                original_end = extracted_event_details.get("current_end_utc")
                original_title = extracted_event_details.get("title", "Meeting")
                original_location = extracted_event_details.get("location")
                original_internal_only = extracted_event_details.get("internal_only", True)
                
                # Format original event to match expected structure
                # Normalizer expects: id, title (or summary), start, end, locked, protected, flexible, attendees
                # internal_only is optional and defaults to True
                original_event = {
                    "id": original_event_id,
                    "title": original_title,
                    "summary": original_title,  # Some code paths use summary
                    "start": original_start,  # Already in ISO 8601 UTC format
                    "end": original_end,  # Already in ISO 8601 UTC format
                    "locked": False,  # Can be moved
                    "protected": False,  # Can be overridden
                    "flexible": True,  # Can be moved
                    "internal_only": original_internal_only,
                    "attendees": original_participants[1:] if len(original_participants) > 1 else [],  # Exclude owner
                    "attendees_list": original_participants[1:] if len(original_participants) > 1 else []  # MCP format
                }
                
                # Add location if available
                if original_location:
                    original_event["location"] = original_location
                
                # Add original event to each participant's calendar
                for participant_id in original_participants:
                    # Ensure participant has an entry in events_by_participant
                    if participant_id not in events_by_participant:
                        events_by_participant[participant_id] = []
                    
                    # Check if event already exists (avoid duplicates)
                    event_exists = any(
                        evt.get("id") == original_event_id 
                        for evt in events_by_participant[participant_id]
                    )
                    
                    if not event_exists:
                        events_by_participant[participant_id].append(original_event)
                        # Log addition
                        try:
                            print(f"[orchestrate_scheduling] Added original event '{original_title}' (ID: {original_event_id}) to participant {participant_id}'s calendar for rescheduling", file=sys.stderr, flush=True)
                        except:
                            pass
                            
            except Exception as e:
                # Log error but continue - event might already be in calendar
                try:
                    print(f"[orchestrate_scheduling] Error adding original event to events_by_participant: {str(e)}", file=sys.stderr, flush=True)
                except:
                    pass
        
        # CRITICAL: Map scheduling_problem.participants to actual keys in events_by_participant
        # This ensures the solver uses the correct participant IDs that match busy_slots keys
        # Build a mapping from participant IDs/emails to the actual keys in events_by_participant
        participant_id_mapping = {}
        events_by_participant_keys = set(events_by_participant.keys())
        
        # First, try direct matches
        for p_id in scheduling_problem.participants:
            if p_id in events_by_participant_keys:
                participant_id_mapping[p_id] = p_id
            else:
                # Try case-insensitive match
                p_id_lower = p_id.lower()
                for key in events_by_participant_keys:
                    if key.lower() == p_id_lower:
                        participant_id_mapping[p_id] = key
                        break
                # If still no match, try to find by email in context
                if p_id not in participant_id_mapping and context_json:
                    context_dict = context_json if isinstance(context_json, dict) else json.loads(context_json)
                    if "participants" in context_dict:
                        for p in context_dict["participants"]:
                            p_context_id = p.get("id", "")
                            p_context_email = p.get("email", "")
                            if p_id == p_context_id or p_id == p_context_email:
                                # Find matching key in events_by_participant
                                for key in events_by_participant_keys:
                                    if key.lower() == p_context_email.lower() or key.lower() == p_context_id.lower():
                                        participant_id_mapping[p_id] = key
                                        break
                                if p_id in participant_id_mapping:
                                    break
        
        # CRITICAL: If scheduling_problem.participants is empty, use participant_ids parameter as fallback
        # This handles cases where DSPy doesn't extract participants from the utterance
        if not scheduling_problem.participants and participant_ids:
            scheduling_problem.participants = participant_ids
            print(f"[orchestrate_scheduling] Using participant_ids parameter as fallback (empty participants): {participant_ids}", file=sys.stderr, flush=True)
        
        # Map scheduling_problem.participants to actual keys
        mapped_participants = [participant_id_mapping.get(p_id, p_id) for p_id in scheduling_problem.participants]
        
        # Check if any mapped participants are missing from events_by_participant
        missing_participants = [p for p in mapped_participants if p not in events_by_participant]
        
        # CRITICAL: If participants are missing AND participant_ids is provided, use participant_ids as fallback
        # This handles cases where DSPy extracts invalid/example.com emails instead of real participant IDs
        if missing_participants and participant_ids:
            # Check if participant_ids would work better
            mapped_participant_ids = [participant_id_mapping.get(p_id, p_id) for p_id in participant_ids]
            missing_from_participant_ids = [p for p in mapped_participant_ids if p not in events_by_participant]
            
            # If participant_ids has fewer or no missing participants, use it instead
            if len(missing_from_participant_ids) < len(missing_participants):
                scheduling_problem.participants = participant_ids
                mapped_participants = mapped_participant_ids
                missing_participants = missing_from_participant_ids
                print(f"[orchestrate_scheduling] Using participant_ids parameter as fallback (invalid extracted participants): {participant_ids}", file=sys.stderr, flush=True)
        
        # Validate that all participants have events (even if empty)
        if missing_participants:
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Missing events for participants: {', '.join(missing_participants)}. Please call Get_Events for all participants mentioned in the request.",
                proposals=[],
                error_message=f"Missing events for participants: {missing_participants}",
                debug=debug_info
            ).model_dump()
        
        # Update scheduling_problem.participants to use mapped IDs
        # Create a new SchedulingProblem with mapped participants
        # We'll need to update all references to use mapped_participants
        original_participants = scheduling_problem.participants
        scheduling_problem.participants = mapped_participants
        
        # Debug: Log the mapping
        print(f"[DEBUG] Participant ID mapping - original: {original_participants}, mapped: {mapped_participants}", file=sys.stderr, flush=True)
        print(f"[DEBUG] events_by_participant keys: {list(events_by_participant.keys())[:5]}", file=sys.stderr, flush=True)
        
        # 3. Normalize events to 15-minute grid
        try:
            import copy as copy_module  # For deepcopy

            normalized_data = normalize_events(events_by_participant, context_json or {})
            debug_info.normalization_time_ms = int((time.time() - start_time) * 1000) - debug_info.extraction_time_ms

            # Save original normalized_data before any horizon reduction
            # ASP fallback needs the original data, not the reduced version used by Python solver
            # CRITICAL: Use deepcopy to prevent shared references between nested dictionaries
            # (Issue #10 fix - shallow copy caused data mutation bugs)
            original_normalized_data = copy_module.deepcopy(normalized_data)
        except Exception as e:
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to normalize events: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
        slot_indexer = normalized_data["slot_indexer"]
        
        # CRITICAL: Ensure all participants in scheduling_problem have work hours defined
        # Normalization might miss participants that are in the problem but not in events/context
        # Apply default 9-5 Eastern for any missing participants
        work_hours_slots = normalized_data.get("work_hours_slots", {})
        
        for participant_id in scheduling_problem.participants:
            if participant_id not in work_hours_slots or not work_hours_slots[participant_id]:
                # Participant missing work hours - apply default 9-5 Eastern
                # Issue #16 fix: Use helper function instead of duplicating calculation
                try:
                    from .normalizer import parse_work_hours
                except (ImportError, ValueError):
                    try:
                        from normalizer import parse_work_hours
                    except ImportError:
                        from scheduling_orchestrator.normalizer import parse_work_hours

                import pytz

                default_work_hours_tz = "America/New_York"
                default_work_hours_str = "M-F 09:00-17:00"
                participant_tz = pytz.timezone(default_work_hours_tz)
                work_hours = parse_work_hours(default_work_hours_str, default_work_hours_tz)

                # Inline work hours calculation (Issue #16 helper moved inline for Letta compatibility)
                work_slots = set()
                current_date = slot_indexer.horizon_start.replace(hour=0, minute=0, second=0, microsecond=0)
                from datetime import timedelta as td_inline_1

                while current_date < slot_indexer.horizon_end:
                    current_date_local = current_date.astimezone(participant_tz)
                    day_of_week = current_date_local.weekday()

                    for day, start_hm, end_hm in work_hours:
                        if day_of_week == day:
                            start_hour = start_hm // 100
                            start_min = start_hm % 100
                            end_hour = end_hm // 100
                            end_min = end_hm % 100

                            work_start = current_date_local.replace(
                                hour=start_hour, minute=start_min, second=0, microsecond=0
                            )
                            work_end = current_date_local.replace(
                                hour=end_hour, minute=end_min, second=0, microsecond=0
                            )

                            work_start_utc = work_start.astimezone(pytz.UTC)
                            work_end_utc = work_end.astimezone(pytz.UTC)

                            work_period_slots = slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                            work_slots.update(work_period_slots)

                    current_date += td_inline_1(days=1)

                work_hours_slots[participant_id] = work_slots
                normalized_data["work_hours_slots"] = work_hours_slots
        
        # Log normalization results (before reduction)
        all_slots = slot_indexer.get_all_slots()
        num_slots = len(all_slots)
        busy_slots = normalized_data.get("busy_slots", {})
        total_busy_slots = sum(len(slots) for slots in busy_slots.values())
        
        # OPTIMIZATION: Reduce horizon if too large to avoid "too many messages" error
        # The "too many messages" error occurs when clingo grounds too many atoms,
        # even with optimized facts. For multi-move scenarios (allow_overlaps), we need
        # to be even more conservative because we generate facts for all work-hours slots.
        # Strategy:
        # 1. Try Python solver first (handles free slots + single-move efficiently)
        # 2. If Python fails, reduce horizon aggressively before ASP fallback
        # 3. For multi-move, use tighter limits (fewer candidate slots)
        
        # Check if we'll need ASP fallback (no free slots)
        duration_slots = max(1, scheduling_problem.duration_minutes // 15)
        try:
            from .fact_generator import _find_free_slots
        except (ImportError, ValueError):
            try:
                from scheduling_orchestrator.fact_generator import _find_free_slots
            except ImportError:
                from fact_generator import _find_free_slots
        
        free_slots_check = _find_free_slots(
            all_slots,
            busy_slots,
            normalized_data.get("work_hours_slots", {}),
            scheduling_problem.participants,
            duration_slots,
            normalized_data.get("min_gap_slots", 0)
        )
        
        # Determine max slots based on whether ASP fallback will be needed
        if not free_slots_check:
            # No free slots - ASP fallback will be needed, use tighter limit
            # For multi-move, we generate facts for all work-hours slots, so need smaller horizon
            MAX_SLOTS_FOR_ASP = 96  # 1 day * 96 slots/day - very conservative for multi-move
        else:
            # Free slots exist - Python solver should handle it, but prepare for ASP just in case
            MAX_SLOTS_FOR_ASP = 192  # 2 days * 96 slots/day - normal limit
        
        if num_slots > MAX_SLOTS_FOR_ASP:
            try:
                original_slots = num_slots
                
                # Inline horizon reduction to avoid import issues
                # Strategy: Prioritize time window if specified (more aggressive reduction)
                min_slot = None
                max_slot = None
                
                # First, try to use time window if specified
                if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
                    start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
                    
                    if start_dt.tzinfo is None:
                        start_dt = pytz.UTC.localize(start_dt)
                    else:
                        start_dt = start_dt.astimezone(pytz.UTC)
                    
                    if end_dt.tzinfo is None:
                        end_dt = pytz.UTC.localize(end_dt)
                    else:
                        end_dt = end_dt.astimezone(pytz.UTC)
                    
                    window_start_slot = slot_indexer.datetime_to_slot(start_dt)
                    window_end_slot = slot_indexer.datetime_to_slot(end_dt)
                    
                    if window_start_slot is not None and window_end_slot is not None:
                        # Use time window as base
                        min_slot = window_start_slot
                        max_slot = window_end_slot
                        
                        # Add small padding (4 hours = 16 slots) to allow for moves
                        padding_slots = 16
                        min_slot = max(0, min_slot - padding_slots)
                        max_slot = min(num_slots - 1, max_slot + padding_slots)
                        
                        # If still too large, limit to max_slots centered on time window
                        if max_slot - min_slot + 1 > MAX_SLOTS_FOR_ASP:
                            center = (window_start_slot + window_end_slot) // 2
                            min_slot = max(0, center - MAX_SLOTS_FOR_ASP // 2)
                            max_slot = min(num_slots - 1, min_slot + MAX_SLOTS_FOR_ASP - 1)
                
                # Fallback to busy slots strategy if time window didn't work
                if min_slot is None or max_slot is None:
                    all_busy_slots_set = set()
                    for participant_slots in busy_slots.values():
                        all_busy_slots_set.update(participant_slots)
                    
                    if not all_busy_slots_set:
                        # No busy slots - reduce to first max_slots (start of horizon)
                        min_slot = 0
                        max_slot = MAX_SLOTS_FOR_ASP - 1
                    else:
                        min_busy = min(all_busy_slots_set)
                        max_busy = max(all_busy_slots_set)
                        
                        # Add padding: 1 day before and after (96 slots = 1 day)
                        padding_slots = 96
                        min_slot = max(0, min_busy - padding_slots)
                        max_slot = min(num_slots - 1, max_busy + padding_slots)
                        
                        # Limit to max_slots
                        if max_slot - min_slot + 1 > MAX_SLOTS_FOR_ASP:
                            # Center the window around busy slots
                            center = (min_busy + max_busy) // 2
                            min_slot = max(0, center - MAX_SLOTS_FOR_ASP // 2)
                            max_slot = min(num_slots - 1, min_slot + MAX_SLOTS_FOR_ASP - 1)
                
                # Create new slot indexer with reduced horizon
                original_start = slot_indexer.slot_to_datetime(min_slot)
                original_end = slot_indexer.slot_to_datetime(max_slot + 1)  # +1 to include the last slot
                
                if original_start and original_end:
                    # Import SlotIndexer using the same lazy import pattern as other modules
                    # SlotIndexer should already be imported via normalizer, but we need it here too
                    try:
                        try:
                            from .slot_indexer import SlotIndexer
                        except (ImportError, ValueError):
                            # Fallback to absolute imports
                            import sys
                            import os
                            current_file = os.path.abspath(__file__)
                            if current_file.endswith('.pyc'):
                                current_file = current_file[:-1]
                            orchestrator_dir = os.path.dirname(current_file)
                            if orchestrator_dir not in sys.path:
                                sys.path.insert(0, orchestrator_dir)
                            try:
                                from slot_indexer import SlotIndexer
                            except ImportError:
                                # Last resort: try direct import
                                from scheduling_orchestrator.slot_indexer import SlotIndexer
                        
                        # Create new slot indexer
                        new_slot_indexer = SlotIndexer(original_start, original_end)
                        
                        # Re-normalize busy slots to new indexer (shift slot indices)
                        new_busy_slots = {}
                        for participant_id, slots in busy_slots.items():
                            new_slots = set()
                            for slot in slots:
                                if min_slot <= slot <= max_slot:
                                    # Shift to new indexer (slot - min_slot)
                                    new_slots.add(slot - min_slot)
                            new_busy_slots[participant_id] = new_slots
                        
                        # Re-normalize work hours slots
                        # IMPORTANT: Work hours must be RECALCULATED for the new horizon,
                        # not just shifted, because the new horizon starts at a different time.
                        # Shifting would preserve slot indices but not the actual time-of-day work hours.
                        work_hours_slots = normalized_data.get("work_hours_slots", {})
                        new_work_hours_slots = {}
                        
                        # Recalculate work hours for the new horizon using the context
                        # Parse context_json if it's a string
                        context_dict = context_json
                        if isinstance(context_json, str):
                            try:
                                context_dict = json.loads(context_json)
                            except:
                                context_dict = {}
                        
                        if context_dict and "participants" in context_dict:
                            try:
                                from .normalizer import parse_work_hours
                            except (ImportError, ValueError):
                                try:
                                    from normalizer import parse_work_hours
                                except ImportError:
                                    from scheduling_orchestrator.normalizer import parse_work_hours
                            
                            import pytz
                            from datetime import timedelta
                            
                            # Default work hours are 9-5 Eastern time unless specified otherwise
                            default_work_hours_tz = "America/New_York"
                            
                            for participant in context_dict["participants"]:
                                participant_id = participant.get("id", "")
                                work_hours_str = participant.get("work_hours", "")
                                
                                # Determine timezone for work hours
                                if work_hours_str:
                                    # Participant has explicit work hours - use their timezone or timeframe timezone
                                    participant_timezone = participant.get("timezone")
                                    if not participant_timezone:
                                        participant_timezone = context_dict.get("timeframe", {}).get("tz", default_work_hours_tz)
                                    work_hours_tz = participant_timezone
                                else:
                                    # No explicit work hours - use default 9-5 Eastern
                                    work_hours_str = "M-F 09:00-17:00"
                                    work_hours_tz = default_work_hours_tz
                                
                                participant_tz = pytz.timezone(work_hours_tz)
                                
                                # Parse work hours
                                work_hours = parse_work_hours(work_hours_str, work_hours_tz)

                                # Inline work hours calculation (Letta compatibility)
                                work_slots = set()
                                current_date = original_start.replace(hour=0, minute=0, second=0, microsecond=0)
                                from datetime import timedelta as td_inline_2

                                while current_date < original_end:
                                    current_date_local = current_date.astimezone(participant_tz)
                                    day_of_week = current_date_local.weekday()

                                    for day, start_hm, end_hm in work_hours:
                                        if day_of_week == day:
                                            start_hour = start_hm // 100
                                            start_min = start_hm % 100
                                            end_hour = end_hm // 100
                                            end_min = end_hm % 100

                                            work_start = current_date_local.replace(
                                                hour=start_hour, minute=start_min, second=0, microsecond=0
                                            )
                                            work_end = current_date_local.replace(
                                                hour=end_hour, minute=end_min, second=0, microsecond=0
                                            )

                                            work_start_utc = work_start.astimezone(pytz.UTC)
                                            work_end_utc = work_end.astimezone(pytz.UTC)

                                            work_period_slots = new_slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                                            work_slots.update(work_period_slots)

                                    current_date += td_inline_2(days=1)

                                new_work_hours_slots[participant_id] = work_slots

                        # CRITICAL: Ensure ALL participants in scheduling_problem have work hours defined
                        # After horizon reduction, some participants might be missing work hours
                        # Apply default 9-5 Eastern for any missing participants
                        # Issue #16 fix: Consolidated two separate loops into one
                        default_work_hours_tz = "America/New_York"
                        default_work_hours_str = "M-F 09:00-17:00"

                        for participant_id in scheduling_problem.participants:
                            if participant_id not in new_work_hours_slots or not new_work_hours_slots[participant_id]:
                                # Participant missing work hours - apply default 9-5 Eastern
                                try:
                                    from .normalizer import parse_work_hours
                                except (ImportError, ValueError):
                                    try:
                                        from normalizer import parse_work_hours
                                    except ImportError:
                                        from scheduling_orchestrator.normalizer import parse_work_hours

                                import pytz

                                participant_tz = pytz.timezone(default_work_hours_tz)
                                work_hours = parse_work_hours(default_work_hours_str, default_work_hours_tz)

                                # Inline work hours calculation (Letta compatibility)
                                work_slots = set()
                                current_date = original_start.replace(hour=0, minute=0, second=0, microsecond=0)
                                from datetime import timedelta as td_inline_3

                                while current_date < original_end:
                                    current_date_local = current_date.astimezone(participant_tz)
                                    day_of_week = current_date_local.weekday()

                                    for day, start_hm, end_hm in work_hours:
                                        if day_of_week == day:
                                            start_hour = start_hm // 100
                                            start_min = start_hm % 100
                                            end_hour = end_hm // 100
                                            end_min = end_hm % 100

                                            work_start = current_date_local.replace(
                                                hour=start_hour, minute=start_min, second=0, microsecond=0
                                            )
                                            work_end = current_date_local.replace(
                                                hour=end_hour, minute=end_min, second=0, microsecond=0
                                            )

                                            work_start_utc = work_start.astimezone(pytz.UTC)
                                            work_end_utc = work_end.astimezone(pytz.UTC)

                                            work_period_slots = new_slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                                            work_slots.update(work_period_slots)

                                    current_date += td_inline_3(days=1)

                                new_work_hours_slots[participant_id] = work_slots
                        
                        # Update normalized_data
                        normalized_data["slot_indexer"] = new_slot_indexer
                        normalized_data["busy_slots"] = new_busy_slots
                        normalized_data["work_hours_slots"] = new_work_hours_slots
                        
                        slot_indexer = new_slot_indexer
                        all_slots = slot_indexer.get_all_slots()
                        num_slots = len(all_slots)
                        debug_info.horizon_reduced = True
                        debug_info.original_slots = original_slots
                        debug_info.reduced_slots = num_slots
                    except Exception as e:
                        # Reduction failed - log but continue with original horizon
                        debug_info.horizon_reduced = False
                        debug_info.horizon_reduction_error = f"Failed to create reduced slot indexer: {str(e)}"
                else:
                    # Could not convert slots to datetimes - fallback
                    debug_info.horizon_reduced = False
                    debug_info.horizon_reduction_error = "Could not convert slot indices to datetimes"
            except Exception as e:
                # Reduction failed - log but continue with original horizon
                debug_info.horizon_reduced = False
                debug_info.horizon_reduction_error = f"Failed to reduce horizon: {str(e)}"
        else:
            debug_info.horizon_reduced = False
        
        debug_info.slots_considered = num_slots
        debug_info.total_busy_slots = total_busy_slots
        
        # 4. Solve using pure Python constraint solver (replaces ASP/clingo)
        # This eliminates "too many messages" errors and handles common cases efficiently
        try:
            try:
                from .python_solver import find_optimal_slot, compute_move_deltas_python, compute_objective_scores_python
            except (ImportError, ValueError):
                # Fallback to absolute imports (when run standalone or in Letta)
                import sys
                import os
                
                # Find the letta directory and add it to path
                current_file = os.path.abspath(__file__)
                if current_file.endswith('.pyc'):
                    current_file = current_file[:-1]  # Remove .pyc to get .py
                
                # Get letta directory (parent of scheduling_orchestrator)
                letta_dir = os.path.dirname(os.path.dirname(current_file))
                if letta_dir not in sys.path:
                    sys.path.insert(0, letta_dir)
                
                # Also try adding the scheduling_orchestrator directory itself
                orchestrator_dir = os.path.dirname(current_file)
                if orchestrator_dir not in sys.path:
                    sys.path.insert(0, orchestrator_dir)
                
                # Now try absolute imports
                try:
                    from scheduling_orchestrator.python_solver import find_optimal_slot, compute_move_deltas_python, compute_objective_scores_python
                except ImportError:
                    # Last resort: try direct imports from orchestrator_dir
                    from python_solver import find_optimal_slot, compute_move_deltas_python, compute_objective_scores_python
            
            # Count free slots for debugging
            try:
                try:
                    from .fact_generator import _find_free_slots
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.fact_generator import _find_free_slots
                    except ImportError:
                        from fact_generator import _find_free_slots
                
                duration_slots = max(1, scheduling_problem.duration_minutes // 15)
                # Use mapped participants for free slot calculation
                free_slots = _find_free_slots(
                    all_slots,
                    busy_slots,
                    normalized_data.get("work_hours_slots", {}),
                    scheduling_problem.participants,  # Already mapped
                    duration_slots,
                    normalized_data.get("min_gap_slots", 0)
                )
                debug_info.free_slots_found = len(free_slots)
                debug_info.free_slots_ratio = len(free_slots) / num_slots if num_slots > 0 else 0
                
                # CRITICAL: Store free slots in normalized_data so ASP can use them
                normalized_data["free_slots"] = free_slots
                original_normalized_data["free_slots"] = free_slots
                
                # Debug: Log participant ID matching
                print(f"[DEBUG] Free slot calculation - participants: {scheduling_problem.participants}", file=sys.stderr, flush=True)
                print(f"[DEBUG] Free slot calculation - busy_slots keys: {list(busy_slots.keys())[:5]}", file=sys.stderr, flush=True)
                print(f"[DEBUG] Free slot calculation - found {len(free_slots)} free slots", file=sys.stderr, flush=True)
            except Exception:
                # If we can't count free slots, that's okay - just skip this debug info
                pass
            
            # Solve with Python solver
            # CRITICAL: Use original_normalized_data for Python solver to ensure we don't lose solutions
            # due to horizon reduction. The Python solver can handle the full horizon efficiently.
            # Only use reduced horizon for ASP fallback (which has stricter memory/time constraints)
            # NOTE: Use deepcopy to prevent shared references (Issue #10 consistency fix)
            python_normalized_data = copy_module.deepcopy(original_normalized_data)
            python_slot_indexer = original_normalized_data["slot_indexer"]
            
            solve_start_time = time.time()
            # Try to find multiple solutions for diversity
            find_top_candidates = None
            try:
                # Try absolute import first (works in Letta environment)
                try:
                    from scheduling_orchestrator.python_solver import find_top_candidates
                    print(f"[SOLVER] Successfully imported find_top_candidates from scheduling_orchestrator.python_solver", file=sys.stderr, flush=True)
                except (ImportError, ValueError):
                    try:
                        from python_solver import find_top_candidates
                        print(f"[SOLVER] Successfully imported find_top_candidates from python_solver", file=sys.stderr, flush=True)
                    except ImportError:
                        try:
                            from .python_solver import find_top_candidates
                            print(f"[SOLVER] Successfully imported find_top_candidates from .python_solver", file=sys.stderr, flush=True)
                        except (ImportError, ValueError) as e:
                            print(f"[SOLVER] Failed to import find_top_candidates: {e}", file=sys.stderr, flush=True)
                            find_top_candidates = None
            except Exception as e:
                print(f"[SOLVER] Unexpected error importing find_top_candidates: {e}", file=sys.stderr, flush=True)
                find_top_candidates = None
            
            solutions = []
            python_solutions_found = False
            if find_top_candidates:
                print(f"[SOLVER] find_top_candidates is available, calling it...", file=sys.stderr, flush=True)
                # Find multiple top candidates
                # Use a high limit to get all 0-move and 1-move solutions
                # We'll filter by move count later when building proposals
                # Use original_normalized_data (full horizon) to find all solutions
                print(f"[SOLVER] Calling Python solver find_top_candidates...", file=sys.stderr, flush=True)
                solutions = find_top_candidates(
                    python_normalized_data,
                    scheduling_problem,
                    python_slot_indexer,
                    context_json,
                    max_candidates=2000  # High limit to capture all feasible solutions
                )
                print(f"[SOLVER] Python solver returned {len(solutions)} solutions", file=sys.stderr, flush=True)
                # If we found multiple solutions, use them; otherwise fall back to single solution
                if not solutions:
                    print(f"[SOLVER] No solutions from find_top_candidates, trying find_optimal_slot...", file=sys.stderr, flush=True)
                    solution = find_optimal_slot(
                        python_normalized_data,
                        scheduling_problem,
                        python_slot_indexer,
                        context_json
                    )
                    if solution:
                        solutions = [solution]
                        python_solutions_found = True
                        print(f"[SOLVER] find_optimal_slot found 1 solution", file=sys.stderr, flush=True)
                else:
                    solution = solutions[0]  # Keep for compatibility with existing code
                    python_solutions_found = True
                    print(f"[SOLVER] Python solver found {len(solutions)} solutions", file=sys.stderr, flush=True)
                    if solutions:
                        sample = solutions[0]
                        print(f"[SOLVER] Sample solution: method={sample.get('method')}, start_slot={sample.get('start_slot')}, score={sample.get('score')}", file=sys.stderr, flush=True)
            else:
                # Fallback to single solution
                solution = find_optimal_slot(
                    normalized_data,
                    scheduling_problem,
                    slot_indexer,  # Pass the current slot_indexer (might be reduced)
                    context_json
                )
                if solution:
                    solutions = [solution]
            
            solve_time_ms = int((time.time() - solve_start_time) * 1000)
            debug_info.solve_time_ms = solve_time_ms

            # ISSUE #15 FIX: Skip ASP if Python solver found free slots (no moves needed)
            # Free slots are optimal - no conflicts, no moves - ASP cannot improve on them
            python_found_free_slots = False
            if solutions:
                # Count how many free slot solutions we have
                free_slot_count = sum(1 for sol in solutions if sol.get("method") == "free_slot")
                python_found_free_slots = free_slot_count > 0
                if python_found_free_slots:
                    print(f"[SOLVER] Python solver found {free_slot_count} free slots - skipping ASP (Issue #15 optimization)", file=sys.stderr, flush=True)

            asp_solution_found = False

            try:
                    # Import ASP solver components
                    try:
                        from .clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                        from .fact_generator import generate_asp_program
                        asp_available = True
                    except (ImportError, ValueError):
                        try:
                            from scheduling_orchestrator.clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                            from scheduling_orchestrator.fact_generator import generate_asp_program
                            asp_available = True
                        except ImportError:
                            try:
                                from clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                                from fact_generator import generate_asp_program
                                asp_available = True
                            except ImportError:
                                # ASP not available - fall through to UNSAT
                                asp_available = False

                    # ISSUE #15 FIX: Skip ASP if we already have free slot solutions
                    # Free slots are optimal (0-move) - ASP cannot improve on them
                    if python_found_free_slots:
                        asp_available = False  # This skips all ASP logic below
                    else:
                        print(f"[SOLVER] No free slots from Python solver - running ASP sliding window...", file=sys.stderr, flush=True)

                    if asp_available:
                        # SLIDING WINDOW APPROACH: Explore full date range by solving overlapping windows
                        # This allows us to find solutions across the entire timeframe without
                        # overwhelming ASP with a huge horizon
                        
                        # Calculate window parameters
                        window_days = 3  # Each window covers 3 days
                        overlap_days = 1  # Windows overlap by 1 day to avoid missing solutions at boundaries
                        window_slots = window_days * 96  # 96 slots per day (24 hours * 4 slots/hour)
                        
                        # Get the full time window from scheduling problem
                        # For new meeting requests, time_window_start/end may be null, so use context_json timeframe
                        from datetime import datetime, timedelta
                        import pytz
                        
                        # Determine time window: use scheduling_problem if available, otherwise fall back to context_json
                        full_start_dt = None
                        full_end_dt = None
                        
                        if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
                            # Use explicit time window from scheduling problem
                            full_start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
                            full_end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
                            
                            if full_start_dt.tzinfo is None:
                                full_start_dt = pytz.UTC.localize(full_start_dt)
                            else:
                                full_start_dt = full_start_dt.astimezone(pytz.UTC)
                            
                            if full_end_dt.tzinfo is None:
                                full_end_dt = pytz.UTC.localize(full_end_dt)
                            else:
                                full_end_dt = full_end_dt.astimezone(pytz.UTC)
                        elif context_json and isinstance(context_json, dict) and "timeframe" in context_json:
                            # Fall back to context_json timeframe for new meeting requests
                            try:
                                timeframe = context_json["timeframe"]
                                tz_str = timeframe.get("tz", "America/New_York")
                                tz = pytz.timezone(tz_str)
                                
                                # Parse date strings and localize to the specified timezone
                                from_date_str = timeframe.get("from")
                                to_date_str = timeframe.get("to")
                                
                                if from_date_str and to_date_str:
                                    # Parse as date and set to start/end of day in the specified timezone
                                    # Parse from_date (handles both date-only and ISO 8601 datetime formats)
                                    try:
                                        from_date_dt = datetime.fromisoformat(from_date_str.replace('Z', '+00:00'))
                                        if from_date_dt.tzinfo:
                                            from_date_dt = from_date_dt.replace(tzinfo=None)
                                    except (ValueError, AttributeError):
                                        from_date_dt = datetime.strptime(from_date_str, "%Y-%m-%d")
                                    from_date = from_date_dt.date()
                                    # Parse to_date (handles both date-only and ISO 8601 datetime formats)
                                    try:
                                        to_date_dt = datetime.fromisoformat(to_date_str.replace('Z', '+00:00'))
                                        if to_date_dt.tzinfo:
                                            to_date_dt = to_date_dt.replace(tzinfo=None)
                                    except (ValueError, AttributeError):
                                        to_date_dt = datetime.strptime(to_date_str, "%Y-%m-%d")
                                    to_date = to_date_dt.date()
                                    
                                    # Set to start of day (00:00:00) and end of day (23:59:59) in the specified timezone
                                    full_start_dt = tz.localize(datetime.combine(from_date, datetime.min.time()))
                                    full_end_dt = tz.localize(datetime.combine(to_date, datetime.max.time().replace(microsecond=0)))
                                    
                                    # Convert to UTC for consistency
                                    full_start_dt = full_start_dt.astimezone(pytz.UTC)
                                    full_end_dt = full_end_dt.astimezone(pytz.UTC)
                                    
                                    try:
                                        print(f"[orchestrate_scheduling] Using context_json timeframe for ASP solver: {from_date_str} to {to_date_str} ({tz_str})", file=sys.stderr, flush=True)
                                    except:
                                        pass
                            except Exception as e:
                                try:
                                    print(f"[orchestrate_scheduling] Failed to parse context_json timeframe for ASP solver: {e}", file=sys.stderr, flush=True)
                                except:
                                    pass
                        
                        if full_start_dt and full_end_dt:
                            # Calculate number of windows needed
                            
                            # Calculate number of windows needed
                            total_days = (full_end_dt.date() - full_start_dt.date()).days + 1
                            step_days = window_days - overlap_days  # How much to advance each window
                            num_windows = max(1, (total_days - window_days) // step_days + 1)
                            
                            # Collect solutions from all windows
                            all_asp_solutions = []
                            all_asp_stats = []
                            
                            try:
                                from .horizon_reducer import reduce_horizon_to_feasible_window
                            except (ImportError, ValueError):
                                try:
                                    from scheduling_orchestrator.horizon_reducer import reduce_horizon_to_feasible_window
                                except ImportError:
                                    from horizon_reducer import reduce_horizon_to_feasible_window
                            
                            for window_idx in range(num_windows):
                                # Calculate window boundaries
                                window_start_dt = full_start_dt + timedelta(days=window_idx * step_days)
                                window_end_dt = min(window_start_dt + timedelta(days=window_days), full_end_dt)
                                
                                # Create a modified scheduling problem for this window
                                from copy import deepcopy
                                window_problem = deepcopy(scheduling_problem)
                                window_problem.time_window_start = window_start_dt.isoformat()
                                window_problem.time_window_end = window_end_dt.isoformat()
                                
                                # Reduce horizon for this window
                                asp_normalized_data = reduce_horizon_to_feasible_window(
                                    original_normalized_data,
                                    window_problem,
                                    max_slots=window_slots,
                                    prefer_time_window=True
                                )
                                
                                # Debug: Check what free slots are available before generating ASP program
                                try:
                                    import sys
                                    free_slots_before_asp = asp_normalized_data.get("free_slots", set())
                                    if isinstance(free_slots_before_asp, dict):
                                        free_slots_before_asp = set()
                                        for slots in free_slots_before_asp.values():
                                            free_slots_before_asp.update(slots)
                                    elif not isinstance(free_slots_before_asp, set):
                                        free_slots_before_asp = set(free_slots_before_asp) if free_slots_before_asp else set()
                                    print(f"[ASP_WINDOW] Window {window_idx+1}: Free slots before ASP program generation: {len(free_slots_before_asp)} slots", file=sys.stderr, flush=True)
                                    if len(free_slots_before_asp) > 0 and len(free_slots_before_asp) <= 10:
                                        print(f"  Free slot indices: {sorted(free_slots_before_asp)}", file=sys.stderr, flush=True)
                                except:
                                    pass
                                
                                # Generate ASP program for this window
                                asp_program = generate_asp_program(
                                    asp_normalized_data,
                                    window_problem,
                                    request_id="q1",
                                    include_soft_constraints=True,
                                    include_work_hours=True,
                                    include_min_gap=True,
                                    include_locked_events=True,
                                    phase=4,
                                    allow_multi_move=True
                                )
                                
                                # Solve this window
                                asp_solver = ClingoSolver(timeout=30)
                                asp_model, asp_stats, asp_result = asp_solver.solve(asp_program)
                                
                                # Debug: Log ASP solver results for each window
                                try:
                                    import sys
                                    from datetime import datetime
                                    import pytz
                                    reduced_start = asp_normalized_data["slot_indexer"].horizon_start
                                    reduced_end = asp_normalized_data["slot_indexer"].horizon_end
                                    et_start = reduced_start.astimezone(pytz.timezone('America/New_York'))
                                    et_end = reduced_end.astimezone(pytz.timezone('America/New_York'))
                                    
                                    # Count facts in program (rough estimate)
                                    fact_lines = asp_program.count('\n') - asp_program.count('%')
                                    program_size = len(asp_program)
                                    
                                    # Check if there are free slots in this window
                                    # Free slots might be stored as a set or dict
                                    free_slots_in_window = asp_normalized_data.get("free_slots", set())
                                    if isinstance(free_slots_in_window, dict):
                                        total_free_slots = sum(len(slots) for slots in free_slots_in_window.values())
                                    elif isinstance(free_slots_in_window, (set, list)):
                                        total_free_slots = len(free_slots_in_window)
                                    else:
                                        total_free_slots = 0
                                    
                                    # Check work hours slots
                                    work_hours_slots = asp_normalized_data.get("work_hours_slots", {})
                                    total_work_hours_slots = sum(len(slots) for slots in work_hours_slots.values()) if isinstance(work_hours_slots, dict) else 0
                                    
                                    # Check busy slots
                                    busy_slots = asp_normalized_data.get("busy_slots", {})
                                    total_busy_slots = sum(len(slots) for slots in busy_slots.values()) if isinstance(busy_slots, dict) else 0
                                    
                                    # Count free_slot facts in ASP program
                                    free_slot_facts = asp_program.count("free_slot(")
                                    
                                    print(f"[ASP_WINDOW] Window {window_idx+1} ({window_start_dt.strftime('%b %d')}-{window_end_dt.strftime('%b %d')}):", file=sys.stderr, flush=True)
                                    print(f"  Horizon: {et_start.strftime('%Y-%m-%d %H:%M')} to {et_end.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr, flush=True)
                                    print(f"  ASP satisfiable: {asp_result.satisfiable}, models found: {len(asp_solver.models) if hasattr(asp_solver, 'models') else 0}", file=sys.stderr, flush=True)
                                    print(f"  ASP stats: {asp_stats.get('models_found', 0)} models, solve_time={asp_stats.get('solve_time_ms', 0)}ms, ground_time={asp_stats.get('ground_time_ms', 0)}ms", file=sys.stderr, flush=True)
                                    # Count window facts
                                    window_facts = asp_program.count(f"window({window_problem.request_id if hasattr(window_problem, 'request_id') else 'q1'}, ")
                                    min_gap_facts = asp_program.count("min_gap(")
                                    locked_event_facts = asp_program.count("locked_event(")
                                    workhours_facts = asp_program.count("workhours(")
                                    
                                    print(f"  Program size: {program_size} chars, ~{fact_lines} lines, free_slot facts: {free_slot_facts}", file=sys.stderr, flush=True)
                                    print(f"  Free slots in normalized_data: {total_free_slots}, work_hours_slots: {total_work_hours_slots}, busy_slots: {total_busy_slots}", file=sys.stderr, flush=True)
                                    print(f"  Window facts: {window_facts}, min_gap facts: {min_gap_facts}, locked_event facts: {locked_event_facts}, workhours facts: {workhours_facts}", file=sys.stderr, flush=True)
                                    
                                    # If UNSAT and we have free slots, try to understand why
                                    if not asp_result.satisfiable and total_free_slots > 0:
                                        print(f"  WARNING: UNSAT despite {total_free_slots} free slots - constraints may be too strict", file=sys.stderr, flush=True)
                                        # Check if window facts match free slots
                                        if window_facts == 0 and total_free_slots > 0:
                                            print(f"  ERROR: No window facts generated despite {total_free_slots} free slots!", file=sys.stderr, flush=True)
                                        elif window_facts < total_free_slots:
                                            print(f"  NOTE: Only {window_facts} window facts for {total_free_slots} free slots (some may be filtered)", file=sys.stderr, flush=True)
                                    if asp_stats.get('error'):
                                        print(f"  ASP error: {asp_stats.get('error')}", file=sys.stderr, flush=True)
                                    if asp_stats.get('timeout'):
                                        print(f"  ASP timeout: {asp_stats.get('timeout')}", file=sys.stderr, flush=True)
                                    if asp_stats.get('unsat'):
                                        print(f"  ASP UNSAT: Problem is unsatisfiable", file=sys.stderr, flush=True)
                                except Exception as e:
                                    try:
                                        import sys
                                        print(f"[ASP_WINDOW] Error logging window {window_idx+1}: {e}", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                
                                # Collect models from this window
                                asp_models_list = asp_solver.models if hasattr(asp_solver, 'models') else []
                                if asp_model and asp_model not in asp_models_list:
                                    asp_models_list.insert(0, asp_model)
                                asp_models_list = asp_models_list[:10]  # Limit per window
                                
                                # Store solutions from this window
                                if asp_result.satisfiable and asp_models_list:
                                    all_asp_stats.append(asp_stats)
                                    window_solution_count = len(asp_models_list)
                                    # Debug: log window results
                                    try:
                                        import sys
                                        from datetime import datetime
                                        import pytz
                                        reduced_start = asp_normalized_data["slot_indexer"].horizon_start
                                        reduced_end = asp_normalized_data["slot_indexer"].horizon_end
                                        et_start = reduced_start.astimezone(pytz.timezone('America/New_York'))
                                        et_end = reduced_end.astimezone(pytz.timezone('America/New_York'))
                                        print(f"[SLIDING_WINDOW] Window {window_idx+1} ({window_start_dt.strftime('%b %d')}-{window_end_dt.strftime('%b %d')}): {window_solution_count} models found, horizon={et_start.strftime('%Y-%m-%d %H:%M')} to {et_end.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                else:
                                    # Debug: log why no models were found
                                    try:
                                        import sys
                                        print(f"[ASP_WINDOW] Window {window_idx+1}: No models found - satisfiable={asp_result.satisfiable}, models_list_len={len(asp_models_list) if hasattr(asp_solver, 'models') else 0}", file=sys.stderr, flush=True)
                                        if not asp_result.satisfiable:
                                            print(f"  → Problem is UNSAT (unsatisfiable)", file=sys.stderr, flush=True)
                                        elif not asp_models_list:
                                            print(f"  → Problem is satisfiable but no models returned (may be timeout or constraint too tight)", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                    # CRITICAL: Make a deep copy of asp_normalized_data to avoid it being overwritten
                                    from copy import deepcopy
                                    for model_data in asp_models_list:
                                        all_asp_solutions.append((model_data, deepcopy(asp_normalized_data), window_problem))
                            
                            # Aggregate stats from all windows
                            total_models = sum(s.get("models_found", 0) for s in all_asp_stats)
                            total_solve_time = sum(s.get("solve_time_ms", 0) for s in all_asp_stats)
                            total_ground_time = sum(s.get("ground_time_ms", 0) for s in all_asp_stats)
                            
                            debug_info.asp_stats = {
                                "models": total_models,
                                "optimum": any(s.get("optimum", False) for s in all_asp_stats),
                                "solve_time_ms": total_solve_time,
                                "ground_time_ms": total_ground_time,
                                "windows_explored": num_windows,
                                "satisfiable": any(s.get("satisfiable", False) for s in all_asp_stats),
                                "asp_model_truthy": len(all_asp_solutions) > 0,
                                "asp_result_satisfiable": True
                            }
                            
                            # Process solutions from all windows
                            asp_solutions_list = []
                            original_slot_indexer = original_normalized_data["slot_indexer"]
                            
                            for model_idx, (model_data, window_normalized_data, window_problem) in enumerate(all_asp_solutions):
                                asp_solution = extract_scheduling_solution(model_data, "q1")
                                if not asp_solution:
                                    continue
                                
                                asp_slot_indexer = window_normalized_data.get("slot_indexer")
                                if not asp_slot_indexer:
                                    # Debug: log missing slot_indexer
                                    try:
                                        import sys
                                        print(f"[WINDOW_SOLUTION] Window {window_idx+1 if 'window_idx' in locals() else '?'}, model {model_idx}: Missing slot_indexer in window_normalized_data!", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                    continue
                                
                                reduced_slot = asp_solution["start_slot"]
                                
                                # Convert to datetime
                                slot_datetime = asp_slot_indexer.slot_to_datetime(reduced_slot)
                                if not slot_datetime:
                                    continue
                                
                                # Convert to original horizon slot
                                original_slot = original_slot_indexer.datetime_to_slot(slot_datetime)
                                if original_slot is None:
                                    duration = slot_datetime - original_slot_indexer.horizon_start
                                    calculated_slot = int(duration.total_seconds() / 60 / 15)
                                    if 0 <= calculated_slot < original_slot_indexer.total_slots:
                                        original_slot = calculated_slot
                                    else:
                                        continue
                                
                                # CRITICAL: Validate that the converted slot doesn't conflict in the original horizon
                                # The reduced horizon's busy_slots might be different from the original
                                # BUT: ASP solutions may require moving events, so we need to compute moves first
                                duration_slots = max(1, window_problem.duration_minutes // 15)
                                meeting_slots = range(original_slot, original_slot + duration_slots)
                                original_busy_slots = original_normalized_data.get("busy_slots", {})
                                
                                # Compute which events the ASP solution would move (in the reduced horizon)
                                # This tells us which events are being moved to make this slot work
                                try:
                                    from .clingo_wrapper import compute_move_deltas
                                except (ImportError, ValueError):
                                    try:
                                        from scheduling_orchestrator.clingo_wrapper import compute_move_deltas
                                    except ImportError:
                                        from clingo_wrapper import compute_move_deltas
                                
                                # Compute moved events in the reduced horizon context
                                moved_events_reduced = compute_move_deltas(
                                    asp_solution,
                                    window_normalized_data,
                                    window_problem
                                )
                                
                                # Build set of event keys that are being moved
                                moved_event_keys = set()
                                for moved_event in moved_events_reduced:
                                    owner = moved_event.get("owner")
                                    event_id = moved_event.get("event_id")
                                    if owner and event_id:
                                        moved_event_keys.add((owner, event_id))
                                
                                # Check if this slot conflicts with events that CAN'T be moved (locked events)
                                # Events that are being moved are OK (they'll be moved out of the way)
                                event_protection = original_normalized_data.get("event_protection", {})
                                event_slots_map = original_normalized_data.get("event_slots_map", {})
                                
                                has_locked_conflict = False
                                for participant_id in window_problem.participants:
                                    participant_busy = original_busy_slots.get(participant_id, set())
                                    conflicting_slots = set(meeting_slots).intersection(participant_busy)
                                    
                                    if conflicting_slots:
                                        # Check which events are causing the conflict
                                        for (p_id, e_id), slots in event_slots_map.items():
                                            if p_id == participant_id and slots.intersection(conflicting_slots):
                                                event_key = (p_id, e_id)
                                                # If this event is being moved, it's OK
                                                if event_key in moved_event_keys:
                                                    continue
                                                # If this event is locked, it can't be moved - conflict!
                                                protection = event_protection.get(event_key, "flexible")
                                                if protection == "locked":
                                                    has_locked_conflict = True
                                                    break
                                        
                                        if has_locked_conflict:
                                            break
                                
                                if has_locked_conflict:
                                    # Skip this solution - it conflicts with locked events that can't be moved
                                    try:
                                        import sys
                                        print(f"[WINDOW_SOLUTION] Rejecting ASP solution {model_idx}: conflicts with locked events", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                    continue
                                
                                # Solution is valid - log if it has moves
                                try:
                                    import sys
                                    if moved_events_reduced:
                                        print(f"[WINDOW_SOLUTION] Accepting ASP solution {model_idx}: slot {original_slot}, {len(moved_events_reduced)} events to move", file=sys.stderr, flush=True)
                                    else:
                                        print(f"[WINDOW_SOLUTION] Accepting ASP solution {model_idx}: slot {original_slot}, no moves needed", file=sys.stderr, flush=True)
                                except:
                                    pass
                                
                                # Create solution dict
                                asp_solution_dict = {
                                    "start_slot": original_slot,
                                    "score": 500 - model_idx,  # Score based on order
                                    "moved_events": [],
                                    "method": "asp_multi_move",
                                    "_asp_model_data": model_data,
                                    "_asp_solution": asp_solution,
                                    "_asp_reduced_slot": reduced_slot,
                                    "_asp_normalized_data": window_normalized_data  # Store for move computation
                                }
                                asp_solutions_list.append(asp_solution_dict)
                            
                            if asp_solutions_list:
                                solution = asp_solutions_list[0]
                                # Only add ASP solutions if Python solver didn't find any
                                # Python solver solutions are preferred (they use full horizon)
                                if not python_solutions_found:
                                    solutions.extend(asp_solutions_list)
                                    asp_solution_found = True
                                    print(f"[SOLVER] ASP solver found {len(asp_solutions_list)} solutions (Python found none)", file=sys.stderr, flush=True)
                                else:
                                    print(f"[SOLVER] ASP solver found {len(asp_solutions_list)} solutions but Python already found {len(solutions)}, using Python solutions", file=sys.stderr, flush=True)
                                debug_info.horizon_reduced = True
                                debug_info.reduced_slots = window_slots
                                # Store windows_explored in asp_stats instead of debug_info directly
                                debug_info.asp_stats["windows_explored"] = num_windows
                        else:
                            # No time window specified - can't do sliding window
                            debug_info.asp_stats = {
                                "models": 0,
                                "optimum": False,
                                "solve_time_ms": 0,
                                "ground_time_ms": 0,
                                "error": "No time window specified for sliding window approach",
                                "error_type": None,
                                "satisfiable": False,
                                "asp_model_truthy": False,
                                "asp_result_satisfiable": False,
                                "windows_explored": 0
                            }
                    
                    # Only return UNSAT if we have no solutions at all (neither Python nor ASP)
                    if not solutions and not asp_solution_found:
                        # No solution found with either Python or ASP - return UNSAT
                        unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
                        return ResponseEnvelope(
                            status="unsat",
                            explanation=unsat_info["explanation"],
                            proposals=[],
                            relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
                            debug=debug_info
                        ).model_dump()
            
            except Exception as e:
                    # ASP fallback failed - return UNSAT
                    import traceback
                    error_traceback = traceback.format_exc()
                    unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
                    return ResponseEnvelope(
                        status="unsat",
                        explanation=f"{unsat_info['explanation']} (ASP fallback error: {str(e)})",
                        proposals=[],
                        relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
                        debug=debug_info
                    ).model_dump() | {"asp_fallback_error": str(e), "asp_fallback_traceback": error_traceback}
            
            # Process multiple solutions to build diverse proposals
            all_proposals = []
            # By default, return all proposals with 0, 1, or 2 moves (zero, single-move, or double-move solutions)
            # This ensures we return all feasible options without overwhelming the user
            max_moved_events = 2  # Return all proposals with 0, 1, or 2 moves
            
            # Sort solutions by score (highest first), then by number of moved events (fewer is better)
            # Score already prioritizes free slots, then single moves, etc.
            # We also want to prioritize solutions with fewer moved events within same score tier
            # Build sort keys inline to avoid schema generator analyzing nested functions
            for sol in solutions:
                method = sol.get("method", "")
                if method == "free_slot":
                    sol["_sort_priority"] = 0
                    sol["_moved_estimate"] = 0
                elif method == "single_move":
                    sol["_sort_priority"] = 1
                    sol["_moved_estimate"] = 1
                elif method == "solo_override":
                    sol["_sort_priority"] = 2
                    sol["_moved_estimate"] = 0
                else:
                    sol["_sort_priority"] = 3
                    sol["_moved_estimate"] = 10
            solutions.sort(key=lambda s: (s.get("_sort_priority", 3), s.get("score", 0), -s.get("_moved_estimate", 10)), reverse=True)
            
            # Count solutions that pass validation after grouping by day
            validated_count = 0
            
            # Group solutions by day for diversity filtering
            from datetime import datetime
            import pytz
            solutions_by_day: Dict[str, List[Dict[str, Any]]] = {}
            
            for sol in solutions:
                # For ASP solutions, use original slot_indexer for validation and conversion
                # For Python solutions, also use original slot_indexer (they were computed with full horizon)
                validation_slot_indexer = python_slot_indexer  # Use original for Python solutions
                if sol.get("method") == "asp_multi_move":
                    validation_slot_indexer = original_normalized_data["slot_indexer"]
                
                start_slot = sol["start_slot"]
                
                # Validate slot
                if start_slot < 0 or start_slot >= validation_slot_indexer.total_slots:
                    continue
                
                start_dt = validation_slot_indexer.slot_to_datetime(start_slot)
                if not start_dt:
                    continue
                
                duration_slots = max(1, scheduling_problem.duration_minutes // 15)
                end_slot = start_slot + duration_slots
                
                if end_slot > validation_slot_indexer.total_slots:
                    continue
                
                if end_slot == validation_slot_indexer.total_slots:
                    end_dt = validation_slot_indexer.horizon_end
                else:
                    end_dt = validation_slot_indexer.slot_to_datetime(end_slot)
                
                if not end_dt:
                    continue
                
                # Group by day for diversity
                if start_dt.tzinfo is None:
                    start_dt = pytz.UTC.localize(start_dt)
                day_key = start_dt.date().isoformat()
                
                if day_key not in solutions_by_day:
                    solutions_by_day[day_key] = []
                sol["_start_dt"] = start_dt
                sol["_end_dt"] = end_dt
                sol["_validation_slot_indexer"] = validation_slot_indexer
                solutions_by_day[day_key].append(sol)
                validated_count += 1
            
            # Select diverse solutions across the full date range
            # Strategy: Ensure representation from different parts of the timeframe
            selected_solutions = []
            selected_days = set()
            
            # Group days by week/period for better distribution
            all_days = sorted(solutions_by_day.keys())
            # Process all solutions - we'll filter by move count when building proposals
            # Use a reasonable limit to prevent excessive processing
            MAX_SOLUTIONS_TO_PROCESS = 2000
            if not all_days:
                # No solutions grouped by day - use all solutions up to limit
                selected_solutions = solutions[:MAX_SOLUTIONS_TO_PROCESS]
            else:
                # First pass: best solution from each day (prioritize days with fewer moved events)
                # Sort days by the best solution's moved event estimate
                days_with_scores = []
                for day_key in all_days:
                    day_solutions = solutions_by_day[day_key]
                    if day_solutions:
                        # Find best solution for this day (by score, which correlates with moved events)
                        best_sol = max(day_solutions, key=lambda s: s.get("score", 0))
                        method = best_sol.get("method", "")
                        moved_estimate = 0 if method == "free_slot" else (1 if method == "single_move" else 10)
                        days_with_scores.append((day_key, moved_estimate, best_sol))
                
                # Sort by moved_estimate (fewer is better), then by day
                days_with_scores.sort(key=lambda x: (x[1], x[0]))
                
                # Take best solution from each day, prioritizing days with fewer moves
                for day_key, _, best_sol in days_with_scores:
                    if len(selected_solutions) >= MAX_SOLUTIONS_TO_PROCESS:
                        break
                    # Ensure solution has required attributes before adding
                    if "_start_dt" not in best_sol or "_end_dt" not in best_sol or "_validation_slot_indexer" not in best_sol:
                        continue  # Skip invalid solutions
                    if best_sol not in selected_solutions:
                        selected_solutions.append(best_sol)
                        selected_days.add(day_key)
                
                # Second pass: add remaining solutions up to limit, ensuring we cover the full range
                if len(selected_solutions) < MAX_SOLUTIONS_TO_PROCESS:
                    # Sort all solutions by score (best first)
                    all_solutions_sorted = sorted(solutions, key=lambda s: s.get("score", 0), reverse=True)
                    
                    for sol in all_solutions_sorted:
                        if len(selected_solutions) >= MAX_SOLUTIONS_TO_PROCESS:
                            break
                        if "_start_dt" not in sol:
                            continue
                        day_key = sol["_start_dt"].date().isoformat()
                        
                        # Add solutions not yet selected
                        if sol not in selected_solutions:
                            selected_solutions.append(sol)
            
            # Build proposals from selected solutions
            # Initialize error collection list (all_proposals already initialized above)
            proposal_build_errors = []  # Collect errors for debugging
            
            # Ensure python_normalized_data is available (it should be from Python solver path)
            # Check if we're in the scope where python_normalized_data exists
            if 'python_normalized_data' not in locals() and 'python_normalized_data' not in globals():
                # Fallback: use original_normalized_data if python_normalized_data not available
                # This can happen if we're in a different execution path
                try:
                    python_normalized_data = original_normalized_data
                except NameError:
                    # If original_normalized_data also not available, we have a bigger issue
                    python_normalized_data = normalized_data
            
            # Ensure generate_proposal_id is available
            if 'generate_proposal_id' not in locals() and 'generate_proposal_id' not in globals():
                try:
                    from .formatting import generate_proposal_id
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.formatting import generate_proposal_id
                    except ImportError:
                        from formatting import generate_proposal_id
            
            for sol_idx, sol in enumerate(selected_solutions):
                # Validate that solution has required attributes
                if "_start_dt" not in sol or "_end_dt" not in sol or "_validation_slot_indexer" not in sol:
                    # Skip solutions that weren't properly validated
                    import traceback
                    print(f"[WARNING] Skipping solution missing required attributes: {sol.get('method', 'unknown')} at slot {sol.get('start_slot', 'unknown')}", file=sys.stderr, flush=True)
                    continue
                
                start_dt = sol["_start_dt"]
                end_dt = sol["_end_dt"]
                validation_slot_indexer = sol["_validation_slot_indexer"]
                
                # Compute moved events and objective scores
                solution_method = sol.get("method", "unknown")
                has_asp_model_data = "_asp_model_data" in sol
                
                try:
                    if solution_method == "asp_multi_move" and has_asp_model_data:
                        # ASP solution - use ASP move computation
                        asp_model_data_ref = sol.get("_asp_model_data")
                        asp_solution_ref = sol.get("_asp_solution")
                        if asp_model_data_ref and asp_solution_ref:
                            # CRITICAL: Convert occurs_slots from reduced horizon to original horizon
                            # The asp_solution_ref has occurs_slots relative to the reduced horizon,
                            # but we need to compute move deltas using the original horizon's event_slots_map
                            asp_solution_original = asp_solution_ref.copy()
                            if "_asp_reduced_slot" in sol and "start_slot" in sol:
                                # Convert occurs_slots from reduced horizon to original horizon
                                reduced_slot = sol.get("_asp_reduced_slot")
                                original_slot = sol.get("start_slot")
                                if reduced_slot is not None and original_slot is not None:
                                    slot_offset = original_slot - reduced_slot
                                    original_occurs_slots = [slot + slot_offset for slot in asp_solution_ref.get("occurs_slots", [])]
                                    asp_solution_original["occurs_slots"] = original_occurs_slots
                            
                            # Use original_normalized_data for move computation to match events correctly
                            moved_events_list = compute_move_deltas(asp_solution_original, original_normalized_data, scheduling_problem) or []
                            objective_scores_dict = compute_objective_scores(asp_model_data_ref, asp_solution_ref, asp_normalized_data, scheduling_problem) or {}
                        else:
                            moved_events_list = []
                            objective_scores_dict = {}
                    else:
                        # Python solution - check if moved_events are already computed
                        # Python solver solutions may already have moved_events populated
                        if "moved_events" in sol and sol.get("moved_events"):
                            # Use pre-computed moved_events if available
                            moved_events_list = sol.get("moved_events", [])
                            # Also check for objective_scores
                            if "objective_scores" in sol:
                                objective_scores_dict = sol.get("objective_scores", {})
                            else:
                                objective_scores_dict = compute_objective_scores_python(sol, python_normalized_data, scheduling_problem) or {}
                        else:
                            # Compute moved events and scores
                            moved_events_list = compute_move_deltas_python(sol, python_normalized_data, scheduling_problem) or []
                            objective_scores_dict = compute_objective_scores_python(sol, python_normalized_data, scheduling_problem) or {}
                        
                        # Store the method in the proposal for sorting purposes
                        solution_method = sol.get("method", "unknown")
                    
                    moved_events = [MovedEvent(**me) for me in moved_events_list]
                    scores_dict = {
                        "moved_minutes": objective_scores_dict.get("moved_minutes", 0),
                        "focus_block_bonus": objective_scores_dict.get("focus_block_bonus", 0),
                        "preference_penalty": objective_scores_dict.get("preference_penalty", 0),
                        "protected_events_moved": objective_scores_dict.get("protected_events_moved", 0),
                        "priority_score": objective_scores_dict.get("priority_score", 0.0)
                    }
                    scores = ObjectiveScores(**scores_dict)
                    
                    # Store the score temporarily for sorting (will be in objective_scores.priority_score)
                    # Also store solution score for fallback if priority_score is 0
                    solution_score = sol.get("score", 0.0)
                    if scores.priority_score == 0.0 and solution_score != 0.0:
                        scores.priority_score = solution_score
                    
                    # Prepare original event details for rescheduling proposals
                    original_event_id_value = None
                    original_event_details_value = None
                    if extracted_event_details and scheduling_problem.is_rescheduling:
                        original_event_id_value = extracted_event_details.get("event_id")
                        # Use merged title from scheduling_problem if extracted title is "Untitled Meeting"
                        # This handles cases where the event's summary was empty but the title was extracted from utterance
                        extracted_title = extracted_event_details.get("title", "")
                        display_title = extracted_title
                        if extracted_title in ("Untitled Meeting", "", None) and scheduling_problem.title:
                            display_title = scheduling_problem.title
                        original_event_details_value = {
                            "title": display_title,
                            "start_utc": extracted_event_details.get("current_start_utc"),
                            "end_utc": extracted_event_details.get("current_end_utc"),
                            "participants": extracted_event_details.get("participants", []),
                            "location": extracted_event_details.get("location"),
                            "duration_minutes": extracted_event_details.get("duration_minutes")
                        }
                    
                    proposal = Proposal(
                        title=scheduling_problem.title or "Meeting",
                        participants=scheduling_problem.participants,
                        start_utc=start_dt.isoformat(),
                        end_utc=end_dt.isoformat(),
                        moved_events=moved_events,
                        objective_scores=scores,
                        location=scheduling_problem.location,
                        proposal_id=generate_proposal_id(),  # Add unique ID
                        original_event_id=original_event_id_value,
                        original_event_details=original_event_details_value
                    )
                    # Store solution method temporarily for sorting (solo_override needs special handling)
                    # We'll remove this attribute before returning
                    if solution_method == "solo_override":
                        proposal._solution_method = "solo_override"
                    # Store solution score temporarily for sorting
                    proposal._solution_score = scores.priority_score
                    all_proposals.append(proposal)
                except Exception as e:
                    # Skip this solution if proposal building fails
                    import traceback
                    error_tb = traceback.format_exc()
                    error_msg = f"Solution {sol_idx}: {type(e).__name__}: {str(e)}"
                    proposal_build_errors.append(error_msg)
                    print(f"[ERROR] Failed to build proposal from solution {sol_idx}: {str(e)}", file=sys.stderr, flush=True)
                    print(f"[ERROR] Traceback: {error_tb}", file=sys.stderr, flush=True)
                    print(f"[ERROR] Solution details: method={sol.get('method', 'unknown')}, start_slot={sol.get('start_slot', 'unknown')}, has_start_dt={'_start_dt' in sol}", file=sys.stderr, flush=True)
                    # Only show first 3 errors to avoid overwhelming the response
                    if len(proposal_build_errors) <= 3:
                        print(f"[ERROR] Full error: {error_tb}", file=sys.stderr, flush=True)
                    continue
            
            # Phase 5: Proactive Calendar Fetching for Missing Participants
            # Identify participants from moved events who are not in the original request
            # and fetch their calendars before validation
            #
            # IMPORTANT (Issue #1 fix): Validation calendars are stored SEPARATELY from
            # original_normalized_data to prevent leaking validation data into user output.
            # The validation_normalized_data is passed explicitly to validate_moved_event_dict().
            missing_participants = set()
            validation_normalized_data = None  # Will hold additional calendars for validation only
            event_participants_map = original_normalized_data.get("event_participants", {})
            
            # Collect all participants from moved events
            for prop in all_proposals:
                if hasattr(prop, 'moved_events') and prop.moved_events:
                    for moved_event in prop.moved_events:
                        # Get event key from moved event
                        event_key = (moved_event.owner, moved_event.event_id)
                        # Get all participants of this event
                        participants = event_participants_map.get(event_key, [moved_event.owner])
                        for participant_id in participants:
                            # Check if this participant is not in the original events_by_participant
                            if participant_id not in events_by_participant:
                                missing_participants.add(participant_id)
            
            # Fetch calendars for missing participants if we have MCP client capability
            if missing_participants and context_json and context_json.get("timeframe"):
                try:
                    # Import MCP client - try absolute imports first
                    try:
                        from scheduling_orchestrator.mcp_client import MCPCalendarClient, MCPError
                    except (ImportError, ValueError):
                        try:
                            from .mcp_client import MCPCalendarClient, MCPError
                        except (ImportError, ValueError):
                            try:
                                from mcp_client import MCPCalendarClient, MCPError
                            except ImportError:
                                MCPCalendarClient = None
                                MCPError = None
                    
                    if MCPCalendarClient:
                        mcp_url = os.getenv(
                            "MCP_CALENDAR_SERVER_URL",
                            "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
                        )
                        
                        mcp_client = MCPCalendarClient(
                            base_url=mcp_url,
                            timeout=int(os.getenv("MCP_CALENDAR_TIMEOUT", "30")),
                            max_retries=int(os.getenv("MCP_CALENDAR_RETRY_ATTEMPTS", "3"))
                        )
                        
                        # Fetch calendars for missing participants
                        async def fetch_missing_calendars():
                            await mcp_client.initialize()
                            
                            # Reuse the fetch_calendar_events function logic
                            async def fetch_participant_events(participant_id):
                                try:
                                    result = await mcp_client.get_core_event_data(
                                        calendar_id=participant_id,
                                        before=context_json["timeframe"]["to"],
                                        after=context_json["timeframe"]["from"]
                                    )
                                    
                                    # Normalize events to orchestrator format
                                    normalized_events = []
                                    for evt in result:
                                        # Skip all-day events
                                        if evt.get("start", {}).get("date"):
                                            continue
                                        
                                        start_dt = evt.get("start", {}).get("dateTime") or evt.get("start", {}).get("date")
                                        end_dt = evt.get("end", {}).get("dateTime") or evt.get("end", {}).get("date")
                                        
                                        if not start_dt or not end_dt:
                                            continue
                                        
                                        # Extract attendees_list (for backward compatibility)
                                        attendees_list = evt.get("attendees_list", [])
                                        if isinstance(attendees_list, str):
                                            try:
                                                import ast
                                                attendees_list = ast.literal_eval(attendees_list)
                                            except:
                                                attendees_list = []
                                        elif not isinstance(attendees_list, list):
                                            attendees_list = []
                                        
                                        # Extract attendees_details (new field with names)
                                        attendees_details = evt.get("attendees_details", [])
                                        if not isinstance(attendees_details, list):
                                            attendees_details = []
                                        
                                        # If attendees_details not available, construct from attendees_list
                                        if not attendees_details and attendees_list:
                                            attendees_details = [
                                                {"email": email, "name": email.split("@")[0]}  # Use email prefix as name fallback
                                                for email in attendees_list
                                                if isinstance(email, str)
                                            ]
                                        
                                        # Preserve both 'summary' (raw MCP) and 'title' (normalized) fields
                                        evt_summary = evt.get("summary", "")
                                        normalized_events.append({
                                            "id": evt.get("id", ""),
                                            "title": evt_summary,  # Use summary as title for normalized format
                                            "summary": evt_summary,  # Preserve original summary field
                                            "start": start_dt,
                                            "end": end_dt,
                                            "locked": evt.get("locked", False),
                                            "protected": evt.get("protected", False),
                                            "flexible": evt.get("flexible", True),
                                            "transparent": evt.get("transparent", False),  # True = "show as free"
                                            "description": evt.get("description", ""),  # For description-based protection detection
                                            "attendees": attendees_list,  # Keep for backward compatibility
                                            "attendees_details": attendees_details  # New field with names
                                        })

                                    return participant_id, normalized_events
                                except Exception as e:
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.error(f"Failed to fetch events for {participant_id}: {e}")
                                    return participant_id, []

                            # Fetch all missing calendars concurrently
                            tasks = [fetch_participant_events(pid) for pid in missing_participants]
                            results = await asyncio.gather(*tasks)
                            
                            # Build result dictionary
                            fetched_events = {}
                            for participant_id, events in results:
                                fetched_events[participant_id] = events
                            
                            return fetched_events
                        
                        # Fetch missing calendars
                        fetched_events = asyncio.run(fetch_missing_calendars())
                        
                        # Merge into events_by_participant
                        for pid, events in fetched_events.items():
                            events_by_participant[pid] = events
                        
                        # Re-normalize with additional participants
                        # This updates normalized_data with the new participants' calendar data
                        try:
                            from scheduling_orchestrator.normalizer import normalize_events
                        except (ImportError, ValueError):
                            try:
                                from .normalizer import normalize_events
                            except (ImportError, ValueError):
                                from normalizer import normalize_events
                        
                        # Re-normalize with all participants (original + newly fetched)
                        updated_normalized_data = normalize_events(events_by_participant, context_json)

                        # ISSUE #1 FIX: Store new participants' data in validation_normalized_data (SEPARATE)
                        # instead of merging into original_normalized_data to prevent data leakage to user output.
                        # Validation functions receive this data explicitly via additional_calendars parameter.
                        validation_normalized_data = {
                            "busy_slots": {},
                            "event_slots_map": {},
                            "event_metadata": {},
                            "event_participants": {},
                            "event_protection": {},
                            "work_hours_slots": {},
                            "slot_indexer": original_normalized_data["slot_indexer"],  # Share slot_indexer
                        }

                        for pid in fetched_events.keys():
                            # Add busy slots
                            if pid in updated_normalized_data["busy_slots"]:
                                validation_normalized_data["busy_slots"][pid] = updated_normalized_data["busy_slots"][pid]

                            # Add event_slots_map entries
                            for event_key, slots in updated_normalized_data["event_slots_map"].items():
                                if event_key[0] == pid:  # Event belongs to this participant
                                    validation_normalized_data["event_slots_map"][event_key] = slots

                            # Add event_metadata entries
                            for event_key, metadata in updated_normalized_data["event_metadata"].items():
                                if event_key[0] == pid:  # Event belongs to this participant
                                    validation_normalized_data["event_metadata"][event_key] = metadata

                            # Add event_participants entries
                            for event_key, participants_list in updated_normalized_data["event_participants"].items():
                                if event_key[0] == pid:  # Event belongs to this participant
                                    validation_normalized_data["event_participants"][event_key] = participants_list

                            # Add work_hours_slots if available
                            if pid in updated_normalized_data.get("work_hours_slots", {}):
                                validation_normalized_data["work_hours_slots"][pid] = updated_normalized_data["work_hours_slots"][pid]

                        # Update event_protection for validation calendars
                        for event_key, protection in updated_normalized_data["event_protection"].items():
                            if event_key[0] in fetched_events.keys():
                                validation_normalized_data["event_protection"][event_key] = protection

                        print(f"[orchestrate_scheduling] Stored {len(fetched_events)} validation calendars SEPARATELY (Issue #1 fix)", file=sys.stderr, flush=True)
                        
                except Exception as e:
                    # Log error but don't fail - we'll validate with available data
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to fetch calendars for missing participants {missing_participants}: {e}")
                    # Continue without the missing participants - validation will handle this
            
            # Phase 4: Post-Solution Validation
            # Validate all moved events to ensure they don't conflict with participants' calendars
            validated_proposals = []
            validation_errors = []
            
            for prop in all_proposals:
                # Validate the meeting time itself (for all proposals, including zero-conflict)
                try:
                    try:
                        from scheduling_orchestrator.move_validator import validate_proposal_meeting_time
                    except (ImportError, ValueError):
                        try:
                            from .move_validator import validate_proposal_meeting_time
                        except (ImportError, ValueError):
                            from move_validator import validate_proposal_meeting_time
                    
                    # Debug: Check if participants match busy_slots keys
                    busy_slots_keys = list(original_normalized_data.get("busy_slots", {}).keys())
                    participants_not_in_busy = [p for p in prop.participants if p not in original_normalized_data.get("busy_slots", {})]
                    
                    # Debug logging
                    print(f"[VALIDATION] Checking proposal {prop.proposal_id} - participants: {prop.participants}", file=sys.stderr, flush=True)
                    print(f"[VALIDATION] busy_slots keys: {busy_slots_keys[:5]}", file=sys.stderr, flush=True)
                    print(f"[VALIDATION] Meeting time: {prop.start_utc} to {prop.end_utc}", file=sys.stderr, flush=True)
                    
                    if participants_not_in_busy:
                        # Try case-insensitive match
                        busy_slots_lower = {k.lower(): k for k in busy_slots_keys}
                        for p in participants_not_in_busy[:]:
                            if p.lower() in busy_slots_lower:
                                # Found case-insensitive match - this is handled in validate_proposal_meeting_time
                                participants_not_in_busy.remove(p)
                    
                    if participants_not_in_busy:
                        # Participant ID mismatch - this is a data consistency issue
                        print(f"[VALIDATION] Participant ID mismatch: {participants_not_in_busy} not in busy_slots", file=sys.stderr, flush=True)
                        validation_errors.append({
                            "proposal_id": prop.proposal_id,
                            "start_utc": prop.start_utc,
                            "errors": [f"Participant ID mismatch: {participants_not_in_busy} not in busy_slots. Available keys: {busy_slots_keys[:5]}"]
                        })
                        continue
                    
                    # Debug: Check what slots the meeting time maps to
                    try:
                        from datetime import datetime
                        import pytz
                        start_dt_val = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
                        if start_dt_val.tzinfo is None:
                            start_dt_val = pytz.UTC.localize(start_dt_val)
                        else:
                            start_dt_val = start_dt_val.astimezone(pytz.UTC)
                        end_dt_val = datetime.fromisoformat(prop.end_utc.replace("Z", "+00:00"))
                        if end_dt_val.tzinfo is None:
                            end_dt_val = pytz.UTC.localize(end_dt_val)
                        else:
                            end_dt_val = end_dt_val.astimezone(pytz.UTC)
                        start_slot_val = original_normalized_data["slot_indexer"].datetime_to_slot(start_dt_val)
                        end_slot_val = original_normalized_data["slot_indexer"].datetime_to_slot(end_dt_val)
                        print(f"[VALIDATION] Meeting maps to slots {start_slot_val}-{end_slot_val}", file=sys.stderr, flush=True)
                        # Check busy slots for these slots
                        for p_id in prop.participants:
                            p_busy = original_normalized_data.get("busy_slots", {}).get(p_id, set())
                            conflicts = set(range(start_slot_val, end_slot_val)) & p_busy
                            if conflicts:
                                print(f"[VALIDATION] Participant {p_id} has {len(conflicts)} conflicting slots: {sorted(list(conflicts))[:5]}", file=sys.stderr, flush=True)
                    except Exception as e:
                        print(f"[VALIDATION] Error in debug check: {e}", file=sys.stderr, flush=True)
                    
                    # Check if this is a solo_override proposal
                    is_solo_override = getattr(prop, '_solution_method', None) == "solo_override"
                    
                    # Convert moved_events to dict format for validation
                    moved_events_for_validation = None
                    if prop.moved_events:
                        moved_events_for_validation = [
                            {
                                "owner": me.owner,
                                "event_id": me.event_id,
                                "old_start": me.old_start,
                                "new_start": me.new_start,
                                "old_end": me.old_end,
                                "new_end": me.new_end,
                                "shift_minutes": me.shift_minutes
                            }
                            for me in prop.moved_events
                        ]
                    
                    # Get original_event_id from proposal if it exists
                    original_event_id_for_validation = None
                    if hasattr(prop, 'original_event_id') and prop.original_event_id:
                        original_event_id_for_validation = prop.original_event_id
                    
                    meeting_valid, meeting_error = validate_proposal_meeting_time(
                        prop.start_utc,
                        prop.end_utc,
                        prop.participants,
                        original_normalized_data,
                        original_normalized_data["slot_indexer"],
                        is_solo_override=is_solo_override,
                        moved_events=moved_events_for_validation,
                        original_event_id=original_event_id_for_validation
                    )
                    
                    # Debug: Log validation result for all proposals, especially Dec 16 ones
                    if "2025-12-16" in prop.start_utc or prop.proposal_id in ["prop_a01a243fa33b", "prop_95e6382bcf9d", "prop_77c6c5bdf7dd", "prop_eaf5d91de7a9", "prop_ee576526aec2"]:
                        print(f"[VALIDATION] Proposal {prop.proposal_id}: meeting_valid={meeting_valid}, error={meeting_error}, is_solo_override={is_solo_override}, start={prop.start_utc}", file=sys.stderr, flush=True)
                    
                    if not meeting_valid:
                        # Meeting time itself conflicts - reject proposal
                        validation_errors.append({
                            "proposal_id": prop.proposal_id,
                            "start_utc": prop.start_utc,
                            "errors": [f"Meeting time conflict: {meeting_error}"]
                        })
                        continue
                except Exception as e:
                    # If validation fails due to error, reject the proposal
                    validation_errors.append({
                        "proposal_id": prop.proposal_id,
                        "start_utc": prop.start_utc,
                        "errors": [f"Validation error: {str(e)}"]
                    })
                    continue
                
                # If no moved events, meeting time is valid - accept proposal
                if not prop.moved_events:
                    validated_proposals.append(prop)
                    continue
                
                # Validate each moved event
                all_moves_valid = True
                move_validation_errors = []
                
                # Build set of all event keys being moved (to exclude from conflict checks)
                all_moved_event_keys = set()
                for me in prop.moved_events:
                    try:
                        if hasattr(me, 'model_dump'):
                            me_dict = me.model_dump()
                        elif isinstance(me, dict):
                            me_dict = me
                        else:
                            me_dict = {
                                "owner": getattr(me, 'owner', None),
                                "event_id": getattr(me, 'event_id', None)
                            }
                        if me_dict.get("owner") and me_dict.get("event_id"):
                            all_moved_event_keys.add((me_dict["owner"], me_dict["event_id"]))
                    except:
                        pass
                
                for moved_event in prop.moved_events:
                    # Convert Pydantic model to dict if needed
                    try:
                        if hasattr(moved_event, 'model_dump'):
                            moved_event_dict = moved_event.model_dump()
                        elif isinstance(moved_event, dict):
                            moved_event_dict = moved_event
                        else:
                            # Try to access attributes directly
                            moved_event_dict = {
                                "owner": getattr(moved_event, 'owner', None),
                                "event_id": getattr(moved_event, 'event_id', None),
                                "new_start": getattr(moved_event, 'new_start', None),
                                "new_end": getattr(moved_event, 'new_end', None)
                            }
                        
                        # Validate required fields
                        if not moved_event_dict.get("owner") or not moved_event_dict.get("event_id"):
                            all_moves_valid = False
                            move_validation_errors.append(f"Invalid moved_event structure: missing owner or event_id")
                            continue
                    except Exception as e:
                        all_moves_valid = False
                        move_validation_errors.append(f"Error converting moved_event to dict: {str(e)}")
                        continue
                    
                    # Get event metadata to check internal-only constraint
                    event_key = (moved_event_dict["owner"], moved_event_dict["event_id"])
                    event_metadata = original_normalized_data.get("event_metadata", {})
                    event_meta = event_metadata.get(event_key, {})
                    
                    # Check internal-only constraint (should already be enforced, but double-check)
                    internal_only = event_meta.get("internal_only", True)
                    if not internal_only:
                        all_moves_valid = False
                        move_validation_errors.append(f"Event {moved_event_dict['event_id']} is not internal-only")
                        continue
                    
                    # Validate new location doesn't conflict with participants
                    try:
                        try:
                            from scheduling_orchestrator.move_validator import validate_moved_event_dict
                        except (ImportError, ValueError):
                            try:
                                from .move_validator import validate_moved_event_dict
                            except (ImportError, ValueError):
                                from move_validator import validate_moved_event_dict
                        
                        is_valid, error_msg = validate_moved_event_dict(
                            moved_event_dict,
                            original_normalized_data,
                            original_normalized_data["slot_indexer"],
                            exclude_event_keys=all_moved_event_keys,
                            additional_calendars=validation_normalized_data  # Issue #1 fix: pass validation data explicitly
                        )
                        
                        if not is_valid:
                            all_moves_valid = False
                            move_validation_errors.append(f"Event {moved_event_dict.get('event_id', 'unknown')}: {error_msg}")
                    except Exception as e:
                        # If validation fails due to error, reject the move
                        all_moves_valid = False
                        move_validation_errors.append(f"Validation error for event {moved_event_dict.get('event_id', 'unknown')}: {str(e)}")
                
                if all_moves_valid:
                    validated_proposals.append(prop)
                else:
                    # Log validation errors for debugging
                    validation_errors.append({
                        "proposal_id": prop.proposal_id,
                        "start_utc": prop.start_utc,
                        "errors": move_validation_errors
                    })
            
            # Replace all_proposals with validated proposals
            all_proposals = validated_proposals
            
            # Log validation summary
            if validation_errors:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Rejected {len(validation_errors)} proposals due to invalid moves: {validation_errors[:3]}")  # Log first 3
                # Also print to stderr for debugging
                print(f"[VALIDATION] Rejected {len(validation_errors)} proposals due to invalid moves", file=sys.stderr, flush=True)
                for i, ve in enumerate(validation_errors[:3]):
                    print(f"[VALIDATION] Proposal {i+1}: {ve.get('proposal_id', 'unknown')} - {ve.get('errors', [])}", file=sys.stderr, flush=True)
            
            if not all_proposals:
                # Include validation errors in the response if all proposals were rejected
                error_details = f"Processed {len(selected_solutions)} solutions but none could be converted to proposals. "
                error_details += f"Validated solutions: {validated_count}. "
                error_details += f"Solutions selected: {len(selected_solutions)}. "
                
                # Add validation error details
                if validation_errors:
                    error_details += f"All {len(validation_errors)} proposals were rejected during validation. "
                    first_error = validation_errors[0]
                    if first_error.get('errors'):
                        error_details += f"Sample validation error: {first_error.get('errors', [])[0]}. "
                    # Show participant ID mismatch if that's the issue
                    if len(validation_errors) > 0:
                        # Check if all errors are about missing participants
                        all_missing_participant = all(
                            any("calendar not available" in str(err) for err in ve.get('errors', []))
                            for ve in validation_errors[:5]
                        )
                        if all_missing_participant:
                            error_details += f"All validation errors are about missing participant calendars. "
                            error_details += f"Participants in proposals: {scheduling_problem.participants}. "
                            error_details += f"Participants in events_by_participant: {list(events_by_participant.keys()) if events_by_participant else 'none'}. "
                            error_details += f"Participants in busy_slots: {list(original_normalized_data.get('busy_slots', {}).keys())}. "
                
                if selected_solutions:
                    error_details += f"Sample solution keys: {list(selected_solutions[0].keys()) if selected_solutions else 'none'}. "
                if proposal_build_errors:
                    error_details += f"Proposal build errors: {proposal_build_errors[0] if proposal_build_errors else 'none'}"
                    if len(proposal_build_errors) > 1:
                        error_details += f" (and {len(proposal_build_errors) - 1} more similar errors)"
                
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Failed to build any valid proposals from solutions. {error_details}",
                    proposals=[],
                    error_message=f"Proposal building failed: {validation_errors[0].get('errors', ['Unknown error'])[0] if validation_errors else (proposal_build_errors[0] if proposal_build_errors else 'Unknown error')}",
                    debug=debug_info
                ).model_dump()
            
            # Calculate free-block scores and preference scores for all proposals
            # This prioritizes proposals that preserve/create long unbroken stretches on requester's calendar
            try:
                try:
                    from .free_block_scorer import calculate_free_block_score, identify_requester
                    from .preference_scorer import compute_aggregate_preference_score
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.free_block_scorer import calculate_free_block_score, identify_requester
                        from scheduling_orchestrator.preference_scorer import compute_aggregate_preference_score
                    except ImportError:
                        from free_block_scorer import calculate_free_block_score, identify_requester
                        from preference_scorer import compute_aggregate_preference_score
                requester_id = identify_requester(scheduling_problem, context_dict)
                
                for prop in all_proposals:
                    # Pass moved_events to free-block scorer so it can account for event moves
                    moved_events_list = []
                    if hasattr(prop, 'moved_events') and prop.moved_events:
                        # Convert Pydantic models to dicts if needed
                        for me in prop.moved_events:
                            if hasattr(me, 'model_dump'):
                                moved_events_list.append(me.model_dump())
                            elif isinstance(me, dict):
                                moved_events_list.append(me)
                    
                    free_block_stats = calculate_free_block_score(
                        prop.start_utc,
                        scheduling_problem,
                        original_normalized_data,
                        original_normalized_data["slot_indexer"],
                        requester_id,
                        moved_events=moved_events_list if moved_events_list else None
                    )
                    # Store free-block score temporarily for sorting
                    prop._free_block_score = free_block_stats.get("free_block_score", 0.0)
                    prop._free_block_stats = free_block_stats
                    
                    # Calculate preference score for this proposal
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(prop.start_utc.replace('Z', '+00:00'))
                        slot_indexer = original_normalized_data["slot_indexer"]
                        slot = slot_indexer.datetime_to_slot(start_dt)
                        if slot is not None:
                            preference_score = compute_aggregate_preference_score(
                                slot,
                                scheduling_problem,
                                context_dict,
                                slot_indexer,
                                requester_id
                            )
                            # Store preference score temporarily for sorting
                            prop._preference_score = preference_score
                        else:
                            prop._preference_score = 0.0
                    except Exception:
                        prop._preference_score = 0.0
                    
                    # Also store in the Proposal's free_block_stats field for output
                    try:
                        try:
                            from .schemas import FreeBlockStats
                        except (ImportError, ValueError):
                            try:
                                from scheduling_orchestrator.schemas import FreeBlockStats
                            except ImportError:
                                from schemas import FreeBlockStats
                        prop.free_block_stats = FreeBlockStats(**free_block_stats)
                    except Exception:
                        # If FreeBlockStats import fails, continue without it
                        pass
            except Exception as e:
                # If free-block scoring fails, continue without it
                import traceback
                print(f"ERROR in free-block scoring: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                for prop in all_proposals:
                    prop._free_block_score = 0.0
                    prop._free_block_stats = {}
            
            # Final sort: prioritize proposals by type, then by free-block score, then by priority score
            # Priority order: free_slot (0 moves) > single_move (1 move) > solo_override (0 moves but lower priority) > multi-move
            # For zero-conflict: category priority maintained, free-block score determines order within category
            # For one-move and override: free-block score takes precedence across categories, then category priority
            # Time-based prioritization: earlier dates/times within the requested interval get higher priority
            # Using helper function defined at the start of orchestrate_scheduling
            # Build sort keys inline for each proposal to avoid schema generator analyzing nested functions
            for prop in all_proposals:
                moved_count = len(prop.moved_events) if prop.moved_events else 0
                is_solo_override = getattr(prop, '_solution_method', None) == "solo_override"
                if moved_count == 0 and not is_solo_override:
                    prop._sort_priority = 0
                elif moved_count == 1:
                    prop._sort_priority = 1
                elif is_solo_override:
                    prop._sort_priority = 2
                else:
                    prop._sort_priority = 3
                
                priority_score = getattr(prop, '_solution_score', 0.0)
                if priority_score == 0.0:
                    priority_score = prop.objective_scores.priority_score if prop.objective_scores else 0.0
                prop._sort_priority_score = priority_score
                
                try:
                    start_dt = datetime.fromisoformat(prop.start_utc.replace('Z', '+00:00'))
                    prop._sort_time = start_dt.timestamp()
                except (ValueError, AttributeError):
                    prop._sort_time = prop.start_utc
                
                prop._sort_free_block = getattr(prop, '_free_block_score', 0.0)
                prop._sort_preference = getattr(prop, '_preference_score', 0.0)
            
            # Sort using inline lambda (lambdas aren't analyzed by schema generator)
            all_proposals.sort(key=lambda p: (
                (-10000, (moved_count := len(p.moved_events) if p.moved_events else 0), -p._sort_free_block, -p._sort_preference, -p._sort_priority_score, p._sort_time) if p._sort_priority == 0 else
                (-1000, -p._sort_free_block, -p._sort_preference, p._sort_priority, (moved_count := len(p.moved_events) if p.moved_events else 0), -p._sort_priority_score, p._sort_time) if p._sort_priority in (1, 2) else
                (-500, p._sort_priority, (moved_count := len(p.moved_events) if p.moved_events else 0), -p._sort_free_block, -p._sort_preference, -p._sort_priority_score, p._sort_time)
            ))
            
            # Filter to only include proposals with 0 or 1 moves OR solo_override (treated as separate tier)
            filtered_proposals = []
            for prop in all_proposals:
                moved_count = len(prop.moved_events) if prop.moved_events else 0
                is_solo_override = getattr(prop, '_solution_method', None) == "solo_override"
                
                if moved_count <= max_moved_events or is_solo_override:
                    filtered_proposals.append(prop)
            
            all_proposals = filtered_proposals
            
            # Mark solo-override proposals in notes_for_invite before removing temporary attribute
            # This allows downstream consumers to identify them
            for prop in all_proposals:
                if hasattr(prop, '_solution_method'):
                    if prop._solution_method == "solo_override":
                        # Add note to indicate this is a solo-override proposal
                        current_notes = prop.notes_for_invite or ""
                        if current_notes:
                            prop.notes_for_invite = f"{current_notes} [This slot conflicts with solo/blocking events but can override them]"
                        else:
                            prop.notes_for_invite = "This slot conflicts with solo/blocking events but can override them"
                    delattr(prop, '_solution_method')
                # Remove temporary score attributes (they're stored in objective_scores)
                # But preserve free_block_stats in notes_for_invite or as a separate field for debugging
                if hasattr(prop, '_solution_score'):
                    delattr(prop, '_solution_score')
                # Keep free_block_stats available for test output (remove at the very end if needed)
                # For now, we'll keep it as it might be useful for debugging
            
            # Generate explanation grouped by proposal type
            # Import helper to check if proposal only overlaps transparent events
            try:
                from .formatting import proposal_only_overlaps_transparent
            except (ImportError, ValueError):
                try:
                    from scheduling_orchestrator.formatting import proposal_only_overlaps_transparent
                except ImportError:
                    from formatting import proposal_only_overlaps_transparent

            # Group proposals by type
            free_proposals = []
            single_move_proposals = []
            solo_override_proposals = []
            multi_move_proposals = []
            # Track transparent events for each section (for subheader display)
            free_transparent_events = []  # Transparent events overlapping free proposals

            # Define formatting_normalized_data early for use in proposal categorization
            # (also used later in format_refined_user_display)
            formatting_normalized_data = original_normalized_data if 'original_normalized_data' in locals() else normalized_data

            # Build event_registry early for use in proposal categorization
            # (also used later in format_refined_user_display)
            try:
                from .agent_data_builder import build_event_registry
            except (ImportError, ValueError):
                try:
                    from scheduling_orchestrator.agent_data_builder import build_event_registry
                except ImportError:
                    from agent_data_builder import build_event_registry
            event_registry = build_event_registry(all_proposals, formatting_normalized_data)

            for prop in all_proposals:
                moved_count = len(prop.moved_events) if prop.moved_events else 0
                notes = prop.notes_for_invite or ""
                is_solo_override = "solo/blocking events" in notes.lower()

                if moved_count == 0 and not is_solo_override:
                    # "True free" proposal - but check if it overlaps any transparent events
                    # (Transparent events aren't blocking, but we want to note the overlap)
                    _, transparent_events = proposal_only_overlaps_transparent(
                        prop, formatting_normalized_data, event_registry
                    )
                    if transparent_events:
                        for owner, event_id, event_title, time_range in transparent_events:
                            if (owner, event_id, event_title, time_range) not in free_transparent_events:
                                free_transparent_events.append((owner, event_id, event_title, time_range))
                    free_proposals.append(prop)
                elif moved_count == 1:
                    single_move_proposals.append(prop)
                elif is_solo_override:
                    # Check if this "solo_override" only overlaps transparent events
                    # If so, treat it as a free proposal instead
                    only_transparent, transparent_events = proposal_only_overlaps_transparent(
                        prop, formatting_normalized_data, event_registry
                    )
                    if only_transparent:
                        # Transparent-only overlap: keep in free_proposals, not override section
                        free_proposals.append(prop)
                        # Track the transparent events for the subheader
                        for owner, event_id, event_title, time_range in transparent_events:
                            if (owner, event_id, event_title, time_range) not in free_transparent_events:
                                free_transparent_events.append((owner, event_id, event_title, time_range))
                    else:
                        # Has at least one opaque solo event: stays in override section
                        solo_override_proposals.append(prop)
                else:
                    multi_move_proposals.append(prop)
            
            # Check if this is a rescheduling operation
            is_rescheduling = any(
                prop.original_event_id or prop.original_event_details 
                for prop in all_proposals
            )
            
            if is_rescheduling:
                # Get original event details from first proposal that has them
                original_details = None
                for prop in all_proposals:
                    if prop.original_event_details:
                        original_details = prop.original_event_details
                        break
                
                if original_details:
                    original_title = original_details.get("title", "meeting")
                    explanation_parts = [f"Found {len(all_proposals)} alternative time option(s) for rescheduling '{original_title}':"]
                else:
                    explanation_parts = [f"Found {len(all_proposals)} alternative time option(s) for rescheduling:"]
            else:
                explanation_parts = [f"Found {len(all_proposals)} meeting option(s):"]
            
            # Free slots
            if free_proposals:
                explanation_parts.append(f"{len(free_proposals)} free slot(s)")
            
            # Single-move slots
            if single_move_proposals:
                explanation_parts.append(f"{len(single_move_proposals)} option(s) requiring 1 event move")
            
            # Solo-override slots (after single-move, as requested)
            if solo_override_proposals:
                explanation_parts.append(f"{len(solo_override_proposals)} option(s) available by overriding solo/blocking events")
            
            # Multi-move slots
            if multi_move_proposals:
                explanation_parts.append(f"{len(multi_move_proposals)} option(s) requiring multiple event moves")
            
            explanation = ". ".join(explanation_parts) + "."
            
            # Add category, rank, and preference_score to each proposal
            for rank, prop in enumerate(all_proposals, 1):
                # Determine category
                moved_count = len(prop.moved_events) if prop.moved_events else 0
                notes = prop.notes_for_invite or ""
                is_solo_override = "solo/blocking events" in notes.lower()
                
                if moved_count == 0 and not is_solo_override:
                    prop.category = "zero_conflict"
                elif moved_count == 1:
                    prop.category = "single_move"
                elif is_solo_override:
                    prop.category = "solo_override"
                else:
                    prop.category = "multi_move"
                
                # Add rank
                prop.rank = rank
                
                # Store preference_score if available
                preference_score = getattr(prop, '_preference_score', None)
                if preference_score is not None:
                    prop.preference_score = preference_score
            
            # Build dual-format response
            debug_info.total_time_ms = int((time.time() - start_time) * 1000)
            
            # Get timezone from context
            timezone_str = "America/New_York"
            if context_json and "timeframe" in context_json:
                timezone_str = context_json["timeframe"].get("tz", "America/New_York")
            
            # Build event registry - ensure it's available
            if 'build_event_registry' not in locals() and 'build_event_registry' not in globals():
                try:
                    from .agent_data_builder import build_event_registry
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.agent_data_builder import build_event_registry
                    except ImportError:
                        from agent_data_builder import build_event_registry
            
            event_registry = build_event_registry(all_proposals, normalized_data)
            
            # Build user display
            formatted_proposals = []
            categories_info = {}
            
            # Ensure dual-format schema classes are available
            if 'CategoryInfo' not in locals() and 'CategoryInfo' not in globals():
                try:
                    from .schemas import CategoryInfo, UserDisplay, AgentData, CrossReferenceMapping, FormattedProposal
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.schemas import CategoryInfo, UserDisplay, AgentData, CrossReferenceMapping, FormattedProposal
                    except ImportError:
                        from schemas import CategoryInfo, UserDisplay, AgentData, CrossReferenceMapping, FormattedProposal
            
            # Import refined formatting function
            try:
                from .formatting import format_refined_user_display
            except (ImportError, ValueError):
                try:
                    from scheduling_orchestrator.formatting import format_refined_user_display
                except ImportError:
                    from formatting import format_refined_user_display
            
            # Generate refined formatted display
            # CRITICAL: Use original_normalized_data to ensure slot indices match between
            # proposals (converted from UTC times) and event_slots_map (which uses original horizon)
            formatting_normalized_data = original_normalized_data if 'original_normalized_data' in locals() else normalized_data
            # Parse context_json if it's a string
            context_json_for_formatting = None
            if context_json:
                if isinstance(context_json, str):
                    try:
                        import json
                        context_json_for_formatting = json.loads(context_json)
                    except:
                        context_json_for_formatting = None
                else:
                    context_json_for_formatting = context_json
            
            # Limit proposals for user-facing display to prevent response size issues
            # Keep all proposals in agent_data, but limit user-facing formats
            # Use higher limits for solo_override since users often want to see more override options
            MAX_DISPLAY_PROPOSALS_FREE = 5
            MAX_DISPLAY_PROPOSALS_MOVE = 5
            MAX_DISPLAY_PROPOSALS_OVERRIDE = 10  # Higher limit for override proposals
            limited_free_proposals = free_proposals[:MAX_DISPLAY_PROPOSALS_FREE] if len(free_proposals) > MAX_DISPLAY_PROPOSALS_FREE else free_proposals
            limited_move_proposals = single_move_proposals[:MAX_DISPLAY_PROPOSALS_MOVE] if len(single_move_proposals) > MAX_DISPLAY_PROPOSALS_MOVE else single_move_proposals
            limited_override_proposals = solo_override_proposals[:MAX_DISPLAY_PROPOSALS_OVERRIDE] if len(solo_override_proposals) > MAX_DISPLAY_PROPOSALS_OVERRIDE else solo_override_proposals
            
            # Get external_participants_for_display if it exists, otherwise use empty list
            external_participants_for_formatting = external_participants_for_display if 'external_participants_for_display' in locals() and external_participants_for_display else None

            # Look up participant display names from identity service
            # Collect all unique participant emails from various sources
            all_participant_emails = set()
            if participant_ids:
                all_participant_emails.update(participant_ids)
            if user_id:
                all_participant_emails.add(user_id)
            # Also collect from event registry (event owners)
            if event_registry:
                for event_meta in event_registry.values():
                    if hasattr(event_meta, 'owner') and event_meta.owner:
                        all_participant_emails.add(event_meta.owner)

            # Look up display names (colloquial names) from Letta identity service
            participant_names_for_formatting = {}
            if all_participant_emails:
                try:
                    from .identity_lookup import lookup_participant_names
                except ImportError:
                    try:
                        from scheduling_orchestrator.identity_lookup import lookup_participant_names
                    except ImportError:
                        try:
                            from identity_lookup import lookup_participant_names
                        except ImportError:
                            lookup_participant_names = None

                if lookup_participant_names:
                    try:
                        participant_names_for_formatting = lookup_participant_names(list(all_participant_emails))
                        logger.info(f"Resolved {len(participant_names_for_formatting)} participant names from identity service")
                    except Exception as e:
                        logger.warning(f"Failed to lookup participant names: {e}")

            verbatim_user_output_text = format_refined_user_display(
                free_proposals=limited_free_proposals,
                move_proposals=limited_move_proposals,
                override_proposals=limited_override_proposals,
                event_registry=event_registry,
                normalized_data=formatting_normalized_data,
                user_id=user_id,
                timezone_str=timezone_str,
                context_json=context_json_for_formatting,
                external_participants=external_participants_for_formatting,
                free_transparent_events=free_transparent_events,  # For subheader in Best Options
                participant_names=participant_names_for_formatting,
            )
            
            # Add note if proposals were truncated, with specific counts per category
            truncation_notes = []
            if len(free_proposals) > MAX_DISPLAY_PROPOSALS_FREE:
                truncation_notes.append(f"{len(limited_free_proposals)} of {len(free_proposals)} free slot options")
            if len(single_move_proposals) > MAX_DISPLAY_PROPOSALS_MOVE:
                truncation_notes.append(f"{len(limited_move_proposals)} of {len(single_move_proposals)} single-move options")
            if len(solo_override_proposals) > MAX_DISPLAY_PROPOSALS_OVERRIDE:
                truncation_notes.append(f"{len(limited_override_proposals)} of {len(solo_override_proposals)} override options")
            
            if truncation_notes:
                total_displayed = len(limited_free_proposals) + len(limited_move_proposals) + len(limited_override_proposals)
                truncation_msg = f"\n\n*Note: Showing top options ({', '.join(truncation_notes)}). {total_displayed} of {len(all_proposals)} total options shown. All {len(all_proposals)} options are available in the proposals array.*"
                verbatim_user_output_text += truncation_msg
            
            # Also keep the old format for backward compatibility
            # Group by category for display
            # Use limited proposals for formatted_proposals to prevent response size issues
            display_categories = {
                "best_options": limited_free_proposals,
                "with_moves": limited_move_proposals,
                "with_overrides": limited_override_proposals
            }
            
            for cat_key, prop_list in display_categories.items():
                if prop_list:
                    for prop in prop_list:
                        formatted = format_proposal_for_display(
                            prop, prop.rank, cat_key, event_registry, timezone_str
                        )
                        formatted_proposals.append(formatted)
                    
                    # Build category info
                    if cat_key == "best_options":
                        categories_info[cat_key] = CategoryInfo(
                            count=len(prop_list),
                            description="Zero-conflict slots available immediately"
                        )
                    elif cat_key == "with_moves":
                        categories_info[cat_key] = CategoryInfo(
                            count=len(prop_list),
                            description="Options requiring moving 1 existing meeting"
                        )
                    elif cat_key == "with_overrides":
                        categories_info[cat_key] = CategoryInfo(
                            count=len(prop_list),
                            description="Options available by overriding solo/blocking events"
                        )
            
            # Update summary if proposals were truncated
            proposals_were_truncated = (
                len(free_proposals) > MAX_DISPLAY_PROPOSALS_FREE or 
                len(single_move_proposals) > MAX_DISPLAY_PROPOSALS_MOVE or 
                len(solo_override_proposals) > MAX_DISPLAY_PROPOSALS_OVERRIDE
            )
            if proposals_were_truncated:
                total_displayed = len(formatted_proposals)
                summary_text = f"Found {len(all_proposals)} meeting option(s) (showing top {total_displayed})"
            else:
                summary_text = f"Found {len(all_proposals)} meeting option(s)"
            
            user_display = UserDisplay(
                summary=summary_text,
                explanation=explanation,
                formatted_proposals=formatted_proposals,
                categories=categories_info,
                verbatim_user_output=verbatim_user_output_text
            )
            
            # Build agent data - ensure functions are available
            if 'generate_ranking_rationale' not in locals() and 'generate_ranking_rationale' not in globals():
                try:
                    from .agent_data_builder import generate_ranking_rationale, build_optimization_summary, build_constraints_applied
                except (ImportError, ValueError):
                    try:
                        from scheduling_orchestrator.agent_data_builder import generate_ranking_rationale, build_optimization_summary, build_constraints_applied
                    except ImportError:
                        from agent_data_builder import generate_ranking_rationale, build_optimization_summary, build_constraints_applied
            
            # Limit proposals in agent_data to prevent response size issues
            # Keep top proposals for agent analysis, but limit to prevent truncation
            MAX_AGENT_DATA_PROPOSALS = 20  # Limit agent_data proposals to prevent response size issues
            limited_agent_proposals = all_proposals[:MAX_AGENT_DATA_PROPOSALS] if len(all_proposals) > MAX_AGENT_DATA_PROPOSALS else all_proposals
            
            ranking_rationale = generate_ranking_rationale(limited_agent_proposals)
            optimization_summary = build_optimization_summary(limited_agent_proposals, scheduling_problem)
            constraints_applied = build_constraints_applied(normalized_data, scheduling_problem, context_json)
            
            agent_data = AgentData(
                proposals=limited_agent_proposals,  # Limited to prevent response size issues
                event_registry=event_registry,
                ranking_rationale=ranking_rationale,
                optimization_summary=optimization_summary,
                constraints_applied=constraints_applied
            )
            
            # Build cross-reference mapping
            rank_to_proposal_id = {prop.rank: prop.proposal_id for prop in all_proposals if prop.proposal_id}
            proposal_id_to_rank = {prop.proposal_id: prop.rank for prop in all_proposals if prop.proposal_id}
            
            # Map event IDs to proposals
            event_id_to_proposals = {}
            for prop in all_proposals:
                if prop.proposal_id:
                    for moved in prop.moved_events:
                        if moved.event_id not in event_id_to_proposals:
                            event_id_to_proposals[moved.event_id] = []
                        event_id_to_proposals[moved.event_id].append(prop.proposal_id)
            
            # Map categories to proposal IDs
            category_to_proposals = {
                "best_options": [p.proposal_id for p in free_proposals if p.proposal_id],
                "with_moves": [p.proposal_id for p in single_move_proposals if p.proposal_id],
                "with_overrides": [p.proposal_id for p in solo_override_proposals if p.proposal_id]
            }
            
            mapping = CrossReferenceMapping(
                rank_to_proposal_id=rank_to_proposal_id,
                proposal_id_to_rank=proposal_id_to_rank,
                event_id_to_proposals=event_id_to_proposals,
                category_to_proposals=category_to_proposals
            )
            
            # Limit main proposals array to prevent response size issues
            # Agent can still access proposals via agent_data.proposals
            # Use a higher limit to include more proposals, especially override options
            MAX_PROPOSALS_IN_RESPONSE = 20  # Increased from 10 to show more options
            limited_proposals_for_response = all_proposals[:MAX_PROPOSALS_IN_RESPONSE] if len(all_proposals) > MAX_PROPOSALS_IN_RESPONSE else all_proposals
            
            # Return response with dual format
            result = ResponseEnvelope(
                status="ok",
                proposals=limited_proposals_for_response,  # Limited for response size, more in agent_data
                explanation=explanation,  # Backward compatibility
                debug=debug_info,
                user_display=user_display,
                agent_data=agent_data,
                mapping=mapping
            ).model_dump()
            
            # Reorder response to put verbatim_user_output first for better agent visibility
            # Extract verbatim_user_output and add it as top-level field, and reorder user_display
            if "user_display" in result and result["user_display"] and "verbatim_user_output" in result["user_display"]:
                verbatim_output = result["user_display"]["verbatim_user_output"]
                
                # Reorder user_display dict to put verbatim_user_output first
                user_display_dict = result["user_display"]
                reordered_user_display = {
                    "verbatim_user_output": verbatim_output,
                }
                # Add remaining user_display fields
                for key, value in user_display_dict.items():
                    if key != "verbatim_user_output":
                        reordered_user_display[key] = value
                result["user_display"] = reordered_user_display
                
                # Also add verbatim_user_output as top-level field for easier access
                # Create a new ordered dict with verbatim_user_output first
                reordered_result = {
                    "verbatim_user_output": verbatim_output,
                    "status": result["status"],
                    "proposals": result["proposals"],
                    "explanation": result["explanation"],
                }
                # Add remaining fields
                for key, value in result.items():
                    if key not in reordered_result:
                        reordered_result[key] = value
                result = reordered_result
            
            # Ensure result is JSON-serializable before returning
            try:
                json.dumps(result)
            except (TypeError, ValueError) as ser_err:
                try:
                    import sys
                    print(f"[orchestrate_scheduling] JSON serialization error in success path: {ser_err}", file=sys.stderr, flush=True)
                except:
                    pass
                # Return a safe fallback
                return {
                    "status": "bad_input",
                    "explanation": f"Response serialization failed: {str(ser_err)}",
                    "proposals": [],
                    "error_message": "Internal error: response could not be serialized",
                    "debug": {"error_type": "SerializationError", "original_error": str(ser_err)}
                }
            
            return result
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to solve scheduling problem: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
    except Exception as e:
        # Catch any unexpected errors and return them with full traceback
        # This should never happen if all code paths are properly handled, but it's a safety net
        error_traceback = traceback.format_exc()
        
        # Log to stderr (visible in Docker logs)
        try:
            import sys
            print(f"[orchestrate_scheduling] UNEXPECTED ERROR: {type(e).__name__}: {str(e)}", file=sys.stderr, flush=True)
            print(f"[orchestrate_scheduling] Traceback:\n{error_traceback}", file=sys.stderr, flush=True)
        except:
            pass  # Don't fail if logging fails
        
        # Try to use ResponseEnvelope if available, otherwise fall back to dict
        try:
            # ResponseEnvelope should be available from imports above
            result = ResponseEnvelope(
                status="bad_input",
                explanation=f"Unexpected error in orchestrate_scheduling: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=DebugInfo(
                    error_type=type(e).__name__,
                    error_traceback=error_traceback
                )
            ).model_dump() | {"error_traceback": error_traceback}
            
            # Ensure result is JSON-serializable
            try:
                json.dumps(result)
            except (TypeError, ValueError) as ser_err:
                try:
                    import sys
                    print(f"[orchestrate_scheduling] JSON serialization error in error path: {ser_err}", file=sys.stderr, flush=True)
                except:
                    pass
                # Return a safe fallback without traceback (which might not be serializable)
                return {
                    "status": "bad_input",
                    "explanation": f"Unexpected error: {str(e)}",
                    "proposals": [],
                    "error_message": str(e),
                    "debug": {"error_type": type(e).__name__}
                }
            
            return result
        except (NameError, Exception) as inner_e:
            # If ResponseEnvelope isn't available or fails, use dict
            try:
                import sys
                print(f"[orchestrate_scheduling] Failed to create ResponseEnvelope: {inner_e}", file=sys.stderr, flush=True)
            except:
                pass
            return {
                "status": "bad_input",
                "explanation": f"Unexpected error in orchestrate_scheduling: {str(e)}",
                "proposals": [],
                "error_message": str(e),
                "error_traceback": error_traceback,
                "debug": {
                    "error_type": type(e).__name__,
                    "error_args": str(e.args) if hasattr(e, 'args') else None
                }
            }

