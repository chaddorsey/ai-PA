# Modify Block

PATCH https://api.letta.com/v1/agents/{agent_id}/core-memory/blocks/{block_label}
Content-Type: application/json

Updates a core memory block of an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/core-memory/blocks/block_label \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.modify(
    agent_id="agent_id",
    block_label="block_label",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.modify("agent_id", "block_label", {});

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/core-memory/blocks/:block_label \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.modify(
    agent_id="agent_id",
    block_label="block_label",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.modify("agent_id", "block_label", {});

```