# Update MCP Server

PATCH https://api.letta.com/v1/tools/mcp/servers/{mcp_server_name}
Content-Type: application/json

Update an existing MCP server configuration

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/tools/mcp/servers/mcp_server_name \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta, UpdateStdioMcpServer

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.update_mcp_server(
    mcp_server_name="mcp_server_name",
    request=UpdateStdioMcpServer(),
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.updateMcpServer("mcp_server_name", {});

```

```shell
curl -X PATCH https://api.letta.com/v1/tools/mcp/servers/:mcp_server_name \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta, UpdateStdioMcpServer

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.update_mcp_server(
    mcp_server_name="mcp_server_name",
    request=UpdateStdioMcpServer(),
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.updateMcpServer("mcp_server_name", {});

```