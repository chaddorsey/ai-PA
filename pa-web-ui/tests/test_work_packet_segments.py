"""Work-packet rich-note rendering fidelity (_build_work_packet_segments).

Phase 2 (2026-06-15): the renderer dropped direct_action + the three-node model,
doubled list markers when content already had "• "/"-", emitted literal "\\n",
and carried no time estimate. These tests lock the fidelity contract.

Run: cd pa-web-ui && python -m pytest tests/test_work_packet_segments.py -v
"""
import app

_build_work_packet_segments = app._build_work_packet_segments


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


def test_agent_estimate_is_duration_string_not_bare_int():
    # The OF timer's parseDurationToMs matches Nh/Nm, NOT bare ints — so the
    # "Agent Estimate" line MUST be a duration string or the timer logs 0/None.
    t = _text(segs())                       # PASSAGE has "- Agent Estimate: 45"
    assert "Agent Estimate: 45m" in t
    assert "Agent Estimate: 45\n" not in t  # never a bare int


def test_agent_estimate_uses_original_not_revised():
    # Eval-critical: the Agent Estimate line is the IMMUTABLE original, never the
    # revised value (revised would corrupt agentEstimateMin in the timer log).
    t = _text(app._build_work_packet_segments("r", PASSAGE, ENRICH, original_est=30, revised_est=90))
    assert "Agent Estimate: 30m" in t
    assert "90" not in t.split("Estimate (current)")[0]  # 90 not in the agent line
    assert "Estimate (current): 1h 30m" in t             # revised shown, timer-safe label


def test_estimate_original_only_no_current_line():
    t = _text(app._build_work_packet_segments("r", PASSAGE, ENRICH, original_est=30, revised_est=None))
    assert "Agent Estimate: 30m" in t
    assert "Estimate (current)" not in t


def test_meeting_case_revised_only_no_agent_line():
    # original None (agent never estimated), user revised to 90: NO Agent Estimate
    # line (nothing for the timer baseline), revised shown under the safe label.
    t = _text(app._build_work_packet_segments("r", "no estimate here", {}, original_est=None, revised_est=90))
    assert "Agent Estimate:" not in t
    assert "Estimate (current): 1h 30m" in t


def test_resource_line_with_live_and_offline_links_renders_both():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[primary] SOW draft — https://docs.google.com/document/d/X/edit | offline: openfile:///Users/u/Dropbox/letta-shared-files/staged/notes/r/SOW.md (read)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    urls = [s["url"] for s in segs if isinstance(s, dict) and s.get("url")]
    assert "https://docs.google.com/document/d/X/edit" in urls
    assert "openfile:///Users/u/Dropbox/letta-shared-files/staged/notes/r/SOW.md" in urls


def test_offline_link_gets_offline_display_text():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[primary] Notes — openfile:///Users/u/x.md (read)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    offline = [s for s in segs if isinstance(s, dict) and s.get("url", "").startswith("openfile://")]
    assert offline and offline[0]["text"].strip() == "Offline copy"


def test_single_https_resource_still_renders_once():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[secondary] Doc — https://example.com/a (reference)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    urls = [s["url"] for s in segs if isinstance(s, dict) and s.get("url")]
    assert urls == ["https://example.com/a"]


def test_resource_label_strips_priority_marker():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[primary] SOW draft — https://docs.google.com/document/d/X/edit | offline: openfile:///u/SOW.md (read)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    label_segs = [s["text"] for s in segs if isinstance(s, dict)
                  and s.get("text", "").strip().startswith("SOW draft")]
    assert label_segs, "label 'SOW draft' should render (priority marker stripped)"
    assert "[primary]" not in "".join(s.get("text", "") for s in segs if isinstance(s, dict))


def test_url_with_trailing_paren_not_overstripped():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[secondary] Doc — https://example.com/path(v2)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    urls = [s["url"] for s in segs if isinstance(s, dict) and s.get("url")]
    assert urls == ["https://example.com/path(v2)"]
