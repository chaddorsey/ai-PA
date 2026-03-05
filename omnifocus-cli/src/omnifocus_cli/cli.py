import click


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx, json_output):
    """OmniFocus CLI - manage tasks, projects, and tags."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
