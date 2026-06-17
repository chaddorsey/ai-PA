import os, importlib.util
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("ck", os.path.join(_REPO, "scripts", "check-packet-enrichment.py"))
ck = importlib.util.module_from_spec(spec); spec.loader.exec_module(ck)

def test_thin_when_single_channel():
    res = ["[primary] Meeting notes — https://notes.granola.ai/d/x (read)"]
    assert ck.is_thin(res) is True

def test_not_thin_with_multiple_channels():
    res = ["[primary] SOW — https://docs.google.com/document/d/x/edit (edit)",
           "[secondary] Status — https://acme.slack.com/archives/C/p (reference)"]
    assert ck.is_thin(res) is False
