"""
Example payloads for testing the orchestrate_scheduling tool.

These examples can be used for integration tests and manual verification.
"""

from typing import Dict, Any, List

# Example 1: Simple common slot finding
EXAMPLE_1_INPUT: Dict[str, Any] = {
    "utterance": "Find 45 minutes with Alex & Priya Tue–Thu mornings. Minimize disruption.",
    "events_by_participant": {
        "exec": [
            {
                "id": "evt1",
                "title": "Standup",
                "start": "2025-11-25T14:00:00Z",
                "end": "2025-11-25T14:15:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "owner": "exec"
            },
            {
                "id": "evt2",
                "title": "Client Meeting",
                "start": "2025-11-26T16:00:00Z",
                "end": "2025-11-26T17:00:00Z",
                "locked": True,
                "protected": True,
                "flexible": False,
                "owner": "exec"
            }
        ],
        "alex": [
            {
                "id": "evt3",
                "title": "Team Sync",
                "start": "2025-11-25T15:00:00Z",
                "end": "2025-11-25T16:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "owner": "alex"
            }
        ],
        "priya": [
            {
                "id": "evt4",
                "title": "Design Review",
                "start": "2025-11-26T10:00:00Z",
                "end": "2025-11-26T11:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "owner": "priya"
            }
        ]
    },
    "context_json": {
        "timeframe": {
            "from": "2025-11-24",
            "to": "2025-11-28",
            "tz": "America/New_York"
        },
        "participants": [
            {
                "id": "exec",
                "email": "me@acme.com",
                "work_hours": "M-F 09:00-17:30"
            },
            {
                "id": "alex",
                "email": "alex@corp.com",
                "work_hours": "M-F 09:00-17:30"
            },
            {
                "id": "priya",
                "email": "priya@corp.com",
                "work_hours": "M-F 09:00-17:30"
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 10
            },
            "soft": {
                "maximize_focus_blocks": {
                    "block_min": 90,
                    "weight": 10
                },
                "minimize_moves_of_existing": {
                    "weight_per_min_shift": 2,
                    "tier": "protected"
                },
                "respect_others_prefs_weight": 3
            },
            "lexicographic_levels": [
                "feasibility",
                "protected_events",
                "move_costs",
                "focus_blocks"
            ]
        },
        "slot_size_minutes": 15
    }
}

# Example 2: Focus block optimization
EXAMPLE_2_INPUT: Dict[str, Any] = {
    "utterance": "Schedule a 1-hour meeting next week, prefer morning. Maximize my focus blocks.",
    "events_by_participant": {
        "exec": [
            {
                "id": "evt5",
                "title": "Quick Sync",
                "start": "2025-11-25T09:00:00Z",
                "end": "2025-11-25T09:30:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "owner": "exec"
            },
            {
                "id": "evt6",
                "title": "Standup",
                "start": "2025-11-25T10:00:00Z",
                "end": "2025-11-25T10:30:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "owner": "exec"
            },
            {
                "id": "evt7",
                "title": "Review",
                "start": "2025-11-25T14:00:00Z",
                "end": "2025-11-25T14:30:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "owner": "exec"
            }
        ]
    },
    "context_json": {
        "timeframe": {
            "from": "2025-11-24",
            "to": "2025-12-01",
            "tz": "America/New_York"
        },
        "participants": [
            {
                "id": "exec",
                "email": "me@acme.com",
                "work_hours": "M-F 09:00-17:30"
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 15
            },
            "soft": {
                "maximize_focus_blocks": {
                    "block_min": 90,
                    "weight": 10
                }
            }
        }
    }
}

# Example 3: UNSAT case (over-constrained)
EXAMPLE_3_INPUT: Dict[str, Any] = {
    "utterance": "Find 2 hours with the entire team tomorrow 9-10am only",
    "events_by_participant": {
        "exec": [
            {
                "id": "evt8",
                "title": "All Day Meeting",
                "start": "2025-11-25T09:00:00Z",
                "end": "2025-11-25T17:00:00Z",
                "locked": True,
                "protected": True,
                "flexible": False,
                "owner": "exec"
            }
        ],
        "team_member_1": [
            {
                "id": "evt9",
                "title": "Busy",
                "start": "2025-11-25T09:00:00Z",
                "end": "2025-11-25T10:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "owner": "team_member_1"
            }
        ]
    },
    "context_json": {
        "timeframe": {
            "from": "2025-11-25",
            "to": "2025-11-25",
            "tz": "America/New_York"
        },
        "participants": [
            {"id": "exec", "email": "me@acme.com", "work_hours": "M-F 09:00-17:30"},
            {"id": "team_member_1", "email": "tm1@acme.com", "work_hours": "M-F 09:00-17:30"}
        ],
        "policy": {
            "hard": {
                "min_gap_min": 15
            }
        }
    }
}

# Example expected output structure (for reference)
EXAMPLE_OUTPUT_OK: Dict[str, Any] = {
    "status": "ok",
    "proposals": [
        {
            "title": "Alex & Priya sync",
            "participants": ["me@acme.com", "alex@corp.com", "priya@corp.com"],
            "start_utc": "2025-11-26T15:15:00Z",
            "end_utc": "2025-11-26T16:00:00Z",
            "location": "VC",
            "notes_for_invite": "Morning preference respected (EST). Minimal move: shifted internal sync by 15m.",
            "moved_events": [
                {
                    "owner": "exec",
                    "event_id": "evt1",
                    "old_start": "2025-11-25T14:00:00Z",
                    "new_start": "2025-11-25T14:15:00Z",
                    "old_end": "2025-11-25T14:15:00Z",
                    "new_end": "2025-11-25T14:30:00Z",
                    "shift_minutes": 15
                }
            ],
            "objective_scores": {
                "moved_minutes": 15,
                "focus_block_bonus": 60,
                "preference_penalty": 0,
                "protected_events_moved": 0
            }
        }
    ],
    "explanation": "Selected Wed 10:15–11:00 Eastern. Everyone is free; preserving a protected client meeting. Moving a flexible standup by 15 minutes creates a 2‑hour block later.",
    "debug": {
        "asp_stats": {
            "models": 1,
            "optimum": True
        },
        "extraction_time_ms": 250,
        "normalization_time_ms": 50,
        "solve_time_ms": 1200,
        "total_time_ms": 1500,
        "facts_generated": 450,
        "slots_considered": 480
    }
}

EXAMPLE_OUTPUT_UNSAT: Dict[str, Any] = {
    "status": "unsat",
    "proposals": [],
    "explanation": "Unable to find a meeting time that satisfies all constraints. All participants are busy during the requested time window.",
    "relaxations": [
        {
            "description": "Widen time window to include afternoon hours (14:00-17:00)",
            "expected_impact": "high",
            "policy_change": {
                "time_window_end": "2025-11-25T17:00:00Z"
            },
            "rank": 1
        },
        {
            "description": "Relax minimum gap from 15 to 10 minutes",
            "expected_impact": "medium",
            "policy_change": {
                "min_gap_minutes": 10
            },
            "rank": 2
        },
        {
            "description": "Allow scheduling outside work hours (before 9am or after 5:30pm)",
            "expected_impact": "low",
            "policy_change": {
                "allow_off_hours": True
            },
            "rank": 3
        }
    ],
    "debug": {
        "asp_stats": {
            "models": 0,
            "unsat": True
        }
    }
}

