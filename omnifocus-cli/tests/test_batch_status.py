from click.testing import CliRunner
from omnifocus_cli.cli import cli
from omnifocus_cli.schema import get_schema


def test_batch_status_schema_exists():
    schema = get_schema("task.batch-status")
    assert schema is not None
    assert schema["method"] == "checkTaskCompletionStatus"
    assert "taskIds" in schema["params"]


def test_batch_status_dry_run():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--dry-run", "--body", '{"taskIds": ["t-1", "t-2"]}',
        "task", "batch-status",
    ])
    assert result.exit_code == 0
    assert "checkTaskCompletionStatus" in result.output
    assert "t-1" in result.output
