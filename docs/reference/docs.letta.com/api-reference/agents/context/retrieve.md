# Retrieve Agent Context Window

GET https://api.letta.com/v1/agents/{agent_id}/context

Retrieve the context window of a specific agent.

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/context \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.context.retrieve(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.context.retrieve("agent_id");

```

```shell
curl https://api.letta.com/v1/agents/:agent_id/context \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.context.retrieve(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.context.retrieve("agent_id");

```