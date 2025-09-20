# List MCP Tools By Server

GET https://api.letta.com/v1/tools/mcp/servers/{mcp_server_name}/tools

Get a list of all tools for a specific MCP server

## Examples

```shell
curl https://api.letta.com/v1/tools/mcp/servers/mcp_server_name/tools \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.list_mcp_tools_by_server(
    mcp_server_name="mcp_server_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.listMcpToolsByServer("mcp_server_name");

```

```shell
curl https://api.letta.com/v1/tools/mcp/servers/:mcp_server_name/tools \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.list_mcp_tools_by_server(
    mcp_server_name="mcp_server_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.listMcpToolsByServer("mcp_server_name");

```