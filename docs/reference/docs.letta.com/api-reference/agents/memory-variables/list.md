# Retrieve Memory Variables

GET https://api.letta.com/v1/agents/{agent_id}/core-memory/variables

<Note>This endpoint is only available on Letta Cloud.</Note>

Returns the memory variables associated with an agent.


## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id/core-memory/variables \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.memory_variables.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.memoryVariables.list("agent_id");

```

```shell
curl https://api.letta.com/v1/agents/:agent_id/core-memory/variables \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.memory_variables.list(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.memoryVariables.list("agent_id");

```