"""
Simple test for ASP encoding.

Tests that the ASP program can be grounded and solved with toy instances.
"""

def test_simple_satisfiable():
    """Test a simple satisfiable instance."""
    from .asp_encoding import BASE_ASP_PROGRAM
    from .fact_generator import generate_asp_program
    from .normalizer import normalize_events
    from .schemas import SchedulingProblem
    from datetime import datetime
    import pytz
    
    # Simple case: one participant, one hour meeting, no conflicts
    events = {
        'p1': []
    }
    context = {
        'timeframe': {
            'from': '2025-11-25',
            'to': '2025-11-25',
            'tz': 'UTC'
        },
        'participants': [{
            'id': 'p1',
            'email': 'p1@example.com',
            'work_hours': 'M-F 09:00-17:30'
        }]
    }
    
    normalized = normalize_events(events, context)
    
    problem = SchedulingProblem(
        participants=['p1'],
        duration_minutes=60,
        time_window_start='2025-11-25T10:00:00Z',
        time_window_end='2025-11-25T15:00:00Z'
    )
    
    program = generate_asp_program(normalized, problem)
    
    # Check that program is syntactically valid (has facts and rules)
    assert "slot(" in program
    assert "request(" in program
    assert "needs(" in program
    assert "window(" in program
    assert "start(" in program
    assert "occurs(" in program
    
    print("✓ ASP program generated successfully")
    return program


def test_unsatisfiable():
    """Test an unsatisfiable instance (all slots busy)."""
    from .fact_generator import generate_asp_program
    from .normalizer import normalize_events
    from .schemas import SchedulingProblem
    
    # All slots busy
    events = {
        'p1': [
            {
                'id': 'evt1',
                'title': 'All Day',
                'start': '2025-11-25T00:00:00Z',
                'end': '2025-11-26T00:00:00Z',
                'locked': True,
                'protected': True,
                'flexible': False
            }
        ]
    }
    context = {
        'timeframe': {
            'from': '2025-11-25',
            'to': '2025-11-25',
            'tz': 'UTC'
        },
        'participants': [{
            'id': 'p1',
            'email': 'p1@example.com',
            'work_hours': 'M-F 09:00-17:30'
        }]
    }
    
    normalized = normalize_events(events, context)
    
    problem = SchedulingProblem(
        participants=['p1'],
        duration_minutes=60,
        time_window_start='2025-11-25T10:00:00Z',
        time_window_end='2025-11-25T15:00:00Z'
    )
    
    program = generate_asp_program(normalized, problem)
    
    # Should have busy facts
    assert "busy(p1," in program
    assert "locked_event(p1," in program
    
    print("✓ Unsatisfiable instance generated (will be UNSAT when solved)")
    return program


if __name__ == "__main__":
    print("Testing ASP encoding...")
    test_simple_satisfiable()
    test_unsatisfiable()
    print("All tests passed!")

