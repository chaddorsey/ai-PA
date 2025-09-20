# Attach Block

PATCH https://api.letta.com/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}

Attach a core memory block to an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/core-memory/blocks/attach/block_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.attach(
    agent_id="agent_id",
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.attach("agent_id", "block_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/agents/:agent_id/core-memory/blocks/attach/:block_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.attach(
    agent_id="agent_id",
    block_id="block_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.attach("agent_id", "block_id");

```