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
    dspy = None

from .schemas import SchedulingProblem


class ExtractSchedulingRequest(dspy.Signature if DSPY_AVAILABLE else object):
    """
    Extract structured scheduling problem from natural language utterance.
    
    Input: utterance (natural language scheduling request)
    Output: JSON string matching SchedulingProblem schema
    """
    utterance: str = dspy.InputField(desc="Natural language scheduling request")
    context_json: str = dspy.InputField(desc="JSON string of context (working hours, preferences, policy)")
    problem_json: str = dspy.OutputField(desc="JSON string matching SchedulingProblem schema with participants, duration_minutes, time_window_start, time_window_end, preferred_times, preferred_days, title, location, min_gap_minutes, allow_off_hours")


def initialize_dspy():
    """Initialize DSPy with LLM configuration."""
    if not DSPY_AVAILABLE:
        return None
    
    # Get LLM configuration from environment
    # Support OpenAI, Anthropic, or other providers
    openai_api_key = os.getenv("OPENAI_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if openai_api_key:
        lm = dspy.LM(model="gpt-4o-mini", api_key=openai_api_key)
    elif anthropic_api_key:
        lm = dspy.LM(model="claude-3-5-sonnet-20241022", api_key=anthropic_api_key)
    else:
        # Default to OpenAI if available
        lm = dspy.LM(model="gpt-4o-mini")
    
    dspy.configure(lm=lm)
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
    
    # Initialize DSPy if not already configured
    if dspy.settings.lm is None:
        initialize_dspy()
    
    # Convert context_json to string if provided
    context_str = json.dumps(context_json) if context_json else "{}"
    
    # Create extraction module with ChainOfThought for better reasoning
    extractor = dspy.ChainOfThought(ExtractSchedulingRequest)
    
    # Use BestOfN for reliability (try multiple candidates)
    best_of_n = dspy.BestOfN(extractor, n=3)
    
    # Try extraction
    try:
        result = best_of_n(utterance=utterance, context_json=context_str)
        problem_json_str = result.problem_json
        
        # Validate JSON
        if not validate_scheduling_problem_json(problem_json_str):
            # Try to refine if invalid
            # Use Refine to fix schema violations
            refiner = dspy.Refine(extractor)
            result = refiner(utterance=utterance, context_json=context_str, problem_json=problem_json_str)
            problem_json_str = result.problem_json
            
            # Validate again
            if not validate_scheduling_problem_json(problem_json_str):
                raise ValueError(f"Extracted JSON does not match SchedulingProblem schema: {problem_json_str}")
        
        # Parse JSON
        problem_data = json.loads(problem_json_str)
        
        # Create SchedulingProblem object
        return SchedulingProblem(**problem_data)
    
    except Exception as e:
        # Fallback: try basic extraction without BestOfN
        try:
            result = extractor(utterance=utterance, context_json=context_str)
            problem_json_str = result.problem_json
            
            if validate_scheduling_problem_json(problem_json_str):
                problem_data = json.loads(problem_json_str)
                return SchedulingProblem(**problem_data)
        except Exception:
            pass
        
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
        # Fallback: create minimal SchedulingProblem
        # This is a basic fallback - in practice, you might want more sophisticated parsing
        # For now, return a default problem that the user can refine
        
        # Try to extract duration (look for numbers followed by "min", "hour", etc.)
        import re
        duration_match = re.search(r'(\d+)\s*(?:min|minute|hour|hr)', utterance, re.IGNORECASE)
        duration_minutes = 60  # default
        if duration_match:
            num = int(duration_match.group(1))
            unit = duration_match.group(2).lower() if duration_match.group(2) else ""
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
        
        return SchedulingProblem(
            participants=participants if participants else ["exec"],  # default to exec
            duration_minutes=duration_minutes,
            time_window_start=None,
            time_window_end=None,
            preferred_times=None,
            preferred_days=None,
            title=None,
            location=None,
            min_gap_minutes=15,
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
    from .extraction_validator import validate_scheduling_problem
    
    try:
        data = json.loads(json_str)
        is_valid, _ = validate_scheduling_problem(data)
        return is_valid
    except json.JSONDecodeError:
        return False

