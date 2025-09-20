# Add MCP Tool

POST https://api.letta.com/v1/tools/mcp/servers/{mcp_server_name}/{mcp_tool_name}

Register a new MCP tool as a Letta server by MCP server + tool name

## Examples

```shell
curl -X POST https://api.letta.com/v1/tools/mcp/servers/mcp_server_name/mcp_tool_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.add_mcp_tool(
    mcp_server_name="mcp_server_name",
    mcp_tool_name="mcp_tool_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.addMcpTool("mcp_server_name", "mcp_tool_name");

```

```shell
curl -X POST https://api.letta.com/v1/tools/mcp/servers/:mcp_server_name/:mcp_tool_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.add_mcp_tool(
    mcp_server_name="mcp_server_name",
    mcp_tool_name="mcp_tool_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.addMcpTool("mcp_server_name", "mcp_tool_name");

```