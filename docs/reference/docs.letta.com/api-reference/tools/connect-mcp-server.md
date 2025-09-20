# Connect MCP Server

POST https://api.letta.com/v1/tools/mcp/servers/connect
Content-Type: application/json

Connect to an MCP server with support for OAuth via SSE.
Returns a stream of events handling authorization state and exchange if OAuth is required.

## Examples

```shell
curl -X POST https://api.letta.com/v1/tools/mcp/servers/connect \
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
response = client.tools.connect_mcp_server(
    request=StdioServerConfig(
        server_name="server_name",
        command="command",
        args=["args"],
    ),
)
for chunk in response.data:
    yield chunk

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
const response = await client.tools.connectMcpServer({
    serverName: "server_name",
    command: "command",
    args: ["args"]
});
for await (const item of response) {
    console.log(item);
}

```

```shell
curl -X POST https://api.letta.com/v1/tools/mcp/servers/connect \
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
response = client.tools.connect_mcp_server(
    request=StdioServerConfig(
        server_name="server_name",
        command="command",
        args=["args"],
    ),
)
for chunk in response.data:
    yield chunk

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
const response = await client.tools.connectMcpServer({
    serverName: "server_name",
    command: "command",
    args: ["args"]
});
for await (const item of response) {
    console.log(item);
}

```