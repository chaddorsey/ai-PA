from letta_push_receiver.app_server_client import parse_responses_json

def test_parse_completed_extracts_text_and_context_tokens():
    # Shape confirmed by the Task-1 spike: single /v1/responses JSON object.
    obj = {
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "exec_command"},
            {"type": "message", "content": [{"type": "output_text", "text": "ENRICHED: ref_id=x"}]},
        ],
        # Spike-realistic shape: input_tokens is the last-turn delta,
        # total_tokens is the real per-task context size.
        "usage": {"input_tokens": 708, "total_tokens": 35167},
    }
    r = parse_responses_json(obj)
    assert r.status == "done"
    assert r.context_tokens == 35167
    assert "ENRICHED" in r.detail

def test_parse_non_completed_is_error():
    obj = {"status": "incomplete", "output": [], "error": {"message": "context_window exceeded"},
           "usage": {"input_tokens": 271000}}
    r = parse_responses_json(obj)
    assert r.status == "error"
    assert "context_window" in r.detail
