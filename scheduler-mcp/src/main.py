"""Run scheduler MCP server."""

import uvicorn

from scheduler_mcp.server import create_app


def main() -> None:
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8088)


if __name__ == "__main__":
    main()


