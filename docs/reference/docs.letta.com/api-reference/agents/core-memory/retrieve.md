# Retrieve Agent Memory

GET https://api.letta.com/v1/agents/{agent_id}/core-memory

Retrieve the memory state of a specific agent.
This endpoint fetches the current memory state of the agent identified by the user ID and agent ID.

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/core-memory \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.core_memory.retrieve(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.coreMemory.retrieve("agent_id");

```

```shell
curl https://api.letta.com/v1/agents/:agent_id/core-memory \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.core_memory.retrieve(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.coreMemory.retrieve("agent_id");

```