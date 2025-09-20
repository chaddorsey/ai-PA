# Detach Block

PATCH https://api.letta.com/v1/agents/{agent_id}/core-memory/blocks/detach/{block_id}

Detach a core memory block from an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/core-memory/blocks/detach/block_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.detach(
    agent_id="agent_id",
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.detach("agent_id", "block_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/core-memory/blocks/detach/:block_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.detach(
    agent_id="agent_id",
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.detach("agent_id", "block_id");

```