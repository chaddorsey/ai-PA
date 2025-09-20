# Test MCP Server

POST https://api.letta.com/v1/tools/mcp/servers/test
Content-Type: application/json

Test connection to an MCP server without adding it.
Returns the list of available tools if successful.

## Examples

```shell
curl -X POST https://api.letta.com/v1/tools/mcp/servers/test \
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
client.tools.test_mcp_server(
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
await client.tools.testMcpServer({
    serverName: "server_name",
    command: "command",
    args: ["args"]
});

```

```shell
curl -X POST https://api.letta.com/v1/tools/mcp/servers/test \
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
client.tools.test_mcp_server(
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
await client.tools.testMcpServer({
    serverName: "server_name",
    command: "command",
    args: ["args"]
});

```