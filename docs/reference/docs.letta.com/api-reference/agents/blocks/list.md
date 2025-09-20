# List Blocks

GET https://api.letta.com/v1/agents/{agent_id}/core-memory/blocks

Retrieve the core memory blocks of a specific agent.

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/core-memory/blocks \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.list("agent_id");

```

```shell
curl https://api.letta.com/v1/agents/:agent_id/core-memory/blocks \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.blocks.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.blocks.list("agent_id");

```