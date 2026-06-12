from bookmark_archiver import summarize

def test_parse_core_handles_reasoning_preamble():
    raw = ("Okay the user wants a title and summary. Let me think...\n"
           "TITLE: Intern Crashes Outlook\n"
           "SUMMARY: An intern emailed 50k people; reply-all storm crashed Outlook.\n"
           "REPLY_WORTH: no")
    out = summarize.parse_core(raw)
    assert out["title"] == "Intern Crashes Outlook"
    assert out["summary"].startswith("An intern emailed")
    assert out["reply_worth"] is False

def test_parse_core_reply_worth_yes():
    raw = "TITLE: Agent loop patterns\nSUMMARY: Thread on agent loops.\nREPLY_WORTH: yes"
    assert summarize.parse_core(raw)["reply_worth"] is True

def test_extract_json_from_noisy_output():
    raw = ('I will now produce JSON.\n{"has_durable_value": true, '
           '"group_sense": "Crowd shared repos.", '
           '"artifacts": [{"type":"repo","ref":"https://github.com/a/b","note":"agent lib"}], '
           '"topics": ["agents"]}  \nDone.')
    out = summarize.parse_reply_json(raw)
    assert out["has_durable_value"] is True
    assert out["artifacts"][0]["ref"] == "https://github.com/a/b"
    assert out["topics"] == ["agents"]

def test_extract_json_returns_none_on_garbage():
    assert summarize.parse_reply_json("no json here at all") is None

def test_call_llm_uses_monkeypatched_http(monkeypatch):
    monkeypatch.setattr(summarize, "_post", lambda body: {"choices": [{"message": {"content": "hello"}}]})
    assert summarize.call_llm("prompt", max_tokens=10) == "hello"
