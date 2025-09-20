# Add MCP Server To Config

PUT https://api.letta.com/v1/tools/mcp/servers
Content-Type: application/json

Add a new MCP server to the Letta MCP server config

## Examples

```shell
curl -X PUT https://api.letta.com/v1/tools/mcp/servers \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "server_name": "string",
  "command": "string",
  "args": [
    "string"
  ]
}'
```

```python
from letta_client import Letta, StdioServerConfig

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.add_mcp_server(
    request=StdioServerConfig(
        server_name="server_name",
        command="command",
        args=["args"],
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.addMcpServer({
    serverName: "server_name",
    command: "command",
    args: ["args"]
});

```

```shell
curl -X PUT https://api.letta.com/v1/tools/mcp/servers \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "server_name": "string",
  "command": "string",
  "args": [
    "string"
  ]
}'
```

```python
from letta_client import Letta, StdioServerConfig

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.add_mcp_server(
    request=StdioServerConfig(
        server_name="server_name",
        command="command",
        args=["args"],
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.addMcpServer({
    serverName: "server_name",
    command: "command",
    args: ["args"]
});

```