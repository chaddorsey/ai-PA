"""Work-packet rich-note rendering fidelity (_build_work_packet_segments).

Phase 2 (2026-06-15): the renderer dropped direct_action + the three-node model,
doubled list markers when content already had "• "/"-", emitted literal "\\n",
and carried no time estimate. These tests lock the fidelity contract.

Run: cd pa-web-ui && python -m pytest tests/test_work_packet_segments.py -v
"""
import app


def _text(segments):
    return "".join(s if isinstance(s, str) else s.get("text", "") for s in segments)


ENRICH = {
    "packet_info": {
        "direct_action": "Review the OpenSciEd audit and share it with Chad",
        "artifact_provenance": "Audit lives in a Google Doc linked from Kiley's email",
        "intent_genesis": "Board asked for a materials-quality check in the May meeting",
        "context_brief": ["• Email from Kiley Brown", "Second point with a literal\\nnewline inside"],
        "knowns": ["• Sender: Kiley Brown"],
        "unknowns": ["The actual audit URL"],
        "resources": ["Audit doc — https://docs.google.com/document/d/abc"],
        "related_tasks": [],
        "mismatch_warnings": [],
        "additional_notes": "source fetch degraded",
    }
}
# passage carries the agent estimate the timer widget greps for
PASSAGE = "Task: Review Kiley's audit\n- Agent Estimate: 45\n- Estimate: 45\n"


def segs():
    return app._build_work_packet_segments("19e93fe4", PASSAGE, ENRICH)


def test_direct_action_is_rendered():
    assert "Review the OpenSciEd audit and share it with Chad" in _text(segs())


def test_three_node_model_rendered():
    t = _text(segs())
    assert "Google Doc" in t            # artifact_provenance
    assert "May meeting" in t           # intent_genesis


def test_no_double_bullets():
    t = _text(segs())
    assert "• •" not in t and "•  •" not in t


def test_no_double_marker_on_knowns():
    # content "• Sender" under the ✓ marker must not become "✓ • Sender"
    assert "✓ •" not in _text(segs())


def test_literal_backslash_n_becomes_real_newline():
    t = _text(segs())
    assert "\\n" not in t               # no literal backslash-n in output
    # a "...\n..." item splits into separate real lines, both parts present
    assert "Second point with a literal" in t
    assert "newline inside" in t


def test_estimate_section_preserves_timer_widget_hook():
    # the OmniFocus timer widget greps the note for "Agent Estimate: N"
    assert "Agent Estimate: 45" in _text(segs())
