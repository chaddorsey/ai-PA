"""
DSPy extraction program for converting natural language to structured scheduling problems.

Uses DSPy Predict/ChainOfThought with BestOfN/Refine for reliable extraction.
"""

from typing import Dict, Any, Optional, List
import json
import os

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    # Create dummy classes for when dspy is not available
    class DummySignature:
        pass
    class DummyField:
        def __init__(self, desc=""):
            self.desc = desc
    # Create a mock dspy module
    class DummyDspy:
        class Signature:
            pass
        @staticmethod
        def InputField(desc=""):
            return DummyField(desc)
        @staticmethod
        def OutputField(desc=""):
            return DummyField(desc)
    dspy = DummyDspy()

# Handle both relative and absolute imports
try:
    from .schemas import SchedulingProblem
except (ImportError, ValueError):
    from schemas import SchedulingProblem


# Define the class conditionally based on DSPY_AVAILABLE
if DSPY_AVAILABLE:
    class ExtractSchedulingRequest(dspy.Signature):
        """
        Extract structured scheduling problem from natural language utterance.
        
        Input: utterance (natural language scheduling request)
        Output: JSON string matching SchedulingProblem schema
        """
        utterance: str = dspy.InputField(desc="Natural language scheduling request. When the utterance says 'me' or 'I', it refers to the requester (first participant in context). When the utterance says 'with X and Y', the requester should be included in the participants list. Extract participant preferences: If utterance mentions 'X prefers mornings' or 'X likes Tuesday', extract as participant preference. If utterance mentions 'avoid Friday' or 'not on Monday', extract as avoid preference. If utterance mentions 'flexible meetings' or 'moveable events', extract as flexibility notes.")
        context_json: str = dspy.InputField(desc="JSON string of context (working hours, preferences, policy). The 'participants' field contains participant objects with 'id' (email address) and optionally 'name' and 'email' fields. The first participant is typically the requester. When the utterance mentions names like 'Sue' or 'Danielle', you must map them to the email addresses (participant IDs) from the context.")
        problem_json: str = dspy.OutputField(desc="Valid JSON object (not a string) matching SchedulingProblem schema. Required fields: participants (list of email addresses/IDs from context - MUST include the requester if utterance uses 'with', 'me', or 'I'), duration_minutes (integer), time_window_start (ISO 8601 UTC string or null), time_window_end (ISO 8601 UTC string or null), preferred_times (list of ISO strings or null), preferred_days (list like ['Monday', 'Tuesday'] or null), participant_preferences (array of {participant_id, preferred_times, preferred_days, avoid_times, avoid_days, flexibility_notes} or null), avoid_times (array of ISO 8601 UTC strings for times to avoid or null), avoid_days (array of day names to avoid like ['Friday'] or null), title (string or null), location (string or null), min_gap_minutes (integer or null), allow_off_hours (boolean). Map participant names to their email addresses from the context. Always include the requester when utterance contains 'with' or mentions 'me'/'I'.")
else:
    # Fallback class when dspy is not available
    class ExtractSchedulingRequest:
        """
        Extract structured scheduling problem from natural language utterance.
        
        This is a fallback class when DSPy is not available.
        """
        utterance: str = None
        context_json: str = None
        problem_json: str = None


