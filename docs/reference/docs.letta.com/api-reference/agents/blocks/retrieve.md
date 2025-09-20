# Retrieve Block

GET https://api.letta.com/v1/agents/{agent_id}/core-memory/blocks/{block_label}

Retrieve a core memory block from an agent.

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/core-memory/blocks/block_label \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.retrieve(
    agent_id="agent_id",
    block_label="block_label",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.retrieve("agent_id", "block_label");

```

```shell
curl https://api.letta.com/v1/agents/:agent_id/core-memory/blocks/:block_label \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.retrieve(
    agent_id="agent_id",
    block_label="block_label",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.retrieve("agent_id", "block_label");

```