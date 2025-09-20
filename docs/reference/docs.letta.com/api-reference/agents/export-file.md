# Export Agent

GET https://api.letta.com/v1/agents/{agent_id}/export
Content-Type: application/json

Export the serialized JSON representation of an agent, formatted with indentation.

Supports two export formats:
- Legacy format (use_legacy_format=true): Single agent with inline tools/blocks
- New format (default): Multi-entity format with separate agents, tools, blocks, files, etc.

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/export \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.export_file(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.exportFile("agent_id");

```

```shell
curl -G https://api.letta.com/v1/agents/:agent_id/export \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d max_steps=0 \
     -d use_legacy_format=true
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.export_file(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.exportFile("agent_id");

```