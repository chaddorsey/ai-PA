import os, sys, importlib.util
from unittest import mock
from click.testing import CliRunner

_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
spec = importlib.util.spec_from_file_location(
    "task_cli.cli", os.path.join(_REPO, "task-cli", "src", "task_cli", "cli.py"))
cli_mod = importlib.util.module_from_spec(spec)
sys.modules["task_cli.cli"] = cli_mod
spec.loader.exec_module(cli_mod)


def _patches(render_spy):
    return (
        mock.patch("letta.write_packet_info_tool.write_packet_info",
                   return_value={"status": "ok", "ref_id": "abc123ef"}),
        mock.patch.object(cli_mod, "_render_work_packet_note", render_spy),
    )


def test_packet_write_triggers_render_by_default():
    spy = mock.Mock(return_value={"status": "ok"})
    p1, p2 = _patches(spy)
    with p1, p2:
        r = CliRunner().invoke(cli_mod.cli,
            ["packet-write", "--ref-id", "abc123ef", "--direct-action", "do it"])
    assert r.exit_code == 0, r.output
    spy.assert_called_once_with("abc123ef")


def test_no_render_flag_skips_render():
    spy = mock.Mock(return_value={"status": "ok"})
    p1, p2 = _patches(spy)
    with p1, p2:
        r = CliRunner().invoke(cli_mod.cli,
            ["packet-write", "--ref-id", "abc123ef", "--direct-action", "do it", "--no-render"])
    assert r.exit_code == 0, r.output
    spy.assert_not_called()
