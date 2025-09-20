# List MCP Servers

GET https://api.letta.com/v1/tools/mcp/servers

Get a list of all configured MCP servers

## Examples

```shell
curl https://api.letta.com/v1/tools/mcp/servers \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.list_mcp_servers()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.listMcpServers();

```

```shell
curl https://api.letta.com/v1/tools/mcp/servers \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.tools.list_mcp_servers()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.tools.listMcpServers();

```