def initialize_dspy():
    """Initialize DSPy with LLM configuration."""
    import sys
    if not DSPY_AVAILABLE:
        # DSPy not available - will use fallback extraction
        print(f"[initialize_dspy] DSPy not available", file=sys.stderr, flush=True)
        return None
    
    # Re-import dspy to ensure it's available
    try:
        import dspy
    except ImportError:
        print(f"[initialize_dspy] Failed to import dspy", file=sys.stderr, flush=True)
        return None
    
    # Load .env file if it exists (for local development)
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        env_path = Path(__file__).parent.parent.parent.parent / '.env'
        if env_path.exists():
            load_dotenv(env_path)
    except (ImportError, Exception):
        pass  # python-dotenv not installed or .env doesn't exist
    
    # Get LLM configuration from environment
    # Support OpenAI, Anthropic, or other providers
    openai_api_key = os.getenv("OPENAI_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if openai_api_key:
        lm = dspy.LM(model="gpt-4o-mini", api_key=openai_api_key)
        print(f"[initialize_dspy] Using OpenAI with model gpt-4o-mini", file=sys.stderr, flush=True)
    elif anthropic_api_key:
        lm = dspy.LM(model="claude-3-5-sonnet-20241022", api_key=anthropic_api_key)
        print(f"[initialize_dspy] Using Anthropic with model claude-3-5-sonnet-20241022", file=sys.stderr, flush=True)
    else:
        # No API keys available
        print(f"[initialize_dspy] WARNING: No API keys found, DSPy will not work", file=sys.stderr, flush=True)
        return None
    
    dspy.configure(lm=lm)
    print(f"[initialize_dspy] DSPy configured successfully", file=sys.stderr, flush=True)
    return lm




def extract_scheduling_request(
    utterance: str,
    context_json: Optional[Dict[str, Any]] = None
) -> SchedulingProblem:
    """
    Extract structured scheduling problem from natural language using DSPy.
    
    Args:
        utterance: Natural language scheduling request
        context_json: Optional context dictionary (working hours, preferences, policy)
        
    Returns:
        SchedulingProblem object
        
    Raises:
        ValueError: If extraction fails or result is invalid
    """
    if not DSPY_AVAILABLE:
        raise ValueError("DSPy is not available. Please install dspy-ai package.")
    
    # Re-import dspy to ensure it's available
    try:
        import dspy
    except ImportError:
        raise ValueError("DSPy is not available. Please install dspy-ai package.")
    
    # Initialize DSPy if not already configured
    # Check if DSPy is configured - settings.lm might not exist or be None
    needs_init = False
    if not hasattr(dspy, 'settings'):
        needs_init = True
    elif not hasattr(dspy.settings, 'lm') or dspy.settings.lm is None:
        needs_init = True
    
    if needs_init:
        lm = initialize_dspy()
        if lm is None:
            raise ValueError("Failed to initialize DSPy - no API keys available")
        
        # Verify it was actually configured
        if not hasattr(dspy, 'settings') or not hasattr(dspy.settings, 'lm') or dspy.settings.lm is None:
            raise ValueError("DSPy initialization completed but LM is not configured")
    
    # Convert context_json to string if provided
    context_str = json.dumps(context_json) if context_json else "{}"
    
    # Create extraction module with ChainOfThought for better reasoning
    extractor = dspy.ChainOfThought(ExtractSchedulingRequest)
    
    # Try extraction with ChainOfThought
    import sys
    import time
    extraction_start = time.time()
    try:
        print(f"[extract_scheduling_request] Starting DSPy extraction...", file=sys.stderr, flush=True)
        result = extractor(utterance=utterance, context_json=context_str)
        extraction_elapsed = (time.time() - extraction_start) * 1000
        print(f"[extract_scheduling_request] DSPy extraction took {extraction_elapsed:.0f}ms", file=sys.stderr, flush=True)
        problem_json_str = result.problem_json
        print(f"[extract_scheduling_request] Raw DSPy output (first 300 chars): {problem_json_str[:300]}", file=sys.stderr, flush=True)
        
        # Clean up JSON string (remove markdown code blocks if present)
        problem_json_str = problem_json_str.strip()
        if problem_json_str.startswith("```json"):
            problem_json_str = problem_json_str[7:]
        if problem_json_str.startswith("```"):
            problem_json_str = problem_json_str[3:]
        if problem_json_str.endswith("```"):
            problem_json_str = problem_json_str[:-3]
        problem_json_str = problem_json_str.strip()
        
        # Try to parse JSON
        try:
            problem_data = json.loads(problem_json_str)
        except json.JSONDecodeError as json_err:
            # If JSON parsing fails, try to extract JSON from the string
            import sys
            import re
            print(f"[extract_scheduling_request] JSON parse error: {json_err}", file=sys.stderr, flush=True)
            print(f"[extract_scheduling_request] Raw output: {problem_json_str[:500]}", file=sys.stderr, flush=True)
            
            # Try to find JSON object in the string
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', problem_json_str, re.DOTALL)
            if json_match:
                try:
                    problem_data = json.loads(json_match.group(0))
                    print(f"[extract_scheduling_request] Extracted JSON from response", file=sys.stderr, flush=True)
                except json.JSONDecodeError:
                    raise ValueError(f"Failed to parse JSON from DSPy output: {problem_json_str[:500]}")
            else:
                raise ValueError(f"Failed to parse JSON from DSPy output: {problem_json_str[:500]}")
        
        # Map participant names to emails if context has participant info
        requester_id = None
        if context_json and "participants" in context_json:
            # Identify requester (first participant or explicitly marked)
            participants_list = context_json["participants"]
            if participants_list:
                # Check for explicit requester_id in context
                if "requester_id" in context_json:
                    requester_id = context_json["requester_id"]
                else:
                    # First participant is the requester
                    requester_id = participants_list[0].get("id", "")
                
                # Build participant mapping
                participant_map = {}
                for p in participants_list:
                    p_id = p.get("id", "")
                    p_email = p.get("email", "")
                    p_name = p.get("name", "")
                    # Create mapping from name/email to participant ID
                    if p_id:
                        participant_map[p_id.lower()] = p_id
                        if p_email:
                            participant_map[p_email.lower()] = p_id
                        if p_name:
                            participant_map[p_name.lower()] = p_id
                            # Handle "Sue" -> find email containing "sue" or similar
                            participant_map[p_name.split()[0].lower()] = p_id
                
                # Map "me" and "i" to requester
                if requester_id:
                    participant_map["me"] = requester_id
                    participant_map["i"] = requester_id
                    participant_map["myself"] = requester_id
                
                # Try to map participant names to IDs
                mapped_participants = []
                for p in problem_data.get("participants", []):
                    p_lower = str(p).lower().strip()
                    if p_lower in participant_map:
                        mapped_participants.append(participant_map[p_lower])
                    elif "@" in str(p):
                        # Already an email
                        mapped_participants.append(p)
                    else:
                        # Try fuzzy matching
                        found = False
                        for key, p_id in participant_map.items():
                            if key in p_lower or p_lower in key:
                                mapped_participants.append(p_id)
                                found = True
                                break
                        if not found:
                            mapped_participants.append(p)  # Keep original if no match
                
                # Check for explicit exclusion phrases that indicate requester should NOT be included
                utterance_lower = utterance.lower()
                has_exclusion = False
                
                # Explicit exclusion phrases - check in order of specificity
                if "without me" in utterance_lower or "without i" in utterance_lower:
                    has_exclusion = True
                elif "excluding me" in utterance_lower or "excluding i" in utterance_lower:
                    has_exclusion = True
                elif " for just " in utterance_lower or " for only " in utterance_lower:
                    has_exclusion = True
                elif "between " in utterance_lower:
                    # "between X and Y" typically excludes the requester unless "me" or "I" is also mentioned
                    # BUT we need to check if "between" refers to participants or dates/times
                    between_idx = utterance_lower.find("between ")
                    text_after_between = utterance_lower[between_idx:]
                    
                    # Check if "between" is referring to dates/times (has month names, dates, or time words)
                    date_time_indicators = ["december", "january", "february", "march", "april", "may", "june",
                                          "july", "august", "september", "october", "november",
                                          "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                                          "morning", "afternoon", "evening", "night", "am", "pm",
                                          "2025", "2024", "2026", ":", "00", "30"]  # Time patterns
                    
                    is_date_time = any(indicator in text_after_between[:50] for indicator in date_time_indicators)
                    
                    if not is_date_time:
                        # "between" likely refers to participants - check if "me" or "I" is mentioned
                        # Only exclude if "me" or "I" is NOT mentioned after "between" or with "with"
                        # Also check if "with" appears anywhere (if so, don't exclude - "with" takes precedence)
                        has_with_anywhere = " with " in utterance_lower
                        has_me_or_i = (" me " in text_after_between or " i " in text_after_between or 
                                       text_after_between.startswith("between me ") or 
                                       text_after_between.startswith("between i ") or
                                       " with me" in utterance_lower or " with i" in utterance_lower)
                        
                        # Exclude only if no "with" anywhere and no "me"/"I" mentioned
                        if not has_with_anywhere and not has_me_or_i:
                            has_exclusion = True
                
                # Additional check: "just X and Y" or "only X and Y" (at sentence boundaries or after "for")
                import re
                if re.search(r'\b(for\s+)?just\s+\w+\s+and\s+\w+', utterance_lower):
                    has_exclusion = True
                elif re.search(r'\b(for\s+)?only\s+\w+\s+and\s+\w+', utterance_lower):
                    has_exclusion = True
                
                if has_exclusion and requester_id:
                    # Remove requester if it was added
                    if requester_id in mapped_participants:
                        mapped_participants.remove(requester_id)
                        import sys
                        print(f"[extract_scheduling_request] Removed requester {requester_id} due to exclusion phrasing", file=sys.stderr, flush=True)
                
                # Handle "with" phrasing - if utterance contains "with" and requester is not in participants, add them
                # BUT only if no exclusion was detected
                if not has_exclusion:
                    has_with = " with " in utterance_lower or utterance_lower.startswith("with ")
                    if has_with and requester_id and requester_id not in mapped_participants:
                        # Add requester to the beginning of the list
                        mapped_participants.insert(0, requester_id)
                        import sys
                        print(f"[extract_scheduling_request] Added requester {requester_id} due to 'with' phrasing", file=sys.stderr, flush=True)
                    
                    # Also check for "me" or "I" in utterance - ensure requester is included
                    if requester_id and (" me " in utterance_lower or " i " in utterance_lower or 
                                         utterance_lower.startswith("me ") or utterance_lower.startswith("i ") or
                                         " for me" in utterance_lower or " for i" in utterance_lower):
                        if requester_id not in mapped_participants:
                            mapped_participants.insert(0, requester_id)
                            import sys
                            print(f"[extract_scheduling_request] Added requester {requester_id} due to 'me'/'I' reference", file=sys.stderr, flush=True)
                
                problem_data["participants"] = mapped_participants
        
        # Validate JSON structure
        if not validate_scheduling_problem_json(json.dumps(problem_data)):
            import sys
            print(f"[extract_scheduling_request] Validation failed for: {json.dumps(problem_data)[:300]}", file=sys.stderr, flush=True)
            # Try to fix common issues
            if "participants" not in problem_data:
                problem_data["participants"] = []
            if "duration_minutes" not in problem_data:
                problem_data["duration_minutes"] = 45
        
        # Create SchedulingProblem object
        print(f"[extract_scheduling_request] Successfully extracted: participants={problem_data.get('participants', [])}, duration={problem_data.get('duration_minutes')}", file=sys.stderr, flush=True)
        return SchedulingProblem(**problem_data)
    
    except Exception as e:
        # Log the error for debugging
        import sys
        import traceback
        print(f"[extract_scheduling_request] Extraction error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise ValueError(f"Failed to extract scheduling problem from utterance: {e}")


def extract_with_fallback(
    utterance: str,
    context_json: Optional[Dict[str, Any]] = None
) -> SchedulingProblem:
    """
    Extract scheduling problem with fallback to basic parsing if DSPy fails.
    
    Args:
        utterance: Natural language scheduling request
        context_json: Optional context dictionary
        
    Returns:
        SchedulingProblem object
    """
    try:
        return extract_scheduling_request(utterance, context_json)
    except Exception as e:
        # Log the error for debugging
        import sys
        print(f"[extract_with_fallback] DSPy extraction failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        import traceback
        print(f"[extract_with_fallback] Traceback:", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        # Fallback: create minimal SchedulingProblem
        # This is a basic fallback - in practice, you might want more sophisticated parsing
        # For now, return a default problem that the user can refine
        
        # Try to extract duration (look for numbers followed by "min", "hour", etc.)
        import re
        duration_match = re.search(r'(\d+)\s*(min|minute|hour|hr)?', utterance, re.IGNORECASE)
        duration_minutes = 60  # default
        if duration_match:
            num = int(duration_match.group(1))
            # Safely get group 2 (unit) - it may not exist if optional group didn't match
            try:
                unit_str = duration_match.group(2)
                unit = unit_str.lower() if unit_str else ""
            except (IndexError, AttributeError):
                unit = ""
            
            if "hour" in unit or "hr" in unit:
                duration_minutes = num * 60
            else:
                duration_minutes = num
        
        # Extract participants (look for names or "with X and Y" patterns)
        # This is very basic - DSPy would do better
        participants = []
        if context_json and "participants" in context_json:
            # Use all participants from context as default
            participants = [p.get("id", "") for p in context_json["participants"] if p.get("id")]
        
        # If no participants found in context, try to extract from utterance
        if not participants:
            # Look for participant names in the utterance (simple pattern matching)
            # This is a very basic fallback - DSPy would do much better
            participant_pattern = r'\b(?:for|with)\s+([A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)*)'
            participant_match = re.search(participant_pattern, utterance, re.IGNORECASE)
            if participant_match:
                names_str = participant_match.group(1)
                # Split on "and" or commas
                names = [name.strip() for name in re.split(r'\s+and\s+|,', names_str) if name.strip()]
                # Convert to lowercase IDs (assuming participant IDs are lowercase)
                participants = [name.lower() for name in names]
        
        return SchedulingProblem(
            participants=participants if participants else ["exec"],  # default to exec
            duration_minutes=duration_minutes,
            time_window_start=None,
            time_window_end=None,
            preferred_times=None,
            preferred_days=None,
            title=None,
            location=None,
            min_gap_minutes=0,
            allow_off_hours=False
        )


# Update the validator to use the extraction_validator module
def validate_scheduling_problem_json(json_str: str) -> bool:
    """
    Validate that JSON string matches SchedulingProblem schema.
    
    Args:
        json_str: JSON string to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Handle both relative and absolute imports
    try:
        from .extraction_validator import validate_scheduling_problem
    except (ImportError, ValueError):
        from extraction_validator import validate_scheduling_problem
    
    try:
        data = json.loads(json_str)
        is_valid, _ = validate_scheduling_problem(data)
        return is_valid
    except json.JSONDecodeError:
        return False

