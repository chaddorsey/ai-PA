# Delete MCP Server From Config

DELETE https://api.letta.com/v1/tools/mcp/servers/{mcp_server_name}

Delete a MCP server configuration

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/tools/mcp/servers/mcp_server_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.delete_mcp_server(
    mcp_server_name="mcp_server_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.deleteMcpServer("mcp_server_name");

```

```shell
curl -X DELETE https://api.letta.com/v1/tools/mcp/servers/:mcp_server_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.delete_mcp_server(
    mcp_server_name="mcp_server_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.deleteMcpServer("mcp_server_name");

```