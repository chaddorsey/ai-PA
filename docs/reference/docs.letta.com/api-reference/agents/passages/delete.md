# Delete Passage

DELETE https://api.letta.com/v1/agents/{agent_id}/archival-memory/{memory_id}

Delete a memory from an agent's archival memory store.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/agents/agent_id/archival-memory/memory_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.delete(
    agent_id="agent_id",
    memory_id="memory_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.delete("agent_id", "memory_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/agents/:agent_id/archival-memory/:memory_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.delete(
    agent_id="agent_id",
    memory_id="memory_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.delete("agent_id", "memory_id");

```