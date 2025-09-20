# Modify

PATCH https://api.letta.com/v1/agents/{agent_id}/archival-memory/{memory_id}

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/archival-memory/memory_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.modify(
    agent_id="agent_id",
    memory_id="memory_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.modify("agent_id", "memory_id");

```